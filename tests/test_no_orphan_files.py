"""跟踪文件零引用扫描：工作件（调参页/演示页/一次性脚本）漏清兜底。

每个 git 跟踪文件必须被其他跟踪文本文件的正文提及其文件名；
按约定加载（无人显式引用也合法）的类别在 EXEMPT 清单登记，
清单本身即「哪些文件靠约定加载」的索引——新增类别补一行，类别消亡删行。
"""
import fnmatch
import subprocess
import unittest
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
]


def _tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _exempt(rel):
    return any(fnmatch.fnmatchcase(rel, pat) for pat in EXEMPT)


class NoOrphanTrackedFiles(unittest.TestCase):
    def test_every_tracked_file_referenced_or_exempt(self):
        files = _tracked()
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
            '以下跟踪文件未被任何其他文件正文提及（工作件漏清，或新约定加载类别未登记 EXEMPT）：\n'
            + '\n'.join(orphan))

    def test_exempt_patterns_alive(self):
        files = _tracked()
        dead = [pat for pat in EXEMPT
                if not any(fnmatch.fnmatchcase(rel, pat) for rel in files)]
        self.assertEqual([], dead, f'豁免模式已无存活文件，应删除：{dead}')


if __name__ == '__main__':
    unittest.main()
