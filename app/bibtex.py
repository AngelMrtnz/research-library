"""BibTeX in Billy's house style (see bibtex-style.md)."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .names import Author

ENTRY_TYPES = ["article", "unpublished", "book", "inproceedings", "incollection",
               "phdthesis", "techreport", "misc"]

# Field order per entry type, taken from Billy's examples where available.
FIELD_ORDER = {
    "article": ["title", "author", "journal", "year", "volume", "number", "pages",
                "url", "note"],
    "unpublished": ["author", "title", "year", "journal", "url", "note"],
    "book": ["author", "title", "address", "edition", "isbn", "publisher", "series",
             "volume", "year", "url", "note"],
    "inproceedings": ["title", "author", "booktitle", "year", "pages", "publisher",
                      "address", "url", "note"],
    "incollection": ["title", "author", "booktitle", "editor", "year", "pages",
                     "publisher", "address", "url", "note"],
    "phdthesis": ["author", "title", "school", "year", "url", "note"],
    "techreport": ["author", "title", "institution", "number", "year", "url", "note"],
    "misc": ["author", "title", "year", "howpublished", "url", "note"],
}


class Entry(BaseModel):
    """Everything needed to render one citation."""

    entry_type: str = "article"
    key: str
    title: str
    authors: list[Author] = Field(default_factory=list)
    year: int | None = None
    journal: str = ""
    booktitle: str = ""
    volume: str = ""
    number: str = ""
    pages: str = ""
    publisher: str = ""
    address: str = ""
    edition: str = ""
    isbn: str = ""
    series: str = ""
    school: str = ""
    institution: str = ""
    editor: str = ""
    howpublished: str = ""
    doi: str = ""
    arxiv: str = ""
    url: str = ""
    note: str = ""


def note_value(e: Entry) -> str:
    """DOI or arXiv link as ``\\href``; otherwise the free-text note."""
    if e.doi:
        return rf"\href{{https://doi.org/{e.doi}}}{{{e.doi}}}"
    if e.arxiv:
        return rf"\href{{https://arxiv.org/abs/{e.arxiv}}}{{{e.arxiv}}}"
    return e.note


def field_values(e: Entry) -> dict[str, str]:
    values = {
        "author": " and ".join(a.full for a in e.authors),
        "title": f"{{{e.title}}}",
        "year": str(e.year) if e.year else "",
        "journal": e.journal or ("Preprint" if e.entry_type == "unpublished" and e.arxiv else ""),
        "booktitle": e.booktitle,
        "volume": e.volume,
        "number": e.number,
        "pages": re.sub(r"\s*(--|–|—|-)\s*", "-", e.pages),
        "publisher": e.publisher,
        "address": e.address,
        "edition": e.edition,
        "isbn": e.isbn,
        "series": e.series,
        "school": e.school,
        "institution": e.institution,
        "editor": e.editor,
        "howpublished": e.howpublished,
        "url": e.url,
        "note": note_value(e),
    }
    if e.entry_type == "article" and e.volume:
        values["volume"] = rf"{{\bf {e.volume}}}"
    return values


def render(e: Entry) -> str:
    order = FIELD_ORDER.get(e.entry_type, FIELD_ORDER["misc"])
    values = field_values(e)
    lines = [f"@{e.entry_type}{{{e.key},"]
    for name in order:
        if values.get(name):
            lines.append(f"  {name} = {{{values[name]}}},")
    lines.append("}")
    return "\n".join(lines)


def render_library(bibtex_entries: list[str]) -> str:
    return "\n\n".join(b.strip() for b in bibtex_entries) + "\n"
