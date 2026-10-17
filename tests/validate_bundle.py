#!/usr/bin/env python3
"""Offline engineering skills-repo structure/static validation."""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(sys.argv[1]).expanduser().resolve() if __name__ == '__main__' and len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SKILLS = {
    'mv-toolchain-manager',
    'mv-image-build',
    'mv-local-debug',
    'mv-container-deploy',
    'mv-git-publisher',
    'mv-java-backend-standards',
    'mv-tech-stack-standards',
    'mv-engineering-doc-writer',
    'mv-unattended-watch',
    'mv-nfr-intake',
}

# Scripts shipped verbatim in several skills so each installs independently;
# every copy must stay byte-identical so a fix cannot silently miss a sibling.
DUPLICATE_GROUPS = [
    ['mv-toolchain-manager/scripts/doctor.py',
     'mv-local-debug/scripts/doctor.py',
     'mv-container-deploy/scripts/doctor.py'],
    ['mv-git-publisher/scripts/quality-check.sh',
     'mv-image-build/scripts/quality-check.sh',
     'mv-java-backend-standards/scripts/quality-check.sh'],
    ['mv-git-publisher/scripts/security-scan.sh',
     'mv-image-build/scripts/security-scan.sh'],
    ['mv-image-build/scripts/wsl-bridge.sh',
     'mv-container-deploy/scripts/wsl-bridge.sh'],
    ['mv-image-build/templates/compose.delivery.yml',
     'mv-container-deploy/templates/compose.delivery.yml'],
]


def frontmatter(data):
    """Read the repository's scalar YAML fields, including folded descriptions.

    This is a repository check, not a general YAML parser. Nested optional
    metadata is left to the client's parser; name/description must be strings.
    """
    match = re.match(r'\A---\n(.*?)\n---(?:\n|$)', data, re.S)
    if not match:
        raise ValueError('missing YAML frontmatter')
    fields = {}
    lines = match.group(1).splitlines()
    for index, line in enumerate(lines):
        if not line.strip() or line.startswith('#') or line[0].isspace():
            continue
        field = re.fullmatch(r'([\w-]+):(?:[ \t]+(.*))?', line)
        if not field:
            raise ValueError('malformed frontmatter field: ' + line)
        key, value = field.group(1), field.group(2) or ''
        if key in fields:
            raise ValueError('duplicate frontmatter field: ' + key)
        if key not in ('name', 'description'):
            fields[key] = value
            continue
        if value in ('>', '>-', '>+', '|', '|-', '|+'):
            parts = []
            for continuation in lines[index + 1:]:
                if continuation and not continuation[0].isspace():
                    break
                parts.append(continuation.strip())
            value = (' ' if value.startswith('>') else '\n').join(parts).strip()
        elif value.startswith('"'):
            # YAML double-quoted strings used here share Python's common escapes.
            value = ast.literal_eval(value)
            if not isinstance(value, str):
                raise ValueError(key + ' must be a string')
        elif value.startswith("'"):
            if not re.fullmatch(r"'(?:[^']|'')*'", value):
                raise ValueError('invalid single-quoted ' + key)
            value = value[1:-1].replace("''", "'")
        else:
            if ': ' in value or value.startswith(('[', '{', '&', '*', '!', '#', '@', '`')):
                raise ValueError('quote YAML special characters in ' + key)
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
            if value.lower() in ('true', 'false', 'null', '~') or re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value):
                raise ValueError(key + ' must be a string')
        fields[key] = value
    return fields, data[match.end():]


def metadata_errors(data, directory):
    errors = []
    try:
        fields, body = frontmatter(data)
    except (ValueError, SyntaxError) as exc:
        return ['Bad frontmatter: ' + str(exc)]
    name = fields.get('name', '')
    description = fields.get('description', '')
    if not 1 <= len(name) <= 64 or not re.fullmatch(r'mv-[a-z0-9]+(?:-[a-z0-9]+)*', name):
        errors.append('name must be mv-prefixed kebab-case and at most 64 characters')
    if name != directory:
        errors.append('name must match its directory')
    if not description.strip() or len(description) > 1024:
        errors.append('description must contain 1–1024 characters')
    if re.search(r'<[^>]+>', name + description):
        errors.append('name/description must not contain XML tags')
    if len(body.splitlines()) > 500:
        errors.append('SKILL.md body exceeds repository limit of 500 lines')
    return errors


def local_link_errors(path, data, root):
    """Check file destinations, excluding fenced examples and remote links."""
    errors = []
    text = re.sub(r'^(`{3,}|~{3,}).*?^\1[^\n]*$', '', data, flags=re.M | re.S)
    for raw in re.findall(r'!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)', text):
        target = raw.strip('<>')
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        destination = (path.parent / unquote(parsed.path)).resolve()
        if not destination.is_relative_to(root.resolve()):
            errors.append('Local link escapes bundle: ' + target)
        elif not destination.exists():
            errors.append('Broken local link: ' + target)
    return errors


def validate():
    errors = []
    def error(msg): errors.append(msg)

    if (ROOT / '.claude-plugin').exists():
        error('.claude-plugin must not exist (plugin/marketplace packaging deferred)')
    found = {p.name for p in ROOT.iterdir() if p.is_dir() and (p / 'SKILL.md').is_file()}
    if found != SKILLS:
        error(f'expected skills {sorted(SKILLS)}, found {sorted(found)}')
    for name in sorted(SKILLS & found):
        path = ROOT / name / 'SKILL.md'
        data = path.read_text(encoding='utf-8')
        for message in metadata_errors(data, name):
            error(f'{name}: {message}')
        for ref in re.findall(r'\$\{SKILL_ROOT\}/(scripts/[\w./-]+)', data):
            if not (path.parent / ref).is_file():
                error(f'Broken script: {name}/{ref}')
        for ref in set(re.findall(r'`(?:\$\{SKILL_ROOT\}/)?(templates/[\w./-]+)`', data)):
            if not (path.parent / ref).is_file():
                error(f'Broken template: {name}/{ref}')
        if '${SKILL_ROOT}' in data and 'SKILL_ROOT`' not in data:
            error(f'SKILL_ROOT must be documented: {name}')

    for path in sorted(ROOT.rglob('*.md')):
        if any(part.startswith('.') for part in path.relative_to(ROOT).parts):
            continue
        for message in local_link_errors(path, path.read_text(encoding='utf-8'), ROOT):
            error(f'{path.relative_to(ROOT)}: {message}')

    for group in DUPLICATE_GROUPS:
        if not all((ROOT / f).is_file() for f in group):
            error(f'Duplicate group incomplete: {group}')
            continue
        blobs = [(ROOT / f).read_bytes() for f in group]
        if any(blob != blobs[0] for blob in blobs[1:]):
            error(f'Drifted duplicate copies: {group[0]} vs {[f for f, blob in zip(group, blobs) if blob != blobs[0]]}')

    bash = 'bash'
    if os.name == 'nt':
        exe = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe'
        if not exe.exists():
            error('shell syntax checks skipped: Git Bash not found')
            bash = None
        else:
            bash = str(exe)
    if bash:
        for path in sorted(ROOT.rglob('*.sh')):
            with path.open('rb') as fh:
                proc = subprocess.run([bash, '-n'], stdin=fh, capture_output=True, text=True)
            if proc.returncode:
                error(f'Shell syntax error: {path} {proc.stderr}')
    for path in sorted(ROOT.rglob('*.py')):
        proc = subprocess.run([sys.executable, '-m', 'py_compile', str(path)], capture_output=True, text=True)
        if proc.returncode:
            error(f'Python syntax error: {path} {proc.stderr}')

    for message in errors:
        print('FAIL:', message)
    if not errors:
        print(f'PASS: {len(SKILLS)} skills; metadata limits; local links; scripts; duplicates; Python + shell syntax')
    return int(bool(errors))


if __name__ == '__main__':
    sys.exit(validate())
