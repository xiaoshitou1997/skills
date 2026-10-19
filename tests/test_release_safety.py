"""发布安全针对性回归：仅离线 mock、临时工具缓存与临时值守状态。"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'mv-toolchain-manager/scripts/installer'))
import activate
import detect as installer_detect
import download
import installed as installed_mod
import runtime_cli
import sources

_spec = importlib.util.spec_from_file_location(
    'release_safety_gate', ROOT / 'mv-unattended-watch/scripts/gate.py')
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def signed_url(filename):
    return 'https://release-assets.githubusercontent.com/opaque-id?' + urllib.parse.urlencode({
        'sig': 'offline-test',
        'response-content-disposition': f'attachment; filename="{filename}"',
    })


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        # 默认封死联网；需要响应体的用例仅替换为内存响应。
        self.addCleanup(mock.patch.stopall)
        mock.patch('urllib.request.urlopen', side_effect=AssertionError('unexpected network')).start()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))
        self.enterContext(contextlib.redirect_stderr(self.stderr))


class JdkArchiveTests(OfflineTestCase):
    def metadata(self, filename, url=None):
        return [{'binary': {'package': {
            'name': filename,
            'link': url or 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21/' + filename,
        }}}]

    def test_official_assets_resolve_portable_archive_for_each_platform(self):
        for os_name, arch, api_arch, ext in (
                ('windows', 'x64', 'x64', '.zip'),
                ('linux', 'arm64', 'aarch64', '.tar.gz'),
                ('mac', 'arm64', 'aarch64', '.tar.gz')):
            with self.subTest(os=os_name):
                filename = f'OpenJDK21U-jdk_{api_arch}_{os_name}_hotspot_21.0.11_10{ext}'
                metadata = self.metadata(filename)
                with mock.patch.object(download, 'os_name', return_value=os_name), \
                        mock.patch.object(download, 'arch', return_value=arch), \
                        mock.patch.dict(os.environ, {'FF_MIRROR': ''}), \
                        mock.patch.object(sources, '_get_json', return_value=metadata) as get:
                    urls = sources.jdk_urls('21')
                self.assertEqual(urls, [metadata[0]['binary']['package']['link']])
                self.assertTrue(download.validate_archive_url(urls[0]))
                api = urllib.parse.urlsplit(get.call_args.args[0])
                self.assertEqual(api.path, '/v3/assets/latest/21/hotspot')
                query = urllib.parse.parse_qs(api.query)
                self.assertEqual(query['architecture'], [api_arch])
                self.assertEqual(query['os'], [os_name])
                self.assertEqual(query['image_type'], ['jdk'])
                self.assertEqual(query['vendor'], ['eclipse'])

    def test_mirror_opt_in_uses_same_portable_filename_then_official(self):
        filename = 'OpenJDK21U-jdk_aarch64_mac_hotspot_21.0.11_10.tar.gz'
        metadata = self.metadata(filename)
        with mock.patch.object(download, 'os_name', return_value='mac'), \
                mock.patch.object(download, 'arch', return_value='arm64'), \
                mock.patch.dict(os.environ, {'FF_MIRROR': 'cn'}), \
                mock.patch.object(sources, '_get_json', return_value=metadata) as get:
            urls = sources.jdk_urls('21')
        self.assertEqual(len(urls), 2)
        self.assertTrue(urls[0].startswith('https://mirrors.tuna.tsinghua.edu.cn/'))
        self.assertTrue(urls[0].endswith('/' + filename))
        self.assertEqual(urls[1], metadata[0]['binary']['package']['link'])
        self.assertEqual(get.call_count, 1)

    def test_signed_official_asset_uses_disposition_for_mirror_and_cache(self):
        filename = 'OpenJDK21U-jdk_x64_windows_hotspot_21.0.11_10.zip'
        url = signed_url(filename)
        with mock.patch.object(download, 'os_name', return_value='windows'), \
                mock.patch.object(download, 'arch', return_value='x64'), \
                mock.patch.dict(os.environ, {'FF_MIRROR': 'cn'}), \
                mock.patch.object(sources, '_get_json', return_value=self.metadata(filename, url)):
            urls = sources.jdk_urls('21')
        self.assertTrue(urls[0].endswith('/' + filename))
        self.assertEqual(urls[1], url)
        self.assertEqual(download.archive_filename(url), filename)

    def test_metadata_rejects_installers_and_mismatched_names(self):
        for filename, link in (
                ('jdk.msi', 'https://example.com/jdk.msi'),
                ('jdk.zip', 'https://example.com/jdk.msi'),
                ('jdk.zip', 'https://example.com/different.zip'),
                ('jdk.tar.gz', 'https://example.com/jdk.tar.gz')):
            with self.subTest(filename=filename, link=link), \
                    mock.patch.object(download, 'os_name', return_value='windows'), \
                    mock.patch.object(download, 'arch', return_value='x64'), \
                    mock.patch.object(sources, '_get_json', return_value=self.metadata(filename, link)):
                with self.assertRaises(RuntimeError):
                    sources.jdk_urls('21')

    def test_jdk_resolution_failure_is_nonzero_json_error(self):
        with mock.patch.dict(os.environ, {'MV_TOOLCHAIN_MANAGER_HOME': str(self.base / 'tools')}), \
                mock.patch.object(sources, '_get_json', side_effect=OSError('offline')):
            code = runtime_cli.main(['ensure', '--jdk', '21'])
        self.assertEqual(code, 1)
        result = json.loads(self.stdout.getvalue())
        self.assertIn('error', result)
        self.assertEqual(result['resolved'], {})
        self.assertFalse((self.base / 'tools/selection.json').exists())

    def test_cached_jdk_needs_no_metadata_or_download(self):
        target = self.base / 'tools/jdk/temurin-21'
        target.mkdir(parents=True)
        (target / 'release').write_text('test cache', encoding='utf-8')
        with mock.patch.dict(os.environ, {'MV_TOOLCHAIN_MANAGER_HOME': str(self.base / 'tools')}), \
                mock.patch.object(sources, '_get_json', side_effect=AssertionError('metadata for cached tool')):
            self.assertEqual(runtime_cli.main(['ensure', '--jdk', '21']), 0)
        self.assertEqual(json.loads(self.stdout.getvalue())['actions'][0]['action'], 'satisfied')


class DownloadArchiveTests(OfflineTestCase):
    def test_signed_filename_formats_preserve_extensions_and_plus(self):
        for name in ('jdk+21.zip', 'jdk+21.tar.gz', 'jdk.tgz'):
            with self.subTest(name=name):
                self.assertEqual(download.archive_filename(signed_url(name)), name)
                self.assertTrue(download.validate_archive_url(signed_url(name)))
        extended = 'https://example.com/opaque?' + urllib.parse.urlencode({
            'response-content-disposition': "attachment; filename*=UTF-8''jdk%2B21.tar.gz"})
        self.assertEqual(download.archive_filename(extended), 'jdk+21.tar.gz')

    def test_installer_and_unsafe_names_blocked_before_network(self):
        urls = [
            'https://example.com/jdk.exe',
            'https://example.com/jdk%2Emsi',
            'https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse',
            'https://example.com/jdk.exe?' + urllib.parse.urlencode({
                'response-content-disposition': 'attachment; filename=jdk.zip'}),
        ]
        urls += [signed_url(name) for name in (
            'jdk.exe', 'jdk.msi', 'jdk.pkg', 'jdk.dmg', '../jdk.zip',
            '..\\jdk.zip', 'C:\\jdk.zip', 'jdk.zip:stream', 'jdk\n.zip')]
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    download.download(url, self.base / 'archive.zip', show_progress=False)
        self.assertEqual(list(self.base.iterdir()), [])

    def test_signed_install_uses_real_filename_for_checksum_and_extraction(self):
        filename = 'OpenJDK21U-jdk_x64_windows_hotspot_21.zip'
        url = signed_url(filename)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('jdk-21/bin/java.txt', 'offline fixture')
        payload = stream.getvalue()
        response = io.BytesIO(payload)
        response.headers = {'Content-Length': str(len(payload))}
        response.geturl = lambda: url
        checksum = hashlib.sha256(payload).hexdigest() + '  ' + filename
        target = self.base / 'jdk/temurin-21'
        with mock.patch.object(download, 'probe_url', return_value=len(payload)), \
                mock.patch('urllib.request.urlopen', return_value=response), \
                mock.patch.object(download, '_fetch_checksum_text', return_value=checksum):
            installed, status = download.install_portable([url], target, 'test JDK')
        self.assertEqual((installed, status), (target, 'installed'))
        self.assertEqual((target / 'bin/java.txt').read_text(encoding='utf-8'), 'offline fixture')
        self.assertIn('checksum OK', self.stderr.getvalue())
        self.assertNotIn('offline-test', self.stderr.getvalue())
        self.assertIn('<redacted>', self.stderr.getvalue())
        # 缓存命中不能再探测网络，也不能重新解析签名链接。
        with mock.patch.object(download, 'probe_url', side_effect=AssertionError('probe for cache')):
            self.assertEqual(download.install_portable([url], target, 'test JDK'), (target, 'cached'))

    def test_tar_gz_install_preserves_format_for_linux_and_mac(self):
        for os_name in ('linux', 'mac'):
            with self.subTest(os=os_name):
                filename = f'OpenJDK21U-jdk_x64_{os_name}_hotspot_21.tar.gz'
                url = signed_url(filename)
                stream = io.BytesIO()
                payload_file = b'offline tar fixture'
                with tarfile.open(fileobj=stream, mode='w:gz') as archive:
                    info = tarfile.TarInfo('jdk-21/bin/java.txt')
                    info.size = len(payload_file)
                    archive.addfile(info, io.BytesIO(payload_file))
                payload = stream.getvalue()
                response = io.BytesIO(payload)
                response.headers = {'Content-Length': str(len(payload))}
                response.geturl = lambda: url
                checksum = hashlib.sha256(payload).hexdigest() + '  ' + filename
                target = self.base / os_name / 'temurin-21'
                with mock.patch.object(download, 'probe_url', return_value=len(payload)), \
                        mock.patch('urllib.request.urlopen', return_value=response), \
                        mock.patch.object(download, '_fetch_checksum_text', return_value=checksum):
                    self.assertEqual(download.install_portable(url, target, 'JDK tar'),
                                     (target, 'installed'))
                self.assertEqual((target / 'bin/java.txt').read_bytes(), payload_file)

    def test_content_disposition_without_filename_uses_url_name(self):
        self.assertEqual(download.archive_filename(
            'https://example.com/jdk.zip', 'attachment'), 'jdk.zip')
        self.assertEqual(download.archive_filename(
            signed_url('jdk.zip'), 'attachment'), 'jdk.zip')

    def test_probe_rejects_redirect_to_installer(self):
        response = mock.MagicMock()
        response.status = 200
        response.headers = {}
        response.geturl.return_value = 'https://example.com/jdk.msi'
        response.__enter__.return_value = response
        with mock.patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(ValueError):
                download.probe_url('https://example.com/jdk.zip')

    def test_download_rejects_redirect_to_installer_before_reading(self):
        response = mock.MagicMock()
        response.headers = {}
        response.geturl.return_value = signed_url('jdk.exe')
        response.__enter__.return_value = response
        with mock.patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(ValueError):
                download.download('https://example.com/jdk.zip', self.base / 'jdk.zip', False)
        response.read.assert_not_called()
        self.assertFalse((self.base / 'jdk.zip').exists())

    def test_checksum_mismatch_stops_without_fallback(self):
        urls = ['https://example.com/first.zip', 'https://example.com/second.zip']
        def fetch(url, path):
            path.write_bytes(b'archive fixture')
        with mock.patch.object(download, 'probe_url', return_value=10), \
                mock.patch.object(download, 'download', side_effect=fetch) as get, \
                mock.patch.object(download, '_fetch_checksum_text', return_value='0' * 64), \
                mock.patch.object(download, 'extract') as extract:
            with self.assertRaises(download.ChecksumMismatch):
                download.install_portable(urls, self.base / 'target', 'fixture')
        self.assertEqual(get.call_count, 1)
        extract.assert_not_called()
        self.assertFalse((self.base / 'target').exists())

    def test_missing_checksum_warns(self):
        archive = self.base / 'jdk.zip'
        archive.write_bytes(b'fixture')
        with mock.patch.object(download, '_fetch_checksum_text', side_effect=OSError('not published')):
            download.verify_download('https://example.com/jdk.zip', archive)
        self.assertIn('no published checksum', self.stderr.getvalue())


class CraneInstallerTests(OfflineTestCase):
    def test_crane_urls_follow_release_asset_names(self):
        for os_name, arch, asset_os, asset_arch in (
                ('windows', 'x64', 'Windows', 'x86_64'),
                ('linux', 'arm64', 'Linux', 'arm64'),
                ('mac', 'x64', 'Darwin', 'x86_64')):
            with self.subTest(os=os_name):
                with mock.patch.object(download, 'os_name', return_value=os_name), \
                        mock.patch.object(download, 'arch', return_value=arch):
                    urls = sources.crane_urls('0.22.1')
                self.assertEqual(urls, [
                    'https://github.com/google/go-containerregistry/releases/download/'
                    f'v0.22.1/go-containerregistry_{asset_os}_{asset_arch}.tar.gz'
                ])
                self.assertTrue(download.validate_archive_url(urls[0]))

    def test_crane_exact_version_does_not_touch_network(self):
        with mock.patch.object(sources, '_final_url',
                               side_effect=AssertionError('unexpected network')):
            self.assertEqual(sources.resolve_crane('0.22.1'), '0.22.1')
            self.assertEqual(sources.resolve_crane('v0.22.1'), '0.22.1')

    def test_crane_latest_resolves_from_release_redirect(self):
        with mock.patch.object(
                sources, '_final_url',
                return_value='https://github.com/google/go-containerregistry/'
                             'releases/tag/v0.22.1'):
            self.assertEqual(sources.resolve_crane('latest'), '0.22.1')
            self.assertEqual(sources.resolve_crane(''), '0.22.1')
            self.assertEqual(sources.resolve_crane('>=0.20'), '0.22.1')

    def test_crane_release_publishes_checksums_txt(self):
        url = ('https://github.com/google/go-containerregistry/releases/download/'
               'v0.22.1/go-containerregistry_Windows_x86_64.tar.gz')
        self.assertIn(
            'https://github.com/google/go-containerregistry/releases/download/'
            'v0.22.1/checksums.txt',
            download._checksum_candidates(url))

    def test_crane_activation_prepends_archive_root(self):
        sel = {'crane': {'version': '0.22.1', 'path': '/tools/crane/v0.22.1'}}
        with mock.patch.object(activate, 'os_name', return_value='linux'):
            self.assertIn('export PATH="/tools/crane/v0.22.1:$PATH"',
                          activate.emit(sel, 'sh'))
            self.assertIn('$env:PATH = "\\tools\\crane\\v0.22.1;$env:PATH"',
                          activate.emit(sel, 'ps1'))
            self.assertIn('set "PATH=\\tools\\crane\\v0.22.1;%PATH%"',
                          activate.emit(sel, 'cmd'))

    def test_ensure_installs_crane_on_demand(self):
        root = self.base / 'tools'
        target = root / 'crane' / 'v0.22.1'

        def fake_install(urls, dest, label):
            dest.mkdir(parents=True)
            (dest / 'crane.exe').write_text('', encoding='utf-8')
            return dest, 'installed'

        with mock.patch.dict(os.environ,
                             {'MV_TOOLCHAIN_MANAGER_HOME': str(root)}), \
                mock.patch.object(
                    sources, '_final_url',
                    return_value='https://github.com/google/go-containerregistry/'
                                 'releases/tag/v0.22.1'), \
                mock.patch.object(activate, 'os_name', return_value='linux'), \
                mock.patch.object(download, 'install_portable',
                                  side_effect=fake_install) as install:
            code = runtime_cli.main(['ensure', '--crane', '--print', 'sh'])
        self.assertEqual(code, 0)
        install.assert_called_once()
        result = json.loads(self.stdout.getvalue())
        self.assertEqual(result['resolved']['crane']['version'], '0.22.1')
        self.assertIn(str(target), result['activate'])
        selection = json.loads((root / 'selection.json').read_text(encoding='utf-8'))
        self.assertEqual(selection['crane']['version'], '0.22.1')

    def test_crane_is_discovered_from_install_root(self):
        root = self.base / 'tools'
        (root / 'crane' / 'v0.22.1').mkdir(parents=True)
        with mock.patch.dict(os.environ,
                             {'MV_TOOLCHAIN_MANAGER_HOME': str(root)}):
            listed = installed_mod.list_installed()
            entry = installed_mod.find_matching(
                'crane', {'constraint': '0.22.1'}, listed)
        self.assertEqual(entry['version'], '0.22.1')
        self.assertEqual(entry['path'], str(root / 'crane' / 'v0.22.1'))


class PythonInstallerTests(OfflineTestCase):
    SUMS = '\n'.join([
        'a' * 64 + '  cpython-3.11.17+20261013-x86_64-pc-windows-msvc-install_only.tar.gz',
        'b' * 64 + '  cpython-3.12.15+20261013-x86_64-pc-windows-msvc-install_only.tar.gz',
        'c' * 64 + '  cpython-3.13.16+20261013-x86_64-pc-windows-msvc-install_only.tar.gz',
        'd' * 64 + '  cpython-3.16.0a1+20261013-x86_64-pc-windows-msvc-install_only.tar.gz',
        'e' * 64 + '  cpython-3.12.15+20261013-x86_64-unknown-linux-gnu-install_only.tar.gz',
    ])

    def test_python_urls_follow_python_build_standalone_assets(self):
        for os_name, arch, triple in (
                ('windows', 'x64', 'x86_64-pc-windows-msvc'),
                ('windows', 'arm64', 'aarch64-pc-windows-msvc'),
                ('linux', 'x64', 'x86_64-unknown-linux-gnu'),
                ('linux', 'arm64', 'aarch64-unknown-linux-gnu'),
                ('mac', 'x64', 'x86_64-apple-darwin'),
                ('mac', 'arm64', 'aarch64-apple-darwin')):
            with self.subTest(os=os_name, arch=arch):
                with mock.patch.object(download, 'os_name', return_value=os_name), \
                        mock.patch.object(download, 'arch', return_value=arch):
                    urls = sources.python_urls('3.12.15', '20261013')
                self.assertEqual(urls, [
                    'https://github.com/astral-sh/python-build-standalone/'
                    'releases/download/20261013/'
                    f'cpython-3.12.15+20261013-{triple}-install_only.tar.gz'
                ])
                self.assertTrue(download.validate_archive_url(urls[0]))

    def test_resolve_python_picks_highest_stable_match(self):
        with mock.patch.object(
                sources, '_final_url',
                return_value='https://github.com/astral-sh/python-build-standalone/'
                             'releases/tag/20261013'), \
                mock.patch.object(sources, '_get_text', return_value=self.SUMS), \
                mock.patch.object(download, 'os_name', return_value='windows'), \
                mock.patch.object(download, 'arch', return_value='x64'):
            self.assertEqual(sources.resolve_python(''), ('3.13.16', '20261013'))
            self.assertEqual(sources.resolve_python('3.12'), ('3.12.15', '20261013'))
            self.assertEqual(sources.resolve_python('3.12.15'), ('3.12.15', '20261013'))
            with self.assertRaises(RuntimeError):
                sources.resolve_python('3.99')

    def test_python_release_publishes_sha256sums(self):
        url = ('https://github.com/astral-sh/python-build-standalone/releases/'
               'download/20261013/'
               'cpython-3.12.15+20261013-x86_64-pc-windows-msvc-install_only.tar.gz')
        self.assertIn(
            'https://github.com/astral-sh/python-build-standalone/releases/'
            'download/20261013/SHA256SUMS',
            download._checksum_candidates(url))

    def test_python_activation_prepends_bin(self):
        sel = {'python': {'version': '3.12.15', 'path': '/tools/python/v3.12.15'}}
        unix_bin = os.path.join('/tools/python/v3.12.15', 'bin')
        win_root = '/tools/python/v3.12.15'
        with mock.patch.object(activate, 'os_name', return_value='linux'):
            self.assertIn(f'export PATH="{unix_bin}:$PATH"', activate.emit(sel, 'sh'))
            self.assertIn(
                '$env:PATH = "' + unix_bin.replace('/', '\\') + ';$env:PATH"',
                activate.emit(sel, 'ps1'))
        with mock.patch.object(activate, 'os_name', return_value='windows'):
            self.assertIn(f'export PATH="{win_root}:$PATH"', activate.emit(sel, 'sh'))
            self.assertIn(
                '$env:PATH = "' + win_root.replace('/', '\\') + ';$env:PATH"',
                activate.emit(sel, 'ps1'))

    def test_python_is_discovered_from_install_root(self):
        root = self.base / 'tools'
        (root / 'python' / 'v3.12.15').mkdir(parents=True)
        with mock.patch.dict(os.environ,
                             {'MV_TOOLCHAIN_MANAGER_HOME': str(root)}):
            listed = installed_mod.list_installed()
            entry = installed_mod.find_matching(
                'python', {'constraint': '3.12.15'}, listed)
        self.assertEqual(entry['version'], '3.12.15')
        self.assertEqual(entry['path'], str(root / 'python' / 'v3.12.15'))

    def test_ensure_installs_python_on_demand(self):
        root = self.base / 'tools'
        target = root / 'python' / 'v3.12.15'

        def fake_install(urls, dest, label):
            dest.mkdir(parents=True)
            (dest / 'python.exe').write_text('', encoding='utf-8')
            return dest, 'installed'

        with mock.patch.dict(os.environ,
                             {'MV_TOOLCHAIN_MANAGER_HOME': str(root)}), \
                mock.patch.object(
                    sources, '_final_url',
                    return_value='https://github.com/astral-sh/python-build-standalone/'
                                 'releases/tag/20261013'), \
                mock.patch.object(sources, '_get_text', return_value=self.SUMS), \
                mock.patch.object(download, 'os_name', return_value='windows'), \
                mock.patch.object(download, 'arch', return_value='x64'), \
                mock.patch.object(activate, 'os_name', return_value='windows'), \
                mock.patch.object(download, 'install_portable',
                                  side_effect=fake_install) as install:
            code = runtime_cli.main(['ensure', '--python', '3.12', '--print', 'sh'])
        self.assertEqual(code, 0)
        install.assert_called_once()
        result = json.loads(self.stdout.getvalue())
        self.assertEqual(result['resolved']['python']['version'], '3.12.15')
        self.assertIn('python/v3.12.15', result['activate'])
        selection = json.loads((root / 'selection.json').read_text(encoding='utf-8'))
        self.assertEqual(selection['python']['version'], '3.12.15')


class ExpandedToolchainTests(OfflineTestCase):
    def test_uv_urls_and_published_checksum_manifest(self):
        for os_name, arch, triple, ext in (
                ('windows', 'x64', 'x86_64-pc-windows-msvc', 'zip'),
                ('linux', 'arm64', 'aarch64-unknown-linux-gnu', 'tar.gz'),
                ('mac', 'x64', 'x86_64-apple-darwin', 'tar.gz')):
            with self.subTest(os=os_name):
                with mock.patch.object(download, 'os_name', return_value=os_name), \
                        mock.patch.object(download, 'arch', return_value=arch):
                    url = sources.uv_urls('0.5.12')[0]
                self.assertEqual(
                    url,
                    'https://github.com/astral-sh/uv/releases/download/0.5.12/'
                    f'uv-{triple}.{ext}')
                self.assertTrue(download.validate_archive_url(url))
                self.assertIn(url.rsplit('/', 1)[0] + '/sha256sum.txt',
                              download._checksum_candidates(url))

    def test_exact_uv_resolution_stays_offline(self):
        with mock.patch.object(sources, '_final_url', side_effect=AssertionError('network')):
            self.assertEqual(sources.resolve_uv('0.5.12'), '0.5.12')
            self.assertEqual(sources.resolve_uv('v0.5.12'), '0.5.12')

    def test_npm_registry_resolution_requires_integrity(self):
        metadata = {
            'version': '9.15.0',
            'dist': {
                'tarball': 'https://registry.npmjs.org/pnpm/-/pnpm-9.15.0.tgz',
                'integrity': 'sha512-' + 'YQ==',
            },
        }
        with mock.patch.object(sources, '_get_json', return_value=metadata) as get:
            result = sources.resolve_npm_package('pnpm', '9.15.0')
        self.assertEqual(result['version'], '9.15.0')
        self.assertEqual(result['url'], metadata['dist']['tarball'])
        self.assertEqual(result['integrity'], metadata['dist']['integrity'])
        self.assertIn('/pnpm/9.15.0', get.call_args.args[0])

    def test_npm_integrity_mismatch_fails_closed(self):
        archive = self.base / 'pnpm.tgz'
        archive.write_bytes(b'fixture')
        with self.assertRaises(download.ChecksumMismatch):
            download.verify_integrity(archive, 'sha512-YQ==')

    def test_package_manager_detector_prefers_checked_in_yarn(self):
        project = self.base / 'project'
        releases = project / '.yarn' / 'releases'
        releases.mkdir(parents=True)
        (releases / 'yarn-4.6.0.cjs').write_text('// fixture', encoding='utf-8')
        (project / 'package.json').write_text(
            json.dumps({'packageManager': 'yarn@4.6.0'}), encoding='utf-8')
        got = installer_detect.detect_package_manager(project)
        self.assertTrue(got['project_managed'])
        self.assertEqual(got['tool'], 'yarn')
        self.assertEqual(got['source'], '.yarnrc.yml/yarnPath')

    def test_yarn_lock_without_declaration_is_not_guessed(self):
        project = self.base / 'project'
        project.mkdir()
        (project / 'yarn.lock').write_text('# yarn lockfile', encoding='utf-8')
        got = installer_detect.detect_package_manager(project)
        self.assertEqual(got['tool'], 'yarn')
        self.assertIn('does not identify', got['error'])

    def test_python_uv_and_package_manager_detection(self):
        project = self.base / 'project'
        project.mkdir()
        (project / '.python-version').write_text('3.12.15\n', encoding='utf-8')
        (project / 'pyproject.toml').write_text(
            '[project]\nrequires-python = ">=3.11"\n[tool.uv]\n', encoding='utf-8')
        (project / 'package.json').write_text(
            json.dumps({'packageManager': 'pnpm@9.15.0'}), encoding='utf-8')
        got = installer_detect.detect_all(project)
        self.assertEqual(got['python']['constraint'], '3.12.15')
        self.assertEqual(got['uv']['source'], 'pyproject.toml#tool.uv')
        self.assertEqual(got['package_manager']['tool'], 'pnpm')
        self.assertEqual(got['package_manager']['constraint'], '9.15.0')

    def test_wrappers_are_reported_without_portable_install(self):
        project = self.base / 'project'
        (project / '.mvn' / 'wrapper').mkdir(parents=True)
        (project / 'gradle' / 'wrapper').mkdir(parents=True)
        (project / '.mvn' / 'wrapper' / 'maven-wrapper.properties').write_text(
            'distributionUrl=https://example/apache-maven-3.9.9-bin.zip\n', encoding='utf-8')
        (project / 'gradle' / 'wrapper' / 'gradle-wrapper.properties').write_text(
            'distributionUrl=https://example/gradle-8.12-bin.zip\n', encoding='utf-8')
        with mock.patch.dict(os.environ, {'MV_TOOLCHAIN_MANAGER_HOME': str(self.base / 'tools')}):
            self.assertEqual(runtime_cli.main(['ensure', '--project', str(project)]), 0)
        result = json.loads(self.stdout.getvalue())
        actions = {item['tool']: item for item in result['actions']}
        self.assertEqual(actions['maven']['action'], 'project-managed')
        self.assertEqual(actions['gradle']['action'], 'project-managed')
        self.assertFalse((self.base / 'tools' / 'maven').exists())
        self.assertFalse((self.base / 'tools' / 'gradle').exists())

    def test_npm_project_requirement_uses_selected_node(self):
        project = self.base / 'project'
        project.mkdir()
        (project / 'package.json').write_text(
            json.dumps({'packageManager': 'npm@10.9.0'}), encoding='utf-8')
        node_root = self.base / 'tools' / 'node' / 'v22.0.0'
        node_root.mkdir(parents=True)
        (node_root / 'node').write_text('', encoding='utf-8')
        with mock.patch.dict(os.environ, {'MV_TOOLCHAIN_MANAGER_HOME': str(self.base / 'tools')}), \
                mock.patch.object(sources, 'resolve_node', return_value='22.0.0'), \
                mock.patch.object(runtime_cli, '_command_version', return_value='10.9.0'):
            self.assertEqual(
                runtime_cli.main(['ensure', '--project', str(project), '--node', '22']), 0)
        result = json.loads(self.stdout.getvalue())
        self.assertEqual(result['resolved']['npm']['version'], '10.9.0')
        self.assertEqual(result['actions'][-1]['action'], 'bundled')

    def test_new_tool_activation_paths_are_session_only(self):
        sel = {
            'uv': {'version': '0.5.12', 'path': '/tools/uv/v0.5.12'},
            'pnpm': {'version': '9.15.0', 'path': '/tools/pnpm/v9.15.0'},
            'yarn': {'version': '4.6.0', 'path': '/tools/yarn/v4.6.0'},
        }
        with mock.patch.object(activate, 'os_name', return_value='linux'):
            text = activate.emit(sel, 'sh')
        self.assertIn('export PATH="/tools/uv/v0.5.12:$PATH"', text)
        self.assertIn('export PATH="/tools/pnpm/v9.15.0/bin:$PATH"', text)
        self.assertIn('export PATH="/tools/yarn/v4.6.0/bin:$PATH"', text)


class PurgeTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.base / 'tools'
        self.enterContext(mock.patch.dict(os.environ, {'MV_TOOLCHAIN_MANAGER_HOME': str(self.root)}))
        self.tool = self.root / 'jdk'
        self.tool.mkdir(parents=True)
        (self.tool / 'busy-file').write_text('fixture', encoding='utf-8')
        self.selection = {'jdk': {'version': '21', 'path': str(self.tool)},
                          'node': {'version': '22', 'path': 'fixture-node'}}
        runtime_cli.activate.save_selection(self.selection, merge=False)

    def test_deletion_failure_nonzero_preserves_selection(self):
        selection_path = runtime_cli.activate.selection_path()
        before = selection_path.read_bytes()
        with mock.patch.object(runtime_cli.shutil, 'rmtree', side_effect=PermissionError('busy')) as remove, \
                mock.patch.object(runtime_cli.activate, 'save_selection') as save:
            code = runtime_cli.main(['purge', '--tool', 'jdk'])
        self.assertEqual(code, 1)
        remove.assert_called_once_with(self.tool)
        save.assert_not_called()
        self.assertEqual(selection_path.read_bytes(), before)
        self.assertTrue(self.tool.exists())
        result = json.loads(self.stdout.getvalue())
        self.assertIn('error', result)
        self.assertNotIn('purged', result)

    def test_success_removes_selection_after_directory_and_preserves_other_tools(self):
        original_save = runtime_cli.activate.save_selection
        def save_after_delete(selection, **kwargs):
            self.assertFalse(self.tool.exists())
            return original_save(selection, **kwargs)
        with mock.patch.object(runtime_cli.activate, 'save_selection', side_effect=save_after_delete):
            self.assertEqual(runtime_cli.main(['purge', '--tool', 'jdk']), 0)
        self.assertEqual(runtime_cli.activate.load_selection(), {'node': self.selection['node']})
        self.assertIn('purged', json.loads(self.stdout.getvalue()))

    def test_missing_directory_clears_stale_selection(self):
        runtime_cli.shutil.rmtree(self.tool)
        self.assertEqual(runtime_cli.main(['purge', '--tool', 'jdk']), 0)
        self.assertEqual(runtime_cli.activate.load_selection(), {'node': self.selection['node']})
        self.assertIn('nothing', json.loads(self.stdout.getvalue()))


class GateSchemaTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.dict(os.environ, {'MV_UNATTENDED_WATCH_HOME': str(self.base)}))
        self.state = {
            'active': True, 'scope': 'machine',
            'activated_at': '2020-01-01T00:00:00+08:00',
            'expires_at': '2999-01-02T00:00:00+08:00',
            'boundaries': {'irreversible': 'defer', 'notes': ''},
            'log_path': 'relative/decisions.md',
        }

    def write(self, data):
        gate.state_file().write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_valid_json_with_bad_fields_is_corrupt_and_blocked(self):
        cases = [[], {}, {'active': 'true'}, {'active': False}, {'scope': []},
                 {'activated_at': '2020-01-01T00:00:00'},
                 {'expires_at': '2999-01-01T00:00:00'},
                 {'expires_at': '2020-01-01T00:00:00'},
                 {'expires_at': None}, {'expires_at': 'not-a-timestamp'},
                 {'expires_at': 123}, {'expires_at': []},
                 {'boundaries': []}, {'boundaries': {'irreversible': 'typo'}},
                 {'boundaries': {'irreversible': 'defer', 'notes': []}},
                 {'log_path': []}]
        for changes in cases:
            with self.subTest(changes=changes):
                state = copy.deepcopy(self.state)
                if isinstance(changes, dict) and changes:
                    state.update(changes)
                else:
                    state = changes
                self.write(state)
                self.assertEqual(gate.read_state()[0], 'corrupt')
                self.assertEqual(gate.main(['block']), 2)
                self.assertEqual(gate.main(['status']), 1)
                self.assertEqual(gate.main(['prompt']), 0)

    def test_missing_required_field_is_corrupt(self):
        for field in self.state:
            with self.subTest(field=field):
                state = copy.deepcopy(self.state)
                del state[field]
                self.write(state)
                self.assertEqual(gate.read_state()[0], 'corrupt')
                self.assertEqual(gate.main(['block']), 2)

    def test_schema_does_not_impose_new_log_path_or_unknown_field_rules(self):
        state = copy.deepcopy(self.state)
        state['log_path'] = ''
        state['future_extension'] = {'anything': True}
        del state['boundaries']['notes']
        self.write(state)
        self.assertEqual(gate.read_state()[0], 'ok')
        self.assertEqual(gate.main(['block']), 2)

    def test_block_exception_still_denies_and_reminder_exception_is_nonblocking(self):
        with mock.patch.object(gate, 'read_state', side_effect=RuntimeError('unexpected')):
            self.assertEqual(gate.main(['block']), 2)
            self.assertEqual(gate.main(['prompt']), 0)
            self.assertEqual(gate.main(['status']), 1)
        self.assertIn('fail-closed', self.stderr.getvalue())

    def test_expired_valid_state_status_and_off_remain_normal(self):
        state = copy.deepcopy(self.state)
        state['expires_at'] = '2020-01-02T00:00:00+08:00'
        self.write(state)
        self.assertEqual(gate.read_state()[0], 'expired')
        self.assertEqual(gate.main(['block']), 0)
        self.assertEqual(gate.main(['status']), 0)
        self.assertIn('已过期', self.stdout.getvalue())
        for mode in ('prompt', 'compact', 'session'):
            before = self.stdout.getvalue()
            self.assertEqual(gate.main([mode]), 0)
            self.assertEqual(self.stdout.getvalue(), before)
        self.assertEqual(gate.main(['off']), 0)
        self.assertFalse(gate.state_file().exists())
        self.assertEqual(gate.main(['off']), 0)
        self.assertEqual(gate.main(['block']), 0)

    def test_naive_expiry_can_be_cleared_by_off(self):
        state = copy.deepcopy(self.state)
        state['expires_at'] = '2020-01-01T00:00:00'
        self.write(state)
        self.assertEqual(gate.main(['off']), 0)
        self.assertFalse(gate.state_file().exists())

    def test_expired_timestamp_cannot_hide_other_corrupt_fields(self):
        self.state['expires_at'] = '2020-01-02T00:00:00+08:00'
        self.state['boundaries'] = ['bad']
        self.write(self.state)
        self.assertEqual(gate.main(['block']), 2)
        self.assertEqual(gate.main(['status']), 1)

    def test_normal_on_status_block_off_lifecycle_in_temporary_state(self):
        self.assertEqual(gate.main(['on', '--expires-hours', '1']), 0)
        self.assertEqual(gate.read_state()[0], 'ok')
        self.assertEqual(gate.main(['status']), 0)
        self.assertEqual(gate.main(['block']), 2)
        self.assertEqual(gate.main(['off']), 0)
        self.assertEqual(gate.main(['block']), 0)
        self.assertEqual(len(list(self.base.glob('decisions-*.md'))), 1)


class VersionResolutionTests(OfflineTestCase):
    def test_gradle_exact_minor_and_patch_do_not_query_network(self):
        with mock.patch.object(sources, '_get_json', side_effect=AssertionError('network')), \
                mock.patch.object(sources, '_get_text', side_effect=AssertionError('network')):
            self.assertEqual(sources.resolve_gradle('8.5'), '8.5')
            self.assertEqual(sources.resolve_gradle('8.5.1'), '8.5.1')
            self.assertEqual(sources.resolve_maven('3.9.6'), '3.9.6')

    def test_gradle_range_picks_highest_match_not_mismatched_current(self):
        with mock.patch.object(sources, '_get_json', return_value={'version': '9.1'}), \
                mock.patch.object(sources, '_get_text', return_value=(
                    'gradle-8.5-bin.zip gradle-8.14-bin.zip gradle-8.6-bin.zip')):
            self.assertEqual(sources.resolve_gradle('>=8 <9'), '8.14')
            with self.assertRaises(RuntimeError):
                sources.resolve_gradle('<8')

    def test_gradle_range_can_resolve_when_current_is_offline(self):
        with mock.patch.object(sources, '_get_json', side_effect=OSError('offline')), \
                mock.patch.object(sources, '_get_text', return_value='gradle-8.5-bin.zip'):
            self.assertEqual(sources.resolve_gradle('>=8 <9'), '8.5')
            with self.assertRaises(RuntimeError):
                sources.resolve_gradle('latest')

    def test_resolution_failure_never_returns_raw_range_or_unmatched_latest(self):
        with mock.patch.object(sources, '_get_json', return_value={'version': '9.1'}), \
                mock.patch.object(sources, '_get_text', side_effect=OSError('offline')), \
                mock.patch.object(sources, '_list_maven_versions', return_value=['4.0.0']):
            with self.assertRaises(RuntimeError):
                sources.resolve_gradle('<9')
            with self.assertRaises(RuntimeError):
                sources.resolve_maven('<4')
        with mock.patch.object(sources, '_list_maven_versions', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                sources.resolve_maven('3.9')


if __name__ == '__main__':
    unittest.main()
