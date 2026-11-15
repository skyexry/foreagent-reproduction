"""Original ForeAgent with server-local controller/worker transport and audit logs."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import shlex
import signal
import sys
import threading
import time
import uuid
from types import SimpleNamespace

import httpx
import openai
import yaml
import bridge
from bridge import BASE, PYTHON, RemoteInterpreter, clear_remote_submission, remote, sync_public_input

HERE = Path(__file__).resolve().parent
SOURCE = Path('/root/autodl-tmp/foreagent/preflight/upstream/mle-bench/agents/aide')
sys.path.insert(0, str(SOURCE))
sys.dont_write_bytecode = True


class SmokeComplete(Exception):
    pass


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)


def route(body):
    model = body['model']
    if model not in {'DeepSeek-V3.2', 'DeepSeek-V3.2-Thinking', 'gpt-4o-mini-2024-07-18'} or body.get('stream'):
        raise ValueError('unsupported model request')
    if model.startswith('DeepSeek'):
        enabled = model == 'DeepSeek-V3.2-Thinking'
        if body.pop('thinking', None) != ({'type': 'enabled'} if enabled else None):
            raise ValueError('unexpected thinking setting')
        body.update(model='deepseek-ai/DeepSeek-V3.2', enable_thinking=enabled)
        return 'siliconflow', 'https://api.siliconflow.cn/v1/chat/completions'
    return 'openai', 'https://api.openai.com/v1/chat/completions'


def setup_models(run_dir, config):
    from aide.backend import backend_openai as backend
    key_dir = Path(config.get('keys_dir', '/root/.config/foreagent'))
    keys = {name: (key_dir / (name + '.key')).read_text().strip()
            for name in ('openai', 'siliconflow')}
    if not all(keys.values()):
        raise ValueError('provider credentials are empty')
    providers = config.get('providers', {})
    transports = {name: httpx.HTTPTransport(proxy=providers.get(name, {}).get('proxy'))
                  for name in keys}
    archive = run_dir / 'api-records'
    archive.mkdir(mode=0o700)
    lock = threading.Lock()

    def record(value):
        with lock, (run_dir / 'api.jsonl').open('a') as output:
            print(json.dumps(value), file=output, flush=True)

    def save(path, contents):
        # Request/response headers are excluded; redact provider keys defensively.
        for key in keys.values():
            contents = contents.replace(key.encode(), b'<redacted>')
        path.write_bytes(contents)
        path.chmod(0o600)

    class Transport(httpx.BaseTransport):
        def handle_request(self, request):
            key = uuid.uuid4().hex
            started = time.time()
            body = json.loads(request.content)
            role = body['model']
            save(archive / (key + '.request.json'), request.content)
            provider, url = route(body)
            url = providers.get(provider, {}).get('url', url)
            record({'event': 'request_start', 'request_id': key, 'time': started,
                    'role': role, 'provider': provider})
            forwarded = httpx.Request('POST', url,
                                     headers={'Authorization': 'Bearer ' + keys[provider]},
                                     json=body, extensions=request.extensions)
            save(archive / (key + '.routed-request.json'), forwarded.content)
            try:
                response = transports[provider].handle_request(forwarded)
                try:
                    content = response.read()
                finally:
                    response.close()
                save(archive / (key + '.response.json'), content)
                trace_names = ('x-request-id', 'request-id', 'x-siliconcloud-request-id',
                               'x-sf-request-id', 'traceparent', 'cf-ray')
                trace_headers = {name: response.headers[name] for name in trace_names
                                 if name in response.headers}
                try:
                    info = json.loads(content)
                except (ValueError, UnicodeError):
                    info = {}
                record({'event': 'response', 'request_id': key, 'time': time.time(),
                        'elapsed_seconds': time.time() - started, 'role': role,
                        'provider': provider, 'http': response.status_code,
                        'response_id': info.get('id'), 'model': info.get('model'),
                        'usage': info.get('usage'),
                        'provider_request_id': trace_headers.get('x-request-id') or
                                               trace_headers.get('request-id') or
                                               trace_headers.get('x-siliconcloud-request-id'),
                        'trace_headers': trace_headers})
                return httpx.Response(response.status_code, content=content,
                                      headers={'content-type': 'application/json'})
            except Exception as error:
                record({'event': 'request_error', 'request_id': key, 'time': time.time(),
                        'elapsed_seconds': time.time() - started, 'role': role,
                        'provider': provider, 'error_type': type(error).__name__})
                raise

        def close(self):
            for transport in transports.values():
                transport.close()

    os.environ['OPENAI_API_KEY'] = 'local-routing'
    backend._setup_openai_client()
    backend._client = openai.OpenAI(api_key='local-routing',
                                   base_url='http://foreagent.invalid/v1', max_retries=0,
                                   http_client=httpx.Client(transport=Transport(), timeout=600))
    del os.environ['OPENAI_API_KEY']


def get_hardware(scope):
    probe = ('import json,multiprocessing,platform,torch; x=torch.ones(2,device="cuda"); '
             'print(json.dumps(dict(gpu=torch.cuda.get_device_name(0),cores=multiprocessing.cpu_count(),'
             'cuda=x.sum().item()==2,devices=torch.cuda.device_count(),torch=torch.__version__,'
             'cuda_build=torch.version.cuda,python=platform.python_version())))')
    output = remote(shlex.join(['bash', BASE + '/guest.sh', scope, PYTHON, '-c', probe]),
                    capture_output=True, text=True)
    return json.loads(output.stdout.strip().splitlines()[-1])


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', required=True)
    parser.add_argument('--phase', choices=['preflight', 'smoke', 'formal'], required=True)
    parser.add_argument('--model-config', type=Path, default=Path('/root/.config/foreagent/runtime.json'))
    args = parser.parse_args()
    os.environ['FOREAGENT_RUN'] = args.scope
    from bridge import scope_name
    scope = scope_name()
    from aide import agent, run as original
    from aide.world_model import WorldModel
    from omegaconf import OmegaConf
    from aide.utils.config import _load_cfg, prep_cfg, prep_agent_workspace

    data = HERE / 'task'
    run_dir = HERE / 'runs' / scope
    run_dir.mkdir(parents=True, exist_ok=False)
    run_dir.chmod(0o700)
    settings = yaml.safe_load((SOURCE / 'config.yaml').read_text())['ForeAgent/DeepSeek-V3.2']
    hardware = get_hardware(scope)
    if not hardware['cuda']:
        raise RuntimeError('GPU smoke test failed')
    atomic_json(run_dir / 'hardware.json', hardware)
    task = run_dir / 'instructions.txt'
    environment = settings['env_vars']
    budget = int(environment['TIME_LIMIT_SECS'])
    assert budget == 43200
    notes = (SOURCE / 'additional_notes.txt').read_text().replace(
        '${HARDWARE}', '1 ' + hardware['gpu']).replace(
        '${TIME_LIMIT}', '12hrs 0mins 0secs').replace('${STEP_LIMIT}', str(environment['STEP_LIMIT']))
    baked = (HERE / 'baked-instructions.txt').read_bytes()
    assert hashlib.sha256(baked).hexdigest() == '06e667de751ff7e4f24e22b03984bfc3e1734dd748e33b079e5746b3c6520a69'
    task.write_text(baked.decode().replace('/home/', '') + '\n' + notes +
                    '\nCOMPETITION INSTRUCTIONS\n------\n\n' + (data / 'description.md').read_text())
    cfg = _load_cfg(use_cli_args=False)
    for key, value in settings['kwargs'].items():
        OmegaConf.update(cfg, key, value)
    cfg.data_dir = str(data)
    cfg.desc_file = str(task)
    cfg.exp_name = 'exp'
    cfg.log_dir = str(run_dir / 'logs')
    cfg.workspace_dir = str(run_dir / 'workspaces')
    cfg.agent.data_analysis_path = str(data / 'da_report.txt')
    cfg = prep_cfg(cfg)
    OmegaConf.save(cfg, run_dir / 'effective-config.yaml')
    tracked = ['config.yaml', 'aide/agent.py', 'aide/world_model.py',
               'aide/interpreter.py', 'aide/backend/backend_openai.py', 'aide/utils/config.yaml']
    atomic_json(run_dir / 'source-hashes.json',
                {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in tracked})
    for name in ('best_submission', 'best_solution', 'all_nodes'):
        (cfg.workspace_dir / name).mkdir(parents=True, exist_ok=True)

    def worker_preview(_workspace):
        sync_public_input(cfg.workspace_dir)
        command = "from pathlib import Path; from aide.utils.data_preview import generate; print(generate(Path('/home/agent/workspaces/exp')),end='')"
        return remote(shlex.join(['bash', BASE + '/guest.sh', scope, PYTHON, '-c', command]),
                      capture_output=True, text=True).stdout

    if args.phase == 'preflight':
        prep_agent_workspace(cfg)
        (run_dir / 'worker-data-preview.txt').write_text(worker_preview(cfg.workspace_dir))
        atomic_json(run_dir / 'completion.json', {'phase': args.phase, 'status': 'zero-call preflight passed',
                    'time': time.time(), 'cuda': True, 'model_api_calls': 0})
        return

    config = json.loads(args.model_config.read_text()) if args.model_config.exists() else {}
    setup_models(run_dir, config)
    agent.data_preview = SimpleNamespace(generate=worker_preview)
    original.load_cfg = lambda: cfg
    original.Interpreter = RemoteInterpreter
    agent.torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: hardware['cuda']))
    agent.multiprocessing = SimpleNamespace(cpu_count=lambda: hardware['cores'])
    observation = {'completed_tournaments': 0, 'completed_ten_candidate_tournaments': 0,
                   'smoke_ready': False}
    original_tournament = WorldModel.tournament_rank

    def counted_tournament(self, *values, **kwargs):
        result = original_tournament(self, *values, **kwargs)
        observation['completed_tournaments'] += 1
        candidates = values[0] if values else kwargs.get('candidates', [])
        if len(candidates) == 10:
            observation['completed_ten_candidate_tournaments'] += 1
        return result

    WorldModel.tournament_rank = counted_tournament
    original_parse = agent.Agent.parse_exec_result

    def timed_parse(self, node, exec_result):
        job_id = bridge.LAST_EXECUTION_JOB
        path = run_dir / 'tasks' / job_id / 'execution.json'
        execution = json.loads(path.read_text())
        assert execution['code_sha256'] == hashlib.sha256(node.code.encode()).hexdigest()
        execution.update(node_id=node.id, feedback_started=time.time())
        atomic_json(path, execution)
        try:
            return original_parse(self, node=node, exec_result=exec_result)
        except BaseException as error:
            execution['feedback_error_type'] = type(error).__name__
            raise
        finally:
            execution['feedback_ended'] = time.time()
            execution['feedback_wall_seconds'] = execution['feedback_ended'] - execution['feedback_started']
            try:
                atomic_json(path, execution)
            except OSError as error:
                logging.getLogger('aide').error('Feedback timing archive failed: %s', type(error).__name__)

    agent.Agent.parse_exec_result = timed_parse
    original_step = agent.Agent.step

    def observed_step(self, exec_callback):
        if args.phase == 'smoke' and observation['smoke_ready']:
            raise SmokeComplete()
        clear_remote_submission()
        result = original_step(self, exec_callback)
        observation['draft_nodes'] = len(self.journal.draft_nodes)
        observation['journal_nodes'] = len(self.journal)
        observation['smoke_ready'] = (observation['draft_nodes'] >= 3 and
                                      observation['completed_ten_candidate_tournaments'] >= 1)
        atomic_json(run_dir / 'progress.json', dict(observation, time=time.time()))
        from supervisor import node_manifest
        node_manifest(run_dir)
        return result

    agent.Agent.step = observed_step
    started = time.time()
    wall_cap = 7200 if args.phase == 'smoke' else budget
    deadline = started + wall_cap
    os.environ['FOREAGENT_DEADLINE'] = str(deadline)
    atomic_json(run_dir / 'started.json', {'phase': args.phase, 'started': started,
                'deadline': deadline, 'published_budget_seconds': budget,
                'outer_wall_cap_seconds': wall_cap, 'pid': os.getpid()})
    # Default signal termination cannot be swallowed by upstream retry handlers.
    # The persistent supervisor records an alarm exit, as in the frozen run.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(wall_cap)
    status = 'step budget completed'
    try:
        original.run()
    except SmokeComplete:
        status = 'smoke completed after three drafts and first tournament'
    except BaseException as error:
        status = 'interrupted: ' + type(error).__name__
        raise
    finally:
        signal.alarm(0)
        atomic_json(run_dir / 'completion.json', dict(observation, phase=args.phase, status=status,
                    started=started, ended=time.time(), elapsed_seconds=time.time() - started))


if __name__ == '__main__':
    run()
