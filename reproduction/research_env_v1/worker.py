"""Copied to an isolated temporary directory; receives public observations only."""
import importlib.util
import json
import sys
import traceback


def main():
    spec = importlib.util.spec_from_file_location('submitted_policy', sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, 'decide', None)):
        raise ValueError('Policy must define decide(observation)')
    for line in sys.stdin:
        observation = json.loads(line)
        action = module.decide(observation)
        print(json.dumps(action, allow_nan=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
