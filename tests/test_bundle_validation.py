"""Release checks must reject invalid metadata and broken reference links."""
import tempfile
import unittest
from pathlib import Path

from validate_bundle import agent_manifest_errors, local_link_errors, metadata_errors


class BundleValidationTests(unittest.TestCase):
    def document(self, name='mv-example', description='明确触发场景', body='# 示例\n'):
        return f'---\nname: {name}\ndescription: {description}\n---\n{body}'

    def test_metadata_limits_and_directory_identity(self):
        self.assertEqual(metadata_errors(self.document(), 'mv-example'), [])
        self.assertTrue(metadata_errors(self.document(description='字' * 1025), 'mv-example'))
        self.assertTrue(metadata_errors(self.document(name='mv-' + 'x' * 62), 'mv-' + 'x' * 62))
        self.assertTrue(metadata_errors(self.document(name='mv--example'), 'mv--example'))
        self.assertTrue(metadata_errors(self.document(), 'mv-other'))
        self.assertTrue(metadata_errors(self.document(description=''), 'mv-example'))
        self.assertTrue(metadata_errors(self.document(description='[not, a, string]'), 'mv-example'))
        self.assertTrue(metadata_errors(self.document(description='false'), 'mv-example'))

    def test_folded_and_quoted_descriptions(self):
        self.assertEqual(metadata_errors(self.document(description='>\n  处理文档。\n  当需要评审时使用。'), 'mv-example'), [])
        self.assertEqual(metadata_errors(self.document(description='"处理：文档"'), 'mv-example'), [])
        self.assertTrue(metadata_errors(self.document(description='>\n  ' + '字' * 1025), 'mv-example'))
        self.assertTrue(metadata_errors(self.document(description='"unterminated'), 'mv-example'))
        self.assertTrue(metadata_errors(self.document(description="'invalid ' quote'"), 'mv-example'))
        self.assertEqual(metadata_errors(self.document(description="'it''s valid'"), 'mv-example'), [])
        self.assertTrue(metadata_errors(self.document(description='文字\nname: mv-example'), 'mv-example'))

    def test_body_limit_does_not_count_frontmatter(self):
        self.assertEqual(metadata_errors(self.document(body='一行\n' * 500), 'mv-example'), [])
        self.assertTrue(metadata_errors(self.document(body='一行\n' * 501), 'mv-example'))

    def test_agent_manifest_weak_checks(self):
        manifest = 'interface:\n  display_name: "Example"\n  short_description: "一句话职责。"\n'
        self.assertEqual(agent_manifest_errors(manifest), [])
        self.assertEqual(agent_manifest_errors(manifest.replace('一句话职责。', '字' * 200)), [])
        self.assertTrue(agent_manifest_errors(manifest.replace('一句话职责。', '字' * 201)))
        self.assertTrue(agent_manifest_errors(manifest.replace('一句话职责。', '')))
        self.assertTrue(agent_manifest_errors('interface:\n  display_name: "Example"\n'))
        self.assertTrue(agent_manifest_errors('interface:\n  short_description: 无引号文案\n'))

    def test_reference_links_are_checked_outside_entry_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / 'references' / 'guide.md'
            reference.parent.mkdir()
            reference.write_text('# 说明', encoding='utf-8')
            (root / 'file with spaces.md').write_text('# 其他', encoding='utf-8')
            valid = '[已有](guide.md#section) [空格](../file%20with%20spaces.md) [网页](https://example.com/a) [锚点](#a)'
            self.assertEqual(local_link_errors(reference, valid, root), [])
            self.assertTrue(local_link_errors(reference, '[失效](missing.md)', root))
            self.assertTrue(local_link_errors(reference, '[越界](../../outside.md)', root))
            self.assertEqual(local_link_errors(reference, '```markdown\n[示例](missing.md)\n```\n', root), [])


if __name__ == '__main__':
    unittest.main()
