"""Tests for the FastAPI endpoints."""


import pytest

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


@pytest.fixture
def client():
    if not _HAS_FASTAPI:
        pytest.skip("fastapi not installed in test env")
    from api import app
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestRootEndpoint:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["project"] == "ChunkDMesh"


class TestPathTraversal:
    def test_download_rejects_traversal(self, client):
        resp = client.get("/admin/download/../../etc/passwd", headers={"Authorization": "Bearer fake"})
        assert resp.status_code in (400, 401)

    def test_upload_rejects_traversal(self, client):
        resp = client.put(
            "/tasks/upload/999",
            content=b"fake",
            headers={
                "X-Filename": "../../evil.mca",
                "Content-Type": "application/octet-stream",
            },
        )
        assert resp.status_code in (400, 401)
