#!/usr/bin/env python3
"""Offline engineering skills-repo structure/static validation."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SKILLS = {
    'toolchain-manager',
    'local-development',
    'docker-delivery',
    'git-publisher',
    'spring-boot-standards',
    'windows-dlp-environment',
    'engineering-doc-writer',
}

# Scripts shipped verbatim in several skills so each installs independently;
# every copy must stay byte-identical so a fix cannot silently miss a sibling.
DUPLICATE_GROUPS = [
    ['docker-delivery/scripts/doctor.py',
     'local-development/scripts/doctor.py',
     'toolchain-manager/scripts/doctor.py'],
    ['git-publisher/scripts/quality-check.sh',
     'local-development/scripts/quality-check.sh',
     'spring-boot-standards/scripts/quality-check.sh'],
    ['docker-delivery/scripts/security-scan.sh',
     'git-publisher/scripts/security-scan.sh'],
]


def validate():
    errors = []
    def error(msg): errors.append(msg)

    if (ROOT/'.claude-plugin').exists():
        error('.claude-plugin must not exist (plugin/marketplace packaging deferred)')
    found = {p.name for p in ROOT.iterdir() if p.is_dir() and (p/'SKILL.md').is_file()}
    if found != SKILLS:
        error(f'expected skills {sorted(SKILLS)}, found {sorted(found)}')
    for n in sorted(SKILLS & found):
        path = ROOT/n/'SKILL.md'
        data = path.read_text(encoding='utf-8')
        fm = re.match(r'\A---\n(.*?)\n---\n', data, re.S)
        if not fm or f'name: {n}\n' not in fm.group(1) or not re.search(r'^description:\s*\S', fm.group(1), re.M):
            error(f'Bad frontmatter: {n}')
        for ref in re.findall(r'\]\((references/[^)]+)\)', data):
            if not (path.parent/ref).is_file():
                error(f'Broken reference: {n}/{ref}')
        for ref in re.findall(r'\$\{SKILL_ROOT\}/(scripts/[\w./-]+)', data):
            if not (path.parent/ref).is_file():
                error(f'Broken script: {n}/{ref}')
        if '${SKILL_ROOT}' in data and 'SKILL_ROOT`' not in data:
            error(f'SKILL_ROOT must be documented: {n}')

    for group in DUPLICATE_GROUPS:
        if not all((ROOT/f).is_file() for f in group):
            error(f'Duplicate group incomplete: {group}')
            continue
        blobs = [(ROOT/f).read_bytes() for f in group]
        if any(b != blobs[0] for b in blobs[1:]):
            error(f'Drifted duplicate copies: {group[0]} vs {[f for f, b in zip(group, blobs) if b != blobs[0]]}')

    bash = 'bash'
    if os.name == 'nt':
        exe = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe'
        if not exe.exists():
            error('shell syntax checks skipped: Git Bash not found')
            bash = None
        else:
            bash = str(exe)
    if bash:
        for f in sorted(ROOT.rglob('*.sh')):
            with open(f, 'rb') as fh:
                p = subprocess.run([bash, '-n'], stdin=fh, capture_output=True, text=True)
            if p.returncode: error(f'Shell syntax error: {f} {p.stderr}')
    for f in sorted(ROOT.rglob('*.py')):
        p = subprocess.run([sys.executable, '-m', 'py_compile', str(f)], capture_output=True, text=True)
        if p.returncode: error(f'Python syntax error: {f} {p.stderr}')

    for e in errors: print('FAIL:', e)
    if not errors:
        print('PASS: 7 skills; frontmatter; references; Python + shell syntax')
    return int(bool(errors))


if __name__ == '__main__':
    sys.exit(validate())
