# BibTeX style (Billy's house style)

These are Billy's own examples, with keys updated to the confirmed 4-digit year (`PV_00` → `PV_2000`, `Arn_89` → `Arn_1989`, `LRV_24` → `dLRV_2024` under the default particle rule). The app's `bibtex.py` must reproduce them exactly. They double as golden test fixtures.

## Rules
- **Key**: one letter per author surname in the order printed on the paper, then `_` and the 4-digit year. Particle adds its lowercase initial (`de León` → `dL`). Single author: first three letters of the surname. Accents folded to ASCII. _(Particle still to be confirmed: `dL` as in `dLGIMR_2026`, or `L` as in `LRV_24`.)_
- **author**: full `Given Surname` names joined by ` and `, UTF-8 accents.
- **title**: double braces `{{…}}`.
- **journal**: standard abbreviation (`J. Geom. Phys.`). Preprints: `journal = {Preprint}` on an `@unpublished`.
- **volume** (articles): bold, `{{\bf 35}}`. Books: plain.
- **pages**: single hyphen, `35-55`.
- **note**: DOI as `\href{https://doi.org/DOI}{DOI}`; arXiv as `\href{https://arxiv.org/abs/ID}{ID}`; work in progress `(in preparation)`.
- **url**: optional (e.g. Semantic Scholar).
- **Books**: `address, edition, isbn, publisher, series, volume, year`.

## Examples

```bibtex
@unpublished{dLGIMR_2026,
  author = {Manuel de León and Xavier Gràcia and Rubén Izquierdo-López and {\'A}ngel Martínez-Muñoz and Xavier Rivas},
  title = {{From 2-covariant tensor fields to Poisson and Jacobi structures}},
  year = {2026},
  journal = {Preprint},
  note = {\href{https://arxiv.org/abs/2606.20030}{2606.20030}},
}

@article{PV_2000,
  title = {{On the geometry of singular Lagrangians}},
  author = {Fabrizio Pugliese and Alexandre M. Vinogradov},
  journal = {J. Geom. Phys.},
  year = {2000},
  volume = {{\bf 35}},
  pages = {35-55},
  url = {https://api.semanticscholar.org/CorpusID:120620170},
  note = {\href{https://doi.org/10.1016/S0393-0440(99)00076-5}{10.1016/S0393-0440(99)00076-5}},
}

@book{Arn_1989,
  author = {Vladimir I. Arnold},
  title = {{Mathematical Methods of Classical Mechanics}},
  address = {New York},
  edition = {2nd},
  isbn = {0387968903},
  publisher = {Springer},
  series = {Graduate Texts in Mathematics},
  volume = {60},
  year = {1989},
  note = {\href{https://doi.org/10.1007/978-1-4757-1693-1}{10.1007/978-1-4757-1693-1}},
}

@unpublished{dLRV_2024,
  title = {{Multisymplectic reductions induced by polycosymplectic structures}},
  author = {Javier de Lucas and Xavier Rivas and Silvia Vilariño},
  note = {(in preparation)},
  year = {2024},
}
```

## Matching filenames (authors in printed order, ASCII only)
- `2026_deLeo-Gra-Izq-Mar-Riv_From 2-covariant tensor fields to Poisson and Jacobi structures.pdf`
- `2000_Pugliese-Vinogradov_On the geometry of singular Lagrangians.pdf`
- `1989_Arnold_Mathematical Methods of Classical Mechanics.pdf`
- `2024_de Lucas-Rivas-Vilarino_Multisymplectic reductions induced by polycosymplectic structures.pdf`
