"""Server trust boundary: path escapes, bad uploads, read-only hosting."""
import pytest
from fastapi.testclient import TestClient

import forgeai.server as server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server.OllamaLLM, "health", lambda self: {"ok": True})  # no model needed to test validation
    monkeypatch.setattr(server, "RUNS", tmp_runs := server.RUNS.parent / ".pytest_runs")
    tmp_runs.mkdir(exist_ok=True)
    started = []
    monkeypatch.setattr(server, "_start", lambda rid, brief, docs, req: started.append((rid, docs)))  # never run a factory
    c = TestClient(server.app)
    c.started = started
    yield c
    import shutil
    shutil.rmtree(tmp_runs, ignore_errors=True)


def test_input_set_cannot_escape_repo(client):
    for bad in ["../..", "..\\..", "forgeai", "C:/Windows"]:
        r = client.post("/api/runs", json={"name": "x", "input_id": bad})
        assert r.status_code == 400, bad


def test_upload_rejects_bad_names_and_types(client):
    for name in ["run.exe", "a b.md", ".."]:
        r = client.post("/api/runs/upload", data={"name": "x", "brief": "b"}, files=[("files", (name, b"hi"))])
        assert r.status_code == 400, name
    assert not any(server.RUNS.iterdir())  # rejected uploads leave nothing behind


def test_upload_path_components_are_stripped(client):
    r = client.post("/api/runs/upload", data={"name": "x", "brief": "b"}, files=[("files", ("../../evil.md", b"hi"))])
    assert r.status_code == 200
    rid, docs = client.started[0]
    assert docs == server.RUNS / rid / "input_docs" and (docs / "evil.md").read_bytes() == b"hi"
    assert not (server.RUNS.parent / "evil.md").exists()


def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_FILE_BYTES", 10)
    r = client.post("/api/runs/upload", data={"name": "x", "brief": "b"}, files=[("files", ("a.md", b"x" * 11))])
    assert r.status_code == 400 and "20 MB" in r.json()["detail"]


def test_readonly_blocks_work(client, monkeypatch):
    monkeypatch.setattr(server, "READONLY", True)
    assert client.post("/api/runs", json={"name": "x", "input_id": "demos/hr_policy"}).status_code == 403
    assert client.get("/api/runs").status_code == 200  # browsing still works


def test_artifact_whitelist(client):
    assert client.get("/api/runs/..%2F..%2Fforgeai/artifacts/run.json").status_code == 404
    assert client.get("/api/runs/x/artifacts/trace.jsonl").status_code == 404
