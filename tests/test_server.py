"""Server trust boundary: path escapes, bad uploads, read-only hosting."""
import pytest
from fastapi.testclient import TestClient

import forgeai.server as server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "make_llm", lambda *a, **k: type("H", (), {"health": lambda self: {"ok": True}})())  # no model needed
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


def test_archive_then_delete_run(client):
    d = server.RUNS / "r1"
    d.mkdir()
    (d / "run.json").write_text('{"name": "R", "model": "openai/gpt-oss-20b", "finished": true}', encoding="utf-8")
    run = next(r for r in client.get("/api/runs").json() if r["id"] == "r1")
    assert run["provider"] == "groq" and run["archived"] is False  # old runs: provider inferred from the model id
    assert client.post("/api/runs/r1/archive", json={"archived": True}).json()["archived"] is True
    assert next(r for r in client.get("/api/runs").json() if r["id"] == "r1")["archived"] is True
    assert client.post("/api/runs/r1/archive", json={"archived": False}).json()["archived"] is False
    assert client.delete("/api/runs/r1").status_code == 200 and not d.exists()
    assert client.delete("/api/runs/nope").status_code == 404


def test_delete_refuses_running_and_readonly(client, monkeypatch):
    (server.RUNS / "r2").mkdir()
    monkeypatch.setitem(server._active, "r2", {"thread": type("T", (), {"is_alive": lambda self: True})()})
    assert client.delete("/api/runs/r2").status_code == 409
    monkeypatch.setattr(server, "READONLY", True)
    assert client.post("/api/runs/r2/archive", json={}).status_code == 403


def test_stop_running_run(client, monkeypatch):
    import threading
    (server.RUNS / "r3").mkdir()
    (server.RUNS / "r3" / "events.jsonl").write_text('{"ts": 1, "stage": "error", "status": "stopped", "error": "Stopped by you"}\n')
    assert client.post("/api/runs/r3/stop").status_code == 409  # not running here
    st = {"thread": type("T", (), {"is_alive": lambda self: True})(), "stop": threading.Event(), "checkpoint": threading.Event()}
    monkeypatch.setitem(server._active, "r3", st)
    assert client.post("/api/runs/r3/stop").status_code == 200
    assert st["stop"].is_set() and st["checkpoint"].is_set()
    monkeypatch.delitem(server._active, "r3")
    assert next(r for r in client.get("/api/runs").json() if r["id"] == "r3")["status"] == "stopped"
