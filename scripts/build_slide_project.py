#!/usr/bin/env python3
"""Compile a Beamer project safely, check references, and render every slide."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


UNRESOLVED_PATTERNS = (
    r"LaTeX Warning: Reference .* undefined",
    r"LaTeX Warning: Citation .* undefined",
    r"There were undefined references",
    r"There were undefined citations",
    r"Package .* Warning: .* undefined",
)


# latexmk logs box warnings in two measures and four position forms:
#   Overfull \hbox (57.38pt too wide) in paragraph at lines 126--126
#   Overfull \hbox (57.38pt too wide) has occurred while \output is active
#   Overfull \hbox (12.4pt too wide) in alignment at lines 40--52
#   Underfull \hbox (badness 10000) detected at line 3
# Matching only the first two forms drops every underfull warning and
# mislabels a "detected at line" overflow as a theme artifact.
# A digit on the next physical line may continue a wrapped line number.
# Omit that ambiguous location instead of reporting a truncated number or
# guessing whether the next line is a continuation or ordinary log context.
BOX_PATTERN = re.compile(
    r"(?P<kind>Overfull|Underfull|Loose|Tight) \\(?P<axis>[hv])box "
    r"\((?:(?P<size>[0-9.]+)pt too (?:wide|high)|badness (?P<badness>\d+))\)"
    r"(?:"
    r" in (?P<scope>paragraph|alignment) at lines (?P<first>\d+)--(?P<last>\d+)(?!\d|\r?\n\d)"
    r"| detected at line (?P<line>\d+)(?!\d|\r?\n\d)"
    r"| (?P<output>has occurred while \\output is active)"
    r")?"
)


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required command not found: {name}")
    return path


def report_boxes(log: str, threshold: float) -> None:
    """Group box warnings by overflow size or badness with bounded samples.

    A bare total cannot be acted on: the MBZUAI header/footer templates emit the
    same overflow on every frame, so a clean deck still reports a double-digit
    count. Grouping repeated sizes keeps the output concise without attributing
    a warning to the theme or to slide content.
    """

    overfull: dict[float, list[tuple[float, str]]] = {}
    badness_groups: dict[tuple[str, str, int], list[tuple[int, str]]] = {}
    for match in BOX_PATTERN.finditer(log):
        if match.group("scope"):
            location = (
                f"{match.group('scope')} lines "
                f"{match.group('first')}--{match.group('last')}"
            )
        elif match.group("line"):
            location = f"line {match.group('line')}"
        elif match.group("output"):
            location = "page output routine"
        else:
            location = "location not reported"

        if match.group("size") is None:
            badness = int(match.group("badness"))
            bucket = 10000 if badness >= 10000 else 1000 if badness >= 1000 else 0
            kind = match.group("kind")
            group = (kind, match.group("axis"), bucket)
            badness_groups.setdefault(group, []).append((badness, location))
            continue
        size = float(match.group("size"))
        overfull.setdefault(round(size, 2), []).append(
            (size, f"\\{match.group('axis')}box {location}")
        )

    if not overfull and not badness_groups:
        print("Box warnings: none")
        return

    suppressed = 0
    rows = []
    for size, diagnostics in sorted(overfull.items(), reverse=True):
        locations = [location for raw_size, location in diagnostics if raw_size >= threshold]
        suppressed += len(diagnostics) - len(locations)
        if not locations:
            continue
        sample = ", ".join(sorted(set(locations))[:3])
        repeated = " [repeated size]" if len(locations) > 2 else ""
        rows.append(f"  Overfull {size:.2f}pt x{len(locations)}: {sample}{repeated}")

    total = sum(len(value) for value in overfull.values())
    badness_counts: dict[str, int] = {}
    for (kind, _, _), diagnostics in badness_groups.items():
        badness_counts[kind] = badness_counts.get(kind, 0) + len(diagnostics)
    badness_summary = ", ".join(
        f"{badness_counts[kind]} {kind.lower()}"
        for kind in ("Underfull", "Loose", "Tight")
        if kind in badness_counts
    ) or "0 underfull"
    print(
        f"Box warnings: {total} overfull in {len(overfull)} size group(s), "
        f"{badness_summary}; listing overfull at or above {threshold}pt"
    )
    for row in rows:
        print(row)
    if suppressed:
        print(f"  ({suppressed} overfull below {threshold}pt not listed)")

    bucket_labels = {0: "0–999", 1000: "1000–9999", 10000: "≥10000"}
    for (kind, axis, bucket), diagnostics in sorted(
        badness_groups.items(), key=lambda item: (-item[0][2], item[0][0], item[0][1])
    ):
        # Prefer actual source locations, then higher badness within the band.
        samples = sorted(
            set(diagnostics),
            key=lambda item: (
                not item[1].startswith(("line ", "paragraph ", "alignment ")),
                -item[0],
                item[1],
            ),
        )[:3]
        sample = "; ".join(f"badness {badness}, {location}" for badness, location in samples)
        print(
            f"  {kind} \\{axis}box badness {bucket_labels[bucket]} "
            f"x{len(diagnostics)}: {sample}"
        )


def write_contact_sheet(rendered: Path, columns: int, width: int) -> Path | None:
    """Tile every rendered page into one image for the first visual pass.

    Reviewing rhythm, repeated imbalance, and visual centre across a whole deck
    is a single-image job; paging through slides one at a time to find the
    suspect frames is the expensive way to reach the same shortlist.
    """

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("note: Pillow not installed; skipping contact sheet", file=sys.stderr)
        return None

    pages = sorted(rendered.glob("slide-*.png"))
    if not pages:
        return None

    label = 18
    thumbnails = []
    for page in pages:
        with Image.open(page) as image:
            scale = width / image.width
            thumbnails.append(image.convert("RGB").resize(
                (width, max(1, round(image.height * scale)))
            ))

    columns = max(1, min(columns, len(thumbnails)))
    cell_height = max(image.height for image in thumbnails) + label
    rows = -(-len(thumbnails) // columns)
    sheet = Image.new(
        "RGB", (columns * width, rows * cell_height), (255, 255, 255)
    )
    draw = ImageDraw.Draw(sheet)
    for index, thumbnail in enumerate(thumbnails):
        x = (index % columns) * width
        y = (index // columns) * cell_height
        sheet.paste(thumbnail, (x, y + label))
        draw.text((x + 4, y + 4), pages[index].stem, fill=(90, 90, 90))

    destination = rendered / "contact-sheet.png"
    sheet.save(destination)
    return destination


def main() -> int:
    cli = argparse.ArgumentParser(
        description="Compile main.tex with shell escape disabled and render all slides."
    )
    cli.add_argument("project", type=Path, help="slide project directory")
    cli.add_argument("--tex", default="main.tex", help="TeX filename inside the project")
    cli.add_argument(
        "--engine",
        choices=("pdflatex", "xelatex", "lualatex"),
        default="pdflatex",
        help="TeX engine; default pdflatex",
    )
    cli.add_argument("--pdf-name", help="root-level output name; defaults to <project>.pdf")
    cli.add_argument("--skip-render", action="store_true")
    cli.add_argument("--render-dpi", type=int, default=144)
    cli.add_argument(
        "--overfull-threshold",
        type=float,
        default=5.0,
        help="smallest box overflow in pt worth listing; default 5",
    )
    cli.add_argument("--no-contact-sheet", action="store_true")
    cli.add_argument("--contact-columns", type=int, default=4)
    cli.add_argument(
        "--contact-width", type=int, default=480, help="thumbnail width in pixels"
    )
    args = cli.parse_args()

    project = args.project.expanduser().resolve()
    tex = project / args.tex
    if not tex.is_file():
        print(f"error: TeX source not found: {tex}", file=sys.stderr)
        return 2
    if args.render_dpi < 72:
        print("error: --render-dpi must be at least 72", file=sys.stderr)
        return 2
    if args.contact_width < 1:
        print("error: --contact-width must be at least 1", file=sys.stderr)
        return 2

    pdf_name = args.pdf_name or f"{project.name}.pdf"
    if Path(pdf_name).name != pdf_name or not pdf_name.lower().endswith(".pdf"):
        print("error: --pdf-name must be a PDF basename, not a path", file=sys.stderr)
        return 2

    try:
        latexmk = require_command("latexmk")
        pdftoppm = None if args.skip_render else require_command("pdftoppm")
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    build = project / "build"
    rendered = project / "rendered"
    build.mkdir(exist_ok=True)
    rendered.mkdir(exist_ok=True)

    engine_flag, engine_override = {
        "pdflatex": ("-pdf", "-pdflatex"),
        "xelatex": ("-xelatex", "-pdfxelatex"),
        "lualatex": ("-lualatex", "-pdflualatex"),
    }[args.engine]
    command = [
        latexmk,
        "-norc",
        engine_flag,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        f"-outdir={build}",
        f"{engine_override}={args.engine} -no-shell-escape %O %S",
        str(tex),
    ]
    result = subprocess.run(
        command,
        cwd=project,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        print(result.stdout, file=sys.stderr)
        print("error: LaTeX build failed", file=sys.stderr)
        return result.returncode

    built_pdf = build / f"{tex.stem}.pdf"
    log_path = build / f"{tex.stem}.log"
    if not built_pdf.is_file() or not log_path.is_file():
        print("error: build completed without the expected PDF or log", file=sys.stderr)
        return 1

    log = log_path.read_text(encoding="utf-8", errors="replace")
    unresolved = []
    for pattern in UNRESOLVED_PATTERNS:
        unresolved.extend(re.findall(pattern, log, flags=re.IGNORECASE))
    if unresolved:
        for warning in sorted(set(unresolved)):
            print(f"error: {warning}", file=sys.stderr)
        return 1

    # A glyph the fonts cannot set is dropped from the output silently: the
    # build succeeds and the character is simply absent from the PDF. The
    # Unicode shim covers the characters that arrive by copy-paste, so a hit
    # here is a real character loss rather than routine noise.
    dropped = sorted(set(re.findall(r"Missing character: [^\n]+", log)))
    if dropped:
        for warning in dropped[:10]:
            print(f"error: {warning}", file=sys.stderr)
        if len(dropped) > 10:
            print(
                f"error: and {len(dropped) - 10} more dropped glyph(s)",
                file=sys.stderr,
            )
        return 1

    final_pdf = project / pdf_name
    shutil.copy2(built_pdf, final_pdf)

    # Clear the previous run's images before writing new ones, and do it even
    # when rendering or tiling is skipped. Leaving them behind lets the visual
    # pass read a page or a contact sheet that belongs to an older PDF.
    for stale in (*rendered.glob("slide-*.png"), *rendered.glob("contact-sheet.png")):
        stale.unlink()

    if pdftoppm:
        render = subprocess.run(
            [
                pdftoppm,
                "-png",
                "-forcenum",
                "-r",
                str(args.render_dpi),
                str(final_pdf),
                str(rendered / "slide"),
            ],
            cwd=project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if render.returncode:
            print(render.stdout, file=sys.stderr)
            print("error: PDF rendering failed", file=sys.stderr)
            return render.returncode

    rendered_count = len(list(rendered.glob("slide-*.png"))) if pdftoppm else 0
    print(f"Log retained: {log_path}")
    report_boxes(log, args.overfull_threshold)
    if pdftoppm:
        print(f"Rendered slides: {rendered_count} in {rendered}")
        if not args.no_contact_sheet:
            sheet = write_contact_sheet(
                rendered, args.contact_columns, args.contact_width
            )
            if sheet:
                print(f"Contact sheet: {sheet}")
    print(f"Build OK: {final_pdf}")
    print("Visual inspection is still required before delivery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
