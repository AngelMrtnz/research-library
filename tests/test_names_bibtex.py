from app.bibtex import Entry, render
from app.names import (
    Author,
    build_filename,
    citation_key,
    dedupe_filename,
    parse_author,
    sanitize,
    unique_key,
)

DLGIMR = [parse_author(n) for n in [
    "Manuel de León", "Xavier Gràcia", "Rubén Izquierdo-López",
    "Ángel Martínez-Muñoz", "Xavier Rivas",
]]
PV = [parse_author("Fabrizio Pugliese"), parse_author("Alexandre M. Vinogradov")]
ARN = [parse_author("Vladimir I. Arnold")]
LRV = [parse_author(n) for n in ["Javier de Lucas", "Xavier Rivas", "Silvia Vilariño"]]


def test_parse_particles():
    a = parse_author("Manuel de León")
    assert (a.given, a.particle, a.family) == ("Manuel", "de", "León")
    b = parse_author("van der Waals, Johannes Diderik")
    assert (b.given, b.particle, b.family) == ("Johannes Diderik", "van der", "Waals")
    c = parse_author("Rubén Izquierdo-López")
    assert c.family == "Izquierdo-López" and c.particle == ""
    assert parse_author("Ludwig van Beethoven").surname == "van Beethoven"


def test_display_initials():
    assert parse_author("Juan Antonio de León").display == "J. A. de León"
    assert parse_author("Jean-Pierre Serre").display == "J.-P. Serre"
    assert parse_author("Alexandre M. Vinogradov").display == "A. M. Vinogradov"


def test_citation_keys_from_billys_examples():
    assert citation_key(DLGIMR, 2026) == "dLGIMR_2026"
    assert citation_key(PV, 2000) == "PV_2000"
    assert citation_key(ARN, 1989) == "Arn_1989"
    assert citation_key(LRV, 2024) == "dLRV_2024"


def test_key_collision():
    assert unique_key("PV_2000", {"PV_2000", "PV_2000a"}) == "PV_2000b"


def test_filenames():
    assert build_filename(2000, PV, "On the geometry of singular Lagrangians") == (
        "2000_Pugliese-Vinogradov_On the geometry of singular Lagrangians.pdf")
    assert build_filename(1989, ARN, "Mathematical Methods of Classical Mechanics") == (
        "1989_Arnold_Mathematical Methods of Classical Mechanics.pdf")
    assert build_filename(2024, LRV, "Multisymplectic reductions") == (
        "2024_de Lucas-Rivas-Vilarino_Multisymplectic reductions.pdf")
    assert build_filename(2026, DLGIMR, "From 2-covariant tensor fields") == (
        "2026_deLeo-Gra-Izq-Mar-Riv_From 2-covariant tensor fields.pdf")


def test_filename_sanitized_and_short():
    name = build_filename(2020, PV, 'Lie groups: a "primer" / why? ' + "word " * 60)
    assert len(name) <= 150 and name.endswith(".pdf")
    assert not any(c in name for c in '<>:"/\\|?*')
    assert "Lie groups - a primer why" in name
    assert sanitize("CON") == "_CON"
    assert dedupe_filename("a.pdf", {"a.pdf", "a (2).pdf"}) == "a (3).pdf"


def test_render_article_exact():
    e = Entry(
        entry_type="article", key="PV_2000",
        title="On the geometry of singular Lagrangians", authors=PV, year=2000,
        journal="J. Geom. Phys.", volume="35", pages="35--55",
        url="https://api.semanticscholar.org/CorpusID:120620170",
        doi="10.1016/S0393-0440(99)00076-5",
    )
    assert render(e) == r"""@article{PV_2000,
  title = {{On the geometry of singular Lagrangians}},
  author = {Fabrizio Pugliese and Alexandre M. Vinogradov},
  journal = {J. Geom. Phys.},
  year = {2000},
  volume = {{\bf 35}},
  pages = {35-55},
  url = {https://api.semanticscholar.org/CorpusID:120620170},
  note = {\href{https://doi.org/10.1016/S0393-0440(99)00076-5}{10.1016/S0393-0440(99)00076-5}},
}"""


def test_render_book_exact():
    e = Entry(
        entry_type="book", key="Arn_1989",
        title="Mathematical Methods of Classical Mechanics", authors=ARN, year=1989,
        address="New York", edition="2nd", isbn="0387968903", publisher="Springer",
        series="Graduate Texts in Mathematics", volume="60",
        doi="10.1007/978-1-4757-1693-1",
    )
    assert render(e) == r"""@book{Arn_1989,
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
}"""


def test_render_preprint():
    e = Entry(
        entry_type="unpublished", key="dLGIMR_2026",
        title="From 2-covariant tensor fields to Poisson and Jacobi structures",
        authors=DLGIMR, year=2026, arxiv="2606.20030",
    )
    assert render(e) == r"""@unpublished{dLGIMR_2026,
  author = {Manuel de León and Xavier Gràcia and Rubén Izquierdo-López and Ángel Martínez-Muñoz and Xavier Rivas},
  title = {{From 2-covariant tensor fields to Poisson and Jacobi structures}},
  year = {2026},
  journal = {Preprint},
  note = {\href{https://arxiv.org/abs/2606.20030}{2606.20030}},
}"""


def test_render_in_preparation():
    e = Entry(entry_type="unpublished", key="dLRV_2024",
              title="Multisymplectic reductions induced by polycosymplectic structures",
              authors=LRV, year=2024, note="(in preparation)")
    out = render(e)
    assert "note = {(in preparation)}" in out and "journal" not in out
    assert "author = {Javier de Lucas and Xavier Rivas and Silvia Vilariño}" in out


def test_author_model_roundtrip():
    a = Author(given="Manuel", particle="de", family="León")
    assert Author.model_validate(a.model_dump()) == a


def test_filenames_are_ascii():
    authors = [parse_author("Łukasz Großmann"), parse_author("Søren Ødegård")]
    name = build_filename(2021, authors, "Lie–Poisson “brackets” on Æ-manifolds: ∞-jets")
    assert name == "2021_Grossmann-Odegard_Lie-Poisson brackets on AE-manifolds - -jets.pdf"
    assert name.isascii()


def test_latex_title_kept_in_bibtex_shown_as_unicode_flattened_in_filename():
    from app.latex import to_unicode

    title = r"Lie algebroids on $\mathbb{R}^n$ & $\mathfrak{g}$-manifolds"
    e = Entry(key="X_2020", title=title, year=2020,
              authors=[parse_author("Manuel de León")])
    assert r"title = {{Lie algebroids on $\mathbb{R}^n$ \& $\mathfrak{g}$-manifolds}}" in render(e)
    assert "author = {Manuel de León}" in render(e)
    assert to_unicode(title) == "Lie algebroids on ℝⁿ & g-manifolds"
    assert build_filename(2020, e.authors, title) == \
        "2020_de Leon_Lie algebroids on Rn & g-manifolds.pdf"


def test_math_in_filenames_keeps_its_meaning():
    from app.latex import to_plain

    assert to_plain(r"$L_\infty$-algebras") == "L-infinity-algebras"
    assert to_plain(r"Homotopy $L_{\infty}$ structures") == "Homotopy L-infinity structures"
    assert to_plain(r"$\infty$-jets and $\alpha$-x") == "infinity-jets and alpha-x"
