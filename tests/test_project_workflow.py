"""Exercise initialization, refresh, and theme selection without network or TeX."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

import new_slide_project
import sync_theme
import theme_source


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="pps-workflow-test-", dir="/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.theme = self.root / "theme"
        self.theme.mkdir()
        for filename in theme_source.THEME_FILES:
            (self.theme / filename).write_text("% test theme\n", encoding="utf-8")
        (self.theme / "assets").mkdir()
        (self.theme / "LICENSE").write_text("MIT\n", encoding="utf-8")
        (self.theme / "README.md").write_text("Test theme\n", encoding="utf-8")
        template = self.theme / theme_source.TEMPLATE_PATH
        template.parent.mkdir()
        template.write_text(
            "\\documentclass{beamer}\n\\usetheme{MBZUAI}\n"
            "\\title{@@TITLE@@}\n\\institute[RCL]{@@VENUE@@}\n"
            "\\footleft{@@FOOT_LEFT@@}\n\\footmid{@@FOOT_CENTER@@}\n"
            "\\footright{@@FOOT_RIGHT@@}\n\\begin{document}\n\\end{document}\n",
            encoding="utf-8",
        )

    def run_cli(self, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPOSITORY / "scripts" / script), *arguments],
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
        )

    def fake_git(self, command: list[str], **kwargs: object) -> str:
        if "fetch" in command:
            shutil.copytree(self.theme, Path(command[2]), dirs_exist_ok=True)
        return "test-revision" if command[-2:] == ["rev-parse", "HEAD"] else ""

    def test_custom_repository_without_ref_fails_before_git_for_both_clis(self) -> None:
        existing = self.root / "existing"
        existing.mkdir()
        (existing / "main.tex").write_text("unchanged\n", encoding="utf-8")
        for module, arguments in (
            (
                new_slide_project,
                [str(self.root / "new"), "--presenter", "P", "--confirm-default-footer"],
            ),
            (sync_theme, [str(existing), "--yes"]),
        ):
            with self.subTest(module=module.__name__):
                errors = StringIO()
                argv = [module.__name__, *arguments, "--theme-repo", "fixture-custom-repo"]
                with (
                    patch.object(sys, "argv", argv),
                    patch.object(theme_source, "_run") as git,
                    redirect_stderr(errors),
                ):
                    self.assertEqual(module.main(), 1)
                git.assert_not_called()
                self.assertIn("--theme-ref is required", errors.getvalue())
        self.assertFalse((self.root / "new").exists())
        self.assertEqual((existing / "main.tex").read_text(encoding="utf-8"), "unchanged\n")

    def test_explicit_repository_and_ref_reach_fetch_from_both_clis(self) -> None:
        project = self.root / "custom"
        for module, arguments in (
            (
                new_slide_project,
                [str(project), "--presenter", "P", "--confirm-default-footer"],
            ),
            (sync_theme, [str(project), "--yes"]),
        ):
            with self.subTest(module=module.__name__):
                argv = [
                    module.__name__, *arguments,
                    "--theme-repo", "fixture-custom-repo", "--theme-ref", "custom-ref",
                ]
                with (
                    patch.object(sys, "argv", argv),
                    patch.object(theme_source, "_run", side_effect=self.fake_git) as git,
                    redirect_stdout(StringIO()),
                ):
                    self.assertEqual(module.main(), 0)
                commands = [call.args[0] for call in git.call_args_list]
                self.assertTrue(any(command[-1] == "fixture-custom-repo" for command in commands))
                self.assertTrue(any(command[-3:] == ["1", "origin", "custom-ref"] for command in commands))

    def test_default_repository_keeps_the_configured_pin(self) -> None:
        with patch.object(theme_source, "_run", side_effect=self.fake_git) as git:
            with theme_source.resolve_theme() as snapshot:
                self.assertEqual(snapshot.source, theme_source.DEFAULT_THEME_REPO)
                self.assertEqual(snapshot.requested_ref, theme_source.DEFAULT_THEME_REF)
        fetch = next(call.args[0] for call in git.call_args_list if "fetch" in call.args[0])
        self.assertEqual(fetch[-1], theme_source.DEFAULT_THEME_REF)

    def test_local_theme_does_not_require_a_custom_repository_ref(self) -> None:
        with patch.object(theme_source, "_run") as git:
            with theme_source.resolve_theme(
                repository="fixture-custom-repo", local_directory=self.theme
            ) as snapshot:
                self.assertEqual(snapshot.path, self.theme.resolve())
                self.assertEqual(snapshot.requested_ref, "local checkout")
        git.assert_not_called()

    def test_offline_default_project_and_refresh_preserve_existing_defaults(self) -> None:
        project = self.root / "default"
        created = self.run_cli(
            "new_slide_project.py", str(project), "--title", "T", "--presenter", "P",
            "--confirm-default-footer", "--theme-dir", str(self.theme),
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        before = (project / "main.tex").read_bytes()
        self.assertIn(b"\\institute[RCL]{RCL Reading Group}", before)
        self.assertIn(b"\\footmid{RCL Reading Group by \\textit{P}}", before)
        refreshed = self.run_cli(
            "sync_theme.py", str(project), "--yes", "--theme-dir", str(self.theme)
        )
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        self.assertEqual((project / "main.tex").read_bytes(), before)

    def test_custom_venue_updates_default_footer_and_preserves_explicit_footer(self) -> None:
        for name, footer_arguments, expected_center in (
            (
                "default-footer", ["--confirm-default-footer"],
                "Robotics Seminar by \\textit{P}",
            ),
            ("custom-footer", ["--footer", "LEFT", "Confirmed center", "RIGHT"], "Confirmed center"),
        ):
            with self.subTest(footer=name):
                project = self.root / name
                created = self.run_cli(
                    "new_slide_project.py", str(project), "--title", "T", "--presenter", "P",
                    "--venue", "Robotics Seminar", *footer_arguments,
                    "--theme-dir", str(self.theme),
                )
                self.assertEqual(created.returncode, 0, created.stderr)
                main = (project / "main.tex").read_text(encoding="utf-8")
                self.assertIn("\\institute{Robotics Seminar}", main)
                self.assertNotIn("RCL", main)
                self.assertIn(f"\\footmid{{{expected_center}}}", main)
                if name == "custom-footer":
                    self.assertIn("\\footleft{LEFT}", main)
                    self.assertIn("\\footright{RIGHT}", main)

    def test_template_strong_is_renamed_before_user_metadata_is_inserted(self) -> None:
        template = self.theme / theme_source.TEMPLATE_PATH
        template.write_text(
            template.read_text(encoding="utf-8")
            + "\\newcommand{\\strong}[1]{{\\bfseries #1}}\n"
            + "\\strong{Evidence} and \\strong1\n"
            + "\\newcommand{\\stronger}[1]{#1}\n\\stronger{Unchanged}\n",
            encoding="utf-8",
        )
        project = self.root / "strong-command"
        title = r"User \strong{metadata}"
        created = self.run_cli(
            "new_slide_project.py", str(project), "--title", title, "--presenter", "P",
            "--confirm-default-footer", "--theme-dir", str(self.theme),
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        main = (project / "main.tex").read_text(encoding="utf-8")
        self.assertIn(r"\newcommand{\paperstrong}[1]{{\bfseries #1}}", main)
        self.assertIn(r"\paperstrong{Evidence} and \paperstrong1", main)
        self.assertNotIn(r"\newcommand{\strong}", main)
        self.assertIn(r"\newcommand{\stronger}[1]{#1}", main)
        self.assertIn(r"\stronger{Unchanged}", main)
        self.assertIn(f"\\title{{{title}}}", main)
        self.assertIn(f"\\footleft{{{title}}}", main)


if __name__ == "__main__":
    unittest.main()
