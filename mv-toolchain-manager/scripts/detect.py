#!/usr/bin/env python3
"""Read-only project toolchain detector; never installs or mutates the system."""
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET


def sniff(project):
    project = pathlib.Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError('project directory not found')
    found = {}
    for fn in ('.nvmrc', '.node-version', '.java-version', '.python-version',
               '.tool-versions', '.mise.toml', '.yarnrc.yml'):
        path = project / fn
        if path.exists():
            found[fn] = path.read_text(encoding='utf-8', errors='replace').strip()[:4000]
    pkg = project / 'package.json'
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            data = None  # 单来源损坏只跳过该来源,不中断其余检测
        if data is not None:
            found['node'] = {'engines': data.get('engines', {}), 'packageManager': data.get('packageManager')}
    pyproject = project / 'pyproject.toml'
    if pyproject.exists():
        text = pyproject.read_text(encoding='utf-8', errors='replace')
        requires = re.search(r'^\s*requires-python\s*=\s*["\']([^"\']+)', text, re.M)
        found['python'] = {
            'requires-python': requires.group(1) if requires else None,
            'tool.uv': bool(re.search(r'^\s*\[tool\.uv\]', text, re.M)),
        }
    if (project / 'uv.lock').exists():
        found['uv.lock'] = True
    yarn_releases = project / '.yarn' / 'releases'
    if yarn_releases.is_dir():
        found['yarn_release'] = [p.name for p in sorted(yarn_releases.glob('yarn-*.cjs'))]

    pom = project / 'pom.xml'
    if pom.exists():
        try:
            # ET.parse 相比 fromstring(read_text) 能正确处理带 UTF-8 BOM 的 pom
            root = ET.parse(pom).getroot()
        except (OSError, ET.ParseError):
            root = None  # 损坏的 pom 同样只跳过该来源
        if root is not None:
            properties = root.find('{*}properties')
            if properties is not None:
                vals = {child.tag.rsplit('}', 1)[-1]: (child.text or '').strip() for child in properties}
                found['maven_java'] = {k: vals[k] for k in ('java.version', 'maven.compiler.release', 'maven.compiler.source', 'maven.compiler.target') if k in vals}
    for tool, rel in [('gradle', 'gradle/wrapper/gradle-wrapper.properties'), ('maven', '.mvn/wrapper/maven-wrapper.properties')]:
        path = project / rel
        if path.exists():
            text = path.read_text(encoding='utf-8', errors='replace')
            m = re.search(r'^distributionUrl\s*=\s*(.+)', text, re.M)
            found[tool + '_wrapper'] = m.group(1).strip() if m else 'present'
    found['lockfiles'] = [p.name for p in (project / 'pnpm-lock.yaml', project / 'yarn.lock', project / 'package-lock.json') if p.exists()]
    return found


if __name__ == '__main__':
    try:
        print(json.dumps(sniff(sys.argv[1] if len(sys.argv) > 1 else '.'), ensure_ascii=False, indent=2))
    except (ValueError, OSError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f'toolchain detection failed: {exc}', file=sys.stderr)
        sys.exit(2)
