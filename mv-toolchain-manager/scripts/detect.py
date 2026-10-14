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
    for fn in ('.nvmrc', '.node-version', '.java-version', '.tool-versions', '.mise.toml'):
        path = project / fn
        if path.exists():
            found[fn] = path.read_text(encoding='utf-8', errors='replace').strip()[:4000]
    pkg = project / 'package.json'
    if pkg.exists():
        data = json.loads(pkg.read_text(encoding='utf-8'))
        found['node'] = {'engines': data.get('engines', {}), 'packageManager': data.get('packageManager')}
    pom = project / 'pom.xml'
    if pom.exists():
        root = ET.fromstring(pom.read_text(encoding='utf-8'))
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
