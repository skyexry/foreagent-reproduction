"""Mac controller -> restricted GPU candidate -> author's ExecutionResult and submission."""
import json
import hashlib
import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from send_image import ssh, host

BASE='/root/autodl-tmp/foreagent/runtime'
PYTHON='/opt/conda/envs/agent/bin/python'

def remote(command, **kwargs):
    for attempt in range(6):
        result=subprocess.run(ssh+[host,command],**kwargs)
        if result.returncode==0: return result
        if result.returncode!=255 or attempt==5: result.check_returncode()
        time.sleep(5*(attempt+1))

def scope_name():
    name=os.environ['FOREAGENT_RUN']
    if not name or not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):
        raise ValueError('invalid run identifier')
    return name

def wait_job(command):
    # Retrying a status read is safe. Never resubmit a candidate after losing SSH.
    return remote(command,capture_output=True,text=True).stdout.strip()

class RemoteInterpreter:
    def __init__(self,workspace,**cfg):
        self.workspace=Path(workspace)
        self.cfg=cfg
        self.scope=scope_name()
        self.base=f'{BASE}/{self.scope}'

    def run(self,code,reset_session=True):
        from aide.interpreter import ExecutionResult
        assert reset_session
        key=uuid.uuid4().hex
        job=f'{self.base}/jobs/{key}'
        local=self.workspace.parent.parent/'tasks'/key
        local.mkdir(parents=True)
        # Publish the same best-solution and per-node artifacts visible in an upstream workspace.
        # The remote scratch directory persists across candidates just like the upstream working/ directory.
        artifact_src=[str(self.workspace/n) for n in ('best_solution','best_submission','all_nodes') if (self.workspace/n).is_dir()]
        if artifact_src:
            for attempt in range(4):
                result=subprocess.run(['rsync','-rzt','--safe-links','--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r','-e',shlex.join(ssh),*artifact_src,host+':'+self.base+'/workspace/'])
                if result.returncode==0: break
                if attempt==3: result.check_returncode()
                time.sleep(5*(attempt+1))
        msg=json.dumps({'cfg':self.cfg,'code':code})
        (local/'request.json').write_text(msg)
        # request and terminal status belong to the SSH manager. The worker can write only output/.
        remote(f'mkdir -p {job} && install -d -o foreagentx -g foreagentx {job}/output && cat > {job}/request.json',input=msg.encode())
        left=max(1,int(float(os.environ.get('FOREAGENT_DEADLINE',time.time()+self.cfg['timeout']+120))-time.time()))
        run=shlex.join(['timeout','--kill-after=8',str(left),'bash',BASE+'/guest.sh',self.scope,PYTHON,'/worker.py','/jobs/'+key])
        inner=f'mkdir {job}/started 2>/dev/null || exit 0; {run} > {job}/console.log 2>&1; echo $? > {job}/exit.tmp; mv {job}/exit.tmp {job}/exit'
        remote('nohup bash -c '+shlex.quote(inner)+' </dev/null >/dev/null 2>&1 &')
        while True:
            state=wait_job(f'if test -f {job}/exit; then cat {job}/exit; else echo running; fi')
            if state!='running':
                if state!='0':
                    tail=wait_job(f'tail -c 2600 {job}/console.log')
                    raise RuntimeError('GPU worker infrastructure failed: '+tail)
                break
            time.sleep(4)
        result_path=job+'/output/result.json'
        data=remote(f'setpriv --reuid=foreagentx --regid=foreagentx --clear-groups cat {result_path}',capture_output=True).stdout
        result=ExecutionResult.from_json(data.decode())
        (local/'result.json').write_bytes(data)
        dst=self.workspace/'submission/submission.csv'
        path=self.base+'/workspace/submission/submission.csv'
        # A generated candidate may have failed. Respect the upstream file-presence check.
        present=wait_job(f'if test -f {path} && ! test -L {path}; then echo present; else echo absent; fi')
        if present=='present':
            tmp=local/'submission.transfer'
            read_as_worker='setpriv --reuid=foreagentx --regid=foreagentx --clear-groups'
            contents=remote(f'{read_as_worker} cat {path}',capture_output=True).stdout
            digest=hashlib.sha256(contents).hexdigest()
            expected=wait_job(f'{read_as_worker} sha256sum {path}').split()[0]
            if digest!=expected: raise ValueError('submission changed during transfer')
            tmp.write_bytes(contents)
            os.replace(tmp,dst)
            (local/'submission.sha256').write_text(digest+'\n')
        elif dst.exists():
            dst.unlink()
        return result

    def cleanup_session(self):
        pass  # The remote worker cleans its Interpreter before publishing result.json.

def clear_remote_submission():
    path=BASE+'/'+scope_name()+'/workspace/submission'
    # This is the exact per-step cleanup done on the Mac by Agent.step().
    # Run it as the candidate's Unix user so symlinks cannot widen filesystem access.
    remote(f'if test -d {path}; then setpriv --reuid=foreagentx --regid=foreagentx --clear-groups find -P {path} -mindepth 1 -delete; fi')
