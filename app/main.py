from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app.api.v1 import api_router
from app.core.config import settings
from app.db.session import engine
from app.services.content import get_content

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CachedStaticFiles(StaticFiles):
    """Question and sign images never change in place, so let browsers keep them."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=604800"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_content()  # parse question bank, lessons and signs once; fail fast on broken content
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="API ya Tsinda Neza: amasomo, ibyapa, imyitozo n’ibizamini by’amategeko y’umuhanda mu Rwanda.",
    version="1.0.0",
    lifespan=lifespan,
    # The schema lists the admin API too: keep it off the public internet.
    openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Cookie-authenticated API: reject state-changing requests coming from foreign origins (CSRF defence in depth).
    origin = request.headers.get("origin")
    if request.method in UNSAFE_METHODS and origin and origin not in settings.FRONTEND_ORIGINS:
        return JSONResponse({"detail": "Icyifuzo kivuye ahantu hatemewe."}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(api_router)
app.mount("/media", CachedStaticFiles(directory=settings.MEDIA_DIR), name="media")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
