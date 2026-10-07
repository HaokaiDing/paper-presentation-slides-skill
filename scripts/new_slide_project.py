#!/usr/bin/env python3
"""Create a reproducible paper-talk project from the upstream MBZUAI theme."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from theme_source import (
    DEFAULT_THEME_REF,
    DEFAULT_THEME_REPO,
    TEMPLATE_PATH,
    install_theme,
    resolve_theme,
)


SHIM_FILE = "unicode-shim.tex"
DEFAULT_VENUE = "RCL Reading Group"
SHIM_SOURCE = Path(__file__).resolve().parent.parent / "templates" / SHIM_FILE
SHIM_INPUT = f"\\input{{{SHIM_FILE}}}\n"
SHIM_ANCHORS = (
    re.compile(r"^\s*\\usetheme\s*(?:\[[^\]]*\])?\s*\{\s*MBZUAI"),
    re.compile(r"^\s*\\begin\s*\{\s*document\s*\}"),
)


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("%")


def render_with_unicode_shim(main_tex: str) -> str:
    """Return main.tex with the shim \\input added to the preamble.

    pdfLaTeX treats an unmapped non-ASCII character as a fatal error and emits
    no PDF, so a single Greek letter or curly quote pasted from the paper kills
    an otherwise finished build. Install the mapping up front instead.

    Anchors match per line and comment lines are skipped. A plain substring
    replace would hit `% \\usetheme{MBZUAI}` inside a commented-out variant,
    which leaves the \\input dead inside that comment and simultaneously
    promotes the commented anchor itself to live code.
    """

    lines = main_tex.splitlines(keepends=True)
    if any(SHIM_FILE in line and not _is_comment(line) for line in lines):
        return main_tex
    for pattern in SHIM_ANCHORS:
        for index, line in enumerate(lines):
            if not _is_comment(line) and pattern.match(line):
                lines.insert(index, SHIM_INPUT)
                return "".join(lines)
    raise RuntimeError(
        "template has no uncommented preamble anchor for the Unicode shim "
        "(expected \\usetheme{MBZUAI...} or \\begin{document})"
    )


SOURCES = """# Sources and provenance

Retrieval date for online sources: **@@RETRIEVED@@**.

## Paper identity

- Title: *@@TITLE@@*
- Authors:
- Stable identifier:
- Exact version/date used:
- Venue/status:
- Official landing page:
- Official PDF:
- Official TeX or HTML source:
- Supplementary material:
- License:

Keep immutable source copies under `paper-source/`. For each archived download record the local filename, the exact URL it came from, the retrieval date, and its size in bytes.

## Figures and tables

| Local file | Paper locator | Original source | Adaptation | License | Use |
|---|---|---|---|---|---|

List used and archived assets. Mark each as unchanged, cropped, annotated, re-typeset, or reconstructed.

## Equations and derived values

- Record each transcribed equation locator and any notation changes.
- Record arithmetic derived from reported values, including operands and rounding.
- Do not reconstruct unavailable raw data.

## Data and code

- Repository/release/commit:
- Local snapshot:
- License:
- Implementation status at retrieval:
- Public data and transformations used for reconstructed visuals:

## Theme

- Repository/source: @@THEME_SOURCE@@
- Requested ref: `@@THEME_REF@@`
- Resolved commit: `@@THEME_COMMIT@@`
- License: MIT; see `THEME_LICENSE`
- Local provenance: `THEME_UPSTREAM.md`

## Scope of interpretation

Separate paper-reported claims, derived values, and presenter synthesis. Record unresolved version, source, or reproducibility limitations.
"""


def materialize(template: str, values: dict[str, str]) -> str:
    result = template
    for key, value in values.items():
        result = result.replace(f"@@{key}@@", value)
    return result


def main() -> int:
    cli = argparse.ArgumentParser(
        description="Create an MBZUAI Beamer project for one paper presentation."
    )
    cli.add_argument("output", type=Path, help="new project directory")
    cli.add_argument("--title", default="Paper title", help="full LaTeX-safe paper title")
    cli.add_argument("--short-title", help="short title for headers and footers")
    cli.add_argument("--subtitle", default="Research paper presentation")
    cli.add_argument("--authors", default="Paper authors")
    cli.add_argument(
        "--presenter",
        required=True,
        help="presenter display name confirmed by the user",
    )
    cli.add_argument(
        "--venue",
        default=DEFAULT_VENUE,
        help="session or institution name for the title page and default footer",
    )
    cli.add_argument("--date", default=r"\today", help="LaTeX-safe date/version line")
    cli.add_argument("--retrieved", default="YYYY-MM-DD")
    footer = cli.add_mutually_exclusive_group(required=True)
    footer.add_argument(
        "--confirm-default-footer",
        action="store_true",
        help="use confirmed short-title / session-by-presenter / slide-count footer",
    )
    footer.add_argument(
        "--footer",
        nargs=3,
        metavar=("LEFT", "CENTER", "RIGHT"),
        help="three LaTeX-safe footer fields confirmed by the user",
    )
    cli.add_argument(
        "--theme-repo",
        default=DEFAULT_THEME_REPO,
        help="MBZUAI theme Git repository",
    )
    cli.add_argument(
        "--theme-ref",
        default=None,
        help=f"theme branch, tag, or reachable commit; defaults to the pinned {DEFAULT_THEME_REF[:12]}",
    )
    cli.add_argument(
        "--theme-dir",
        type=Path,
        help="use a local theme checkout instead of fetching the repository",
    )
    args = cli.parse_args()

    output = args.output.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        print(f"error: output directory is not empty: {output}", file=sys.stderr)
        return 2

    short_title = args.short_title or args.title
    if args.confirm_default_footer:
        foot_left = short_title
        foot_center = rf"{args.venue} by \textit{{{args.presenter}}}"
        foot_right = r"\insertframenumber{} / \inserttotalframenumber"
    else:
        foot_left, foot_center, foot_right = args.footer

    try:
        with resolve_theme(
            repository=args.theme_repo,
            ref=args.theme_ref,
            local_directory=args.theme_dir,
        ) as snapshot:
            main_template = (snapshot.path / TEMPLATE_PATH).read_text(encoding="utf-8")
            # fontspec owns \strong under XeLaTeX and LuaLaTeX.
            main_template = re.sub(r"\\strong(?![A-Za-z@])", r"\\paperstrong", main_template)
            if args.venue != DEFAULT_VENUE:
                main_template = main_template.replace(
                    r"\institute[RCL]{@@VENUE@@}", r"\institute{@@VENUE@@}"
                )
            values = {
                "TITLE": args.title,
                "SHORT_TITLE": short_title,
                "SUBTITLE": args.subtitle,
                "AUTHORS": args.authors,
                "PRESENTER": args.presenter,
                "VENUE": args.venue,
                "DATE": args.date,
                "RETRIEVED": args.retrieved,
                "FOOT_LEFT": foot_left,
                "FOOT_CENTER": foot_center,
                "FOOT_RIGHT": foot_right,
                "THEME_SOURCE": snapshot.source,
                "THEME_REF": snapshot.requested_ref,
                "THEME_COMMIT": snapshot.commit,
            }

            # Resolve the shim anchor before creating anything on disk, so an
            # incompatible template fails without leaving a half-built project
            # that blocks a retry at the same path.
            main_tex = render_with_unicode_shim(materialize(main_template, values))

            output.mkdir(parents=True, exist_ok=True)
            install_theme(snapshot, output)
            for name in ("paper-source", "figures", "data", "build", "rendered"):
                (output / name).mkdir()
            shutil.copy2(SHIM_SOURCE, output / SHIM_FILE)
            (output / "main.tex").write_text(main_tex, encoding="utf-8")
            (output / "SOURCES.md").write_text(
                materialize(SOURCES, values), encoding="utf-8"
            )
            print(f"Created MBZUAI Beamer paper-talk project: {output}")
            print(f"Theme commit: {snapshot.commit}")
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
