"""End-to-end: inbox PDF -> staged proposal -> review -> confirm -> search -> undo."""

import importlib
import os

import pymupdf
import pytest
from fastapi.testclient import TestClient


def make_pdf(path, title, author, body="Journal of Geometry and Physics 35 (2000) 35-55"):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), title, fontsize=18)
    page.insert_text((72, 140), author, fontsize=11)
    page.insert_text((72, 170), body, fontsize=9)
    doc.set_metadata({"title": title, "author": author})
    doc.save(path)


@pytest.fixture
def client(tmp_path, monkeypatch):
    lib, inbox = tmp_path / "Papers", tmp_path / "Papers" / "Inbox"
    inbox.mkdir(parents=True)
    make_pdf(inbox / "scan_0042.pdf", "On the geometry of singular Lagrangians",
             "Fabrizio Pugliese and Alexandre M. Vinogradov")
    env = {"AUTH_DISABLED": "1", "STORAGE": "local", "GEMINI_API_KEY": "",
           "DATA_DIR": str(tmp_path / "data"), "LOCAL_LIBRARY_DIR": str(lib),
           "LOCAL_INBOX_DIR": str(inbox), "ONLINE_LOOKUP": "0"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from app import config
    config.get_settings.cache_clear()
    import app.main
    main = importlib.reload(app.main)
    with TestClient(main.app) as c:
        c.lib_dir, c.inbox = lib, inbox
        yield c
    config.get_settings.cache_clear()


def test_scan_never_renames(client):
    r = client.post("/scan", follow_redirects=False)
    assert r.status_code == 303
    assert (client.inbox / "scan_0042.pdf").exists()
    assert not (client.lib_dir / "library.bib").exists()
    page = client.get("/staging").text
    assert "scan_0042.pdf" in page and "2000_Pugliese-Vinogradov" in page


def test_confirm_renames_and_writes_bib(client):
    client.post("/scan")
    review = client.get("/staging/1")
    assert review.status_code == 200 and "Confirm &amp; Rename" in review.text
    assert client.get("/papers/1/preview.png").headers["content-type"] == "image/png"

    form = {
        "title": "On the geometry of singular Lagrangians",
        "authors": "Pugliese, Fabrizio\nVinogradov, Alexandre M.",
        "year": "2000", "entry_type": "article", "journal": "J. Geom. Phys.",
        "volume": "35", "pages": "35-55", "doi": "10.1016/S0393-0440(99)00076-5",
        "tags": "geometric-mechanics lagrangian",
    }
    derived = client.post("/staging/1/derive", data=form).text
    assert "PV_2000" in derived and r"{{\bf 35}}" in derived
    form.update(key="PV_2000",
                filename="2000_Pugliese-Vinogradov_On the geometry of singular Lagrangians.pdf",
                bibtex="")
    r = client.post("/staging/1/confirm", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text

    renamed = client.lib_dir / "2000_Pugliese-Vinogradov_On the geometry of singular Lagrangians.pdf"
    assert renamed.exists() and not (client.inbox / "scan_0042.pdf").exists()
    bib = (client.lib_dir / "library.bib").read_text()
    assert bib.startswith("@article{PV_2000,") and "J. Geom. Phys." in bib

    for q in ["vinogradov", "2000", "PV_2000", "lagrang", "geometric"]:
        assert "singular Lagrangians" in client.get("/", params={"q": q}).text, q
    assert "No papers" in client.get("/", params={"q": "hamiltonian"}).text
    assert "singular" in client.get("/", params={"tag": "lagrangian"}).text
    assert "No papers" in client.get("/", params={"tag": ["lagrangian", "nope"]}).text
    assert "PV_2000" in client.get("/export.bib", params={"tag": "lagrangian"}).text

    client.post("/papers/1/undo")
    assert (client.inbox / "scan_0042.pdf").exists() and not renamed.exists()
    assert (client.lib_dir / "library.bib").read_text() == ""


def test_upload_goes_to_staging(client, tmp_path):
    make_pdf(tmp_path / "x.pdf", "A note on Jacobi structures", "Manuel de León")
    with open(tmp_path / "x.pdf", "rb") as f:
        client.post("/upload", files={"files": ("x.pdf", f, "application/pdf")})
    assert (client.inbox / "x.pdf").exists()
    assert "A note on Jacobi structures" in client.get("/staging").text


def test_login_required_when_auth_enabled(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config.get_settings(), "auth_disabled", False)
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"].endswith("/login")
    os.environ.pop("AUTH_DISABLED", None)


def test_inbox_scanned_automatically_and_duplicates_flagged(client):
    import shutil
    shutil.copy(client.inbox / "scan_0042.pdf", client.inbox / "copy.pdf")
    page = client.get("/staging").text  # opening the page scans the inbox
    assert "scan_0042.pdf" in page and "copy.pdf" in page
    notes = [client.get(f"/staging/{i}").text for i in (1, 2)]
    assert any("Possible duplicate" in n for n in notes)


def test_delete_trashes_unconfirmed_pdf(client):
    client.post("/scan")
    r = client.post("/staging/1/delete", follow_redirects=False)
    assert r.status_code == 303
    assert not (client.inbox / "scan_0042.pdf").exists()
    assert "scan_0042.pdf" not in client.get("/staging").text


def test_tag_editor_replaces_tags_and_normalizes(client):
    client.post("/scan")
    r = client.post("/papers/1/tags", data={"tags": "Lie Algebroids,  poisson poisson Géométrie"})
    assert r.json()["tags"] == ["algebroids", "geometrie", "lie", "poisson"]
    assert "poisson" in {t["name"] for t in r.json()["index"]}
    r = client.post("/papers/1/tags", data={"tags": "poisson"})
    assert r.json()["tags"] == ["poisson"]
