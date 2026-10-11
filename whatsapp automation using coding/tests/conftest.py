"""
conftest.py — Shared pytest fixtures for all tests.

The TestClient here uses httpx under the hood and can make requests to
the FastAPI app without starting a real server.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    A test HTTP client wired directly to the FastAPI app.
    No real network calls are made.
    """
    with TestClient(app) as c:
        yield c
