"""Turn a PDF into a metadata proposal (Gemini, with a local fallback)."""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

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
                       "convert ALL CAPS titles to normal case. Write accented letters as "
                       "normal Unicode characters (León), and math or symbols in LaTeX "
                       "between $...$ exactly as printed, e.g. $\\mathbb{R}^n$, "
                       "$\\mathfrak{g}$, $\\alpha$-Lie; never flatten them to plain ASCII.")
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
mathematical physics). From the attached first page, extract citation metadata.
Read the page itself (it may be a scan or a photo): the text layer below can be empty,
garbled or missing symbols, so trust what you see on the page over it.
Rules:
- Authors exactly in the order printed. Never reorder.
- Never invent fields. Leave a field empty when it is not on the page.
- Preprints (arXiv, no journal yet) are entry_type "unpublished".
- journal is only for real periodicals. A chapter in an edited book, memorial volume
  or Festschrift is "incollection" with the book in booktitle; a conference paper is
  "inproceedings" with the proceedings in booktitle.
- Tags: 2-5 topic tags. Existing tags: {tags}.
  Reuse an existing tag whenever it fits. Create a new tag (at most 2) only for a topic
  none of them covers, and never a synonym, plural, abbreviation or narrower variant of
  an existing one (e.g. not "lie-algebroids" when "lie-algebroid" exists). New tags are
  short lowercase-kebab topics, specific enough to be useful across many papers.
- Put anything you are unsure of in notes.
Text layer of the first page, for reference:
---
{text}
---"""


def first_pages(pdf: bytes, n: int = 1) -> bytes:
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
        notes="No Gemini key: check every field.",
        **ids,
    )


@lru_cache(maxsize=2)
def _client(api_key: str):
    """One Gemini client per key, reused across calls and threads."""
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=90_000, retry_options=types.HttpRetryOptions(attempts=2)))


def _generate(api_key: str, models: str, contents: list, schema: type[BaseModel]) -> BaseModel:
    """One structured Gemini call, falling back through the model list."""
    from google.genai import errors, types

    client = _client(api_key)
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_schema=schema, temperature=0.1,
    )
    names = [m.strip() for m in models.split(",") if m.strip()]
    for i, model in enumerate(names):
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
            break
        except errors.APIError as exc:
            # Busy (429/503) or retired (404) models fall through to the next one.
            if exc.code not in (404, 429, 500, 503) or i == len(names) - 1:
                raise
    return resp.parsed or schema.model_validate_json(resp.text)


def gemini(pdf: bytes, existing_tags: list[str], api_key: str, models: str) -> Extraction:
    from google.genai import types

    prompt = PROMPT.format(tags=", ".join(existing_tags) or "(none yet)",
                           text=page_text(pdf, 1).strip()[:6000] or "(none: scanned page)")
    contents = [types.Part.from_bytes(data=first_pages(pdf), mime_type="application/pdf"),
                prompt]
    result = _generate(api_key, models, contents, Extraction)
    # Identifiers found in the text layer beat the model's reading of them.
    for k, v in _identifiers(page_text(pdf)).items():
        setattr(result, k, getattr(result, k) or v)
    return result


class Venue(BaseModel):
    kind: str = Field(description="journal (a real periodical), proceedings (conference "
                      "proceedings volume), book (edited book, festschrift, memorial volume, "
                      "lecture notes), or unknown")
    abbreviation: str = Field("", description="For a journal: its official ISO 4 "
                              "abbreviation, e.g. 'J. Geom. Phys.'. Empty otherwise.")
    name: str = Field("", description="Full canonical name of the venue")


VENUE_PROMPT = """Is "{name}" an academic journal (a periodical with volumes and issues)?
Use your knowledge of real journals. Memorial volumes ("in Memoriam"), Festschrifts,
edited books and lecture-note volumes are books, not journals. If it is a journal, give
its ISO 4 abbreviation (keep it if "{name}" already is one). Do not invent journals."""


def check_venue(name: str, api_key: str, models: str) -> Venue:
    return _generate(api_key, models, [VENUE_PROMPT.format(name=name)], Venue)


def extract(pdf: bytes, existing_tags: list[str], api_key: str, model: str) -> Extraction:
    if api_key:
        return gemini(pdf, existing_tags, api_key, model)
    return heuristic(pdf, existing_tags)
