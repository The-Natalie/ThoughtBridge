"""Boot test: the app factory produces a serving FastAPI application."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_docs_serve_with_thoughtbridge_title() -> None:
    client = TestClient(create_app())
    response = client.get("/docs")
    assert response.status_code == 200
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "ThoughtBridge"
