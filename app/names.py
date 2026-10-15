"""Author parsing, citation keys and Windows-safe filenames.

House rules (see PLAN.md / bibtex-style.md):
- Authors always keep the order printed on the paper.
- Citation key: one letter per surname (particle adds its lowercase initials,
  ``de León`` -> ``dL``), then ``_`` and the 4-digit year. A single author
  uses the first three letters of the surname (``Arn_1989``).
- Filename: ``{Year}_{Authors}_{Title}.pdf``. Up to ``FULL_NAME_LIMIT``
  authors use full surnames joined by ``-``; more use 3-letter surnames.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel

FULL_NAME_LIMIT = 3
MAX_FILENAME = 150

# Lowercase particles that belong to the surname. Multi-word ones first.
PARTICLES = [
    "van der", "van den", "van de", "von der", "von dem", "de la", "de las",
    "de los", "de l'", "della", "delle", "del", "de", "da", "das", "do", "dos",
    "du", "di", "van", "von", "le", "la", "ter", "ten", "zu", "bin", "ibn", "al",
]
_PARTICLE_RE = re.compile(
    r"^(.*?)\s+(" + "|".join(re.escape(p) for p in PARTICLES) + r")\s+(\S.*)$"
)


class Author(BaseModel):
    given: str = ""
    particle: str = ""
    family: str

    @property
    def surname(self) -> str:
        """Surname with particle, as printed: ``de León``."""
        return f"{self.particle} {self.family}".strip()

    @property
    def full(self) -> str:
        """``Manuel de León``: the BibTeX form in Billy's style."""
        return " ".join(p for p in (self.given, self.particle, self.family) if p)

    @property
    def display(self) -> str:
        """``M. de León``: initials + full surname."""
        initials = " ".join(_initial(part) for part in self.given.split())
        return " ".join(p for p in (initials, self.particle, self.family) if p)


def _initial(name: str) -> str:
    if name.endswith("."):
        return name
    # Hyphenated given names: Jean-Pierre -> J.-P.
    return "-".join(p[0] + "." for p in name.split("-") if p)


def parse_author(text: str) -> Author:
    """Parse ``Given [particle] Family`` or ``[particle] Family, Given``."""
    text = re.sub(r"\s+", " ", text).strip().strip(",")
    if "," in text:
        family, given = (s.strip() for s in text.split(",", 1))
        for p in sorted(PARTICLES, key=len, reverse=True):
            if family.startswith(p + " "):
                return Author(given=given, particle=p, family=family[len(p) + 1:])
        return Author(given=given, family=family)
    m = _PARTICLE_RE.match(text)
    if m:
        return Author(given=m.group(1), particle=m.group(2), family=m.group(3))
    parts = text.rsplit(" ", 1)
    if len(parts) == 1:
        return Author(family=parts[0])
    return Author(given=parts[0], family=parts[1])


def ascii_fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c))


def _letters(text: str) -> str:
    return re.sub(r"[^A-Za-z]", "", ascii_fold(text))


def _particle_initials(particle: str) -> str:
    return "".join(_letters(w)[:1].lower() for w in particle.split())


def citation_key(authors: list[Author], year: int | str | None) -> str:
    """``dLGIMR_2026``, ``PV_2000``, ``Arn_1989``."""
    if not authors:
        stem = "Anon"
    elif len(authors) == 1:
        a = authors[0]
        stem = _particle_initials(a.particle) + _letters(a.family)[:3]
    else:
        stem = "".join(
            _particle_initials(a.particle) + _letters(a.family)[:1].upper()
            for a in authors
        )
    return f"{stem}_{year or 'nd'}"


def unique_key(key: str, taken: set[str]) -> str:
    if key not in taken:
        return key
    for suffix in "abcdefghijklmnopqrstuvwxyz":
        if key + suffix not in taken:
            return key + suffix
    raise ValueError(f"too many collisions for {key}")


_INVALID = re.compile(r'[<>"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}


def sanitize(text: str) -> str:
    """Make text safe for a Windows filename component."""
    text = text.replace(":", " -")
    text = _INVALID.sub("", text)
    text = re.sub(r"\s+", " ", text).strip().rstrip(". ")
    if text.upper() in _RESERVED:
        text = f"_{text}"
    return text


def authors_for_filename(authors: list[Author]) -> str:
    if not authors:
        return "Anon"
    if len(authors) <= FULL_NAME_LIMIT:
        return "-".join(a.surname for a in authors)
    return "-".join(a.particle.replace(" ", "") + a.family[:3] for a in authors)


def build_filename(year: int | str | None, authors: list[Author], title: str) -> str:
    head = sanitize(f"{year or 'nd'}_{authors_for_filename(authors)}_")
    title = sanitize(title) or "Untitled"
    room = MAX_FILENAME - len(head) - len(".pdf")
    if len(title) > room:
        cut = title[:room]
        title = cut.rsplit(" ", 1)[0] if " " in cut else cut
        title = title.rstrip(" -.,;")
    return f"{head}{title}.pdf"


def dedupe_filename(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    stem = name[: -len(".pdf")]
    n = 2
    while f"{stem} ({n}).pdf" in taken:
        n += 1
    return f"{stem} ({n}).pdf"
