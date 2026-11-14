"""FastAPI application factory.

Run:  uvicorn medvital.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from medvital import __version__
from medvital.api.records_routes import router as records_router
from medvital.api.routes import router
from medvital.config import Settings
from medvital.db.factory import build_repository
from medvital.db.repository import ObservationRepository
from medvital.registry import build_registry


def create_app(
    settings: Settings | None = None, repository: ObservationRepository | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.auth_mode != "local":
        raise RuntimeError(
            f"MEDVITAL_AUTH_MODE={settings.auth_mode!r} is not implemented: Auth0 JWT validation needs an "
            "approved JWT library (docs/DECISIONS.md D-029). Refusing to start unauthenticated."
        )
    app = FastAPI(
        title="MEDVITAL API",
        version=__version__,
        description=(
            "Offline-first astronaut health-observation platform. Values are labelled "
            "simulated / measured / modeled. Not a medical device; no diagnosis."
        ),
    )
    app.state.settings = settings
    app.state.repository = repository or build_repository(settings)
    app.state.registry = build_registry()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    app.include_router(records_router)
    return app


app = create_app()
