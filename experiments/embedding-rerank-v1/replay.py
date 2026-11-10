"""Recover full C0 display groups, matching all sealed decisions and unique reads."""
import argparse
import gzip
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import select
PREP = ROOT/'experiments/clean-ranking-v1/prepared'


def main(path):
    if path.exists():
        raise FileExistsError(path)
    jobs = [json.loads(row) for row in (PREP/'jobs.jsonl').read_text().splitlines()]
    manifest = ROOT/'experiments/selection-frontier-02/banks/manifest.json'
    sources = {'DS': PREP/'feedback.json', **{k:ROOT/v['path'] for k,v in json.loads(manifest.read_bytes())['banks'].items()}}
    old = ROOT/'experiments/trajectory-weighted-judge-v1/evaluation/run_1/decisions.sealed.jsonl.gz'
    with gzip.open(old,'rt') as f:
        reference = {(r['bank'],r['job_id']):r for r in map(json.loads,f) if r['arm']=='C0'}
    model = load_world()
    original = model.WorldModel.tournament_rank
    def capture(self, nodes):
        ranked, records, meta = original(self, nodes)
        capture.ranks = {i:m['rank'] for i,m in meta.items()}
        return ranked, records, meta
    model.WorldModel.tournament_rank = capture
    rows = []
    for name, source in sources.items():
        bank = json.loads(gzip.decompress(source.read_bytes()) if source.suffix=='.gz' else source.read_bytes())
        for job in jobs:
            ids = job['ids']
            top, log, stats = select(model, job, bank[job['task']], {i:i for i in ids}, 'corrected_tournament', .7)
            old = reference[name,job['job_id']]
            assert (top, log, stats) == (old['selected'],old['trace'],old['stats'])
            assert set(top) == {i for i in ids if capture.ranks[i]==0}
            rows.append(dict(bank=name, job=job['job_id'], task=job['task'], ids=ids,
                             ranks=[capture.ranks[i] for i in ids], reads=len(log)))
        print(name,len(jobs),flush=True)
    assert len(rows)==len(reference)==3400
    path.write_bytes(gzip.compress(''.join(json.dumps(r)+'\n' for r in rows).encode(),mtime=0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    main(p.parse_args().output)
