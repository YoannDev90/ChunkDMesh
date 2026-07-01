"""Tests for the FastAPI endpoints."""

import pytest

pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient


@pytest.fixture
def client():
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
        resp = client.get("/admin/download/%2e%2e/%2e%2e/etc/passwd", headers={"Authorization": "Bearer fake"})
        assert resp.status_code in (400, 401, 404)

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
