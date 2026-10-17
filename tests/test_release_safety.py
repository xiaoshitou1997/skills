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
import download
import runtime_cli
import sources



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
