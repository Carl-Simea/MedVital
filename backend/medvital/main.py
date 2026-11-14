"""FastAPI application factory.

Run:  uvicorn medvital.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from medvital import __version__
from medvital.api.routes import router
from medvital.config import Settings
from medvital.db.factory import build_repository
from medvital.db.repository import ObservationRepository
from medvital.registry import build_registry


def create_app(
    settings: Settings | None = None, repository: ObservationRepository | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
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
    return app


app = create_app()
