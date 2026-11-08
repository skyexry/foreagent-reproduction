"""One paid run after zero-call prompt verification; grade snapshots outside the agent's workspace."""
from pathlib import Path
import json
import signal
import subprocess
import time
from grade_checkpoint import run as checkpoint
from score_run import grade

here=Path(__file__).resolve().parent
scope=json.loads((here/'protocol-v2.json').read_text())['run']
if __name__=='__main__':
    assert 'Compared all three first prompts.' in (here/'prompt-dry-check.log').read_text()
    assert (here/'verified-bridge.json').is_file()
    rd=here/'runs'/scope
    if rd.exists(): raise FileExistsError(rd)
    started=time.time()
    with (here/'controller-v2.log').open('x') as out:
        proc=subprocess.Popen([str(here/'controller-venv/bin/python'),str(here/'controller.py'),scope],cwd=here,stdout=out,stderr=subprocess.STDOUT)
        (here/'controller-v2.pid').write_text(str(proc.pid))
        observed=set(); scored=False
        while proc.poll() is None:
            node=rd/'workspaces/exp/best_solution/node_info.txt'
            if not scored and node.is_file():
                key=node.read_text().splitlines()[0]
                if key not in observed:
                    observed.add(key)
                    try:
                        checkpoint(rd);scored=True
                    except Exception as err:
                        print('Checkpoint not accepted:',key,repr(err),flush=True)
            time.sleep(10)
    code=proc.returncode
    status='published time limit' if code==-signal.SIGALRM else 'step budget' if code==0 else 'interrupted, partial run'
    print('controller exit',code,status,'seconds',round(time.time()-started),flush=True)
    if (rd/'workspaces/exp/best_submission/submission.csv').is_file(): grade(rd,status)
    else:raise RuntimeError('no selected submission; see controller-v2.log')
