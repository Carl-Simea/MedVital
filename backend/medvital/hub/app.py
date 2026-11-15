"""The spacecraft-hub server: the MEDVITAL API + the hub + the web apps, on one port.

    uvicorn --factory medvital.hub.app:create_hub_app --port 8000   (start.py at the repo root does this)

Environment:
    MEDVITAL_NASA_URL      NASA receiver, e.g. http://localhost:5000 (the link to Earth)
    MEDVITAL_DATA_DIR      where spacecraft.db and observations.db live (default: <repo>/runtime)
    MEDVITAL_OLLAMA_MODEL  optional local model for the onboard agent
    CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN   optional Workers AI wording
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from medvital.config import Settings
from medvital.db.sqlite import SqliteObservationRepository
from medvital.hub import settings as S
from medvital.hub.routes import router as hub_router
from medvital.hub.service import Hub
from medvital.hub.store import HubStore
from medvital.main import create_app


class NoCache(StaticFiles):
    """Pages and scripts are always fetched fresh, so an update shows up on a normal reload."""

    async def get_response(self, path, scope):  # type: ignore[no-untyped-def]
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


REPO = Path(os.environ.get("MEDVITAL_REPO_ROOT", Path(__file__).resolve().parents[3]))


def create_hub_app(
    data_dir: str | Path | None = None, nasa_url: str | None = None, start_background: bool = True
) -> FastAPI:
    data = Path(data_dir or os.environ.get("MEDVITAL_DATA_DIR") or REPO / "runtime")
    data.mkdir(parents=True, exist_ok=True)
    observations = SqliteObservationRepository(data / "observations.db")
    settings = Settings(
        repository="sqlite",
        sqlite_path=str(data / "observations.db"),
        cors_origins=("*",),
        max_future_skew_seconds=86400,
    )
    app = create_app(settings, repository=observations)
    hub = Hub(
        HubStore(data / "spacecraft.db"),
        observations,
        app.state.registry,
        nasa_url=nasa_url if nasa_url is not None else os.environ.get("MEDVITAL_NASA_URL"),
        observations_path=data / "observations.db",
    )
    app.state.hub = hub
    app.include_router(hub_router)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_background:
            hub.start()
        yield
        hub.stop()

    app.router.lifespan_context = lifespan

    # The 3D astronaut screen lives at an address that changes with every version (/body-<commit>/), so a
    # browser can never mix old cached scripts or styles with new ones. /body/?astronaut=... redirects there.
    body_url = f"/body-{S.git_commit() if S.git_commit() != '?' else S.VERSION}"

    @app.get("/body", include_in_schema=False)
    @app.get("/body/{path:path}", include_in_schema=False)
    def body_redirect(request: Request, path: str = "") -> RedirectResponse:
        q = request.url.query
        return RedirectResponse(f"{body_url}/{path}" + (f"?{q}" if q else ""), status_code=307)

    for url, folder in (
        ("/astronaut", REPO / "apps" / "astronaut"),
        ("/cloudflare", REPO / "apps" / "cloudflare"),
        ("/shared", REPO / "apps" / "shared"),
        (body_url, REPO / "body-dashboard" / "public"),
        ("/reports", REPO / "reports"),
    ):
        if folder.is_dir():
            app.mount(url, NoCache(directory=folder, html=True), name=url.strip("/"))
    if (REPO / "apps").is_dir():
        app.mount("/apps", NoCache(directory=REPO / "apps", html=True), name="apps")

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/apps/")

    return app
