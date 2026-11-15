"""Server-local transport to the frozen author's restricted GPU Interpreter."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import uuid

BASE = str(Path(__file__).resolve().parent)
PYTHON = '/opt/conda/envs/agent/bin/python'
LAST_EXECUTION_JOB = None


def remote(command, **kwargs):
    """Keep the old adapter interface; commands execute on this server."""
    return subprocess.run(['bash', '-c', command], check=True, **kwargs)


def scope_name():
    name = os.environ['FOREAGENT_RUN']
    if not name or not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):
        raise ValueError('invalid run identifier')
    return name


def worker_base():
    return Path(BASE) / 'workers' / scope_name()


def sync_public_input(workspace):
    target = worker_base() / 'workspace' / 'input'
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-rlt', '--copy-links', '--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r',
                    str(Path(workspace) / 'input') + '/', str(target) + '/'], check=True)


class RemoteInterpreter:
    def __init__(self, workspace, **cfg):
        self.workspace = Path(workspace)
        self.cfg = cfg
        self.scope = scope_name()
        self.base = worker_base()

    def run(self, code, reset_session=True):
        from aide.interpreter import ExecutionResult
        assert reset_session
        global LAST_EXECUTION_JOB
        key = uuid.uuid4().hex
        LAST_EXECUTION_JOB = key
        job = self.base / 'jobs' / key
        local = self.workspace.parent.parent / 'tasks' / key
        local.mkdir(parents=True)
        execution = {'job_id': key, 'scope': self.scope, 'requested': time.time(),
                     'code_sha256': hashlib.sha256(code.encode()).hexdigest(),
                     'status': 'preparing'}
        (local / 'execution.json').write_text(json.dumps(execution, indent=2) + '\n')
        sync_public_input(self.workspace)
        for name in ('best_solution', 'best_submission', 'all_nodes'):
            source = self.workspace / name
            if source.is_dir():
                subprocess.run(['rsync', '-rlt', '--safe-links',
                                '--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r',
                                str(source), str(self.base / 'workspace') + '/'], check=True)
        message = json.dumps({'cfg': self.cfg, 'code': code})
        (local / 'request.json').write_text(message)
        job.mkdir(parents=True)
        subprocess.run(['install', '-d', '-o', 'foreagentx', '-g', 'foreagentx',
                        str(job / 'output')], check=True)
        (job / 'request.json').write_text(message)
        (job / 'request.json').chmod(0o644)
        left = max(1, int(float(os.environ['FOREAGENT_DEADLINE']) - time.time()))
        command = ['timeout', '--kill-after=8', str(left), 'bash', str(Path(BASE) / 'guest.sh'),
                   self.scope, PYTHON, '/worker.py', '/jobs/' + key]
        execution.update(worker_started=time.time(), status='running', command=command)
        (local / 'execution.json').write_text(json.dumps(execution, indent=2) + '\n')
        (job / 'started.json').write_text(json.dumps(execution, indent=2) + '\n')
        with (job / 'console.log').open('wb') as console:
            process = subprocess.Popen(command, stdout=console, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            (job / 'pid').write_text(str(process.pid))
            returncode = process.wait()
        (job / 'exit').write_text(str(returncode))
        execution.update(worker_ended=time.time(), returncode=returncode,
                         status='worker returned' if returncode == 0 else 'worker failed')
        execution['worker_wall_seconds'] = execution['worker_ended'] - execution['worker_started']
        (local / 'execution.json').write_text(json.dumps(execution, indent=2) + '\n')
        if returncode:
            raise RuntimeError('GPU worker infrastructure failed: ' +
                               (job / 'console.log').read_text(errors='replace')[-2600:])
        data = remote(shlex.join(['setpriv', '--reuid=foreagentx', '--regid=foreagentx',
                                 '--clear-groups', 'cat', str(job / 'output/result.json')]),
                      capture_output=True).stdout
        result = ExecutionResult.from_json(data.decode())
        (local / 'result.json').write_bytes(data)
        execution.update(author_exec_seconds=result.exec_time, exception_type=result.exc_type)
        source = self.base / 'workspace/submission/submission.csv'
        destination = self.workspace / 'submission/submission.csv'
        if source.is_file() and not source.is_symlink():
            command = ['setpriv', '--reuid=foreagentx', '--regid=foreagentx', '--clear-groups']
            contents = subprocess.run(command + ['cat', str(source)], check=True,
                                      capture_output=True).stdout
            expected = subprocess.run(command + ['sha256sum', str(source)], check=True,
                                      capture_output=True, text=True).stdout.split()[0]
            digest = hashlib.sha256(contents).hexdigest()
            if digest != expected:
                raise ValueError('submission changed during transfer')
            (local / 'submission.csv').write_bytes(contents)
            (local / 'submission.csv').chmod(0o444)
            execution.update(submission_sha256=digest, submission_saved=True)
            temporary = local / 'submission.transfer'
            temporary.write_bytes(contents)
            os.replace(temporary, destination)
            (local / 'submission.sha256').write_text(digest + '\n')
        elif destination.exists():
            destination.unlink()
        execution.update(completed=time.time(), status='result archived')
        execution.setdefault('submission_saved', False)
        (local / 'execution.json').write_text(json.dumps(execution, indent=2) + '\n')
        return result

    def cleanup_session(self):
        # The unchanged worker cleans its Interpreter before publishing result.json.
        pass


def clear_remote_submission():
    directory = worker_base() / 'workspace/submission'
    if directory.is_dir():
        subprocess.run(['setpriv', '--reuid=foreagentx', '--regid=foreagentx', '--clear-groups',
                        'find', '-P', str(directory), '-mindepth', '1', '-delete'], check=True)
