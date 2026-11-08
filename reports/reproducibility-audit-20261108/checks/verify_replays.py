import json,os,subprocess,sys,tempfile,shutil,hashlib
from pathlib import Path
root=Path(sys.argv[1]).resolve();out=Path(tempfile.mkdtemp(prefix='foreagent-audit-replay-'));print(out,flush=True)
def cp(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
def call(args,folder,name):
 env=dict(os.environ,FOREAGENT_RUN_DIR=str(folder),PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0')
 with (folder/(name+'.log')).open('w') as f:subprocess.run([sys.executable,*args],cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 print(name,'passed',flush=True)
h=out/'historical';h.mkdir();v=root/'vendor/foreagent_upstream/mle-bench/agents/aide/aide'
for name in ('world_model','agent'):cp(v/(name+'.py'),h/(name+'_original.py'))
cp(root/'experiments/historical-v1/source_manifest.json',h/'source_manifest.json');(h/'source_records').symlink_to(root/'data/historical/source_records',target_is_directory=True)
call(['reproduction/historical/replay_author.py'],h,'historical');call(['reproduction/historical/verify_and_report.py'],h,'historical-verify')
p=out/'pairwise';p.mkdir();call(['scripts/verify_pairwise.py'],p,'pairwise')
c=out/'corpus';c.mkdir();cp(v/'world_model.py',c/'world_model_original.py');cp(root/'vendor/foreagent_variants/world_model_cache_direction_canonical.py',c/'world_model_cache_fixed.py')
for name in ('protocol.json','v2_spec.json'):cp(root/'experiments/corpus26-v2'/name,c/name)
for variant in ('original','cache-fixed'):
 cp(c/'protocol.json',c/variant/'protocol.json');call(['reproduction/corpus/replay_full.py','--variant',variant],c,'corpus-'+variant)
call(['reproduction/corpus/verify_replay.py'],c,'corpus-verify')
receipt={'directory':str(out),'historical':json.loads((h/'summary.json').read_text()),'pairwise':json.loads((p/'verification.json').read_text()),'corpus_original':json.loads((c/'original/results.json').read_text()),'corpus_cache_fixed':json.loads((c/'cache-fixed/results.json').read_text())}
Path(sys.argv[2]).write_text(json.dumps(receipt,indent=2)+'\n');print('wrote',sys.argv[2],flush=True)
