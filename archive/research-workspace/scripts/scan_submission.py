"""Scan intended Git content and optional evidence archive; print locations only."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'service-token': re.compile(rb'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b'),
    'literal-credential': re.compile(rb'''(?i)(?:api[_-]?key|access[_-]?token|password|authorization)\s*[:=]\s*["'](?:bearer\s+)?[A-Za-z0-9_./+=-]{20,}["']'''),
}

def scan(name, data, findings):
    for label, pattern in PATTERNS.items():
        for hit in pattern.finditer(data):
            findings.append(dict(file=name, line=data[:hit.start()].count(b'\n')+1, rule=label))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    files = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    findings = []; count = 0
    for name in sorted(set(files)-{''}):
        path = ROOT/name
        if path.is_file():
            if path.name.startswith('.env') or path.suffix == '.key':
                findings.append(dict(file=name, rule='account-config-file'))
            scan(name, path.read_bytes(), findings); count += 1
    archive_files = 0
    if args.archive:
        with zipfile.ZipFile(args.archive) as archive:
            for item in archive.infolist():
                scan(item.filename, archive.read(item), findings); archive_files += 1
    print(json.dumps(dict(candidate_files=count, attachment_files=archive_files, findings=findings), indent=2))
    raise SystemExit(bool(findings))

if __name__ == '__main__':
    main()
