---
name: paper-intake-review
description: Use when extracting citation metadata from an academic PDF, proposing a filename, tags and BibTeX entry in Billy's house style, or reviewing staged papers before renaming.
---

# Paper intake and review

Turns one PDF into a **proposal**. Nothing is renamed or written to `library.bib` until Billy confirms that paper.

## Extract
- **Title**: the paper's own title only; no journal, volume, "Original Article", DOI, trailing period. Fix ALL CAPS.
- **Authors**: all of them, **in the order printed** (never reorder). Split into given / particle / family. Particles stay lowercase with the surname: de, de la, del, van, van der, von, da, di, du, le…; keep accents and hyphens.
- **Year**: publication year. Preprints use the arXiv year.
- **Type**: `article`, `unpublished` (arXiv preprint, or work in preparation), `book`, `inproceedings`, …
- Journal as its standard abbreviation (`J. Geom. Phys.`), volume, pages, DOI, arXiv id, publisher/address/edition/series/ISBN for books. Never invent a field.
- **Tags**: reuse existing tags; at most 2 new lowercase-kebab tags.

## Citation key
One letter per surname in printed order, a particle adds its lowercase initials (`de León` → `dL`), then `_` and the 4-digit year: `dLGIMR_2026`, `PV_2000`. Single author: first three letters of the surname, `Arn_1989`. ASCII-fold accents; on collision add `a`, `b`.

## Filename
`{Year}_{Authors}_{Title}.pdf`, authors in printed order. Up to 3 authors: full surnames joined by `-` (`2024_de Lucas-Rivas-Vilarino_…`). More than 3: first three letters of each surname (`2026_deLeo-Gra-Izq-Mar-Riv_…`). Plain ASCII (accents stripped, ß→ss, ł→l, other non-ASCII dropped), Windows-safe (`:` → ` -`, drop `<>"/\|?*`), ≤ 150 chars cut at a word boundary, ` (2)` on clash.

## BibTeX (see docs/bibtex-style.md)
- `author`: full `Given Surname` names joined by ` and `.
- `title = {{…}}` with math in LaTeX (`$\mathfrak{g}$`), accents as UTF-8, never flattened to ASCII; article `volume = {{\bf 35}}`; `pages = {35-55}`.
- DOI → `note = {\href{https://doi.org/DOI}{DOI}}`; arXiv → `note = {\href{https://arxiv.org/abs/ID}{ID}}` with `journal = {Preprint}`; in preparation → `note = {(in preparation)}`.

## Review
Show the original filename beside the proposed one, flag guessed fields, and wait for an explicit confirm per paper (or an explicit "confirm all of these").
