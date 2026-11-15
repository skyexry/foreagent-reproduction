"""Observe a server-local ForeAgent run; append metadata without API bodies."""
import argparse
from collections import Counter
import csv
import datetime
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


def safe_text(value):
    value = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|authorization|token)\s*[:=]\s*)\S+', r'\1<redacted>', value)
    return re.sub(r'\bsk-[A-Za-z0-9_-]+', '<redacted>', value)[:400]


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def file_info(path):
    try:
        stat = path.stat()
        return {'bytes': stat.st_size, 'mtime': stat.st_mtime,
                'age_seconds': max(0, time.time() - stat.st_mtime)}
    except OSError:
        return None


def exception_tail(path):
    try:
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 8192))
            lines = stream.read().decode(errors='replace').splitlines()
        return [safe_text(line) for line in lines if re.search(
            r'Traceback|\b\w*(?:Error|Exception)\b|CUDA out of memory|Segmentation fault|Killed|Permission denied', line)][-8:]
    except OSError:
        return []


def gpu_state():
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw',
                                 '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8)
        fields = ['index', 'name', 'utilization_percent', 'memory_used_mib', 'memory_total_mib', 'temperature_c', 'power_w']
        return {'exit': result.returncode, 'devices': [dict(zip(fields, map(str.strip, row)))
                for row in csv.reader(io.StringIO(result.stdout))]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error_type': type(error).__name__}


def process_state(pid):
    if not isinstance(pid, int):
        return {'pid': pid, 'alive': False}
    try:
        status = Path(f'/proc/{pid}/status').read_text()
        fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'alive': fields.get('State', '').strip()[:1] != 'Z',
                'state': fields.get('State', '').strip(), 'rss': fields.get('VmRSS', '').strip(),
                'threads': fields.get('Threads', '').strip(),
                'cpu_seconds': (int(stat[11]) + int(stat[12])) / os.sysconf('SC_CLK_TCK')}
    except (OSError, ValueError, IndexError):
        return {'pid': pid, 'alive': False}


def host_state(run_dir):
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            memory[key] = value.strip()
    disk = shutil.disk_usage(run_dir)
    cpu = Path('/proc/stat').read_text().splitlines()[0].split()[1:]
    return {'load_average': os.getloadavg(), 'cpu_ticks': list(map(int, cpu)),
            'memory': memory, 'disk_total_bytes': disk.total, 'disk_free_bytes': disk.free}


class ApiState:
    def __init__(self):
        self.offset = 0
        self.partial = ''
        self.pending = {}
        self.counts = Counter()
        self.http = Counter()
        self.latest = None

    def update(self, path):
        try:
            if path.stat().st_size < self.offset:
                self.__init__()
            with path.open() as stream:
                stream.seek(self.offset)
                chunk = stream.read()
                self.offset = stream.tell()
        except OSError:
            chunk = ''
        lines = (self.partial + chunk).split('\n')
        self.partial = lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                self.counts['unparsed_lines'] += 1
                continue
            kind, request_id = event.get('event'), event.get('request_id')
            self.counts[str(kind)] += 1
            # Only explicit metadata fields enter monitor records.
            metadata = {key: event[key] for key in ('event', 'request_id', 'time', 'role', 'provider',
                         'elapsed_seconds', 'http', 'error_type', 'model') if key in event}
            self.latest = metadata
            if kind == 'request_start':
                self.pending[request_id] = metadata
            elif kind in {'response', 'request_error'}:
                self.pending.pop(request_id, None)
                if kind == 'response':
                    self.http[str(event.get('http'))] += 1
        now = time.time()
        return {'counts': dict(self.counts), 'http_counts': dict(self.http), 'latest': self.latest,
                'pending': [dict(value, wait_seconds=max(0, now - value.get('time', now)))
                            for value in self.pending.values()]}


def latest_job(run_dir):
    jobs = run_dir.parent.parent / 'workers' / run_dir.name / 'jobs'
    try:
        paths = [path for path in jobs.iterdir() if path.is_dir()]
        path = max(paths, key=lambda item: item.stat().st_mtime)
    except (OSError, ValueError):
        return None
    result = {'name': path.name, 'started': file_info(path / 'started.json'),
              'console': file_info(path / 'console.log'),
              'console_exceptions': exception_tail(path / 'console.log'),
              'result': file_info(path / 'output/result.json')}
    try:
        result['exit'] = int((path / 'exit').read_text().strip())
    except (OSError, ValueError):
        result['exit'] = None
    try:
        result['process'] = process_state(int((path / 'pid').read_text().strip()))
    except (OSError, ValueError):
        pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=30)
    args = parser.parse_args()
    if args.interval < 1 or not args.run_dir.is_dir():
        parser.error('run directory must exist and interval must be at least one second')
    run_dir = args.run_dir.resolve()
    output = run_dir / 'monitor.jsonl'
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    api = ApiState()
    started_at = time.time()
    reason = 'monitor_signal'
    with output.open('a', buffering=1) as stream:
        os.chmod(output, 0o600)

        def record(value):
            value.update(time=time.time(), utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')

        record({'event': 'monitor_started', 'monitor_pid': os.getpid(), 'interval_seconds': args.interval})
        try:
            while not stopping:
                started = read_json(run_dir / 'started.json')
                controller = process_state(started.get('pid'))
                aide = run_dir / 'logs/exp/aide.log'
                progress = read_json(run_dir / 'progress.json')
                progress = {key: progress[key] for key in ('completed_tournaments',
                            'completed_ten_candidate_tournaments', 'smoke_ready', 'draft_nodes',
                            'journal_nodes', 'time') if key in progress}
                record({'event': 'sample', 'host': host_state(run_dir), 'gpu': gpu_state(),
                        'controller': controller, 'aide_log': file_info(aide),
                        'aide_exceptions': exception_tail(aide), 'progress': progress,
                        'api': api.update(run_dir / 'api.jsonl'), 'latest_job': latest_job(run_dir),
                        'completion': file_info(run_dir / 'completion.json')})
                if started.get('pid') and not controller['alive']:
                    reason = 'controller_exited'
                    break
                end_wait = time.monotonic() + args.interval
                while not stopping and time.monotonic() < end_wait:
                    time.sleep(min(1, max(0, end_wait - time.monotonic())))
        except Exception as error:
            reason = 'monitor_error'
            record({'event': 'monitor_error', 'error_type': type(error).__name__})
            raise
        finally:
            record({'event': 'monitor_ended', 'reason': reason, 'elapsed_seconds': time.time() - started_at})


if __name__ == '__main__':
    main()
