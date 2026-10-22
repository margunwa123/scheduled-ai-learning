# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "docling",
#     "pandas",
#     "tabulate",
# ]
# ///
"""
Stage B: parse one 10-K/10-Q PDF into a structured JSON artifact, decoupled
from the LlamaIndex/pgvector ingestion stage (see explore_docling.py's
notes on why: docling pins huggingface-hub<2, which conflicts with this
project's own huggingface-hub>=2.2.0 -- these two can never share one
environment, run this with `uv run`, not `uv add docling`).

Produces finance_rag/data/parsed/<ticker>.json: a list of
    {type: "paragraph"|"table", text, page, section, company, fiscal_period}
records, section-tagged by walking the document in reading order and
tracking the most recent Item/Part-level heading. Matched by a GENERIC
SEC heading pattern, not a fixed per-form-type list -- 10-K and 10-Q share
the same "Item N."/"PART N" convention, they just differ in which items
exist, so this works regardless of which form type a given file turns out
to be.

Also writes <ticker>.validation.md -- don't trust the regex blindly:
  1. every Item/Part heading it matched, in document order
  2. a best-effort cross-check against the filing's own Table of Contents
     (if Docling found a table shaped like one) -- free ground truth
  3. every OTHER non-noise heading it did NOT match, so you can skim for
     anything that should have been Item/Part level but wasn't worded
     the standard way (a real false negative, not just noise)

Usage:
    uv run parse_filing.py finance_rag/data/aapl-20260627.pdf AAPL
    uv run parse_filing.py finance_rag/data/ko-20251231.pdf KO
    uv run parse_filing.py finance_rag/data/luv-20251231.pdf LUV
"""

import argparse
import json
import re
import sys
from pathlib import Path

from docling.document_converter import DocumentConverter

# If your installed docling version uses different label strings, run
# `print(sorted({str(i.label) for i,_ in doc.iterate_items()}))` once and
# adjust this.
HEADING_LABELS = ("title", "section_header")

# SEC's standard Item/Part heading convention -- shared by 10-K and 10-Q.
SECTION_RE = re.compile(r"^(PART\s+[IVX]+\b|Item\s+\d+[A-Z]?\.?)", re.IGNORECASE)

# A heading repeated across this many distinct pages is almost certainly a
# running document title (e.g. "Apple Inc." on every statement page), not
# real structure.
NOISE_REPEAT_THRESHOLD = 3

# A heading that's just a parenthesized unit label ("(In millions)") --
# must wrap the WHOLE string, so this one stays anchored with .match().
UNIT_LABEL_RE = re.compile(r"^\(.*\)$")

# A running footer ("Apple Inc. | Q3 2026 Form 10-Q | 17") -- the page
# number at the end means exact-text-repeat counting can never catch this
# (every occurrence is a different string), so this pattern is the only
# thing that can. Uses .search(), not .match(): the footer doesn't START
# with "|", "Apple Inc. " comes first, so an anchored match() never fires.
# Caught and confirmed missing this exact way on the first real AAPL run --
# don't re-introduce a start-anchored check here.
FOOTER_RE = re.compile(r"\|.*\|\s*\d+\s*$")


def is_pattern_noise(text: str) -> bool:
    return bool(UNIT_LABEL_RE.match(text) or FOOTER_RE.search(text))


def page_no_of(item) -> str:
    if getattr(item, "prov", None):
        return str(item.prov[0].page_no)
    return "?"


def find_noise_headings(doc) -> set[str]:
    """First pass: flag headings that repeat across many pages, or match a
    known boilerplate shape, so the second pass can skip them as section
    anchors (and drop them from the output entirely -- pure boilerplate,
    no retrieval value)."""
    pages_per_heading: dict[str, set[str]] = {}
    for item, _level in doc.iterate_items():
        label = str(getattr(item, "label", "")).lower()
        if label not in HEADING_LABELS:
            continue
        pages_per_heading.setdefault(item.text, set()).add(page_no_of(item))

    noise = set()
    for text, pages in pages_per_heading.items():
        if len(pages) >= NOISE_REPEAT_THRESHOLD:
            noise.add(text)
        elif is_pattern_noise(text):
            noise.add(text)
    return noise


def parse_pdf(pdf_path: Path, company: str, fiscal_period: str):
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    doc = result.document

    noise_headings = find_noise_headings(doc)

    records = []
    current_section = None
    matched_sections: list[tuple[str, str]] = []  # (text, page), in order

    for item, _level in doc.iterate_items():
        label = str(getattr(item, "label", "")).lower()
        pg = page_no_of(item)

        if label in HEADING_LABELS:
            text = item.text
            if text in noise_headings:
                continue
            if SECTION_RE.match(text):
                current_section = text
                matched_sections.append((text, pg))
            # Non-matching, non-noise headings ("Net sales:", "iPhone")
            # aren't section anchors, but they're real document text --
            # keep them as plain content under whatever section they're in.
            records.append({
                "type": "paragraph", "text": text, "page": pg,
                "section": current_section, "company": company,
                "fiscal_period": fiscal_period,
            })
            continue

        if type(item).__name__ == "TableItem":
            try:
                df = item.export_to_dataframe(doc)
                table_text = df.to_markdown(index=False)
            except Exception as exc:  # noqa: BLE001 -- surface, don't crash the whole parse
                print(f"  [warn] table on page {pg} failed to export ({exc}); skipped")
                continue
            records.append({
                "type": "table", "text": table_text, "page": pg,
                "section": current_section, "company": company,
                "fiscal_period": fiscal_period,
            })
            continue

        # Catch-all for ordinary body text items -- deliberately checking
        # for a non-empty `.text` rather than a specific class name, since
        # we don't want to guess every item-type name docling might use.
        #
        # The pattern check has to run here too, not just in the heading
        # branch above: confirmed on the real AAPL run that Docling does
        # NOT consistently label every occurrence of the same running
        # footer as a heading across pages -- some instances get
        # section_header/title (caught above), others apparently land
        # here instead, bypassing that check entirely. Pattern-matching
        # is stateless (doesn't need the first-pass repeat count), so it
        # can just run again here independent of which branch an item
        # happened to land in.
        text = getattr(item, "text", None)
        if text and text.strip():
            if is_pattern_noise(text):
                continue
            records.append({
                "type": "paragraph", "text": text, "page": pg,
                "section": current_section, "company": company,
                "fiscal_period": fiscal_period,
            })

    return doc, records, matched_sections, noise_headings


def toc_rows_from(doc):
    """Best-effort: find a table shaped like the filing's own Table of
    Contents (first column full of 'Item N.'-style text), to cross-check
    the regex matches against ground truth from the document itself.
    Not foolproof -- TOC tables sometimes split "Part"/"I" into separate
    columns -- treat this as a hint, not a verdict."""
    for table in doc.tables:
        try:
            df = table.export_to_dataframe(doc)
        except Exception:
            continue
        if df.empty:
            continue
        first_col = df.iloc[:, 0].astype(str)
        if first_col.str.contains(r"Item\s+\d", case=False, regex=True).sum() >= 3:
            return df
    return None


def write_validation_report(out_path: Path, matched_sections, noise_headings, doc):
    lines = ["# Section-detection validation\n"]

    lines.append(f"## Item/Part headings matched by the regex, in document order "
                 f"({len(matched_sections)} total)\n")
    for text, pg in matched_sections:
        lines.append(f"- [page {pg}] {text!r}")

    toc = toc_rows_from(doc)
    if toc is not None:
        lines.append("\n## Cross-check against the filing's own Table of Contents\n")
        lines.append("(best-effort substring match -- eyeball anything flagged)\n")
        matched_lower = [t.lower() for t, _ in matched_sections]
        for _, row in toc.iterrows():
            label = str(row.iloc[0]).strip()
            if not re.search(r"item\s+\d", label, re.IGNORECASE):
                continue  # skip "Part"/blank rows, too generic to match usefully
            row_text = " ".join(str(v) for v in row if str(v).strip())
            hit = any(label.lower() in m for m in matched_lower)
            flag = "OK" if hit else "**NOT MATCHED -- check this one**"
            lines.append(f"- {row_text} -> {flag}")
    else:
        lines.append("\n## No Table-of-Contents-shaped table found to cross-check against.\n")

    lines.append("\n## Non-noise headings that did NOT match the Item/Part regex\n")
    lines.append("(expected to be mostly real sub-headings -- skim for anything that "
                  "looks like it should have been Item/Part level but wasn't worded "
                  "the standard way)\n")
    matched_text_set = {t for t, _ in matched_sections}
    seen = set()
    for item, _level in doc.iterate_items():
        label = str(getattr(item, "label", "")).lower()
        if label not in HEADING_LABELS:
            continue
        text = item.text
        if text in noise_headings or text in matched_text_set or text in seen:
            continue
        seen.add(text)
        lines.append(f"- [page {page_no_of(item)}] {text!r}")

    out_path.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("company", help="Ticker, e.g. AAPL")
    parser.add_argument("--fiscal-period", default=None,
                         help="Defaults to the date suffix in the filename, e.g. 20260627")
    parser.add_argument("--out-dir", type=Path, default=Path("finance_rag/data/parsed"))
    args = parser.parse_args()

    if not args.pdf_path.exists():
        sys.exit(f"File not found: {args.pdf_path}")

    fiscal_period = args.fiscal_period or args.pdf_path.stem.split("-", 1)[-1]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Parsing {args.pdf_path} ({args.company}, {fiscal_period})...")
    doc, records, matched_sections, noise_headings = parse_pdf(
        args.pdf_path, args.company, fiscal_period
    )

    out_json = args.out_dir / f"{args.company}.json"
    out_json.write_text(json.dumps(records, indent=2))

    out_report = args.out_dir / f"{args.company}.validation.md"
    write_validation_report(out_report, matched_sections, noise_headings, doc)

    n_tables = sum(1 for r in records if r["type"] == "table")
    n_paragraphs = len(records) - n_tables
    print(f"Wrote {len(records)} records ({n_paragraphs} paragraph, {n_tables} table) "
          f"to {out_json}")
    print(f"{len(matched_sections)} Item/Part sections matched; "
          f"{len(noise_headings)} noise headings filtered")
    print(f"Validation report: {out_report}")


if __name__ == "__main__":
    main()