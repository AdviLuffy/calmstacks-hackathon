"""P3 API test fixtures: applications built from explicit settings, wiring and store."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.session_store import InMemorySessionStore
from p3_helpers import make_settings, make_wiring


@pytest.fixture
def make_client():
    """Build a test client with injected collaborators. Nothing is read from the environment."""

    def factory(
        *,
        settings: Any = None,
        wiring: Any = None,
        store: Any = None,
    ) -> TestClient:
        application = create_app(
            settings=settings if settings is not None else make_settings(),
            wiring=wiring if wiring is not None else make_wiring(),
            store=store if store is not None else InMemorySessionStore(),
        )
        return TestClient(application)

    return factory


@pytest.fixture
def client(make_client) -> TestClient:
    """A client with no engines wired and no persistence."""
    return make_client()
