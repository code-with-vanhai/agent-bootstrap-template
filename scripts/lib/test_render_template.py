"""Stdlib tests for scripts/lib/render_template.py."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.lib import render_template


class RenderTemplateTest(unittest.TestCase):
    def test_literal_replacement_preserves_special_characters(self):
        text = "url={{URL}}\npath={{PATH}}\nquote={{QUOTE}}\nmulti={{MULTI}}\n"
        rendered = render_template.render_text(
            text,
            {
                "URL": "https://example.test/a/b?x=1&y=2",
                "PATH": r"C:\tmp\agent\file",
                "QUOTE": 'say "hello" & goodbye',
                "MULTI": "line 1\nline 2",
            },
            fallback="fallback",
        )

        self.assertIn("https://example.test/a/b?x=1&y=2", rendered)
        self.assertIn(r"C:\tmp\agent\file", rendered)
        self.assertIn('say "hello" & goodbye', rendered)
        self.assertIn("multi=line 1\nline 2", rendered)

    def test_unknown_placeholder_fallback(self):
        rendered = render_template.render_text(
            "known={{KNOWN}}\nunknown={{UNKNOWN_TOKEN}}\n",
            {"KNOWN": "value"},
            fallback="not confirmed",
        )

        self.assertEqual(rendered, "known=value\nunknown=not confirmed\n")

    def test_render_file_loads_json_token_map(self):
        with tempfile.TemporaryDirectory(prefix="render-template-test-") as tmp:
            root = Path(tmp)
            target = root / "template.md"
            tokens = root / "tokens.json"
            target.write_text("{{NAME}} {{MISSING}}\n", encoding="utf-8")
            tokens.write_text(json.dumps({"NAME": "Agent & Bootstrap"}), encoding="utf-8")

            render_template.render_file(
                target,
                render_template.load_tokens(tokens),
                fallback="fallback",
            )

            self.assertEqual(target.read_text(encoding="utf-8"), "Agent & Bootstrap fallback\n")


if __name__ == "__main__":
    unittest.main()
