"""Regression checks for actionable TeX box diagnostics."""

import contextlib
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_slide_project import report_boxes


def report(log, threshold=5.0):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        report_boxes(log, threshold)
    return output.getvalue()


class WrappedPositions(unittest.TestCase):
    def test_real_wrapped_range_never_reports_truncated_location(self):
        # Real pdfTeX log, max_print_line=63; source paragraph lines 40--52.
        log = "Overfull \\hbox (10000.0pt too wide) in paragraph at lines 40--5\n2\n[] \n"
        output = report(log)
        self.assertIn("10000.00pt x1", output)
        self.assertIn("location not reported", output)
        self.assertNotIn("paragraph lines 40--5", output)

    def test_complete_positions_remain_actionable(self):
        for position, expected in [
            ("in paragraph at lines 40--52", "paragraph lines 40--52"),
            ("in alignment at lines 40--52", "alignment lines 40--52"),
            ("detected at line 52", "line 52"),
            ("has occurred while \\output is active", "page output routine"),
        ]:
            with self.subTest(position=position):
                self.assertIn(expected, report(f"Overfull \\hbox (12.4pt too wide) {position}\n[]\n"))

    def test_wrapped_detected_line_and_crlf_are_ambiguous(self):
        for newline in ("\n", "\r\n"):
            output = report(f"Overfull \\vbox (12.4pt too high) detected at line 5{newline}2{newline}")
            self.assertIn("location not reported", output)
            self.assertNotIn("line 5", output)

    def test_numeric_context_is_never_appended_to_a_location(self):
        output = report("Overfull \\hbox (12.4pt too wide) detected at line 52\n2 ordinary context\n")
        self.assertIn("location not reported", output)
        self.assertNotIn("line 522", output)

    def test_wrapped_separator_does_not_invent_a_range(self):
        output = report("Overfull \\hbox (12.4pt too wide) in paragraph at lines 40-\n-52\n")
        self.assertIn("location not reported", output)


class BadnessKinds(unittest.TestCase):
    def test_real_loose_and_tight_boxes_are_counted_by_kind(self):
        # Real Beamer/pdfTeX diagnostics with hbadness=vbadness=0.
        log = "\n".join(
            f"{kind} \\{axis}box (badness 1) detected at line 16"
            for kind in ("Loose", "Tight") for axis in ("h", "v")
        )
        output = report(log)
        self.assertIn("2 loose, 2 tight", output)
        self.assertNotIn("underfull", output)
        self.assertNotIn("Box warnings: none", output)

    def test_no_diagnostics_still_reports_none(self):
        self.assertEqual("Box warnings: none\n", report("unrelated log output\n"))


class BadnessDetails(unittest.TestCase):
    def test_real_underfull_diagnostics_retain_axis_badness_and_location(self):
        # Real pdfTeX diagnostics from four controlled boxes in one frame.
        log = "\n".join(
            f"Underfull \\{axis}box (badness {badness}) detected at line 20"
            for badness in (800, 10000) for axis in ("h", "v")
        )
        output = report(log)
        self.assertIn("4 underfull", output)
        for axis in ("h", "v"):
            self.assertIn(f"Underfull \\{axis}box badness 0–999 x1: badness 800, line 20", output)
            self.assertIn(f"Underfull \\{axis}box badness ≥10000 x1: badness 10000, line 20", output)

    def test_loose_and_tight_details_keep_the_original_kind(self):
        output = report("Loose \\hbox (badness 1) detected at line 16\nTight \\vbox (badness 1) detected at line 16\n")
        self.assertIn("Loose \\hbox badness 0–999 x1: badness 1, line 16", output)
        self.assertIn("Tight \\vbox badness 0–999 x1: badness 1, line 16", output)

    def test_samples_are_bounded_and_prioritize_known_positions(self):
        warnings = ["Underfull \\hbox (badness 9000)"] * 4
        warnings += [
            f"Underfull \\hbox (badness 1234) in paragraph at lines {line}--{line}"
            for line in range(40, 44)
        ]
        output = report("\n".join(warnings))
        rows = [row for row in output.splitlines() if row.startswith("  Underfull")]
        self.assertEqual(1, len(rows))
        self.assertIn("1000–9999 x8", rows[0])
        self.assertEqual(3, rows[0].count("paragraph lines"))
        self.assertNotIn("location not reported", rows[0])

    def test_overfull_threshold_does_not_suppress_badness_details(self):
        log = "Overfull \\hbox (12.4pt too wide) detected at line 2\nUnderfull \\vbox (badness 1234) detected at line 3\n"
        low = report(log, 5.0)
        high = report(log, 100.0)
        self.assertIn("  Overfull 12.40pt x1", low)
        self.assertNotIn("  Overfull 12.40pt x1", high)
        self.assertIn("badness 1234, line 3", high)
        self.assertEqual(
            [row for row in low.splitlines() if row.startswith("  Underfull")],
            [row for row in high.splitlines() if row.startswith("  Underfull")],
        )

    def test_wrapped_badness_position_is_reported_as_unknown(self):
        output = report("Underfull \\hbox (badness 10000) detected at line 5\n2\n")
        self.assertIn("badness 10000, location not reported", output)
        self.assertNotIn("line 5", output)


class OverfullGroups(unittest.TestCase):
    def test_repeated_content_is_not_attributed_to_the_theme(self):
        warning = "Overfull \\hbox (8.0pt too wide) in paragraph at lines 40--52"
        output = report("\n".join([warning] * 5))
        self.assertIn("8.00pt x5", output)
        self.assertIn("paragraph lines 40--52", output)
        self.assertIn("repeated size", output)
        self.assertNotIn("theme", output)

    def test_sizes_with_the_same_display_precision_share_a_group(self):
        output = report(
            "Overfull \\hbox (5.001pt too wide) detected at line 1\n"
            "Overfull \\hbox (5.004pt too wide) detected at line 2\n"
        )
        self.assertIn("2 overfull in 1 size group(s)", output)
        self.assertEqual(1, output.count("  Overfull 5.00pt x2"))
        self.assertIn("line 1", output)
        self.assertIn("line 2", output)

    def test_threshold_filters_raw_sizes_inside_a_rounded_group(self):
        output = report(
            "Overfull \\hbox (4.999pt too wide) detected at line 1\n"
            "Overfull \\hbox (5.001pt too wide) detected at line 2\n"
        )
        self.assertIn("2 overfull in 1 size group(s)", output)
        self.assertIn("  Overfull 5.00pt x1: \\hbox line 2", output)
        self.assertNotIn("line 1", output)
        self.assertIn("1 overfull below 5.0pt not listed", output)

    def test_rounded_up_size_does_not_pass_the_raw_threshold(self):
        output = report("Overfull \\hbox (4.999pt too wide) detected at line 1\n")
        self.assertNotIn("  Overfull", output)
        self.assertIn("1 overfull below 5.0pt not listed", output)


if __name__ == "__main__":
    unittest.main()
