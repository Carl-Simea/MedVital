"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from medvital import __version__
from medvital.api.routes import router
from medvital.config import Settings
from medvital.db.factory import make_repository
from medvital.db.repository import ObservationRepository


def create_app(
    repo: ObservationRepository | None = None, settings: Settings | None = None
) -> FastAPI:
    app = FastAPI(
        title="MEDVITAL API",
        version=__version__,
        description="Research prototype. Not a medical device. No diagnosis or thresholds.",
    )
    app.state.repo = repo if repo is not None else make_repository(settings or Settings.from_env())
    app.include_router(router)
    return app


app = create_app()
