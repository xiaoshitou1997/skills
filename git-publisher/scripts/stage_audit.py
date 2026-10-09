#!/usr/bin/env python3
"""Read-only audit of the staged index; never changes Git staging."""
import pathlib
import re
import subprocess
import sys

DANGEROUS = re.compile(r'(^|/)(\.env($|\.)|id_(rsa|ed25519)|.*\.(pem|p12|pfx|key)|credentials(\.json)?$|.*secrets.*)', re.I)
SECRET = re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|(?i:aws_secret_access_key\s*[:=])')


def git(*args, text=False):
    return subprocess.run(['git', *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def audit():
    raw = git('diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR')
    paths = [p.decode('utf-8', 'surrogateescape') for p in raw.split(b'\0') if p]
    findings = []
    if not paths:
        findings.append('no staged files')
    for name in paths:
        if DANGEROUS.search(name.replace('\\', '/')):
            findings.append(f'possible sensitive path: {name}')
        data = git('show', ':' + name)
        if len(data) > 5_000_000:
            findings.append(f'large staged file: {name} ({len(data)} bytes)')
        if SECRET.search(data):
            findings.append(f'possible secret content: {name}')
    print(f'staged files: {len(paths)}')
    for item in findings:
        print('WARNING: ' + item)
    return 1 if findings else 0


if __name__ == '__main__':
    try:
        sys.exit(audit())
    except (OSError, subprocess.CalledProcessError) as e:
        print(f'failed to audit staged index: {e}', file=sys.stderr)
        sys.exit(2)
