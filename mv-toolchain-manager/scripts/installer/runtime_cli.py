#!/usr/bin/env python3
"""build-toolchain-installer CLI.

Subcommands (all emit JSON on stdout; progress/diagnostics on stderr):
  detect     Scan project files for required versions.
  installed  List versions cached under ~/.mv/toolchain-manager (+ on PATH).
  ensure     Detect + compare + download missing/mismatched + update selection.
  select     Switch the selected version for a tool (from already-installed set).
  list       Alias of `installed`, also prints the current selection.
  activate   Print a session-scoped activation snippet (sh/ps1/cmd).
  purge      Delete cached installs.

Usage examples:
  python3 scripts/runtime_cli.py detect --project .
  python3 scripts/runtime_cli.py ensure --project .
  python3 scripts/runtime_cli.py ensure --jdk 17 --maven 3.9.6 --gradle 8.5 --node 20
  python3 scripts/runtime_cli.py ensure --crane          # on demand, latest release
  python3 scripts/runtime_cli.py ensure --crane 0.22.1   # on demand, exact version
  python3 scripts/runtime_cli.py ensure --python         # on demand, latest CPython
  python3 scripts/runtime_cli.py ensure --python 3.12    # latest portable 3.12.x
  python3 scripts/runtime_cli.py ensure --uv 0.5.12 --node 22
  python3 scripts/runtime_cli.py ensure --pnpm 9.15.0 --node 22
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
import subprocess
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
from download import install_root


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
            for t in ('node', 'jdk', 'maven', 'gradle', 'crane', 'python',
                      'npm', 'pnpm', 'yarn', 'uv')
        }
    _emit_json(data)
    return data


# --------------------------------------------------------------------------
# ensure
def cmd_ensure(args):
    reqs = _gather_requirements(args)

    if not reqs:
        sys.stderr.write(
            'No requirements detected. Pass --node/--jdk/--maven/--gradle/--python/--uv '
            '--npm/--pnpm/--yarn/--crane '
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
    if 'crane' in reqs:
        _ensure_crane(reqs['crane'], cache, result)
    if 'python' in reqs:
        _ensure_python(reqs['python'], cache, result)
    if 'uv' in reqs:
        _ensure_uv(reqs['uv'], cache, result)
    if 'package_manager' in reqs:
        _ensure_package_manager(reqs['package_manager'], cache, result)
    if 'npm' in reqs and 'package_manager' not in reqs:
        _ensure_npm(reqs['npm'], result)
    if 'pnpm' in reqs:
        _ensure_package_manager(reqs['pnpm'], cache, result)
    if 'yarn' in reqs:
        _ensure_package_manager(reqs['yarn'], cache, result)

    # 任一工具失败都抬升为顶层 error:以退出码做门禁的调用方必须看到非零,
    # 不能让"部分成功"伪装成整体成功(已 resolved 的条目仍写入 selection)。
    errors = [a for a in result['actions'] if 'error' in a]
    if errors:
        result['error'] = '{} tool(s) failed: {}'.format(
            len(errors), '; '.join(str(a.get('error'))[:120] for a in errors))

    if result['resolved']:
        activate.save_selection(result['resolved'])

    fmt = args.print or 'sh'
    if fmt == 'auto':  # 与 cmd_activate 同口径:auto 先探测 shell,避免 emit 抛 ValueError
        fmt = activate.detect_shell()
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
        for tool in ('node', 'jdk', 'maven', 'gradle', 'python', 'uv'):
            if det[tool]:
                reqs[tool] = det[tool]
        package_manager = det.get('package_manager')
        if package_manager:
            reqs['package_manager'] = package_manager

    cli = {
        'node': args.node,
        'jdk': args.jdk,
        'maven': args.maven,
        'gradle': args.gradle,
        'crane': args.crane,
        'python': args.python,
        'uv': args.uv,
        'npm': args.npm,
        'pnpm': args.pnpm,
        'yarn': args.yarn,
    }
    for tool, val in cli.items():
        if not val:
            continue
        request = {'source': 'cli', 'tool': tool, 'constraint': val}
        if tool in ('pnpm', 'yarn'):
            reqs.pop('package_manager', None)
        reqs[tool] = request
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
    target = install_root() / 'node' / f'v{exact}'
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
    urls = []
    target = install_root() / 'jdk' / f'temurin-{feat}'
    try:
        urls = sources.jdk_urls(feat)
        download.install_portable(urls, target, f'Temurin JDK {feat}')
    except Exception as e:
        result['actions'].append({'tool': 'jdk', 'error': f'download failed: {e}',
                                  'urls': [download.display_url(u) for u in urls]})
        return
    entry = {'version': feat, 'feature': feat, 'path': str(target)}
    cache['jdk'].append(entry)
    result['resolved']['jdk'] = entry
    result['actions'].append(
        {'tool': 'jdk', 'action': 'installed', 'version': feat,
         'urls': [download.display_url(u) for u in urls]}
    )


def _ensure_maven(req, cache, result):
    if req.get('project_managed') and req.get('source') != 'cli':
        result['actions'].append({
            'tool': 'maven', 'action': 'project-managed',
            'version': _constraint(req), 'source': req.get('source'),
            'message': 'Maven Wrapper pins this project; no portable Maven was installed',
        })
        return
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
    target = install_root() / 'maven' / f'apache-maven-{exact}'
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
    if req.get('project_managed') and req.get('source') != 'cli':
        result['actions'].append({
            'tool': 'gradle', 'action': 'project-managed',
            'version': _constraint(req), 'source': req.get('source'),
            'message': 'Gradle Wrapper pins this project; no portable Gradle was installed',
        })
        return
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
    target = install_root() / 'gradle' / f'gradle-{exact}'
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


def _ensure_crane(req, cache, result):
    constraint = _constraint(req)
    try:
        exact = sources.resolve_crane(constraint)
    except Exception as e:
        result['actions'].append({'tool': 'crane', 'error': str(e)})
        return
    entry = installed_mod.find_matching('crane', {'constraint': exact}, cache)
    if entry:
        result['resolved']['crane'] = entry
        result['actions'].append(
            {'tool': 'crane', 'action': 'satisfied', 'version': entry['version']}
        )
        return
    urls = sources.crane_urls(exact)
    target = install_root() / 'crane' / f'v{exact}'
    try:
        download.install_portable(urls, target, f'crane {exact}')
    except Exception as e:
        result['actions'].append({'tool': 'crane', 'error': f'download failed: {e}',
                                  'urls': [download.display_url(u) for u in urls]})
        return
    entry = {'version': exact, 'path': str(target)}
    cache['crane'].append(entry)
    result['resolved']['crane'] = entry
    result['actions'].append(
        {'tool': 'crane', 'action': 'installed', 'version': exact,
         'urls': [download.display_url(u) for u in urls]}
    )


def _ensure_python(req, cache, result):
    constraint = _constraint(req)
    try:
        exact, tag = sources.resolve_python(constraint)
    except Exception as e:
        result['actions'].append({'tool': 'python', 'error': str(e)})
        return
    entry = installed_mod.find_matching('python', {'constraint': exact}, cache)
    if entry:
        result['resolved']['python'] = entry
        result['actions'].append(
            {'tool': 'python', 'action': 'satisfied', 'version': entry['version']}
        )
        return
    urls = sources.python_urls(exact, tag)
    target = install_root() / 'python' / f'v{exact}'
    try:
        download.install_portable(urls, target, f'CPython {exact}')
    except Exception as e:
        result['actions'].append({'tool': 'python', 'error': f'download failed: {e}',
                                  'urls': [download.display_url(u) for u in urls]})
        return
    entry = {'version': exact, 'path': str(target)}
    cache['python'].append(entry)
    result['resolved']['python'] = entry
    result['actions'].append(
        {'tool': 'python', 'action': 'installed', 'version': exact,
         'urls': [download.display_url(u) for u in urls]}
    )


def _ensure_uv(req, cache, result):
    constraint = _constraint(req)
    try:
        exact = sources.resolve_uv(constraint)
    except Exception as e:
        result['actions'].append({'tool': 'uv', 'error': str(e)})
        return
    entry = installed_mod.find_matching('uv', {'constraint': exact}, cache)
    if entry:
        result['resolved']['uv'] = entry
        result['actions'].append({'tool': 'uv', 'action': 'satisfied', 'version': entry['version']})
        return
    urls = sources.uv_urls(exact)
    target = install_root() / 'uv' / f'v{exact}'
    try:
        download.install_portable(urls, target, f'uv {exact}')
    except Exception as e:
        result['actions'].append({
            'tool': 'uv', 'error': f'download failed: {e}',
            'urls': [download.display_url(u) for u in urls],
        })
        return
    entry = {'version': exact, 'path': str(target)}
    cache['uv'].append(entry)
    result['resolved']['uv'] = entry
    result['actions'].append({
        'tool': 'uv', 'action': 'installed', 'version': exact,
        'urls': [download.display_url(u) for u in urls],
    })


def _ensure_npm(req, result):
    """npm is bundled with Node; validate, never independently download it."""
    constraint = _constraint(req)
    node = result['resolved'].get('node')
    if not node:
        result['actions'].append({
            'tool': 'npm',
            'error': 'npm is bundled with Node.js; also declare/select a Node.js runtime',
        })
        return
    npm = _node_executable(node, 'npm')
    version = _command_version([str(npm), '--version']) if npm else None
    if version is None:
        result['actions'].append({
            'tool': 'npm',
            'error': f'Node {node["version"]} does not expose a runnable bundled npm',
        })
        return
    if constraint and not versions.parse_constraint(constraint).matches(version):
        result['actions'].append({
            'tool': 'npm',
            'error': f'Node-bundled npm {version} does not satisfy {constraint!r}',
        })
        return
    entry = {'version': version, 'path': str(npm.parent), 'bundled_with': node['version']}
    result['resolved']['npm'] = entry
    result['actions'].append({
        'tool': 'npm', 'action': 'bundled', 'version': version,
        'node': node['version'],
    })


def _ensure_package_manager(req, cache, result):
    tool = req.get('tool')
    if tool == 'npm':
        _ensure_npm(req, result)
        return
    if tool not in ('pnpm', 'yarn'):
        result['actions'].append({'tool': 'package-manager', 'error': 'unknown package manager'})
        return
    if req.get('error'):
        result['actions'].append({'tool': tool, 'error': req['error'], 'source': req.get('source')})
        return
    if req.get('project_managed'):
        result['actions'].append({
            'tool': tool, 'action': 'project-managed', 'source': req.get('source'),
            'path': req.get('path'),
            'message': 'checked-in Yarn distribution will be used; no cache copy was installed',
        })
        return
    constraint = _constraint(req)
    if not versions.is_exact(constraint):
        result['actions'].append({
            'tool': tool,
            'error': f'{tool} needs an exact version; add packageManager or pass --{tool} X.Y.Z',
            'source': req.get('source'),
        })
        return
    node = result['resolved'].get('node')
    if not node:
        result['actions'].append({
            'tool': tool,
            'error': f'{tool} requires a Node.js runtime in this ensure request; declare Node or pass --node',
        })
        return
    entry = installed_mod.find_matching(tool, {'constraint': constraint}, cache)
    if entry:
        result['resolved'][tool] = entry
        result['actions'].append({'tool': tool, 'action': 'satisfied', 'version': entry['version']})
        return
    try:
        package = sources.package_manager_package(tool, constraint)
        resolved = sources.resolve_npm_package(package, constraint)
    except Exception as e:
        result['actions'].append({'tool': tool, 'error': str(e)})
        return
    target = install_root() / tool / f'v{resolved["version"]}'
    try:
        download.install_portable(
            [resolved['url']], target, f'{tool} {resolved["version"]}',
            integrity=resolved['integrity'])
        _write_package_manager_shims(tool, target)
    except Exception as e:
        result['actions'].append({
            'tool': tool, 'error': f'download failed: {e}',
            'url': download.display_url(resolved['url']),
        })
        return
    entry = {
        'version': resolved['version'], 'path': str(target),
        'package': package, 'node': node['version'],
    }
    cache[tool].append(entry)
    result['resolved'][tool] = entry
    result['actions'].append({
        'tool': tool, 'action': 'installed', 'version': resolved['version'],
        'package': package, 'url': download.display_url(resolved['url']),
    })


def _node_executable(entry, name):
    root = Path(entry['path'])
    suffix = '.cmd' if os.name == 'nt' else ''
    direct = root / f'{name}{suffix}'
    nested = root / 'bin' / name
    return direct if direct.exists() else nested


def _command_version(command):
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=15, shell=False)
    except Exception:
        return None
    return installed_mod._parse_plain_version((proc.stdout or '') + (proc.stderr or ''))


def _write_package_manager_shims(tool, target):
    """Create cache-local launchers that use the activated Node runtime.

    The package archive is data only. The wrappers do not modify project files,
    profile files, Corepack state, or global npm prefixes.
    """
    target = Path(target)
    bin_dir = target / 'bin'
    bin_dir.mkdir(exist_ok=True)
    if tool == 'pnpm':
        js = target / 'bin' / 'pnpm.cjs'
        candidates = list(target.glob('**/pnpm.cjs'))
    else:
        js = target / 'bin' / 'yarn.js'
        candidates = list(target.glob('**/yarn.js')) + list(target.glob('**/bin/yarn'))
    if not candidates:
        raise RuntimeError(f'{tool} package archive contains no supported CLI entry point')
    source = candidates[0]
    if source != js:
        shutil.copyfile(source, js)
    sh = bin_dir / tool
    sh.write_text(
        '#!/bin/sh\nexec node "$(dirname "$0")/' + js.name + '" "$@"\n',
        encoding='utf-8')
    try:
        sh.chmod(0o755)
    except OSError:
        pass
    cmd = bin_dir / f'{tool}.cmd'
    cmd.write_text('@echo off\r\nnode "%~dp0' + js.name + '" %*\r\n', encoding='ascii')


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
def _purge_guard(root):
    """Full purge refuses degenerate roots (home itself, filesystem root).

    MV_TOOLCHAIN_MANAGER_HOME legitimately redirects to any scratch/test dir,
    so only clearly dangerous targets are rejected — deleting HOME or '/'.
    """
    r = Path(root).expanduser().resolve()
    home = Path.home().resolve()
    if r == home or r.parent == r:
        raise SystemExit(
            f'refusing to purge {r}: it resolves to HOME or a filesystem root; '
            'check MV_TOOLCHAIN_MANAGER_HOME')


def cmd_purge(args):
    root = install_root()
    if args.tool:
        d = root / args.tool
        existed = d.exists()
        try:
            if existed:
                shutil.rmtree(d)
            # Only remove selection after deletion succeeds (or nothing exists).
            sel = activate.load_selection()
            if args.tool in sel:
                sel.pop(args.tool)
                activate.save_selection(sel, merge=False)
        except OSError as e:
            result = {'error': f'purge failed for {d}: {e}'}
            _emit_json(result)
            return result
        result = {'purged' if existed else 'nothing': str(d)}
        _emit_json(result)
        return result
    _purge_guard(root)
    sel_p = activate.selection_path()
    if sel_p.exists():
        try:
            sel_p.unlink()
        except OSError:
            pass
    if root.exists():
        # 不再用 ignore_errors=True 静默吞错:删不掉的文件必须如实报告并以非零退出。
        try:
            shutil.rmtree(root)
        except OSError as e:
            _emit_json({'error': f'purge failed: {e}'})
            return {'error': f'purge failed: {e}'}
        _emit_json({'purged': str(root)})
        return {'purged': str(root)}
    _emit_json({'nothing': str(root)})
    return {'nothing': str(root)}


# --------------------------------------------------------------------------
# argparse
def build_parser():
    p = argparse.ArgumentParser(
        prog='runtime_cli.py',
        description='build-toolchain-installer: portable JDK/Node/Python, JVM builders, '
                    'Node package managers, and uv',
    )
    p.add_argument(
        '--mirror', '-m', default=None, dest='mirror',
        choices=['cn', 'none'],
        help='mirror region (overrides FF_MIRROR env). "none" disables mirror. '
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
        '--crane', nargs='?', const='latest', default=None,
        help='crane version (exact) or latest; installed on demand for the '
             'mv-image-build crane path',
    )
    pe.add_argument(
        '--python', nargs='?', const='latest', default=None,
        help='CPython version/constraint (e.g. 3.12, 3.12.15) or latest; '
             'installed from python-build-standalone',
    )
    pe.add_argument(
        '--uv', nargs='?', const='latest', default=None,
        help='uv version/constraint or latest; installed from Astral official releases',
    )
    pe.add_argument(
        '--npm', nargs='?', const='latest', default=None,
        help='require bundled npm version from the selected Node runtime (never downloads npm alone)',
    )
    pe.add_argument(
        '--pnpm', default=None,
        help='exact pnpm version; installed as a cache-local npm package',
    )
    pe.add_argument(
        '--yarn', default=None,
        help='exact Yarn version; installed as a cache-local npm package',
    )
    pe.add_argument(
        '--print', default='sh',
        choices=['sh', 'ps1', 'cmd', 'auto'],
        help='activation snippet format to append to the result (default: sh)',
    )
    pe.set_defaults(func=cmd_ensure)

    ps = sub.add_parser('select', help='Switch the selected version of a tool')
    ps.add_argument('tool', choices=[
        'node', 'jdk', 'maven', 'gradle', 'crane', 'python', 'uv', 'pnpm', 'yarn',
    ])
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
    pp.add_argument('--tool', default=None,
                    choices=[
                        'node', 'jdk', 'maven', 'gradle', 'crane', 'python', 'uv',
                        'pnpm', 'yarn',
                    ])
    pp.set_defaults(func=cmd_purge)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, 'mirror', None):
        if args.mirror == 'none':
            os.environ.pop('FF_MIRROR', None)
        else:
            os.environ['FF_MIRROR'] = args.mirror
    sys.stderr.write(f'  mirror: {mirrors.describe()}\n')
    result = args.func(args)
    if isinstance(result, dict) and result.get('error'):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
