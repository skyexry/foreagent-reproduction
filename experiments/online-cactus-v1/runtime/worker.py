"""One generated candidate per invocation, using the unchanged author's Interpreter."""
import json
import multiprocessing
import os
import sys
from pathlib import Path
from aide.interpreter import Interpreter

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn', force=True)
    job = Path(sys.argv[1])
    args = json.loads((job/'request.json').read_text())
    interp = Interpreter(Path('/home/agent/workspaces/exp'), **args['cfg'])
    try:
        result = interp.run(args['code'], reset_session=True)
    finally:
        interp.cleanup_session()
    temporary = job/'output/result.tmp'
    temporary.write_text(result.to_json())
    os.replace(temporary, job/'output/result.json')
