"""Tests for FastAPI application."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_root_endpoint(client: TestClient) -> None:
    """Test root endpoint returns API information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert data["status"] == "running"


def test_health_check(client: TestClient) -> None:
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_docs_available(client: TestClient) -> None:
    """Test that API documentation is available."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available(client: TestClient) -> None:
    """Test that ReDoc documentation is available."""
    response = client.get("/redoc")
    assert response.status_code == 200
