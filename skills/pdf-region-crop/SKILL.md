---
name: pdf-region-crop
description: Render PDF pages and crop any rectangular region (figure, table, text block, formula) from the original page into a high-resolution PNG, saved under a caller-chosen directory and file name. Use when a task needs images of specific parts of a PDF.
---

# PDF Region Crop

Use `./scripts/pdf_regions.py` to capture regions of a PDF as PNG. Prefer this bundled script over writing one-off cropping code.

The pipeline has three steps. Steps 1 and 3 are deterministic; step 2 is the only judgement call and is yours:

1. `prepare` renders pages to PNG (plus page text and draft boxes) into a scratch work directory.
2. You view the pages, choose regions and write them to `regions.json`.
3. `crop` cuts every region out of the original PDF into the output directory and writes a manifest there.

`render` zooms into one page, or part of it, whenever a boundary is hard to see.

## Requirements

- Python 3.9+ with PyMuPDF (`pip install pymupdf`). Check with `python ./scripts/pdf_regions.py --help`; if the import fails, ask the user before installing anything.
- The input PDF may have any file name and live anywhere. Password-protected PDFs are rejected.

## Coordinates

Every box is **normalised**: `[fx0, fy0, fx1, fy1]`, four numbers in `0..1`, fractions of the page width and height **as the page appears in the rendered PNG** (page rotation already applied). Origin is the top-left corner, x grows to the right, y grows downwards.

- The zoom used to view a page never changes these numbers, and they stay valid if an image is downscaled before you see it. Always read boxes as fractions of the whole page image.
- When you read a box off a zoomed `render --rect` image, convert it back to whole-page fractions: `fx = rect_fx0 + local_fx * (rect_fx1 - rect_fx0)`; same for y.
- Page numbers are 1-based **file order**, not the numbers printed on the pages.

## Workflow

1. Run `prepare` on the PDF, restricting `--pages` when only some pages matter. Read `work_dir` and the `page_image` paths from stdout.
2. Find the target content. Use `page-NNN.txt` for the text and `candidates.json` for draft boxes (captions, vector-drawing clusters, embedded bitmaps). Treat the drafts as hints only. Figures usually match a vector cluster or bitmap. Tables drawn with plain rules usually appear in neither, so locate a table by its caption.
3. View every page you will crop from. Do not choose a box without looking at the page image.
4. Choose one box per region. Include the whole object: axes, tick labels, legends, sub-panel labels, table header and footer rules, footnote marks. Keep a small margin (about 0.005 to 0.01) and exclude neighbouring body text. Include or exclude the caption according to the caller's request; exclude it by default. An object split across pages needs one region per page.
5. When a boundary is unclear, zoom with `render --rect ... --scale 3` or higher and convert the box back to whole-page fractions.
6. Write `regions.json` with the file names the caller asked for. If the caller gave no names, use short descriptive names such as `p006-01.png` (page, then index). A name must be a plain file name ending in `.png`, with no spaces, `=` or path separators.
7. Run `crop` into the caller's output directory. Parse stdout. For each `status=fail` line, fix that entry and re-run; successful PNGs are overwritten on re-run.
8. View every output PNG. Check that nothing is cut off, that no stray neighbouring text is included, and that small text is legible. Adjust boxes and re-run `crop` until each image is right.
9. Report `out_dir`, the image names and the manifest path. The work directory is scratch space: never copy it into a deliverable. It may be deleted once cropping is done.

## Rules

- Always cut from the original PDF with `crop`. Never redraw or re-typeset content, and never substitute a full-page screenshot for a smaller region unless the whole page is what was asked for.
- Keep the default crop `--scale 3` unless the caller asks otherwise. It keeps small text, axes and legends legible.
- The caller owns the output directory and the file names. The script writes only the named PNGs plus its manifest, and reports stray PNGs as `untracked` without touching them.
- A box that falls outside its page is reported as a failure. It is never clipped to the page or saved as a blank image.

## Common Commands

Render all pages for inspection into a new temp directory, e.g. `/tmp/pdf-regions-XXXX`:

```bash
python ./scripts/pdf_regions.py prepare paper.pdf
```

Render only pages 20 to the end, with larger previews, into a chosen directory:

```bash
python ./scripts/pdf_regions.py prepare paper.pdf --pages 20- --scale 2 --work-dir ./work
```

Zoom into the upper part of page 6:

```bash
python ./scripts/pdf_regions.py render paper.pdf 6 --rect 0.10 0.05 0.90 0.30 --scale 4
```

Crop every region listed in `regions.json` into `assets/`:

```bash
python ./scripts/pdf_regions.py crop paper.pdf --regions regions.json --out assets
```

`regions.json`:

```json
{
  "fig-1.png":   {"page": 6, "norm": [0.170, 0.098, 0.827, 0.215]},
  "table-1.png": {"page": 7, "norm": [0.173, 0.124, 0.827, 0.245]}
}
```

Full CLI help: `python ./scripts/pdf_regions.py <prepare|render|crop> --help`.

## Output Contract

Progress goes to stderr. Machine-readable results go to stdout as `key=value` lines.

`prepare`:

```text
work_dir=<dir>
candidates=<dir>/candidates.json
page_count=<n>
rendered=<n>
render_scale=<s>
page_image=<dir>/page-NNN.png      one line per rendered page
```

`render`:

```text
image=<png>
page=<n>
scale=<s>
size=<w>x<h>
```

`crop`:

```text
region=<name> status=ok page=<n> size=<w>x<h>
region=<name> status=fail reason=<token>
untracked=<name>
extracted=<n>
failed=<n>
out_dir=<dir>
manifest=<dir>/manifest.json
```

The failure reason tokens are `bad_name`, `bad_spec`, `bad_value`, `norm_length`, `norm_out_of_range`, `empty_box`, `page_out_of_range` and `outside_page`.

Exit status: `0` all done, `1` some regions failed (the others were written), `2` bad invocation or input.

The manifest records the source PDF file name and sha256, the page count and the crop scale. For each image it records the page, the normalised box, the resolved box in PDF points, the pixel size and the sha256. It contains no machine-specific paths.
