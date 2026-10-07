# Paper Presentation Slides Skill

A Codex skill for turning an assigned research paper into a source-grounded, editable, and visually verified LaTeX Beamer presentation.

The skill uses the separately maintained [MBZUAI Beamer Theme](https://github.com/MicDZ/MBZUAI_Beamer_Theme) and codifies a research-talk workflow developed from RCL reading-group decks. It emphasizes argument structure, evidence provenance, complete mathematical notation, honest interpretation of experiments, and rendered-slide QA.

## What it does

- Builds a talk around the paper's question, thesis, method logic, decisive evidence, limitations, and takeaways.
- Uses assertion-style frame titles and checks visual weight rather than relying on fixed column layouts.
- Requires displayed equations to include operational meaning and a complete symbol/type/index/role audit.
- Records paper versions, figures, tables, repositories, transformations, licenses, and derived values in `SOURCES.md`.
- Requires the presenter name and all three footer fields to be explicitly confirmed.
- Compiles with shell escape disabled, rejects unresolved citations/references, retains logs, renders every page, and tiles them into one contact sheet for the first visual pass.
- Splits the completion gate into deterministic blocking checks and recorded judgement checks, so taste disputes do not withhold a deliverable deck.
- Groups overfull warnings by displayed size and Underfull/Loose/Tight diagnostics by badness, retaining bounded location samples without inferring the cause from repetition.
- Installs a Unicode shim, because pdfLaTeX turns one pasted Greek letter or em dash into a fatal error with no PDF.
- Supports multi-paper reading-group talks through an optional session-level narrative guide.
- Fetches a pinned theme/template commit for new projects, records the resolved commit, and can refresh theme-owned files in existing projects.

This skill does **not** depend on browser automation or Zotero. A host agent may use its available source-retrieval tools when the task requires online evidence.

## Install

Clone the repository into the skills directory using the skill's declared name. For Codex:

```bash
git clone https://github.com/HaokaiDing/paper-presentation-slides-skill.git \
  ~/.codex/skills/paper-presentation-slides
```

For Claude Code, the `SKILL.md` frontmatter format is the same:

```bash
git clone https://github.com/HaokaiDing/paper-presentation-slides-skill.git \
  ~/.claude/skills/paper-presentation-slides
```

Restart or reload the host agent so it discovers the new skill.

## Use

Invoke it explicitly:

```text
Use $paper-presentation-slides to turn this assigned paper into a 20-minute reading-group talk.
```

The skill will ask for the exact presenter display name and footer wording before finalizing metadata.

To initialize a project manually:

```bash
python3 scripts/new_slide_project.py ./example-paper-slides \
  --title "Paper title" \
  --short-title "Short title" \
  --authors "First Author et al." \
  --presenter "Confirmed presenter" \
  --confirm-default-footer
```

To compile and render it:

```bash
python3 scripts/build_slide_project.py ./example-paper-slides
```

For CJK text with the pinned theme, configure a CJK package/font and add `--engine lualatex`. `--engine xelatex` is also available, with the observed closing-background opacity limitation documented in [the workflow](references/workflow.md). The default is `pdflatex`; all paths keep shell escape disabled and perform the same log checks and rendering. The helper uses `latexmk -norc`, so it does not execute automatic latexmk startup files. `--tex slides/deck.tex` selects a source within the project, and `--contact-width` requires a positive pixel width.

To update an existing project's theme without changing its `main.tex` or paper figures:

```bash
python3 scripts/sync_theme.py ./example-paper-slides --yes
python3 scripts/build_slide_project.py ./example-paper-slides
```

New projects use the theme commit pinned in `scripts/theme_source.py`, fetched from a fork so that commit stays reachable. Following a moving branch would let an upstream typography or footer change reflow a deck that already passed visual QA. Use `--theme-ref <tag-or-commit>` for a different revision, or `--theme-dir <local-checkout>` for offline work and testing unpublished theme changes. Every generated project records the resolved commit in `THEME_UPSTREAM.md` and `SOURCES.md`; `THEME_MANIFEST.txt` lets later refreshes remove obsolete theme-owned files without deleting paper or custom assets.

Use `--venue "Confirmed session name"` to set the session/institution and the session name in the default center footer. Use `--footer "Left" "Center" "Right"` instead of `--confirm-default-footer` when custom footer text has been confirmed. A custom `--theme-repo` requires an explicit `--theme-ref`.

## Requirements

- Python 3.9 or later. The scripts use only the standard library, except that the contact sheet needs Pillow; without it the build still succeeds and skips tiling.
- Git and network access to fetch the pinned theme, unless `--theme-dir` supplies a local checkout.
- A TeX distribution providing `pdflatex`, `latexmk`, Beamer, TikZ, AMS math packages, `booktabs`, `multirow`, `array`, `adjustbox`, `pifont`, and `newunicodechar`.
- Poppler's `pdftoppm` for rendered-slide inspection.
- `pypdf` only when merging a multi-paper session deck.

## Repository layout

```text
SKILL.md                       Skill entrypoint
agents/openai.yaml             Codex UI metadata
references/design-guide.md     Evidence-driven frame and layout patterns
references/formula-notation.md Complete formula-notation requirements
references/multi-paper-talks.md Multi-paper session guidance
references/workflow.md         Source, build, and visual-QA workflow
templates/unicode-shim.tex     Non-ASCII to LaTeX mappings for pdfLaTeX
scripts/new_slide_project.py   Reproducible project initializer
scripts/build_slide_project.py Safe compiler and page renderer
scripts/sync_theme.py          Existing-project theme updater
scripts/theme_source.py        Theme fetch/validation/install helper
```

## Licensing

The skill instructions and scripts are released under the [MIT License](LICENSE).

The MBZUAI Beamer theme is maintained and licensed separately. Generated projects preserve its MIT license and resolved-source provenance. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Names, logos, and brand assets may also be subject to their owners' trademark or brand-usage rules.
