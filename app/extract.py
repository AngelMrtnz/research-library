"""Turn a PDF into a metadata proposal (Gemini, with a local fallback)."""

from __future__ import annotations

import re
from collections import Counter

import pymupdf
from pydantic import BaseModel, Field

from .names import Author, parse_author

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+[^\s\"<>.,;)\]])", re.I)
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?", re.I)
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


class Extraction(BaseModel):
    entry_type: str = Field(description="article, unpublished (preprints and work in "
                            "preparation), book, inproceedings, incollection, phdthesis, "
                            "techreport or misc")
    title: str = Field(description="The paper's own title only: no journal name, volume, "
                       "'Original Article', DOI or trailing period. Keep its capitalization; "
                       "convert ALL CAPS titles to normal case.")
    authors: list[Author] = Field(description="All authors in the order printed. given = "
                                  "given names as printed, particle = lowercase surname "
                                  "particle such as 'de', 'van der', family = surname. "
                                  "Keep accents and hyphens.")
    year: int | None = Field(description="Publication year, not the received/accepted date.")
    journal: str = Field("", description="Standard ISO4 abbreviation, e.g. 'J. Geom. Phys.'")
    booktitle: str = ""
    volume: str = ""
    number: str = ""
    pages: str = Field("", description="e.g. 35-55")
    publisher: str = ""
    address: str = ""
    edition: str = ""
    isbn: str = ""
    series: str = ""
    doi: str = Field("", description="Bare DOI like 10.1016/..., no URL prefix")
    arxiv: str = Field("", description="arXiv id like 2606.20030, no version")
    tags: list[str] = Field(default_factory=list, description="2-5 topic tags chosen from "
                            "the existing tag list")
    new_tags: list[str] = Field(default_factory=list, description="At most 2 new "
                                "lowercase-kebab tags, only if no existing tag fits")
    notes: str = Field("", description="Anything uncertain or guessed, for the reviewer")


PROMPT = """You catalogue academic papers for a personal library (mostly mathematics and
mathematical physics). From the attached first pages, extract citation metadata.
Rules:
- Authors exactly in the order printed. Never reorder.
- Never invent fields. Leave a field empty when it is not on the page.
- Preprints (arXiv, no journal yet) are entry_type "unpublished".
- Tags: prefer these existing tags: {tags}. Add at most 2 new tags.
- Put anything you are unsure of in notes.
Text layer of the first page, for reference:
---
{text}
---"""


def first_pages(pdf: bytes, n: int = 2) -> bytes:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        out = pymupdf.open()
        out.insert_pdf(doc, from_page=0, to_page=min(n, doc.page_count) - 1)
        return out.tobytes()


def page_text(pdf: bytes, pages: int = 2) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return "\n".join(doc[i].get_text() for i in range(min(pages, doc.page_count)))


def render_preview(pdf: bytes, width: int = 900) -> bytes:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        zoom = width / page.rect.width
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")


def _identifiers(text: str) -> dict:
    found = {}
    if m := DOI_RE.search(text):
        found["doi"] = m.group(1)
    if m := ARXIV_RE.search(text):
        found["arxiv"] = m.group(1)
    return found


def heuristic(pdf: bytes, existing_tags: list[str]) -> Extraction:
    """No-AI fallback: PDF metadata, then the biggest text on page one."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        meta = doc.metadata or {}
        spans = [
            (round(s["size"], 1), s["text"].strip())
            for b in doc[0].get_text("dict")["blocks"] for line in b.get("lines", [])
            for s in line["spans"] if s["text"].strip()
        ]
    text = page_text(pdf)
    title = (meta.get("title") or "").strip()
    if not title and spans:
        biggest = max(size for size, _ in spans)
        title = " ".join(t for size, t in spans if size == biggest)
    authors = [parse_author(a) for a in re.split(r";| and |,(?=\s*\w+\s\w)",
                                                  meta.get("author") or "") if a.strip()]
    years = Counter(YEAR_RE.findall(text))
    ids = _identifiers(text)
    return Extraction(
        entry_type="unpublished" if "arxiv" in ids else "article",
        title=title, authors=authors,
        year=int(years.most_common(1)[0][0]) if years else None,
        notes="Extracted without AI (no Gemini key): check every field.",
        **ids,
    )


def gemini(pdf: bytes, existing_tags: list[str], api_key: str, model: str) -> Extraction:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = PROMPT.format(tags=", ".join(existing_tags) or "(none yet)",
                           text=page_text(pdf, 1)[:6000])
    resp = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=first_pages(pdf), mime_type="application/pdf"),
                  prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=Extraction,
            temperature=0.1,
        ),
    )
    result = resp.parsed or Extraction.model_validate_json(resp.text)
    # Identifiers found in the text layer beat the model's reading of them.
    for k, v in _identifiers(page_text(pdf)).items():
        setattr(result, k, getattr(result, k) or v)
    return result


def extract(pdf: bytes, existing_tags: list[str], api_key: str, model: str) -> Extraction:
    if api_key:
        return gemini(pdf, existing_tags, api_key, model)
    return heuristic(pdf, existing_tags)
