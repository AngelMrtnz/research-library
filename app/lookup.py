"""Find the published version of a paper online (arXiv and Crossref, free, no key).

Used after extraction when a paper looks like a preprint or has no journal. It only
fills the proposal shown on the review screen; nothing is confirmed automatically.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

from .names import ascii_fold

log = logging.getLogger(__name__)
TIMEOUT = 8
HEADERS = {"User-Agent": "ResearchLibrary/1.0 (personal paper manager)"}
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", ascii_fold(re.sub(r"\$[^$]*\$", " ", text)).lower()).strip()


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def arxiv_info(arxiv_id: str) -> dict:
    """DOI and journal reference the authors added to arXiv after publication."""
    xml = _get("https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id))
    entry = ET.fromstring(xml).find("a:entry", ATOM)
    if entry is None:
        return {}
    out = {}
    for key in ("doi", "journal_ref"):
        el = entry.find(f"arxiv:{key}", ATOM)
        if el is not None and el.text:
            out[key] = el.text.strip()
    return out


def crossref_doi(doi: str) -> dict | None:
    if doi.lower().startswith("10.48550/"):  # arXiv's own DOI: not a publication
        return None
    try:
        data = json.loads(_get("https://api.crossref.org/works/" + urllib.parse.quote(doi)))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return data.get("message")


def crossref_search(title: str, first_author: str) -> dict | None:
    """Best journal-article match by title and first author, or None if unsure."""
    q = urllib.parse.urlencode({
        "query.bibliographic": title, "query.author": first_author, "rows": 5,
        "filter": "type:journal-article",
        "select": "title,container-title,short-container-title,volume,issue,page,DOI,"
                  "issued,type,author",
    })
    items = json.loads(_get("https://api.crossref.org/works?" + q))["message"]["items"]
    return pick(items, title, first_author)


def pick(items: list[dict], title: str, first_author: str) -> dict | None:
    surname = _norm(first_author)
    for it in items:
        t = (it.get("title") or [""])[0]
        authors = [_norm(a.get("family", "")) for a in it.get("author", [])]
        if similar(t, title) >= 0.9 and (not surname or surname in authors[:1]):
            return it
    return None


def journal_name(item: dict, journal_ref: str = "") -> str:
    """Prefer an abbreviated name: Crossref's short title, else the arXiv journal_ref."""
    full = (item.get("container-title") or [""])[0]
    short = (item.get("short-container-title") or [""])[0]
    if short and short != full:
        return short
    if m := re.match(r"\s*([A-Za-z][A-Za-z.\s&-]*?\.)\s*\d", journal_ref):
        return m.group(1).strip()
    return full


def fields_from(item: dict, journal_ref: str = "") -> dict:
    """Entry fields, plus ``abbreviated`` when the journal name is already the short form."""
    year = ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    journal = journal_name(item, journal_ref)
    return {k: v for k, v in {
        "entry_type": "article",
        "journal": journal,
        "abbreviated": journal != (item.get("container-title") or [""])[0],
        "volume": item.get("volume", ""),
        "number": item.get("issue", ""),
        "pages": item.get("page", ""),
        "year": year,
        "doi": item.get("DOI", ""),
    }.items() if v}


def published_version(title: str, first_author: str, doi: str = "", arxiv: str = "") -> dict:
    """Fields of the published version, or {} when none is found or the lookup fails."""
    try:
        ref = arxiv_info(arxiv) if arxiv else {}
        doi = doi or ref.get("doi", "")
        item = crossref_doi(doi) if doi else None
        if item is None and title:
            item = crossref_search(title, first_author)
        if item is None or item.get("type") not in (None, "journal-article"):
            return {}
        return fields_from(item, ref.get("journal_ref", ""))
    except Exception as exc:  # noqa: BLE001 - offline or API hiccup: just skip
        log.warning("online lookup failed for %r: %s", title[:60], exc)
        return {}
