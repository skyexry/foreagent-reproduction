"""Run upstream ForeAgent on the Mac and execute all candidate Python only on AutoDL."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import sys
import threading
import time
from types import SimpleNamespace

import httpx
import openai
import yaml
from bridge import BASE, PYTHON, RemoteInterpreter, clear_remote_submission, remote

here=Path(__file__).resolve().parent
upstream=here.parent.parent/'foreagent-author-only/mle-bench'
src=upstream/'agents/aide'
sys.path.insert(0,str(src))
sys.dont_write_bytecode=True

def setup_models(run_dir):
    from aide.backend import backend_openai as backend
    file=here.parent/'lambda/model_gateway.py'
    spec=importlib.util.spec_from_file_location('model_gateway',file)
    router=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    keys={p:(Path.home()/'.config/foreagent'/(p+'.key')).read_text().strip() for p in ('openai','siliconflow')}
    lock=threading.Lock()
    class Transport(httpx.HTTPTransport):
        def handle_request(self,req):
            body=json.loads(req.content)
            role=body['model']
            provider,url=router.route(body)
            req2=httpx.Request('POST',url,headers={'Authorization':'Bearer '+keys[provider]},json=body,extensions=req.extensions)
            r=super().handle_request(req2)
            try: content=r.read()
            finally: r.close()
            info=json.loads(content) if r.is_success else {}
            record=dict(role=role,http=r.status_code,response_id=info.get('id'),model=info.get('model'),usage=info.get('usage'))
            with lock,(run_dir/'api.jsonl').open('a') as out: print(json.dumps(record),file=out)
            return httpx.Response(r.status_code,content=content,headers={'content-type':'application/json'})
    os.environ['OPENAI_API_KEY']='local-routing'
    backend._setup_openai_client()
    backend._client=openai.OpenAI(api_key='local-routing',base_url='http://foreagent.invalid/v1',max_retries=0,http_client=httpx.Client(transport=Transport(),timeout=600))
    del os.environ['OPENAI_API_KEY']

def get_hardware(scope):
    probe=('import json,multiprocessing,platform,torch; x=torch.ones(2,device="cuda"); '
           'print(json.dumps(dict(gpu=torch.cuda.get_device_name(0),cores=multiprocessing.cpu_count(),'
           'cuda=x.sum().item()==2, devices=torch.cuda.device_count(), torch=torch.__version__,'
           'cuda_build=torch.version.cuda, python=platform.python_version())))')
    out=remote(shlex.join(['bash',BASE+'/guest.sh',scope,PYTHON,'-c',probe]),capture_output=True,text=True)
    return json.loads(out.stdout.strip().splitlines()[-1])

def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('scope')
    args=parser.parse_args()
    os.environ['FOREAGENT_RUN']=args.scope
    from bridge import scope_name
    scope=scope_name()
    from aide import agent,run as original
    from omegaconf import OmegaConf
    from aide.utils.config import _load_cfg, prep_cfg
    data=here/'task'
    run_dir=here/'runs'/scope
    settings=yaml.safe_load((src/'config.yaml').read_text())['ForeAgent/DeepSeek-V3.2']
    hardware=get_hardware(scope)
    if not hardware['cuda']: raise RuntimeError('GPU smoke test failed')
    run_dir.mkdir(parents=True,exist_ok=False)
    (run_dir/'hardware.json').write_text(json.dumps(hardware,indent=2))
    task=run_dir/'instructions.txt'
    env=settings['env_vars']
    budget=env['TIME_LIMIT_SECS']
    notes=(src/'additional_notes.txt').read_text().replace('${HARDWARE}','1 '+hardware['gpu']).replace('${TIME_LIMIT}','12hrs 0mins 0secs').replace('${STEP_LIMIT}',str(env['STEP_LIMIT']))
    # start.sh reads /home/instructions.txt from the built image, which differs from the Git source.
    baked=(here/'baked-instructions.txt').read_bytes()
    assert hashlib.sha256(baked).hexdigest()=='06e667de751ff7e4f24e22b03984bfc3e1734dd748e33b079e5746b3c6520a69'
    task.write_text(baked.decode().replace('/home/','')+'\n'+notes+'\nCOMPETITION INSTRUCTIONS\n------\n\n'+(data/'description.md').read_text())
    cfg=_load_cfg(use_cli_args=False)
    for key,value in settings['kwargs'].items(): OmegaConf.update(cfg,key,value)
    cfg.data_dir=str(data); cfg.desc_file=str(task); cfg.exp_name='exp'
    cfg.log_dir=str(run_dir/'logs'); cfg.workspace_dir=str(run_dir/'workspaces')
    cfg.agent.data_analysis_path=str(data/'da_report.txt')
    cfg=prep_cfg(cfg)
    for name in ['best_submission','best_solution','all_nodes']:
        (cfg.workspace_dir/name).mkdir(parents=True,exist_ok=True)
    # Use the author's actual Linux/pandas preview (ties in displayed example IDs depend on pandas).
    def worker_preview(_workspace):
        cmd="from pathlib import Path; from aide.utils.data_preview import generate; print(generate(Path('/home/agent/workspaces/exp')),end='')"
        return remote(shlex.join(['bash',BASE+'/guest.sh',scope,PYTHON,'-c',cmd]),capture_output=True,text=True).stdout
    agent.data_preview=SimpleNamespace(generate=worker_preview)
    original.load_cfg=lambda:cfg
    original.Interpreter=RemoteInterpreter
    # Use the GPU worker's actual detection values in the upstream hardware prompt.
    agent.torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:hardware['cuda']))
    agent.multiprocessing=SimpleNamespace(cpu_count=lambda:hardware['cores'])
    step=agent.Agent.step
    def split_step(self,exec_callback):
        clear_remote_submission()
        return step(self,exec_callback)
    agent.Agent.step=split_step
    setup_models(run_dir)
    print('Starting original ForeAgent with published rollout settings',flush=True)
    os.environ['FOREAGENT_DEADLINE']=str(time.time()+budget)
    signal.alarm(budget)
    try: original.run()
    finally: signal.alarm(0)

if __name__=='__main__': run()
