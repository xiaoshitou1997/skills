#!/usr/bin/env python3
"""build-toolchain-installer CLI.

Subcommands (all emit JSON on stdout; progress/diagnostics on stderr):
  detect     Scan project files for required versions.
  installed  List versions cached under ~/.local/sdks (+ on PATH).
  ensure     Detect + compare + download missing/mismatched + update selection.
  select     Switch the selected version for a tool (from already-installed set).
  list       Alias of `installed`, also prints the current selection.
  activate   Print a session-scoped activation snippet (sh/ps1/cmd).
  purge      Delete cached installs.

Usage examples:
  python3 scripts/runtime_cli.py detect --project .
  python3 scripts/runtime_cli.py ensure --project .
  python3 scripts/runtime_cli.py ensure --jdk 17 --maven 3.9.6 --gradle 8.5 --node 20
  python3 scripts/runtime_cli.py activate --print sh
  python3 scripts/runtime_cli.py select node 20.11.0
  python3 scripts/runtime_cli.py purge --tool node
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

# Make sibling modules importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import activate
import detect
import download
import installed as installed_mod
import mirrors
import sources
import versions
from download import sdks_root


def _emit_json(obj):
    print(json.dumps(obj, indent=2))


# --------------------------------------------------------------------------
# detect
def cmd_detect(args):
    result = detect.detect_all(Path(args.project))
    _emit_json(result)
    return result


# --------------------------------------------------------------------------
# installed / list
def cmd_list(args):
    data = installed_mod.list_installed()
    data['selection'] = activate.load_selection()
    if getattr(args, 'system', False):
        data['system'] = {
            t: installed_mod.system_version(t)
            for t in ('node', 'jdk', 'maven', 'gradle')
        }
    _emit_json(data)
    return data


# --------------------------------------------------------------------------
# ensure
def cmd_ensure(args):
    reqs = _gather_requirements(args)

    if not reqs:
        sys.stderr.write(
            'No requirements detected. Pass --node/--jdk/--maven/--gradle '
            'or --project <dir>.\n'
        )
        _emit_json({'error': 'no requirements'})
        return {'error': 'no requirements'}

    result = {'resolved': {}, 'actions': [], 'requirements': reqs}
    cache = installed_mod.list_installed()

    if 'node' in reqs:
        _ensure_node(reqs['node'], cache, result)
    if 'jdk' in reqs:
        _ensure_jdk(reqs['jdk'], cache, result)
    if 'maven' in reqs:
        _ensure_maven(reqs['maven'], cache, result)
    if 'gradle' in reqs:
        _ensure_gradle(reqs['gradle'], cache, result)

    if result['resolved']:
        activate.save_selection(result['resolved'])

    fmt = args.print or 'sh'
    snippet = ''
    if result['resolved']:
        sel = activate.load_selection()
        snippet = activate.emit(sel, fmt)
        if fmt in ('cmd', 'bat'):
            p = activate.write_cmd_file(sel)
            sys.stderr.write(f'cmd activation file -> {p}\n')
            sys.stderr.write(f'Run: call "{p}"\n')
    result['activate_format'] = fmt
    result['activate'] = snippet
    _emit_json(result)
    return result


def _gather_requirements(args):
    reqs = {}
    if args.project:
        det = detect.detect_all(Path(args.project))
        for tool in ('node', 'jdk', 'maven', 'gradle'):
            if det[tool]:
                reqs[tool] = det[tool]
    cli = {
        'node': args.node,
        'jdk': args.jdk,
        'maven': args.maven,
        'gradle': args.gradle,
    }
    for tool, val in cli.items():
        if val:
            reqs[tool] = {'source': 'cli', 'constraint': val}
    return reqs


def _ensure_node(req, cache, result):
    constraint = _constraint(req)
    try:
        exact = sources.resolve_node(constraint)
    except Exception as e:
        result['actions'].append({'tool': 'node', 'error': str(e)})
        return
    if exact is None:
        result['actions'].append(
            {'tool': 'node', 'error': f'no Node version matches {constraint!r}'}
        )
        return
    entry = installed_mod.find_matching('node', {'constraint': exact}, cache)
    if entry:
        result['resolved']['node'] = entry
        result['actions'].append(
            {'tool': 'node', 'action': 'satisfied', 'version': entry['version']}
        )
        return
    urls = sources.node_urls(exact)
    target = sdks_root() / 'node' / f'v{exact}'
    try:
        download.install_portable(urls, target, f'Node.js {exact}')
    except Exception as e:
        result['actions'].append({'tool': 'node', 'error': f'download failed: {e}', 'urls': urls})
        return
    entry = {'version': exact, 'path': str(target)}
    cache['node'].append(entry)
    result['resolved']['node'] = entry
    result['actions'].append(
        {'tool': 'node', 'action': 'installed', 'version': exact, 'urls': urls}
    )


def _ensure_jdk(req, cache, result):
    feat = _major_version(req)
    if not feat:
        result['actions'].append(
            {'tool': 'jdk', 'error': f'cannot parse JDK feature version from {_constraint(req)!r}'}
        )
        return
    entry = installed_mod.find_matching('jdk', {'constraint': feat}, cache)
    if entry:
        result['resolved']['jdk'] = entry
        result['actions'].append(
            {'tool': 'jdk', 'action': 'satisfied', 'version': entry['version']}
        )
        return
    urls = sources.jdk_urls(feat)
    target = sdks_root() / 'jdk' / f'temurin-{feat}'
    try:
        download.install_portable(urls, target, f'Temurin JDK {feat}')
    except Exception as e:
        result['actions'].append({'tool': 'jdk', 'error': f'download failed: {e}', 'urls': urls})
        return
    entry = {'version': feat, 'feature': feat, 'path': str(target)}
    cache['jdk'].append(entry)
    result['resolved']['jdk'] = entry
    result['actions'].append(
        {'tool': 'jdk', 'action': 'installed', 'version': feat, 'urls': urls}
    )


def _ensure_maven(req, cache, result):
    constraint = _constraint(req)
    try:
        exact = sources.resolve_maven(constraint)
    except Exception as e:
        result['actions'].append({'tool': 'maven', 'error': str(e)})
        return
    entry = installed_mod.find_matching('maven', {'constraint': exact}, cache)
    if entry:
        result['resolved']['maven'] = entry
        result['actions'].append(
            {'tool': 'maven', 'action': 'satisfied', 'version': entry['version']}
        )
        return
    urls = sources.maven_urls(exact)
    target = sdks_root() / 'maven' / f'apache-maven-{exact}'
    try:
        download.install_portable(urls, target, f'Apache Maven {exact}')
    except Exception as e:
        result['actions'].append({'tool': 'maven', 'error': f'download failed: {e}', 'urls': urls})
        return
    entry = {'version': exact, 'path': str(target)}
    cache['maven'].append(entry)
    result['resolved']['maven'] = entry
    result['actions'].append(
        {'tool': 'maven', 'action': 'installed', 'version': exact, 'urls': urls}
    )


def _ensure_gradle(req, cache, result):
    constraint = _constraint(req)
    try:
        exact = sources.resolve_gradle(constraint)
    except Exception as e:
        result['actions'].append({'tool': 'gradle', 'error': str(e)})
        return
    entry = installed_mod.find_matching('gradle', {'constraint': exact}, cache)
    if entry:
        result['resolved']['gradle'] = entry
        result['actions'].append(
            {'tool': 'gradle', 'action': 'satisfied', 'version': entry['version']}
        )
        return
    urls = sources.gradle_urls(exact)
    target = sdks_root() / 'gradle' / f'gradle-{exact}'
    try:
        download.install_portable(urls, target, f'Gradle {exact}')
    except Exception as e:
        result['actions'].append({'tool': 'gradle', 'error': f'download failed: {e}', 'urls': urls})
        return
    entry = {'version': exact, 'path': str(target)}
    cache['gradle'].append(entry)
    result['resolved']['gradle'] = entry
    result['actions'].append(
        {'tool': 'gradle', 'action': 'installed', 'version': exact, 'urls': urls}
    )


def _constraint(req):
    if isinstance(req, dict):
        return str(req.get('constraint', '') or '')
    return str(req or '')


def _major_version(req):
    m = re.search(r'(\d+)', _constraint(req))
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# select
def cmd_select(args):
    sel = activate.load_selection()
    cache = installed_mod.list_installed()
    if args.tool not in cache:
        _emit_json({'error': f'unknown tool {args.tool!r}'})
        return {'error': 'unknown tool'}
    match = None
    for e in cache[args.tool]:
        if args.version == e['version'] or args.version == str(e.get('feature', '')):
            match = e
            break
        if args.version in e['version']:
            match = e
            break
    if not match:
        _emit_json(
            {'error': f'{args.version!r} not installed for {args.tool!r}',
             'available': cache[args.tool]}
        )
        return {'error': 'not installed'}
    sel[args.tool] = match
    activate.save_selection(sel)
    _emit_json({'selected': {args.tool: match}})
    return {'selected': {args.tool: match}}


# --------------------------------------------------------------------------
# activate
def cmd_activate(args):
    fmt = args.print or 'auto'
    if fmt == 'auto':
        fmt = activate.detect_shell()
    sel = activate.load_selection()
    if not sel:
        _emit_json({'error': 'no selection; run `ensure` or `select` first'})
        return {'error': 'no selection'}
    snippet = activate.emit(sel, fmt)
    if fmt in ('cmd', 'bat'):
        p = activate.write_cmd_file(sel)
        sys.stderr.write(f'cmd activation file -> {p}\n')
        sys.stderr.write(f'In cmd.exe run: call "{p}"\n')
    print(snippet)
    return {'format': fmt, 'snippet': snippet}


# --------------------------------------------------------------------------
# purge
def cmd_purge(args):
    root = sdks_root()
    if args.tool:
        d = root / args.tool
        sel = activate.load_selection()
        if args.tool in sel:
            sel.pop(args.tool, None)
            activate.save_selection(sel, merge=False)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            _emit_json({'purged': str(d)})
            return {'purged': str(d)}
        _emit_json({'nothing': str(d)})
        return {'nothing': str(d)}
    sel_p = activate.selection_path()
    if sel_p.exists():
        try:
            sel_p.unlink()
        except OSError:
            pass
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
        _emit_json({'purged': str(root)})
        return {'purged': str(root)}
    _emit_json({'nothing': str(root)})
    return {'nothing': str(root)}


# --------------------------------------------------------------------------
# argparse
def build_parser():
    p = argparse.ArgumentParser(
        prog='runtime_cli.py',
        description='build-toolchain-installer: JDK/Maven/Gradle/Node portable installer',
    )
    p.add_argument(
        '--mirror', '-m', default=None, dest='mirror',
        choices=['cn', 'none'],
        help='mirror region (overrides BTC_MIRROR env). "none" disables mirror. '
             'When set, mirror URLs are prepended to the candidate list for each '
             'tool; download.install_portable pre-validates every URL with HEAD '
             'before fetching, so 404 mirrors fall through without wasting a GET.',
    )
    sub = p.add_subparsers(dest='cmd', required=True)

    pd = sub.add_parser('detect', help='Scan project files for required versions')
    pd.add_argument('--project', default='.', help='project root (default: cwd)')
    pd.set_defaults(func=cmd_detect)

    pl = sub.add_parser('list', help='List cached + selected versions')
    pl.add_argument('--project', default=None)
    pl.add_argument('--system', action='store_true', help='also probe system PATH versions')
    pl.set_defaults(func=cmd_list)
    pi = sub.add_parser('installed', help='Alias of list')
    pi.add_argument('--project', default=None)
    pi.add_argument('--system', action='store_true')
    pi.set_defaults(func=cmd_list)

    pe = sub.add_parser('ensure', help='Detect + download + select missing tools')
    pe.add_argument('--project', default=None, help='project root to scan')
    pe.add_argument('--node', default=None, help='Node.js version/constraint (e.g. 20, >=18, 20.11.0)')
    pe.add_argument('--jdk', default=None, help='JDK feature version (e.g. 17)')
    pe.add_argument('--maven', default=None, help='Apache Maven version (e.g. 3.9.6)')
    pe.add_argument('--gradle', default=None, help='Gradle version (e.g. 8.5)')
    pe.add_argument(
        '--print', default='sh',
        choices=['sh', 'ps1', 'cmd', 'auto'],
        help='activation snippet format to append to the result (default: sh)',
    )
    pe.set_defaults(func=cmd_ensure)

    ps = sub.add_parser('select', help='Switch the selected version of a tool')
    ps.add_argument('tool', choices=['node', 'jdk', 'maven', 'gradle'])
    ps.add_argument('version', help='installed version (exact or substring)')
    ps.set_defaults(func=cmd_select)

    pa = sub.add_parser('activate', help='Print a session activation snippet')
    pa.add_argument(
        '--print', default='auto',
        choices=['sh', 'ps1', 'cmd', 'auto'],
        help='shell format (default: auto-detect)',
    )
    pa.set_defaults(func=cmd_activate)

    pp = sub.add_parser('purge', help='Delete cached installs')
    pp.add_argument('--tool', default=None, choices=['node', 'jdk', 'maven', 'gradle'])
    pp.set_defaults(func=cmd_purge)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, 'mirror', None):
        if args.mirror == 'none':
            os.environ.pop('BTC_MIRROR', None)
        else:
            os.environ['BTC_MIRROR'] = args.mirror
    sys.stderr.write(f'  mirror: {mirrors.describe()}\n')
    result = args.func(args)
    if isinstance(result, dict) and result.get('error'):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
