"""D10: GET /results page and /results/files, with data present and with an empty results folder."""
import importlib
import json
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    d = tmp_path_factory.mktemp("state")
    os.environ["HEDWIG_BACKEND"] = "statevector"
    os.environ["HEDWIG_AUDIT_KEY"] = str(d / "audit.pem")
    os.environ["HEDWIG_DB"] = str(d / "hedwig.db")
    os.environ["HEDWIG_AUDIT_PQ"] = "off"
    os.environ.pop("HEDWIG_USERS_FILE", None)
    import server as srv
    return importlib.reload(srv)


def logged_in(server, user="bob", pw="quantum2026"):
    c = TestClient(server.app)
    assert c.post("/api/login", json={"username": user, "password": pw}).status_code == 200
    return c


@pytest.fixture
def results_dir(server, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "RESULTS_DIR", str(tmp_path))
    return tmp_path


def test_requires_login(server, results_dir):
    c = TestClient(server.app)
    r = c.get("/results", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/results/files/roc/roc_auc.csv").status_code == 401


def test_empty_results_folder(server, results_dir):
    r = logged_in(server).get("/results")
    assert r.status_code == 200
    assert "Not generated yet" in r.text and "manifest.json not generated yet" in r.text
    for tab in ("ROC", "Ablations", "Baselines", "Tightness", "Hardware run", "Reproducibility"):
        assert f">{tab}</button>" in r.text


def test_with_data(server, results_dir):
    (results_dir / "roc").mkdir()
    (results_dir / "roc" / "roc_auc.csv").write_text("L,auc\n16,0.91\n32,0.97\n")
    (results_dir / "roc" / "roc_L16.png").write_bytes(b"\x89PNG fake")
    (results_dir / "manifest.json").write_text(json.dumps({
        "command": "python run_experiments.py --seed 2026", "seed": 2026, "trials": None, "quick": False,
        "finished": "2026-10-27", "seconds": 1.0, "machine": {"cpu": "test", "python": "3.13"},
        "git": {"commit": "abcdef1234567", "branch": "b", "dirty": False},
        "steps": [{"name": "roc", "task": "D2", "status": "ok", "seconds": 1.0}]}))
    c = logged_in(server, "admin", "admin2026")
    r = c.get("/results")
    assert r.status_code == 200
    assert "Seed 2026" in r.text and "Commit abcdef12" in r.text and "script defaults" in r.text
    assert "<td>0.97</td>" in r.text and 'src="/results/files/roc/roc_L16.png"' in r.text
    img = c.get("/results/files/roc/roc_L16.png")
    assert img.status_code == 200 and img.content == b"\x89PNG fake"


def test_long_csv_is_truncated(server, results_dir):
    (results_dir / "baselines").mkdir()
    (results_dir / "baselines" / "baselines.csv").write_text("x\n" + "".join(f"{i}\n" for i in range(60)))
    r = logged_in(server).get("/results")
    assert f"{60 - server.MAX_TABLE_ROWS} more rows" in r.text


def test_files_route_stays_inside_results(server, results_dir, tmp_path_factory):
    secret = tmp_path_factory.mktemp("outside") / "secret.txt"
    secret.write_text("nope")
    c = logged_in(server)
    assert c.get("/results/files/roc/missing.png").status_code == 404
    assert c.get("/results/files/..%2F..%2F/secret.txt").status_code == 404
    assert c.get(f"/results/files/..%2F{secret.parent.name}/secret.txt").status_code == 404


def test_admin_page_links_to_results(server):
    assert 'href="/results"' in logged_in(server, "admin", "admin2026").get("/admin").text
