"""Fail-closed macOS policy worker. The host retains data, scoring and quotas."""
import json
import os
from pathlib import Path
import resource
import select
import selectors
import subprocess
import sys
import tempfile
import time


class PolicyError(RuntimeError):
    pass


def profile(stage):
    # -I -S -B below avoids user imports, site initialization and bytecode writes.
    paths = [str(Path(stage).resolve()), str(Path(sys.base_prefix).resolve()),
             '/System/Library', '/System/Volumes/Preboot/Cryptexes/OS',
             '/usr/lib', '/usr/share', '/Library/Apple']
    read = ' '.join('(subpath '+json.dumps(p)+')' for p in paths)
    return '\n'.join([
        '(version 1)', '(deny default)',
        '(allow process-exec (subpath '+json.dumps(str(Path(sys.base_prefix).resolve()))+'))',
        '(allow file-read* '+read+')',
        '(allow file-read-metadata)',
        '(allow file-read* (literal "/"))',
        '(allow file-read* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))',
        '(allow file-write* (subpath '+json.dumps(str(Path(stage).resolve()))+'))',
        '(allow sysctl-read)', '(allow signal (target self))',
    ])


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024*1024, 1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (48, 48))


class Worker:
    def __init__(self, source, timeout=2.0, episode_timeout=6.0):
        if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
            raise PolicyError('This version requires macOS sandbox-exec; isolation has no insecure fallback')
        self.temp = tempfile.TemporaryDirectory(prefix='foreagent-policy-')
        self.stage = Path(self.temp.name).resolve()
        (self.stage/'policy.py').write_bytes(source)
        (self.stage/'worker.py').write_bytes(Path(__file__).with_name('worker.py').read_bytes())
        self.error_file = (self.stage/'stderr.txt').open('w+b')
        command = ['/usr/bin/sandbox-exec', '-p', profile(self.stage), sys.executable,
                   '-I', '-S', '-B', '-u', str(self.stage/'worker.py'), str(self.stage/'policy.py')]
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.error_file, cwd=self.stage, env={'TMPDIR':str(self.stage), 'LC_ALL':'C'},
            preexec_fn=limits)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        os.set_blocking(self.proc.stdin.fileno(), False)
        self.buffer = b''
        self.timeout = timeout
        self.deadline = time.monotonic()+episode_timeout

    def request(self, observation):
        deadline = min(self.deadline, time.monotonic()+self.timeout)
        payload = (json.dumps(observation, allow_nan=False)+'\n').encode()
        try:
            while payload:
                remaining = deadline-time.monotonic()
                if remaining <= 0 or not select.select([], [self.proc.stdin], [], max(0, remaining))[1]:
                    raise PolicyError('Policy observation/episode timeout')
                payload = payload[os.write(self.proc.stdin.fileno(), payload):]
        except (BrokenPipeError, OSError) as exc:
            raise PolicyError('Worker exited before receiving observation: '+self.error()) from exc
        while b'\n' not in self.buffer:
            remaining = deadline-time.monotonic()
            if remaining <= 0 or not self.selector.select(max(0, remaining)):
                raise PolicyError('Policy response/episode timeout')
            chunk = os.read(self.proc.stdout.fileno(), 8192)
            if not chunk:
                raise PolicyError('Worker exited: '+self.error())
            self.buffer += chunk
            if len(self.buffer) > 65536:
                raise PolicyError('Policy output exceeds protocol limit')
        line, self.buffer = self.buffer.split(b'\n', 1)
        try:
            action = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise PolicyError('Policy output must be a single JSON action') from exc
        if not isinstance(action, dict):
            raise PolicyError('Action must be a JSON object')
        return action

    def error(self):
        self.error_file.flush()
        self.error_file.seek(0)
        return self.error_file.read(4096).decode(errors='replace')

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=3)
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.selector.close()
        self.error_file.close()
        self.temp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def probe():
    """Verify the enforcement mechanism, not only its requested configuration."""
    with tempfile.TemporaryDirectory(prefix='foreagent-private-canary-') as temp:
        secret = Path(temp)/'canary.txt'
        secret.write_text('private evaluation canary')
        source = b'''import socket
def decide(observation):
    blocked = {}
    try:
        open(observation['canary']).read()
        blocked['private_read'] = False
    except PermissionError:
        blocked['private_read'] = True
    try:
        open(observation['canary'], 'w').write('changed')
        blocked['outside_write'] = False
    except PermissionError:
        blocked['outside_write'] = True
    try:
        socket.create_connection(('127.0.0.1', 9), timeout=0.1)
        blocked['network'] = False
    except PermissionError:
        blocked['network'] = True
    except OSError:
        blocked['network'] = False
    return blocked
'''
        with Worker(source) as worker:
            result = worker.request({'canary':str(secret)})
        if result != {'private_read':True, 'outside_write':True, 'network':True}:
            raise PolicyError('Sandbox enforcement probe failed: '+repr(result))
        if secret.read_text() != 'private evaluation canary':
            raise PolicyError('Sandbox canary was changed')
        return result
