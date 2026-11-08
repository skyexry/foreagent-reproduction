"""Zero-call import and configuration check for the two published author baselines."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    src = args.source.resolve()/'mle-bench/agents/aide'
    sys.path.insert(0, str(src))
    import yaml
    from omegaconf import OmegaConf
    from aide import Agent, Journal, backend, run
    from aide.utils.config import _load_cfg
    settings = yaml.safe_load((src/'config.yaml').read_text())
    outcomes = {}
    with tempfile.TemporaryDirectory() as temp, patch.object(
            backend, 'query', side_effect=AssertionError('API calls are outside this dry check')):
        for name in ('ForeAgent/DeepSeek-V3.2', 'aide/DeepSeek-V3.2'):
            cfg = _load_cfg(use_cli_args=False)
            for key, value in settings[name]['kwargs'].items():
                OmegaConf.update(cfg, key, value)
            agent = Agent('Configuration-only check',
                          SimpleNamespace(agent=cfg.agent, workspace_dir=Path(temp)/name), Journal())
            outcomes[name] = {
                'world_model_enabled': agent.use_world_model,
                'code': OmegaConf.to_container(cfg.agent.code),
                'feedback': OmegaConf.to_container(cfg.agent.feedback),
                'search': OmegaConf.to_container(cfg.agent.search),
                'time_limit': cfg.agent.time_limit, 'steps': cfg.agent.steps,
                'exec_timeout': cfg.exec.timeout,
            }
        foreagent, aide = outcomes.values()
        if foreagent['world_model_enabled'] is not True or aide['world_model_enabled'] is not False:
            raise ValueError('Wrong published baseline route')
        for key in ('code', 'feedback', 'search', 'time_limit', 'steps', 'exec_timeout'):
            if foreagent[key] != aide[key]:
                raise ValueError('Mismatched common baseline setting: '+key)
    result = {'status': 'passed', 'models': outcomes, 'new_api_calls': 0, 'training_runs': 0,
              'scope': 'Original modules imported and both Agent objects constructed. GPU runtime, SSH execution and live services are separate preflight items.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('PASS: both published configurations import and construct; shared controls match.')


if __name__ == '__main__':
    main()
