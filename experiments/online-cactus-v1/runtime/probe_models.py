"""Exercise each original backend role with small synthetic inputs on the server."""
import ast
import json
import re
import signal
from pathlib import Path
import controller
import jsonschema

from aide.agent import review_func_spec
from aide.backend import backend_openai
from aide.world_model import BENCH_SYSTEM_PROMPT_COT, build_pairwise_prompt, parse_pairwise_response

HERE = Path(__file__).resolve().parent


def main():
    output = HERE / 'api-preflight-v1'
    output.mkdir(mode=0o700)
    config = json.loads(Path('/root/.config/foreagent/runtime.json').read_text())
    controller.setup_models(output, config)
    results = {}
    for role in ('feedback', 'code', 'select'):
        signal.alarm(300)
        spec = None
        system = 'Give a one-sentence plan and one fenced Python function that computes the mean of a nonempty numeric list.'
        user = None
        if role == 'select':
            system = BENCH_SYSTEM_PROMPT_COT
            user = build_pairwise_prompt('Predict y=2*x on held-out examples. Minimize squared error.', '',
                                         'predict=lambda x: 2*x', 'predict=lambda x: 0')
        if role == 'feedback':
            system = 'Review a successful training log. Validation RMSE = 0.25 (lower is better). Wrote ./submission/submission.csv. Exit code 0.'
            spec = review_func_spec
        model = {'code': 'DeepSeek-V3.2', 'select': 'DeepSeek-V3.2-Thinking',
                 'feedback': 'gpt-4o-mini-2024-07-18'}[role]
        answer, elapsed, incoming, outgoing, info = backend_openai.query(
            system_message=system, user_message=user, func_spec=spec,
            model=model, temperature=1.0 if role == 'select' else 0.5)
        if role == 'code':
            code = re.search(r'```(?:python)?\s*\n(.+?)```', answer, re.S)
            assert code and any(isinstance(node, ast.FunctionDef) for node in ast.parse(code[1].strip()).body)
        elif role == 'select':
            parsed = parse_pairwise_response(answer)
            assert parsed['predicted_best_index'] in (0, 1)
            assert 0 <= parsed['confidence'] <= 1
        else:
            jsonschema.validate(answer, spec.json_schema)
            assert answer['is_bug'] is False and answer['has_csv_submission'] is True
            assert answer['metric'] == 0.25 and answer['lower_is_better'] is True
        results[role] = dict(status='passed', elapsed_seconds=elapsed, tokens_in=incoming,
                             tokens_out=outgoing, returned_model=info['model'])
        (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(role, json.dumps(results[role]), flush=True)
        signal.alarm(0)


if __name__ == '__main__':
    main()
