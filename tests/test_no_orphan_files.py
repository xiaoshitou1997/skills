"""候选工作树零引用扫描：工作件（调参页/演示页/一次性脚本）漏清兜底。

扫描未删除的跟踪文件与未忽略的新文件，避免重构期间漏检新增文件；
每个候选文件必须被其他候选文本文件的正文提及其文件名；
按约定加载（无人显式引用也合法）的类别在 EXEMPT 清单登记，
清单本身即「哪些文件靠约定加载」的索引——新增类别补一行，类别消亡删行。
"""
import fnmatch
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 约定加载豁免（repo 相对路径，fnmatchcase；* 可跨目录段）
EXEMPT = [
    'tests/test_*.py',                              # unittest/pytest 按文件名发现
    '.github/*',                                    # GitHub Actions 按路径加载
    'fig-demo/*',                                   # 演示图集：收录本体即交付物
    'mv-toolchain-manager/scripts/installer/*.py',  # 安装器包模块：包内 import
    'LICENSE',
    '.gitignore',
    '.gitattributes',
    'CLAUDE.md',                                    # Claude Code 会话进入仓库自动加载
]


def _candidates():
    out = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True,
    ).stdout
    return sorted({rel for rel in out.split('\0')
                   if rel and (ROOT / rel).is_file()})


def _exempt(rel):
    return any(fnmatch.fnmatchcase(rel, pat) for pat in EXEMPT)


class NoOrphanCandidateFiles(unittest.TestCase):
    def test_candidate_scan_includes_new_files_and_omits_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('kept.md', 'new.md'):
                (root / name).write_text('# 测试', encoding='utf-8')
            result = subprocess.CompletedProcess(
                [], 0, 'kept.md\0deleted.md\0new.md\0kept.md\0')
            with patch.dict(globals(), ROOT=root), patch.object(
                    subprocess, 'run', return_value=result) as run:
                self.assertEqual(_candidates(), ['kept.md', 'new.md'])
                self.assertIn('--others', run.call_args.args[0])
                self.assertIn('--exclude-standard', run.call_args.args[0])

    def test_every_candidate_file_referenced_or_exempt(self):
        files = _candidates()
        pool = {}
        for rel in files:
            if rel.endswith(('.png', '.pyc')):
                continue
            pool[rel] = (ROOT / rel).read_text(encoding='utf-8', errors='replace')
        orphan = sorted(
            rel for rel in files
            if not _exempt(rel)
            and not any(rel != other and Path(rel).name in body
                        for other, body in pool.items()))
        self.assertEqual(
            [], orphan,
            '以下候选文件未被任何其他文件正文提及（工作件漏清，或新约定加载类别未登记 EXEMPT）：\n'
            + '\n'.join(orphan))

    def test_exempt_patterns_alive(self):
        files = _candidates()
        dead = [pat for pat in EXEMPT
                if not any(fnmatch.fnmatchcase(rel, pat) for rel in files)]
        self.assertEqual([], dead, f'豁免模式已无存活文件，应删除：{dead}')


if __name__ == '__main__':
    unittest.main()
