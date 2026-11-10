# 首次版本对齐与大型研究记录

2026-11-10，按用户要求，以 GitHub main `09b301dee08f52580933c36637736d0da5f8ea54` 为基点归并本地最新研究。日常提交和推送的持续授权见[根 AGENTS.md](../../AGENTS.md)。

## 发布范围

- 保留已有原版复现、HW3、历史归档及发布收据，补回远端独有的 `tests/test_archive_restore.py`。
- 纳入后续模块诊断、轻量裁判训练、整体排序与理由先导的源码、协议、结果、核验及研究交接。根目录的历史研究依赖随代码保留，实验编号与证据路径沿用原版。
- 本附件保存 30 个超过 1 MB 的新增逐场 / 编码产物与 576 个现有固定输入附件之外的本地公开来源输入，原始字节保留；其余较小源码和结果进入 Git。原始公共输入仍由 `research-env-v1` 附件恢复。
- 本地账户配置、下载数据、环境与历史工作区备份沿用忽略规则；既有标签与 Release 保持原版本。

## 下载、核对与恢复

[下载大型记录](https://github.com/skyexry/foreagent-reproduction/releases/tag/research-evidence-20261110)；逐项路径、大小及 SHA-256 见 [evidence-bundle.json](evidence-bundle.json)。附件 95,902,579 bytes，SHA-256：

```text
948bdc1276fdf65115a94f2d2c05f8f1d6fa9e78f9220ad95e8707db0b83885c
```

在仓库根目录执行：

```bash
gh release download research-evidence-20261110 --repo skyexry/foreagent-reproduction \
  --pattern research-evidence-20261110.zip --dir downloads
python3 - <<'PYVERIFY'
from pathlib import Path
import hashlib, json, zipfile
m = json.loads(Path('provenance/first-alignment-20261110/evidence-bundle.json').read_text())
p = Path('downloads') / m['asset']
assert hashlib.sha256(p.read_bytes()).hexdigest() == m['archive_sha256']
with zipfile.ZipFile(p) as z:
    assert len(z.namelist()) == len(m['files']) and set(z.namelist()) == set(m['files'])
    for name, entry in m['files'].items():
        assert hashlib.sha256(z.read(name)).hexdigest() == entry['sha256']
        target = Path(name)
        assert not target.is_absolute() and '..' not in target.parts
        if target.exists():
            assert target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == entry['sha256']
    for name in m['files']:
        if not Path(name).exists():
            z.extract(name, '.')
print('Evidence bundle verified and restored.')
PYVERIFY
```

恢复时先验证整个附件、全部条目与已有文件，再补入缺失产物。代码 / 研究摘要通过 Git 同步，附件字节通过固定版本和哈希衔接。
