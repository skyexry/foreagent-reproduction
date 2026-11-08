"""Grade only the preserved node selected by upstream, with the private evaluator on Mac."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

def grade(run_dir, completion):
    here=Path(__file__).resolve().parent
    base=here.parent.parent/'environment-author'
    root=run_dir/'workspaces/exp'
    submission=root/'best_submission/submission.csv'
    nodeinfo=(root/'best_solution/node_info.txt').read_text()
    ident=re.search(r'^node_id: (\S+)',nodeinfo,re.M)[1]
    node_dir=root/'all_nodes'/('node_'+ident[:8])
    node_copy=node_dir/'submission.csv'
    meta=json.loads((node_dir/'metadata.json').read_text())
    if meta['node_id']!=ident or meta['is_skipped'] or node_copy.read_bytes()!=submission.read_bytes():
        raise ValueError('best submission and selected node copy differ')
    cmd=[str(base/'.venv/bin/mlebench'),'grade-sample',str(submission),'stanford-covid-vaccine','--data-dir',str(here.parent/'data')]
    r=subprocess.run(cmd,cwd=base/'mle-bench',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (run_dir/'official-grade.txt').write_text(r.stdout)
    r.check_returncode()
    idx=r.stdout.find('{',r.stdout.index('Competition report:'))
    report=json.JSONDecoder().raw_decode(r.stdout[idx:])[0]
    if not report.get('valid_submission') or report.get('score') is None:
        raise ValueError('official scorer rejected the selected submission')
    result={'run':run_dir.name,'completion':completion,'node_id':ident,
            'submission_sha256':hashlib.sha256(submission.read_bytes()).hexdigest(),'official_report':report}
    (run_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
if __name__=='__main__': grade(Path(sys.argv[1]).resolve(),sys.argv[2])
