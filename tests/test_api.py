"""Tests for the FastAPI routes."""

import pytest
from fastapi.testclient import TestClient

from hachimi.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAPIRoutes:
    def test_root(self, client):
        res = client.get("/", follow_redirects=False)
        # Should redirect to /app/index.html or return JSON
        assert res.status_code in (200, 307)

    def test_list_tasks(self, client):
        res = client.get("/api/tasks")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_status_not_found(self, client):
        res = client.get("/api/status/nonexistent-id")
        assert res.status_code == 404

    def test_result_not_found(self, client):
        res = client.get("/api/result/nonexistent-id")
        assert res.status_code == 404

    def test_generate_missing_prompt(self, client):
        res = client.post("/api/generate", json={"prompt": ""})
        assert res.status_code == 422  # Validation error
