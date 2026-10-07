"""Theme refreshes keep generated provenance current and preserve user notes."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from theme_source import THEME_FILES, ThemeSnapshot, install_theme


class ThemeProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="theme-provenance-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        theme = root / "theme"
        theme.mkdir()
        for filename in THEME_FILES:
            (theme / filename).write_text("% test theme\n", encoding="utf-8")
        (theme / "assets").mkdir()
        (theme / "LICENSE").write_text("MIT\n", encoding="utf-8")
        (theme / "README.md").write_text("Test theme\n", encoding="utf-8")
        self.project = root / "project"
        self.project.mkdir()
        self.first = ThemeSnapshot(theme, "fixture-source-A", "ref-A", "revision-A")
        self.second = ThemeSnapshot(theme, "fixture-source-B", "ref-B", "revision-B")
        install_theme(self.first, self.project)

    def test_refresh_preserves_notes_and_other_sections_byte_for_byte(self) -> None:
        before = (
            "# Sources\r\n\r\n## Paper identity\r\n"
            "- Repository/source: fixture-source-A\r\n"
            "- Title: 论文 title\r\n\r\n## Theme\r\n\r\n"
        )
        fields = (
            "- Repository/source: fixture-source-A  <!-- retain URL note -->\r\n"
            "- Requested ref: `ref-A`<!-- retain ref note -->\r\n"
            "- Resolved commit: `revision-A`  \t<!-- 保留注释 -->\r\n"
        )
        after = (
            "- License: MIT; see `THEME_LICENSE`\r\n"
            "- Local provenance: `THEME_UPSTREAM.md`\r\n"
            "User theme note: keep the logo placement.\r\n\r\n"
            "### Previous experiment\r\n"
            "- Requested ref: `ref-A`\r\n\r\n"
            "## Scope of interpretation\r\n"
            "- Resolved commit: `revision-A`\r\n"
            "Keep this final line without a newline."
        )
        sources = self.project / "SOURCES.md"
        sources.write_bytes((before + fields + after).encode("utf-8"))

        install_theme(self.second, self.project)

        expected_fields = fields.replace("fixture-source-A", "fixture-source-B").replace(
            "`ref-A`", "`ref-B`"
        ).replace("`revision-A`", "`revision-B`")
        self.assertEqual(
            sources.read_bytes(), (before + expected_fields + after).encode("utf-8")
        )
        provenance = (self.project / "THEME_UPSTREAM.md").read_text(encoding="utf-8")
        for field in (
            "- Repository/source: fixture-source-B",
            "- Requested ref: `ref-B`",
            "- Resolved commit: `revision-B`",
        ):
            self.assertIn(field, provenance)
            self.assertIn(field, sources.read_text(encoding="utf-8"))

        refreshed = sources.read_bytes()
        install_theme(self.second, self.project)
        self.assertEqual(sources.read_bytes(), refreshed)

    def test_existing_field_values_are_updated_without_changing_notes(self) -> None:
        sources = self.project / "SOURCES.md"
        original = (
            "## Theme\n"
            "- Repository/source: fixture-source-A-extra  <!-- source note -->\n"
            "- Requested ref: `ref-A-extra`  <!-- ref note -->\n"
            "- Resolved commit: `revision-A-extra`  <!-- commit note -->\n"
        ).encode("utf-8")
        sources.write_bytes(original)
        install_theme(self.second, self.project)
        expected = original.replace(b"fixture-source-A-extra", b"fixture-source-B").replace(
            b"`ref-A-extra`", b"`ref-B`"
        ).replace(b"`revision-A-extra`", b"`revision-B`")
        self.assertEqual(sources.read_bytes(), expected)

    def test_refresh_repairs_sources_stale_from_an_earlier_sync(self) -> None:
        sources = self.project / "SOURCES.md"
        original = (
            "## Theme\n"
            "- Repository/source: fixture-source-A\n"
            "- Requested ref: `ref-A` <!-- old note -->\n"
            "- Resolved commit: `revision-A`\n"
        )
        sources.write_text(original, encoding="utf-8")
        install_theme(self.second, self.project)
        # Reproduce a project left by the old helper: canonical B, SOURCES A.
        sources.write_text(original, encoding="utf-8")
        third = ThemeSnapshot(self.first.path, "fixture-source-C", "ref-C", "revision-C")

        install_theme(third, self.project)

        expected = original.replace("fixture-source-A", "fixture-source-C").replace(
            "`ref-A`", "`ref-C`"
        ).replace("`revision-A`", "`revision-C`")
        self.assertEqual(sources.read_text(encoding="utf-8"), expected)
        self.assertIn(
            "- Resolved commit: `revision-C`",
            (self.project / "THEME_UPSTREAM.md").read_text(encoding="utf-8"),
        )

    def test_local_directory_value_and_user_subsection_are_preserved(self) -> None:
        sources = self.project / "SOURCES.md"
        original = (
            "## Theme\n"
            "- Repository/source: local directory<!-- local note -->\n"
            "### Previous experiment\n"
            "- Requested ref: `ref-A`\n"
            "- Resolved commit: `revision-A`\n"
        )
        sources.write_text(original, encoding="utf-8")
        install_theme(self.second, self.project)
        self.assertEqual(
            sources.read_text(encoding="utf-8"),
            original.replace("local directory", "fixture-source-B"),
        )

    def test_refresh_without_sources(self) -> None:
        install_theme(self.second, self.project)
        self.assertFalse((self.project / "SOURCES.md").exists())
        self.assertIn(
            "- Resolved commit: `revision-B`",
            (self.project / "THEME_UPSTREAM.md").read_text(encoding="utf-8"),
        )
        self.assertTrue((self.project / THEME_FILES[0]).is_file())

    def test_refresh_without_theme_section_preserves_sources(self) -> None:
        sources = self.project / "SOURCES.md"
        original = b"# Sources\r\n## Paper\r\n- Resolved commit: `revision-A`\r\n"
        sources.write_bytes(original)
        install_theme(self.second, self.project)
        self.assertEqual(sources.read_bytes(), original)
        self.assertIn(
            "- Resolved commit: `revision-B`",
            (self.project / "THEME_UPSTREAM.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
