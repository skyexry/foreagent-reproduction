"""Freeze and grade one upstream-selected checkpoint outside the controller workspace."""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from score_run import grade

def run(run_dir):
    root=run_dir/'workspaces/exp'
    info=(root/'best_solution/node_info.txt').read_text()
    node=re.search(r'^node_id: ([0-9a-f]+)$',info,re.M)[1]
    output=run_dir/'observer-only'/('checkpoint-'+node)
    if (output/'result.json').exists():return
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as name:
        snapshot=Path(name)/output.name
        target=snapshot/'workspaces/exp'
        target.mkdir(parents=True)
        for sub in ('best_solution','best_submission','all_nodes/node_'+node[:8]):
            shutil.copytree(root/sub,target/sub)
        assert (target/'best_solution/node_info.txt').read_text()==info==(root/'best_solution/node_info.txt').read_text()
        snapshot.rename(output)
    grade(output,'intermediate upstream-selected submission; published run continues')
if __name__=='__main__':run(Path(sys.argv[1]).resolve())
