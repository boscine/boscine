# Build Prompt: ASCII-Portrait GitHub Profile README

Build a GitHub profile README (`github.com/<username>/<username>`) that is 100% self-hosted — zero third-party image/badge services. Everything renders from SVGs generated inside the repo by a scheduled GitHub Action. Follow every constraint below exactly; each one was discovered by testing against GitHub's actual markdown sanitizer, not assumed.

## 0. Hard platform constraints (read first)

GitHub's markdown renderer strips: `<style>` blocks, `style="..."` attributes, `class="..."` attributes, inline `<svg>` (must be referenced via `<img>`, not embedded raw), `<font>`, `<small>`, `<big>`.

It keeps: `<sub>`, `<sup>`, `<kbd>`, `<samp>`, `<blockquote>`, `<details>`, `<hr>`, `<picture>`, `align="..."`, `width="..."` on `<img>`/`<td>`.

Consequences to design around:
- No custom fonts via CSS in the README body text itself — only GitHub's default sans/mono (via backticks or `<samp>`/`<code>`). Any custom typeface must be baked into an **image**.
- All animation must be SMIL (`<animate>`, `<set>` elements inside the SVG file) — GitHub strips `<script>`, so JS/CSS animation is dead on arrival.
- Every visual element is an SVG referenced by `<img src="...">`, not inlined.
- Before committing, validate markdown via `POST https://api.github.com/markdown` — it runs the same sanitizer as production.

## 1. Repo setup

- Repo name must exactly match the GitHub username.
- `pip install pillow numpy opencv-python-headless rembg onnxruntime fonttools brotli`
- Note: first `rembg` run downloads a ~176MB background-removal model; cache it, don't re-download per CI run.

## 2. Part 1 — ASCII portrait (SVG, animated)

### Input photo spec (enforce or reject the photo before processing)
- Side lighting, ~45°, single light source — flat frontal light must be rejected (produces a featureless mid-tone blob).
- Tight crop: chin to just above hairline. Face should fill the frame.
- Minimum 1200px on the long edge — anything smaller (e.g. 320px) loses fine detail like glasses frames on downscale.
- Plain, non-black background; subject shouldn't wear black against a dark backdrop.
- Slight head angle, not dead-on frontal — gives nose/jaw a shadow edge.

### Processing pipeline (implement each stage, in order)
1. `rembg` background removal → force background to pure white (maps to blank end of the ASCII ramp; skipping this fills the background with dense characters).
2. Bilateral filter → smooth skin while preserving edges.
3. CLAHE local contrast, clip limit ≈ 3.0 (global autocontrast fails on flatly-lit faces).
4. Darkening curve: `output = (value/255)^1.7` applied before ramp mapping — this is required to keep glasses/brows/lips from washing out. Do not skip this step.
5. Map pixel brightness to an ASCII ramp string (leading character = space, so background clears to nothing).

### Rendering parameters
- 90 columns wide, rendered at 460px display width.
- Row count = `columns * (image_height/image_width) * 0.48` (monospace chars are ~2x taller than wide — do not use a naive aspect ratio).
- Do not go below ~88 columns (face muddies) or far above 90 (block dominates page).

### Typing animation
- Each row lives inside a `<clipPath>` whose rect `width` animates 0 → full via SMIL.
- A small block element rides the reveal edge as a "cursor."
- Stagger rows top-to-bottom: `begin="{row_index * 0.09}s"`.
- Every animation must use `fill="freeze"` — portrait types once and stops; no looping.

### Font metrics — critical, do not eyeball this
- The character grid assumes an advance width of exactly **0.600em** at `font-size: 12.9` (`CHAR_W = 7.74`).
- Liberation Mono / DejaVu Sans Mono / Noto Sans Mono = 0.600 (safe defaults if not embedding your own font).
- Ubuntu Mono (0.560) and Consolas (≈0.55, what Windows defaults to) will misrender the grid ~7% narrow — this is why Part 4 (font embedding) is not optional if you want cross-platform correctness.

### Color rule
- Single fill color for all characters. Do not implement per-character color variation — it reads as visual noise, not intentional design.

## 3. Part 2 — self-generated stats (SVG, via GitHub GraphQL API)

Generate four graphics in the same visual language as the portrait:
1. Hero total contribution count + weekly sparkline
2. Current streak + longest streak, with date ranges
3. Top languages, by bytes and by repo count
4. Full year, one character per day, reusing the portrait's ASCII ramp

### Chart type
- Use column/bar charts for daily contribution counts, not line charts — daily data is sparse/discrete and a line implies interpolated values that never existed. Reserve line/area charts for weekly aggregates only.

### Determinism — both of these WILL cause spurious nightly commits if missed
1. **Pin the window to whole UTC days.** Compute `from` = today − 364 days at `00:00:00Z`, `to` = today at `23:59:59Z`, and pass explicitly to `contributionsCollection(from: $from, to: $to)`. Do not let it default to "past year from request time" — two runs minutes apart will bucket days differently and shift the sparkline.
2. **Filter to `privacy: PUBLIC` repos only** in the GraphQL query. A personal token sees private repos; the CI token doesn't — without this filter, language stats disagree depending on who ran the script.

### Generator implementation
- Python **standard library only** (`urllib` for API calls) — no dependencies to break in CI.
- Auth via the GraphQL API using the repo's built-in `GITHUB_TOKEN` — no personal access token needed.

### GitHub Actions workflow (build this exactly)
```yaml
name: refresh stats
on:
  schedule:
    - cron: "17 5 * * *"
  workflow_dispatch:          # deliberately NO `push` trigger — this job commits,
                              # and a push trigger would re-run it on its own commit
permissions:
  contents: write
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GH_LOGIN: ${{ github.repository_owner }}
        run: python3 scripts/generate_stats.py
      - run: |
          FILES="stats.svg streak.svg langs.svg year.svg hd-*.svg"
          [ -z "$(git status --porcelain -- $FILES)" ] && exit 0
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -- $FILES && git commit -m "stats: refresh" && git push
```
- Commit only when generated files actually changed (the `git status --porcelain` guard above) — otherwise you get a commit every single night.
- Let the Action own the generated SVGs exclusively. Do not regenerate them locally and commit — your local token and the workflow's token can bucket a day near a week boundary differently, producing non-identical output and merge conflicts.

## 4. Part 3 — styling the body text within GitHub's constraints

- **Section headings**: render as SVG images — lowercase mono label with a hairline rule extending to the right edge. This is the only way to get a custom typeface on headings. Trade-off: image headings don't get anchor links, so GitHub's auto-generated README outline will be empty — set meaningful `alt` text so screen readers still get the heading text.
- **Line length control**: full-width paragraphs run ~110 characters, too wide to read well. Two options — a `width` attribute on a `<td>` (but GitHub draws a visible border around table cells), or hard-wrap with `<br>` tags at ~76 characters (no border, but loses reflow on narrow/mobile screens). Pick hard-wrap unless the border is acceptable.
- **Inline mono text**: use `<samp>` instead of backticks where you don't want the grey "chip" background (e.g., a tech-stack row or per-project metadata line).
- **Lede paragraph**: wrap the opening line in `<blockquote>` for a left rule + dimmed text, entirely free, no CSS needed.

## 5. Part 4 — embedding the custom font

- External `@font-face` URLs will NOT work — these SVGs are loaded via `<img>` tags, and browsers refuse subresource fetches inside image documents. Instead, inline the font as a base64 `woff2` data URI inside a `<style>` block within the SVG file itself (SVG's own `<style>` isn't stripped — only `<style>` in the README's HTML is stripped). This means **every SVG carries its own font copy**, so subset aggressively per role or the page gets heavy.
- Recommended typeface: **JetBrains Mono** (SIL OFL license, 1000 units/em with 600 advance width — matches the 0.600em grid assumption exactly, so no geometry recalculation needed). Alternatives: IBM Plex Mono, Fira Code, Source Code Pro (all OFL). Do not use a commercial/non-redistributable font — the file ships inside a public repo.
- Subset per use case with fonttools:
```bash
# ramp subset — only the 13 characters the portrait ramp uses
pyftsubset JetBrainsMono-Regular.ttf --text=' .`:-=+*cs#%@' \
  --flavor=woff2 --layout-features='' --no-hinting -o ramp.woff2
```
- Target sizes: ramp subset (13 chars) ≈ 1.3KB, headings subset (only letters used) ≈ 1.4KB, basic-latin 2-weight subset for data graphics ≈ 4.5KB each. Total budget ≈ 57KB across the whole page — do NOT inline a full TTF per file (that's ~4.5MB total, unacceptable).
- Ship the font's license file (e.g. `OFL.txt`) in the repo alongside the font.

## 6. Verification checklist before calling this done

- [ ] Validated final README markdown against `POST /markdown` (GitHub's real sanitizer)
- [ ] Screenshot-tested SVGs with headless Chrome using a **tall fixed viewport**, NOT `fullPage: true` (full-page screenshots restart/break SMIL animations) — allow ~5.1s for a ~56-row portrait to finish its typing animation before capturing
- [ ] Confirmed zero requests to any third-party domain (no badge/stats services)
- [ ] Confirmed commit-only-on-change logic in the workflow (dry-run twice in a row, second run should produce no commit)
- [ ] Confirmed `contributionsCollection` window is pinned to UTC day boundaries, not request-time-relative
- [ ] Confirmed GraphQL query filters `privacy: PUBLIC`
- [ ] Tested font advance-width rendering isn't needed if font is embedded (skip if Part 4 done); otherwise verified 0.600em-advance font family in use
- [ ] After first push, manually edited the README once via GitHub's web UI if it doesn't appear on the profile (new profile READMEs are cached)
- [ ] Manually set pinned repositories and bio in the GitHub UI — no API/GraphQL mutation exists for either

## 7. Deliverables

- `README.md` — the profile page itself
- `scripts/generate_portrait.py` — photo → animated ASCII SVG
- `scripts/generate_stats.py` — GraphQL calls → 4 stat SVGs (stdlib only)
- `.github/workflows/refresh.yml` — the scheduled Action above
- `assets/fonts/*.woff2` + license file(s)
- Generated SVGs: `stats.svg`, `streak.svg`, `langs.svg`, `year.svg`, portrait SVG, heading SVGs
