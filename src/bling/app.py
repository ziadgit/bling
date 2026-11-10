"""The FastAPI app: the Vapi webhook, a health check, and a small landing page."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .config import Settings
from .landing import LANDING_HTML
from .vapi import Deps, check_secret, handle_message


def create_app(settings: Settings | None = None, *, exa: Any = None, jev: Any = None) -> FastAPI:
    settings = settings or Settings()
    deps = Deps(settings=settings, exa=exa, jev=jev)

    def ensure_clients(stack: AsyncExitStack | None = None) -> None:
        """Build real clients for the keys that are set. Lazy too, because serverless runtimes
        (Vercel) may never run the lifespan."""
        if deps.exa is None and settings.exa_api_key is not None:
            from exa_py import AsyncExa

            deps.exa = AsyncExa(api_key=settings.exa_api_key.get_secret_value())
            if stack is not None:
                stack.push_async_callback(deps.exa.aclose)
        if deps.jev is None and settings.typesafe_api_key is not None:
            from .decision import make_jev

            deps.jev = make_jev(settings)
            if stack is not None:
                stack.push_async_callback(deps.jev.aclose)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            ensure_clients(stack)
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.deps = deps

    @app.get("/", response_class=HTMLResponse)
    async def landing() -> HTMLResponse:
        return HTMLResponse(LANDING_HTML)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/vapi/webhook")
    async def webhook(request: Request) -> Response:
        if not check_secret(request.headers.get("x-bling-secret"), settings):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({})
        ensure_clients()
        return JSONResponse(await handle_message(body, deps))

    return app
