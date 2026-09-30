#!/usr/bin/env python3
"""Capture arbitrary rectangular regions of a PDF (figures, tables, body-text
fragments, titles, formulas, anything with a bounding box) as PNG images.

Three-step pipeline. Steps 1 and 3 are deterministic and done by this script;
step 2 is the only step where a human or an LLM makes a judgement.

    1. prepare   render pages to PNG, plus per-page text and draft boxes
    2. (you)     look at the PNGs, choose regions, write regions.json
    3. crop      cut every region out of the original PDF -> PNGs + manifest

Coordinates are ALWAYS normalised: four numbers in 0..1, fractions of the page
width/height as the page appears in the rendered PNG (page rotation already
applied), in this order:

    [fx0, fy0, fx1, fy1]      left, top, right, bottom

Origin is the TOP-LEFT corner; x grows rightwards, y grows DOWNWARDS.

Output convention: human-readable progress goes to stderr, machine-readable
results go to stdout as key=value lines.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import NoReturn

try:
    import pymupdf as fitz
except ImportError:  # PyMuPDF < 1.24.3 only ships the legacy module name
    try:
        import fitz  # type: ignore[no-redef]
    except ImportError:
        sys.stderr.write("ERROR: PyMuPDF is required: pip install pymupdf\n")
        raise SystemExit(2)

EXIT_OK, EXIT_PARTIAL, EXIT_USAGE = 0, 1, 2
NAME_RE = re.compile(r"^[^\s/\\=]+\.png$", re.I)
CAPTION_RE = re.compile(r"^\s*(Figure|Fig\.|Table|Algorithm|Listing)\s*[A-Za-z0-9.\-]*\s*[:.|]", re.I)
HEADING_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)+|[A-Z])\.?\s+[A-Z]")


# --------------------------------------------------------------------------- io


def log(message: str = "") -> None:
    """Human-readable progress -> stderr."""
    sys.stderr.write(message + "\n")


def emit(key: str, value: object) -> None:
    """Machine-readable result -> stdout, one key=value per line."""
    sys.stdout.write(f"{key}={value}\n")
    sys.stdout.flush()


def fail(message: str) -> NoReturn:
    log(f"ERROR: {message}")
    raise SystemExit(EXIT_USAGE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def open_pdf(path: str | Path) -> "fitz.Document":
    pdf = Path(path)
    if not pdf.is_file():
        fail(f"PDF not found: {pdf}")
    with pdf.open("rb") as fh:
        if not fh.read(5).startswith(b"%PDF"):
            fail(f"not a PDF file (missing %PDF header): {pdf}")
    doc = fitz.open(pdf)
    if doc.needs_pass:
        fail(f"PDF is password-protected: {pdf}")
    return doc


# ------------------------------------------------------------------ geometry


def shown(rect: "fitz.Rect", page: "fitz.Page") -> "fitz.Rect":
    """Map a box from unrotated page space (text/drawings) to displayed space."""
    out = fitz.Rect(rect) * page.rotation_matrix
    out.normalize()
    return out


def to_norm(rect: "fitz.Rect", page: "fitz.Page") -> list[float]:
    """Displayed-space rect -> normalised [fx0, fy0, fx1, fy1]."""
    pr = page.rect
    return [
        round(min(max((rect.x0 - pr.x0) / pr.width, 0.0), 1.0), 6),
        round(min(max((rect.y0 - pr.y0) / pr.height, 0.0), 1.0), 6),
        round(min(max((rect.x1 - pr.x0) / pr.width, 0.0), 1.0), 6),
        round(min(max((rect.y1 - pr.y0) / pr.height, 0.0), 1.0), 6),
    ]


def to_rect(norm: list[float], page: "fitz.Page") -> "fitz.Rect":
    """Normalised box -> displayed-space rect usable as a get_pixmap clip."""
    pr = page.rect
    fx0, fy0, fx1, fy1 = norm
    return fitz.Rect(
        pr.x0 + fx0 * pr.width,
        pr.y0 + fy0 * pr.height,
        pr.x0 + fx1 * pr.width,
        pr.y0 + fy1 * pr.height,
    )


def merge_boxes(boxes: list["fitz.Rect"], gap: float) -> list["fitz.Rect"]:
    """Merge boxes closer than `gap` until no further merge is possible."""
    groups = [fitz.Rect(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        merged: list[fitz.Rect] = []
        for box in groups:
            padded = fitz.Rect(box.x0 - gap, box.y0 - gap, box.x1 + gap, box.y1 + gap)
            hit = next((g for g in merged if g.intersects(padded)), None)
            if hit is None:
                merged.append(fitz.Rect(box))
            else:
                hit.include_rect(box)
                changed = True
        groups = merged
    return sorted(groups, key=lambda r: (round(r.y0), round(r.x0)))


def parse_pages(spec: str, total: int) -> list[int]:
    """'all' | '1-30' | '3,5,7' | '10-' -> sorted 1-based page numbers."""
    spec = spec.strip().lower()
    if spec in ("", "all", "*"):
        return list(range(1, total + 1))
    pages: set[int] = set()
    try:
        for chunk in filter(None, (c.strip() for c in spec.split(","))):
            if "-" in chunk:
                lo, _, hi = chunk.partition("-")
                start, end = int(lo or 1), int(hi or total)
            else:
                start = end = int(chunk)
            pages.update(range(max(1, start), min(total, end) + 1))
    except ValueError:
        fail(f"cannot parse --pages {spec!r}; use 'all', '1-30' or '3,5,7'")
    if not pages:
        fail(f"--pages {spec!r} matches no page (the PDF has {total} pages)")
    return sorted(pages)


# ------------------------------------------------------------------- prepare


def page_metadata(page: "fitz.Page", page_no: int) -> dict:
    """Text blocks, caption-like lines, heading-like lines and vector clusters,
    all as normalised boxes in displayed space."""
    blocks, captions, headings = [], [], []
    for raw in page.get_text("dict")["blocks"]:
        if raw["type"] != 0:
            continue
        text = "\n".join(
            "".join(span["text"] for span in line["spans"]) for line in raw["lines"]
        ).strip()
        if not text:
            continue
        norm = to_norm(shown(fitz.Rect(raw["bbox"]), page), page)
        blocks.append({"norm": norm, "text": text})
        first = text.splitlines()[0]
        if CAPTION_RE.match(first):
            captions.append({"text": first[:160], "norm": norm})
        elif HEADING_RE.match(first) and len(first) <= 120:
            headings.append({"text": first, "norm": norm})

    drawings = [
        shown(d["rect"], page)
        for d in page.get_drawings()
        if d["rect"].width > 2 and d["rect"].height > 2
    ]
    images = [shown(fitz.Rect(info["bbox"]), page) for info in page.get_image_info()]
    clusters = merge_boxes(drawings, gap=12)
    return {
        "page": page_no,
        "rotation": page.rotation,
        "blocks": blocks,
        "captions": captions,
        "headings": headings,
        "vector_clusters": [to_norm(c, page) for c in clusters],
        "raster_images": [to_norm(r, page) for r in images],
    }


def cmd_prepare(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    doc = open_pdf(pdf)
    pages = parse_pages(args.pages, len(doc))
    if args.scale <= 0:
        fail("--scale must be positive")
    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="pdf-regions-"))
    work.mkdir(parents=True, exist_ok=True)

    log(f"source : {pdf.name} ({len(doc)} pages)")
    log(f"work   : {work}")
    drafts: dict[str, dict] = {}
    images: list[Path] = []
    for n in pages:
        page = doc[n - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(args.scale, args.scale), alpha=False)
        png = work / f"page-{n:03d}.png"
        pix.save(png)
        images.append(png)
        (work / f"page-{n:03d}.txt").write_text(
            f"===== PDF PAGE {n} / {len(doc)} =====\n" + page.get_text("text", sort=True),
            encoding="utf-8",
        )
        meta = page_metadata(page, n)
        (work / f"page-{n:03d}-blocks.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        drafts[str(n)] = {k: meta[k] for k in ("rotation", "captions", "headings", "vector_clusters", "raster_images")}
        log(
            f"  page {n:>3}: {png.name} {pix.width}x{pix.height}  "
            f"captions={len(meta['captions'])} vector_clusters={len(meta['vector_clusters'])} "
            f"raster_images={len(meta['raster_images'])}"
        )

    candidates = work / "candidates.json"
    candidates.write_text(
        json.dumps(
            {
                "note": (
                    "Draft boxes to speed up choosing regions; they are hints, not answers. "
                    "vector_clusters come from vector drawings and usually match plotted figures. "
                    "raster_images are embedded bitmaps. Tables drawn with plain rules are often "
                    "missing from both, so locate a table by its caption and take the band next to "
                    "it. Captions may sit above (tables) or below (figures) their object; include or "
                    "exclude them as needed. All boxes are normalised [fx0, fy0, fx1, fy1]."
                ),
                "pdf": pdf.name,
                "pdf_sha256": sha256(pdf),
                "page_count": len(doc),
                "render_scale": args.scale,
                "pages": drafts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log("")
    log("next: view page-NNN.png, choose regions, write regions.json, then run 'crop'.")
    log("      zoom with 'render' when a boundary is hard to see.")
    emit("work_dir", work)
    emit("candidates", candidates)
    emit("page_count", len(doc))
    emit("rendered", len(pages))
    emit("render_scale", f"{args.scale:g}")
    for png in images:
        emit("page_image", png)
    return EXIT_OK


# -------------------------------------------------------------------- render


def check_norm(values: list[float]) -> str | None:
    """Return a failure reason token, or None when the box is valid."""
    if len(values) != 4:
        return "norm_length"
    if not all(0.0 <= v <= 1.0 for v in values):
        return "norm_out_of_range"
    if values[0] >= values[2] or values[1] >= values[3]:
        return "empty_box"
    return None


def cmd_render(args: argparse.Namespace) -> int:
    doc = open_pdf(args.pdf)
    if not 1 <= args.page <= len(doc):
        fail(f"page {args.page} is out of range (the PDF has {len(doc)} pages)")
    if args.scale <= 0:
        fail("--scale must be positive")
    page = doc[args.page - 1]
    if args.rect:
        reason = check_norm(args.rect)
        if reason:
            fail(f"--rect {args.rect} is invalid ({reason}); expected 0 <= fx0 < fx1 <= 1 and 0 <= fy0 < fy1 <= 1")
        clip = to_rect(args.rect, page)
    else:
        clip = page.rect
    if args.output:
        out = Path(args.output)
        if out.suffix.lower() != ".png":
            fail("--output must end with .png")
    else:
        tag = "full" if not args.rect else "rect"
        out = Path(tempfile.mkdtemp(prefix="pdf-regions-")) / f"page-{args.page:03d}-{tag}-x{args.scale:g}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(args.scale, args.scale), clip=clip, alpha=False)
    pix.save(out)
    log(f"rendered page {args.page} at scale {args.scale:g} -> {out} ({pix.width}x{pix.height})")
    emit("image", out)
    emit("page", args.page)
    emit("scale", f"{args.scale:g}")
    emit("size", f"{pix.width}x{pix.height}")
    return EXIT_OK


# ---------------------------------------------------------------------- crop


def cmd_crop(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    doc = open_pdf(pdf)
    if args.scale <= 0:
        fail("--scale must be positive")
    if not args.manifest.strip() or any(sep in args.manifest for sep in ("/", "\\")) or args.manifest.lower().endswith(".png"):
        fail("--manifest must be a plain file name (not a path, not a .png)")

    regions_path = Path(args.regions)
    if not regions_path.is_file():
        fail(f"regions file not found: {regions_path}")
    try:
        regions = json.loads(regions_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{regions_path} is not valid JSON: {exc}")
    if not isinstance(regions, dict) or not regions:
        fail(f'{regions_path} must be a non-empty object like {{"name.png": {{"page": 6, "norm": [0.1, 0.1, 0.9, 0.4]}}}}')

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log(f"source : {pdf.name} ({len(doc)} pages)")
    log(f"output : {out}  (scale {args.scale:g})")

    items: list[dict] = []
    failures: list[dict] = []

    def reject(name: str, reason: str, detail: str) -> None:
        failures.append({"name": name, "reason": reason, "detail": detail})
        log(f"  FAIL {name}: {detail}")
        emit("region", f"{name} status=fail reason={reason}")

    for name, spec in regions.items():
        if not NAME_RE.match(name):
            reject(name.replace(" ", "_") or "<empty>", "bad_name",
                   f"{name!r} must be a plain file name ending in .png, without spaces, '=' or path separators")
            continue
        if not isinstance(spec, dict) or "page" not in spec or "norm" not in spec:
            reject(name, "bad_spec", 'each entry must look like {"page": 6, "norm": [fx0, fy0, fx1, fy1]}')
            continue
        try:
            page_no = int(spec["page"])
            norm = [float(v) for v in spec["norm"]]
        except (TypeError, ValueError):
            reject(name, "bad_value", "page must be an integer and norm a list of four numbers")
            continue
        reason = check_norm(norm)
        if reason:
            reject(name, reason, f"norm {norm} must satisfy 0 <= fx0 < fx1 <= 1 and 0 <= fy0 < fy1 <= 1")
            continue
        if not 1 <= page_no <= len(doc):
            reject(name, "page_out_of_range", f"page {page_no} does not exist (the PDF has {len(doc)} pages)")
            continue

        page = doc[page_no - 1]
        rect = to_rect(norm, page)
        if not page.rect.contains(rect):
            reject(name, "outside_page", f"box {[round(v, 2) for v in rect]} exceeds page {tuple(page.rect)}")
            continue

        target = out / name
        pix = page.get_pixmap(matrix=fitz.Matrix(args.scale, args.scale), clip=rect, alpha=False)
        pix.save(target)
        items.append(
            {
                "name": name,
                "page": page_no,
                "norm": norm,
                "rect_pt": [round(v, 2) for v in rect],
                "size_px": [pix.width, pix.height],
                "sha256": sha256(target),
            }
        )
        log(f"  ok   {name}: page {page_no}, {pix.width}x{pix.height}")
        emit("region", f"{name} status=ok page={page_no} size={pix.width}x{pix.height}")

    untracked = sorted(p.name for p in out.glob("*.png") if p.name not in regions)
    for name in untracked:
        log(f"  note {name}: PNG in the output directory is not listed in regions.json")
        emit("untracked", name)

    manifest = out / args.manifest
    manifest.write_text(
        json.dumps(
            {
                "tool": "pdf_regions.py",
                "pdf": pdf.name,
                "pdf_sha256": sha256(pdf),
                "page_count": len(doc),
                "crop_scale": args.scale,
                "coordinates": "norm = [fx0, fy0, fx1, fy1] in 0..1 of the displayed page, origin top-left",
                "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
                "items": items,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log("")
    log(f"{len(items)} extracted, {len(failures)} failed")
    if failures:
        log("fix the failed entries in regions.json and re-run; successful PNGs are kept and overwritten on re-run")
    emit("extracted", len(items))
    emit("failed", len(failures))
    emit("out_dir", out)
    emit("manifest", manifest)
    return EXIT_PARTIAL if failures else EXIT_OK


# ----------------------------------------------------------------------- cli

COORDS_HELP = (
    "coordinates: every box is normalised [fx0, fy0, fx1, fy1] in 0..1, i.e. fractions of the page\n"
    "width/height as the page looks in the rendered PNG (rotation already applied). Origin is the\n"
    "TOP-LEFT corner, x grows to the right, y grows DOWNWARDS. Example: [0.17, 0.10, 0.83, 0.22]\n"
    "is a band spanning 17%..83% of the width and 10%..22% of the height from the top.\n"
    "The zoom used to view a page never changes these numbers."
)

REGIONS_HELP = (
    "regions.json maps an output file name to a page and a box:\n"
    "  {\n"
    '    "fig-1.png":   {"page": 6, "norm": [0.170, 0.098, 0.827, 0.215]},\n'
    '    "table-1.png": {"page": 7, "norm": [0.173, 0.124, 0.827, 0.245]}\n'
    "  }\n"
    "  - name : plain file name ending in .png; no spaces, '=' or path separators\n"
    "  - page : 1-based page number in FILE order (not the number printed on the page)\n"
    "  - norm : normalised box, see 'coordinates' above"
)

OUTPUT_HELP = (
    "output: progress goes to stderr; results go to stdout as key=value lines.\n"
    "exit status: 0 = all done, 1 = some regions failed (the rest were written), 2 = bad invocation or input."
)


def build_parser() -> argparse.ArgumentParser:
    raw = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(
        prog="pdf_regions.py",
        formatter_class=raw,
        description=(
            "Capture any rectangular region of a PDF (figure, table, body-text fragment, title,\n"
            "formula, ...) as a PNG cut from the original page, not redrawn.\n\n"
            "workflow:\n"
            "  1. prepare  render pages to PNG (+ page text and draft boxes) into a work directory\n"
            "  2. you      view the PNGs, choose regions, write them to regions.json\n"
            "  3. crop     cut every region out of the PDF into an output directory + manifest\n"
            "  (render)    zoom into one page or part of it whenever a boundary is hard to see\n\n"
            + COORDS_HELP
        ),
        epilog=(
            "example:\n"
            "  pdf_regions.py prepare paper.pdf --pages 1-12\n"
            "  pdf_regions.py render  paper.pdf 6 --rect 0.10 0.05 0.90 0.30 --scale 3\n"
            "  pdf_regions.py crop    paper.pdf --regions regions.json --out assets\n\n"
            "run 'pdf_regions.py <command> --help' for the details of each command."
        ),
    )
    subs = parser.add_subparsers(dest="command", required=True, metavar="{prepare,render,crop}")

    p = subs.add_parser(
        "prepare",
        formatter_class=raw,
        help="step 1: render pages to PNG and write page text plus draft boxes",
        description=(
            "Render the requested pages to PNG so regions can be chosen by looking at them, and write\n"
            "helper files next to them:\n"
            "  page-NNN.png          the rendered page (view this)\n"
            "  page-NNN.txt          the page text in reading order\n"
            "  page-NNN-blocks.json  text blocks with normalised boxes\n"
            "  candidates.json       draft boxes: figure/table captions, vector-drawing clusters,\n"
            "                        embedded bitmaps; hints only, always check them on the PNG\n"
            "Everything goes to a NEW directory under the system temp dir (e.g. /tmp/pdf-regions-XXXX)\n"
            "unless --work-dir is given. These are working files; the final images come from 'crop'.\n\n"
            + COORDS_HELP
        ),
        epilog=(
            "stdout keys: work_dir, candidates, page_count, rendered, render_scale, page_image (one per page)\n\n"
            "examples:\n"
            "  pdf_regions.py prepare paper.pdf\n"
            "  pdf_regions.py prepare paper.pdf --pages 20-30 --scale 2\n"
            "  pdf_regions.py prepare paper.pdf --work-dir ./work\n\n"
            + OUTPUT_HELP
        ),
    )
    p.add_argument("pdf", help="source PDF; any file name, any location")
    p.add_argument(
        "--pages",
        default="all",
        metavar="SPEC",
        help="pages to render: 'all' (default), '1-12', '20-' (to the end) or '3,5,7'; 1-based file order",
    )
    p.add_argument(
        "--scale",
        type=float,
        default=1.5,
        help="zoom of the preview PNGs (default: 1.5, i.e. 1.5 px per PDF point). Only changes how big "
             "the previews are; it never changes region coordinates",
    )
    p.add_argument(
        "--work-dir",
        metavar="DIR",
        default=None,
        help="directory for the previews and helper files (default: a new directory under the system temp dir)",
    )
    p.set_defaults(func=cmd_prepare)

    r = subs.add_parser(
        "render",
        formatter_class=raw,
        help="render one page, or part of it, at any zoom to check a boundary",
        description=(
            "Render a single page, or a normalised sub-box of it, to PNG. Use it to zoom in and\n"
            "verify a region before writing it into regions.json. Zooming does not change coordinates:\n"
            "a box read off a zoomed crop must be converted back to whole-page fractions before use\n"
            "(whole-page fx = rect_fx0 + local_fx * (rect_fx1 - rect_fx0), same for y).\n\n"
            + COORDS_HELP
        ),
        epilog=(
            "stdout keys: image, page, scale, size\n\n"
            "examples:\n"
            "  pdf_regions.py render paper.pdf 6\n"
            "  pdf_regions.py render paper.pdf 6 --scale 3 --output page-6.png\n"
            "  pdf_regions.py render paper.pdf 6 --rect 0.10 0.05 0.90 0.30 --scale 4\n\n"
            + OUTPUT_HELP
        ),
    )
    r.add_argument("pdf", help="source PDF")
    r.add_argument("page", type=int, help="1-based page number in file order (not the printed page number)")
    r.add_argument(
        "--rect",
        nargs=4,
        type=float,
        metavar=("FX0", "FY0", "FX1", "FY1"),
        default=None,
        help="optional normalised sub-box to render (left top right bottom, 0..1); default: whole page",
    )
    r.add_argument("--scale", type=float, default=2.0, help="zoom for this render (default: 2.0)")
    r.add_argument(
        "--output",
        metavar="PNG",
        default=None,
        help="where to save the PNG (default: a new directory under the system temp dir)",
    )
    r.set_defaults(func=cmd_render)

    c = subs.add_parser(
        "crop",
        formatter_class=raw,
        help="step 3: cut every region in regions.json out of the PDF into PNGs + a manifest",
        description=(
            "Cut each region listed in regions.json out of the ORIGINAL PDF and save it under --out\n"
            "with the given file name. Also writes a manifest into --out recording, per image, the page,\n"
            "the normalised box, the resolved box in PDF points, the pixel size and the PNG sha256, plus\n"
            "the source PDF file name and sha256 (no machine-specific paths), so the result can be\n"
            "audited and reproduced. An invalid region is reported and skipped; the others are still\n"
            "written. PNGs already in --out but not listed in regions.json are reported as 'untracked'\n"
            "and left untouched.\n\n"
            + COORDS_HELP + "\n\n" + REGIONS_HELP
        ),
        epilog=(
            "stdout keys:\n"
            "  region=<name> status=ok page=<n> size=<w>x<h>      one line per written image\n"
            "  region=<name> status=fail reason=<token>           one line per rejected entry\n"
            "     reason tokens: bad_name, bad_spec, bad_value, norm_length, norm_out_of_range,\n"
            "                    empty_box, page_out_of_range, outside_page\n"
            "  untracked=<name>                                    stray PNG found in --out\n"
            "  extracted, failed, out_dir, manifest                summary\n\n"
            "example:\n"
            "  pdf_regions.py crop paper.pdf --regions regions.json --out assets\n\n"
            + OUTPUT_HELP
        ),
    )
    c.add_argument("pdf", help="source PDF; use the same file that was used for 'prepare'")
    c.add_argument("--regions", required=True, metavar="JSON", help="regions file, format shown above")
    c.add_argument("--out", required=True, metavar="DIR", help="directory that receives the PNGs and the manifest (created if missing)")
    c.add_argument(
        "--scale",
        type=float,
        default=3.0,
        help="zoom of the output PNGs (default: 3.0, keeps small text, axes and legends legible)",
    )
    c.add_argument(
        "--manifest",
        metavar="NAME",
        default="manifest.json",
        help="file name of the manifest written inside --out (default: manifest.json)",
    )
    c.set_defaults(func=cmd_crop)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
