"""Exercise the build CLI without running a TeX compiler or PDF renderer."""

import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_slide_project


class BuildWorkflow(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pps-workflow-test-", dir="/tmp")
        self.addCleanup(self.scratch.cleanup)
        self.project = Path(self.scratch.name).resolve()
        (self.project / "main.tex").write_text("% subprocess fixture\n")
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.commands = []

    def run_command(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if command[0] == "latexmk":
            source = Path(command[-1])
            if not source.is_absolute():
                source = kwargs["cwd"] / source
            self.assertTrue(source.is_file(), f"latexmk source does not exist: {source}")
            (self.project / "build" / f"{source.stem}.pdf").write_bytes(b"mock PDF output")
            (self.project / "build" / f"{source.stem}.log").write_text("")
        elif command[0] == "pdftoppm":
            for number, color in ((1, "red"), (2, "blue")):
                Image.new("RGB", (64, 32), color).save(
                    self.project / "rendered" / f"slide-{number}.png"
                )
        else:
            self.fail(f"unexpected external command: {command}")
        return subprocess.CompletedProcess(command, 0, "")

    def invoke(self, *arguments):
        with (
            patch.object(sys, "argv", ["build_slide_project.py", str(self.project), *arguments]),
            patch.object(build_slide_project, "require_command", side_effect=lambda name: name),
            patch.object(build_slide_project.subprocess, "run", side_effect=self.run_command),
            contextlib.redirect_stdout(self.stdout),
            contextlib.redirect_stderr(self.stderr),
        ):
            return build_slide_project.main()

    def test_invalid_contact_width_fails_before_any_build_work(self):
        for width in ("0", "-1"):
            with self.subTest(width=width):
                self.assertEqual(2, self.invoke("--contact-width", width))
        self.assertEqual([], self.commands)
        self.assertFalse((self.project / "build").exists())
        self.assertNotIn("Build OK", self.stdout.getvalue())
        self.assertIn("--contact-width must be at least 1", self.stderr.getvalue())

    def test_positive_contact_width_writes_real_sheet_before_success(self):
        self.assertEqual(0, self.invoke("--contact-width", "1"))
        sheet = self.project / "rendered" / "contact-sheet.png"
        with Image.open(sheet) as image:
            self.assertEqual((2, 19), image.size)
            self.assertEqual((255, 0, 0), image.getpixel((0, 18)))
            self.assertEqual((0, 0, 255), image.getpixel((1, 18)))
        output = self.stdout.getvalue()
        self.assertLess(output.index("Contact sheet:"), output.index("Build OK:"))

    def test_contact_sheet_save_failure_never_announces_success(self):
        original_save = Image.Image.save

        def fail_sheet_save(image, destination, *args, **kwargs):
            if Path(destination).name == "contact-sheet.png":
                raise OSError("simulated contact-sheet write failure")
            return original_save(image, destination, *args, **kwargs)

        with patch.object(Image.Image, "save", new=fail_sheet_save):
            with self.assertRaisesRegex(OSError, "contact-sheet write failure"):
                self.invoke()
        self.assertNotIn("Build OK", self.stdout.getvalue())
        self.assertFalse((self.project / "rendered" / "contact-sheet.png").exists())

    def test_nested_tex_source_reaches_latexmk_and_expected_output(self):
        source = self.project / "slides" / "deck.tex"
        source.parent.mkdir()
        source.write_text("% nested source fixture\n")
        self.assertEqual(0, self.invoke("--tex", "slides/deck.tex", "--skip-render"))
        command, options = self.commands[0]
        self.assertEqual(source, Path(command[-1]))
        self.assertEqual(self.project, options["cwd"])
        self.assertTrue((self.project / f"{self.project.name}.pdf").is_file())
        self.assertIn("Build OK:", self.stdout.getvalue())

    def test_default_engine_is_pdflatex_with_rc_and_shell_escape_disabled(self):
        self.assertEqual(0, self.invoke("--skip-render"))
        command = self.commands[0][0]
        self.assertIn("-pdf", command)
        self.assertIn("-pdflatex=pdflatex -no-shell-escape %O %S", command)
        self.assertIn("-norc", command)

    def test_selected_engines_use_their_latexmk_interfaces_without_rc_or_shell_escape(self):
        for engine, mode, override in (
            ("pdflatex", "-pdf", "-pdflatex"),
            ("xelatex", "-xelatex", "-pdfxelatex"),
            ("lualatex", "-lualatex", "-pdflualatex"),
        ):
            with self.subTest(engine=engine):
                self.commands.clear()
                self.assertEqual(0, self.invoke("--engine", engine, "--skip-render"))
                command = self.commands[0][0]
                self.assertIn(mode, command)
                self.assertIn(f"{override}={engine} -no-shell-escape %O %S", command)
                self.assertIn("-norc", command)


if __name__ == "__main__":
    unittest.main()
