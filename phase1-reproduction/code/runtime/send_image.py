"""Send only completed, hash-verified layers and unpack with OCI whiteout handling."""
import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path

here = Path(__file__).resolve().parent
root = here / 'image'
known = '/private/tmp/foreagent-autodl-17049-known-hosts'
host = 'root@connect.nmb1.seetacloud.com'
ssh = ['ssh', '-p', '17049', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'UserKnownHostsFile='+known, '-o', 'ConnectTimeout=20', '-o', 'ConnectionAttempts=3', '-o', 'ServerAliveInterval=20', '-o', 'ControlMaster=auto', '-o', 'ControlPersist=180', '-o', 'ControlPath=/private/tmp/foreagent-ctl-17049/cm']
layout = '/root/foreagent-oci'
bundle = '/root/autodl-tmp/foreagent/author-bundle'

def remote(command):
    for attempt in range(6):
        res=subprocess.run(ssh+[host,command],stdout=subprocess.PIPE,text=True)
        if res.returncode==0: return res.stdout.strip()
        if res.returncode!=255 or attempt==5: res.check_returncode()
        time.sleep(5+attempt*5)

def transfer(path, target):
    for attempt in range(4):
        res = subprocess.run(['rsync','-zt','--partial','-e',shlex.join(ssh),str(path),host+':'+target])
        if res.returncode == 0:
            return
        time.sleep(5+attempt*5)
    raise RuntimeError('rsync failed: '+str(path))

def run():
    manifest_file = root/'manifest.json'
    manifest = json.loads(manifest_file.read_text())
    manifest_bytes = manifest_file.read_bytes()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    assert digest == '451d8519af279052a9edfdd499267a2f3df5f969a8439d9192a1f9265fb5c220'
    remote(f'mkdir -p {layout}/blobs/sha256')
    for file, name in [(manifest_file,digest),(root/'config.json',manifest['config']['digest'][7:])]:
        transfer(file,layout+'/blobs/sha256/'+name)
    for name, data in [('oci-layout',{'imageLayoutVersion':'1.0.0'}), ('index.json',{'schemaVersion':2,'manifests':[{'mediaType':manifest['mediaType'],'digest':'sha256:'+digest,'size':len(manifest_bytes),'annotations':{'org.opencontainers.image.ref.name':'author'}}]})]:
        path=root/name
        path.write_text(json.dumps(data))
        transfer(path,layout+'/'+name)
    sizes = {s['digest'][7:]:s['size'] for s in manifest['layers']}
    layers = set(sizes)
    while layers:
        ready = sorted(k for k in layers if (root/k).is_file())
        if not ready:
            time.sleep(6)
            continue
        for k in ready:
            dest=layout+'/blobs/sha256/'+k
            if sizes[k]>=2**31 and (root/'large-transfer-plan.json').is_file():
                if remote(f'test -f {dest} && echo ready || echo pending')!='ready':
                    time.sleep(6)
                    continue
            else:
                transfer(root/k,dest)
            if remote('sha256sum '+dest).split()[0] != k:
                raise RuntimeError('remote checksum mismatch '+k)
            print('verified on AutoDL',k[:12],flush=True)
            layers.remove(k)
    print(remote(f'df -h /root /root/autodl-tmp; umoci unpack --rootless --image {layout}:author {bundle} && du -sh {bundle}/rootfs && df -h /root/autodl-tmp'),flush=True)

if __name__=='__main__':
    run()
