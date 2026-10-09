"""Minimal semver parsing + constraint matching. Stdlib only.

Supports npm-style ranges used by Node.js `engines.node`, and major/exact
matching for JDK / Maven / Gradle.
"""
from __future__ import annotations
import re

_VERSION_RE = re.compile(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?')

# Node majors that are/have been LTS (for 'lts' preference).
NODE_LTS_MAJORS = {22, 20, 18, 16, 14, 12, 10, 8, 6, 4}


def parse_version(v):
    """Parse 'v20.11.0' / '20.11' -> (20, 11, 0). Returns None on failure."""
    if v is None:
        return None
    s = str(v).strip().lstrip('vV')
    m = _VERSION_RE.match(s)
    if not m:
        return None
    parts = [int(m.group(i)) if m.group(i) else 0 for i in range(1, 5)]
    return tuple(parts[:3])


def _cmp(a, b):
    for i in range(3):
        x = a[i] if i < len(a) else 0
        y = b[i] if i < len(b) else 0
        if x != y:
            return -1 if x < y else 1
    return 0


def compare(a, b):
    """Compare two version strings/tuples. Returns -1/0/1."""
    ta = parse_version(a) if isinstance(a, str) else a
    tb = parse_version(b) if isinstance(b, str) else b
    if ta is None or tb is None:
        return 0
    return _cmp(ta, tb)


def _parse_token(tok):
    """Parse one comparator token -> list of (op, tuple)."""
    tok = tok.strip()
    if not tok or tok in ('*', 'x', 'X', 'latest', 'any'):
        return [('>=', (0, 0, 0))]
    m = re.match(r'^(\^|~|>=|<=|==|=|>|<)?\s*v?(\S+)$', tok)
    if not m:
        return []
    op = m.group(1) or '='
    op = '=' if op == '==' else op
    ver_str = m.group(2)
    v = parse_version(ver_str)
    if v is None:
        return []
    dots = ver_str.count('.')
    if op == '=' and dots == 0:
        # major only: treat as >=major, <major+1
        return [('>=', v), ('<', (v[0] + 1, 0, 0))]
    if op == '=' and dots == 1:
        # major.minor: >=X.Y.0, <X.(Y+1).0
        return [('>=', v), ('<', (v[0], v[1] + 1, 0))]
    return [(op, v)]


def parse_constraint(expr):
    """Parse an npm-style constraint string. Returns an object with .matches(version)."""
    expr = (expr or '').strip()
    if not expr or expr in ('*', 'any', 'latest'):
        return _All()
    if expr.lower() == 'lts':
        return _Lts()
    if '||' in expr:
        return _Or([parse_constraint(p) for p in expr.split('||')])
    comps = []
    for tok in expr.split():
        comps.extend(_parse_token(tok))
    if not comps:
        return _All()
    return _And(comps)


def is_exact(version):
    """True if the string looks like an exact X.Y.Z version."""
    return bool(re.match(r'^\d+\.\d+\.\d+$', str(version).strip()))


def is_lts_major(major):
    return int(major) in NODE_LTS_MAJORS


class _All:
    def matches(self, version):
        return True

    def __repr__(self):
        return '*'


class _Lts:
    def matches(self, version):
        v = parse_version(version) if isinstance(version, str) else version
        return v is not None and is_lts_major(v[0])

    def __repr__(self):
        return 'lts'


class _And:
    def __init__(self, comps):
        self.comps = comps

    def matches(self, version):
        v = parse_version(version) if isinstance(version, str) else version
        if v is None:
            return False
        for op, target in self.comps:
            if not _check(v, op, target):
                return False
        return True

    def __repr__(self):
        return ' '.join(f'{op}{".".join(map(str, t))}' for op, t in self.comps)


class _Or:
    def __init__(self, alts):
        self.alts = alts

    def matches(self, version):
        return any(a.matches(version) for a in self.alts)

    def __repr__(self):
        return ' || '.join(repr(a) for a in self.alts)


def _check(v, op, target):
    c = _cmp(v, target)
    if op == '>=':
        return c >= 0
    if op == '<=':
        return c <= 0
    if op == '>':
        return c > 0
    if op == '<':
        return c < 0
    if op == '=':
        return c == 0
    if op == '^':
        if c < 0:
            return False
        return _cmp(v, (target[0] + 1, 0, 0)) < 0
    if op == '~':
        if c < 0:
            return False
        return _cmp(v, (target[0], target[1] + 1, 0)) < 0
    return False


if __name__ == '__main__':
    # quick self-test
    tests = [
        ('>=18', '20.11.0', True),
        ('>=18', '16.0.0', False),
        ('^20', '20.11.0', True),
        ('^20', '21.0.0', False),
        ('~20.11', '20.11.5', True),
        ('~20.11', '20.12.0', False),
        ('18', '18.19.0', True),
        ('18', '19.0.0', False),
        ('>=14 <18', '16.20.0', True),
        ('>=14 <18', '18.0.0', False),
        ('20.11.0', '20.11.0', True),
        ('20.11.0', '20.11.1', False),
    ]
    ok = True
    for expr, ver, expected in tests:
        got = parse_constraint(expr).matches(ver)
        flag = 'OK' if got == expected else 'FAIL'
        if got != expected:
            ok = False
        print(f'  [{flag}] {expr!r}.matches({ver!r}) = {got} (want {expected})')
    print('all-pass' if ok else 'FAILURES')
