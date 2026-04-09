"""Tests für den Deploy Server."""
import pytest
from fastapi.testclient import TestClient

# Import wird angepasst wenn das Modul korrekt eingerichtet ist
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from deploy_server.main import app


@pytest.fixture
def client():
    """Test Client für FastAPI."""
    return TestClient(app)


def test_root(client):
    """Test Root Endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health(client):
    """Test Health Check."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_projects_empty(client):
    """Test Projekt-Liste wenn leer."""
    response = client.get("/projects")
    assert response.status_code == 200
    assert "projects" in response.json()


def test_add_project(client):
    """Test Projekt hinzufügen."""
    project = {
        "name": "test-project",
        "repo_url": "https://github.com/user/repo.git",
        "branch": "main",
        "build_command": "npm run build",
        "output_dir": "dist",
        "project_type": "static"
    }

    response = client.post("/projects", json=project)
    assert response.status_code == 200
    assert response.json()["config"]["name"] == "test-project"


def test_webhook_missing_project(client):
    """Test Webhook für nicht existierendes Projekt."""
    response = client.post("/webhook/nonexistent", json={})
    assert response.status_code == 404
