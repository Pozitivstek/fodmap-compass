"""Сборка FastAPI-приложения: API под /api, мини-приложение — статикой с корня."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_diary, routes_foods, routes_insights, routes_me, routes_misc, routes_recipes
from app.api.deps import AppContext

log = logging.getLogger(__name__)
NO_CACHE = {"Cache-Control": "no-cache"}


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="ФудКомпас", docs_url="/api/docs" if ctx.settings.dev_mode else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if ctx.settings.dev_mode else None)
    app.state.ctx = ctx
    for module in (routes_me, routes_foods, routes_diary, routes_recipes, routes_insights, routes_misc):
        app.include_router(module.router)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Что-то пошло не так. Попробуйте ещё раз."}, status_code=500)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "foods": len(ctx.catalog.foods), "recipes": len(ctx.catalog.recipes)}

    @app.middleware("http")
    async def revalidate_static(request: Request, call_next):
        # Мини-приложение обновляется без смены имён файлов — просим клиента всегда сверять ETag.
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    webapp = ctx.settings.webapp_dir

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(webapp / "index.html", headers=NO_CACHE)

    if webapp.exists():
        app.mount("/", StaticFiles(directory=webapp), name="webapp")
    return app
