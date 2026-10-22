# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "docling",
#     "pandas",
# ]
# ///
"""
Stage B exploration: see what Docling actually extracts from a real 10-K.

NOTE: this carries its own inline dependency block above (PEP 723) instead
of being added to the project's pyproject.toml. Docling pins
huggingface-hub<2 across every one of its versions, which conflicts with
this project's own huggingface-hub>=2.2.0 (from the llama-index stack) --
not a version you can pick around, a hard incompatibility. Run it with
`uv run`, which builds a separate, throwaway environment for just this
script's deps, untouched by the rest of the repo:

    uv run explore_docling.py finance_rag/data/aapl-20260627.pdf --page 20

Do NOT `uv add docling` to the project -- it can't be made to resolve
against the llama-index/huggingface-hub stack in the same environment.

Checks the two things we're worried about:
  1. Tables — does Docling recover real row/column structure (vs. pypdf's
     flattened text), especially for something like AAPL's Note 10
     (Segment Information) on page 20?
  2. Headings / section structure — does Docling's layout model surface
     Item/Part boundaries we can cross-check against the SEC's canonical
     10-K Item taxonomy?

Run against the smallest filing first (AAPL, ~1.55 MB) since full-document
layout inference is slower than a plain text pull, especially on CPU.
KO/LUV are bigger (5-6 MB) — worth timing AAPL first before running those.

Install: nothing to install manually -- `uv run` reads the dependency
block at the top of this file and builds the environment for you on
first call. First run also downloads Docling's layout + TableFormer
models to a local cache; subsequent runs are fully offline.

Usage:
    uv run explore_docling.py finance_rag/data/aapl-20260627.pdf
    uv run explore_docling.py finance_rag/data/aapl-20260627.pdf --page 20
"""

import argparse
import sys
import time
from pathlib import Path

from docling.document_converter import DocumentConverter

# Labels Docling's layout model uses for heading-like text blocks.
# (If this doesn't match what you see on your installed version, run
#  `print(sorted({str(i.label) for i in doc.texts}))` once to check the
#  actual label names and adjust this tuple.)
HEADING_LABELS = ("title", "section_header")


def page_no_of(item) -> str:
    """Best-effort page number for a Docling doc item, for filtering/printing."""
    if getattr(item, "prov", None):
        return str(item.prov[0].page_no)
    return "?"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path, help="Path to a 10-K PDF")
    parser.add_argument(
        "--page",
        type=int,
        default=None,
        help="If set, only show tables/headings found on this page number "
        "(1-indexed) — e.g. --page 20 to directly compare against the "
        "Note 10 Segment Information page from the pypdf screenshot.",
    )
    args = parser.parse_args()

    if not args.pdf_path.exists():
        sys.exit(f"File not found: {args.pdf_path}")

    print(f"Converting {args.pdf_path} with Docling (first run downloads models)...")
    t0 = time.time()
    converter = DocumentConverter()
    result = converter.convert(str(args.pdf_path))
    doc = result.document
    print(f"Done in {time.time() - t0:.1f}s\n")

    # ---- 1. Headings / section structure, and -- in the same pass --
    #    the nearest preceding heading for each table, by walking the
    #    document in reading order and remembering the last heading seen.
    #    (Some period/date labels turn out to live INSIDE a table's own
    #    header row instead of as a separate heading -- see Table 19 in
    #    the first run on AAPL page 20 -- so this is a secondary signal,
    #    not the only place that context can live.)
    print("=" * 70)
    print("DETECTED HEADINGS / SECTION STRUCTURE")
    print("=" * 70)
    heading_count = 0
    last_heading = None
    heading_before_table: dict[int, str | None] = {}
    for item, level in doc.iterate_items():
        label = str(getattr(item, "label", "")).lower()
        pg = page_no_of(item)

        if label in HEADING_LABELS:
            last_heading = item.text
            if args.page is None or pg == str(args.page):
                heading_count += 1
                print(f"[page {pg}] (level {level}) {label}: {item.text!r}")
            continue

        # TableItem instances also show up in this traversal; record what
        # heading preceded each one. Matched by class name (not an import)
        # so this keeps working even if the exact import path moves --
        # if this never matches, run `print(type(item).__name__)` here
        # once to see what your installed version actually calls it.
        if type(item).__name__ == "TableItem":
            heading_before_table[id(item)] = last_heading

    if heading_count == 0:
        print("(none found" + (f" on page {args.page}" if args.page else "") + ")")

    # ---- 2. Tables, as real structured data, not flattened text --------
    print()
    print("=" * 70)
    print(f"DETECTED TABLES: {len(doc.tables)} total")
    print("=" * 70)
    shown = 0
    for i, table in enumerate(doc.tables):
        pg = page_no_of(table)
        if args.page is not None and pg != str(args.page):
            continue
        shown += 1
        nearest = heading_before_table.get(id(table))
        print(f"\n--- Table {i} (page {pg}) ---")
        print(f"Nearest preceding heading: {nearest!r}")
        # Passing `doc` (vs. the old no-arg call) is what lets Docling
        # resolve merged/multi-row header cells correctly.
        df = table.export_to_dataframe(doc)
        print(df.to_string())
    if shown == 0:
        print("(none found" + (f" on page {args.page}" if args.page else "") + ")")

    # ---- 3. Full markdown export, for a quick overall gut-check --------
    out_md = args.pdf_path.with_suffix(".docling.md")
    out_md.write_text(doc.export_to_markdown())
    print(f"\nFull markdown export written to {out_md} — skim it for anything "
          f"the two checks above didn't surface (e.g. mangled tables Docling "
          f"detected but got wrong internally).")


if __name__ == "__main__":
    main()