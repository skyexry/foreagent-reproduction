"""Persistent wrapper for one explicitly selected smoke or formal run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def node_manifest(run_dir):
    """Index every preserved candidate and join execution records by exact code hash."""
    jobs = {}
    node_jobs = {}
    for file in (run_dir / 'tasks').glob('*/execution.json'):
        record = read_json(file)
        if record.get('code_sha256'):
            jobs.setdefault(record['code_sha256'], []).append(record)
        if record.get('node_id'):
            node_jobs.setdefault(record['node_id'], []).append(record)
    nodes = []
    for directory in sorted((run_dir / 'workspaces/exp/all_nodes').glob('node_*')):
        metadata = read_json(directory / 'metadata.json')
        code = directory / 'code.py'
        submission = directory / 'submission.csv'
        code_hash = hashlib.sha256(code.read_bytes()).hexdigest() if code.is_file() else None
        metric = metadata.get('metric')
        valid = (metadata.get('is_buggy') is False and not metadata.get('is_skipped') and
                 metric is not None and not any(token in str(metric).lower()
                                                for token in ('nan', 'inf', 'none')))
        exact_jobs = node_jobs.get(metadata.get('node_id'), [])
        hash_jobs = jobs.get(code_hash, [])
        nodes.append({'node_id': metadata.get('node_id'), 'directory': str(directory),
                      'stage': metadata.get('stage'), 'metric_display': metric,
                      'valid_executed_node': valid, 'code_sha256': code_hash,
                      'submission_exists': submission.is_file(),
                      'submission_sha256': hashlib.sha256(submission.read_bytes()).hexdigest()
                                           if submission.is_file() else None,
                      'execution_records': exact_jobs or hash_jobs,
                      'execution_association': 'node_id' if exact_jobs else
                                               'code_hash_fallback' if hash_jobs else 'missing',
                      'code_hash_execution_candidates': hash_jobs})
    manifest = {'time': time.time(), 'nodes': nodes, 'candidate_count': len(nodes),
                'valid_executed_count': sum(item['valid_executed_node'] for item in nodes),
                'valid_nodes_missing_submission': [item['node_id'] for item in nodes
                    if item['valid_executed_node'] and not item['submission_exists']],
                'policy': 'archive all candidates; preserve original agent selection'}
    write_json(run_dir / 'node-artifacts.json', manifest)
    return manifest


def snapshot(directory):
    directory.mkdir()
    names = ['controller.py', 'bridge.py', 'worker.py', 'guest.sh', 'monitor.py',
             'supervisor.py', 'grade_run.py', 'baked-instructions.txt',
             'requirements-controller.in', 'model-config.example.json',
             'prepare_data.py', 'probe_models.py', 'protocol.json', 'protocol-v1.json', 'README.md']
    hashes = {}
    for name in names:
        source = HERE / name
        if source.is_file():
            shutil.copyfile(source, directory / name)
            hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(directory / 'SHA256.json', hashes)
    return hashes


def pip_record(python, directory, suffix):
    statuses = {}
    for name, arguments in [('freeze', ['freeze', '--all']), ('check', ['check'])]:
        with (directory / ('pip-' + name + '-' + suffix + '.txt')).open('w') as output:
            try:
                result = subprocess.run([str(python), '-m', 'pip'] + arguments,
                                        stdout=output, stderr=subprocess.STDOUT,
                                        timeout=60)
                statuses[name] = result.returncode
            except subprocess.TimeoutExpired:
                statuses[name] = 'timeout'
    return statuses


def alive(pid):
    try:
        os.kill(pid, 0)
        stat = Path('/proc') / str(pid) / 'stat'
        if stat.exists() and stat.read_text().split()[2] == 'Z':
            return False
        return True
    except (ProcessLookupError, FileNotFoundError, ValueError):
        return False
    except PermissionError:
        return True


def worker_states(scope):
    states = []
    for file in (HERE / 'workers' / scope / 'jobs').glob('*/pid'):
        try:
            pid = int(file.read_text().strip())
        except (OSError, ValueError):
            continue
        command = Path('/proc') / str(pid) / 'cmdline'
        try:
            command_text = command.read_text().replace('\x00', ' ')
        except OSError:
            command_text = ''
        states.append({'job': file.parent.name, 'pid': pid, 'alive': alive(pid),
                       'command': command_text,
                       'exit_record': (file.parent / 'exit').read_text().strip()
                       if (file.parent / 'exit').exists() else None})
    return states


def stop_group(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--phase', choices=['smoke', 'formal'], required=True)
    parser.add_argument('--model-config', type=Path)
    args = parser.parse_args()
    if not args.scope or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.scope):
        raise ValueError('invalid scope')
    run_dir = HERE / 'runs' / args.scope
    if run_dir.exists():
        raise FileExistsError(run_dir)
    directory = HERE / 'supervision' / args.scope
    directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(0o700)
    python = HERE / 'controller-venv/bin/python'
    start_hashes = snapshot(directory / 'runtime-start')
    pip_start = pip_record(python, directory, 'start')
    if pip_start.get('check') != 0:
        write_json(directory / 'completion-supervisor.json',
                   {'status': 'controller environment dependency check failed', 'pip_start': pip_start})
        raise RuntimeError('controller pip check failed; see supervision log')
    command = [str(python), '-u', str(HERE / 'controller.py'), '--scope', args.scope,
               '--phase', args.phase]
    if args.model_config:
        command += ['--model-config', str(args.model_config)]
    spawned = time.time()
    wall_cap = 7200 if args.phase == 'smoke' else 43200
    supervisor_deadline = spawned + wall_cap + 20
    monitor = None
    monitor_output = None
    forced_stop = False
    with (directory / 'controller.stdout.log').open('ab', buffering=0) as output:
        process = subprocess.Popen(command, cwd=HERE, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        write_json(directory / 'started-supervisor.json',
                   {'scope': args.scope, 'phase': args.phase, 'supervisor_pid': os.getpid(),
                    'controller_pid': process.pid, 'spawned': spawned,
                    'supervisor_deadline': supervisor_deadline, 'command': command})
        (directory / 'controller.pid').write_text(str(process.pid))
        while process.poll() is None:
            started = read_json(run_dir / 'started.json')
            if monitor is None and started.get('pid') == process.pid:
                monitor_output = (directory / 'monitor.stdout.log').open('ab', buffering=0)
                monitor = subprocess.Popen([str(python), '-u', str(HERE / 'monitor.py'),
                                            '--run-dir', str(run_dir), '--interval', '30'],
                                           cwd=HERE, stdout=monitor_output,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                (directory / 'monitor.pid').write_text(str(monitor.pid))
            if time.time() >= supervisor_deadline:
                forced_stop = True
                stop_group(process)
                break
            time.sleep(1)
        returncode = process.wait()
    exited = time.time()
    started = read_json(run_dir / 'started.json')
    workers_at_exit = worker_states(args.scope)
    # A worker's own timeout uses the controller deadline with an eight-second grace.
    # For early normal exit, allow at most eight seconds to observe normal cleanup.
    grace_end = min(float(started.get('deadline', exited)) + 9, exited + 9)
    while any(item['alive'] for item in worker_states(args.scope)) and time.time() < grace_end:
        time.sleep(1)
    workers_after_grace = worker_states(args.scope)
    if monitor is not None:
        try:
            monitor.wait(timeout=35)
        except subprocess.TimeoutExpired:
            monitor.terminate()
            try:
                monitor.wait(timeout=5)
            except subprocess.TimeoutExpired:
                stop_group(monitor)
                monitor.wait()
        monitor_output.close()
    artifact_manifest = node_manifest(run_dir) if run_dir.is_dir() else {}
    end_hashes = snapshot(directory / 'runtime-end')
    pip_end = pip_record(python, directory, 'end')
    if forced_stop:
        status = 'supervisor hard timeout'
    elif returncode == -signal.SIGALRM:
        status = 'formal wall-clock budget ended' if args.phase == 'formal' else 'smoke diagnostic cap ended; acceptance pending'
    elif returncode == 0:
        status = 'controller exited normally; inspect phase completion and grading'
    else:
        status = 'controller interrupted or failed'
    completion = {'scope': args.scope, 'phase': args.phase, 'status': status,
                  'controller_returncode': returncode, 'forced_stop': forced_stop,
                  'spawned': spawned, 'controller_exited': exited, 'recorded': time.time(),
                  'controller_elapsed_seconds': exited - spawned,
                  'controller_started_record': started,
                  'workers_at_controller_exit': workers_at_exit,
                  'workers_after_termination_grace': workers_after_grace,
                  'runtime_hashes_match': start_hashes == end_hashes,
                  'artifact_candidate_count': artifact_manifest.get('candidate_count'),
                  'valid_nodes_missing_submission': artifact_manifest.get('valid_nodes_missing_submission'),
                  'pip_start': pip_start, 'pip_end': pip_end,
                  'monitor_returncode': monitor.returncode if monitor else None}
    write_json(directory / 'completion-supervisor.json', completion)
    if run_dir.is_dir():
        write_json(run_dir / 'completion-supervisor.json', completion)
    print(json.dumps({'scope': args.scope, 'status': status, 'returncode': returncode,
                      'workers_alive': sum(item['alive'] for item in workers_after_grace)}), flush=True)


if __name__ == '__main__':
    main()
