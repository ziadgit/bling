"""The FastAPI app: Vapi webhook, voice-link pages, health."""

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .config import Settings
from .deepgram import DeepgramClient
from .links import LinkStore
from .pages import explain_page, not_found_page, review_page
from .pipeline import plan_trip
from .vapi import Deps, check_secret, handle_message

log = logging.getLogger(__name__)
MAX_UPLOAD = 10 * 1024 * 1024


def create_app(
    settings: Settings | None = None, *, exa: Any = None, jev: Any = None, deepgram: Any = None
) -> FastAPI:
    settings = settings or Settings()
    deps = Deps(
        settings=settings,
        links=LinkStore(settings.bling_data_dir / "links", settings.link_ttl_hours),
        exa=exa,
        jev=jev,
        deepgram=deepgram,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            if deps.exa is None and settings.exa_api_key is not None:
                from exa_py import AsyncExa

                deps.exa = AsyncExa(api_key=settings.exa_api_key.get_secret_value())
                stack.push_async_callback(deps.exa.aclose)
            if deps.jev is None and settings.typesafe_api_key is not None:
                from .decision import make_jev

                deps.jev = make_jev(settings)
                stack.push_async_callback(deps.jev.aclose)
            if deps.deepgram is None and settings.deepgram_api_key is not None:
                http = await stack.enter_async_context(httpx.AsyncClient())
                deps.deepgram = DeepgramClient(
                    settings.deepgram_api_key.get_secret_value(),
                    http,
                    settings.deepgram_stt_model,
                    settings.deepgram_tts_model,
                )
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.deps = deps

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
            return JSONResponse({}, status_code=200)
        return JSONResponse(await handle_message(body, deps))

    def missing_page() -> HTMLResponse:
        return HTMLResponse(not_found_page(), status_code=404)

    @app.get("/v/{token}")
    async def review(token: str) -> HTMLResponse:
        rec = deps.links.get(token)
        if rec is None or rec.rec is None:
            return missing_page()
        return HTMLResponse(review_page(token, rec.rec.text))

    @app.get("/v/{token}/audio")
    async def review_audio(token: str) -> Response:
        rec = deps.links.get(token)
        path = deps.links.audio_path(token)
        if rec is None or rec.rec is None or path is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if path.is_file():
            return Response(path.read_bytes(), media_type="audio/mpeg")
        if deps.deepgram is None:
            return JSONResponse({"error": "voice is not set up"}, status_code=503)
        try:
            audio = await deps.deepgram.speak(rec.rec.text)
        except Exception as e:  # noqa: BLE001
            log.warning("speak failed: %s", type(e).__name__)
            return JSONResponse({"error": "voice is unavailable"}, status_code=502)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return Response(audio, media_type="audio/mpeg")

    @app.get("/e/{token}")
    async def explain(token: str) -> HTMLResponse:
        rec = deps.links.get(token)
        if rec is None or rec.kind != "explain":
            return missing_page()
        return HTMLResponse(explain_page(rec.trip.destination))

    @app.post("/e/{token}/audio")
    async def explain_audio(token: str, audio: UploadFile) -> JSONResponse:
        record = deps.links.get(token)
        if record is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if record.kind != "explain" or record.used:
            return JSONResponse({"error": "This link was already used."}, status_code=409)
        data = await audio.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            return JSONResponse({"error": "That recording is too long."}, status_code=413)
        if deps.deepgram is None:
            return JSONResponse({"error": "voice is not set up"}, status_code=503)
        try:
            transcript = await deps.deepgram.transcribe(data, audio.content_type or "audio/webm")
        except Exception as e:  # noqa: BLE001
            log.warning("transcribe failed: %s", type(e).__name__)
            return JSONResponse({"error": "I couldn't hear that, try again."}, status_code=502)
        if not transcript.strip():
            return JSONResponse({"error": "I didn't catch that, try again."}, status_code=422)
        trip = record.trip.model_copy(update={"situation": transcript})
        rec = await plan_trip(trip, exa=deps.exa, jev=deps.jev, settings=settings)
        record.trip, record.rec, record.used = trip, rec, True
        deps.links.save(token, record)
        review_token = deps.links.create("review", trip, rec)
        return JSONResponse(
            {"text": rec.text, "audio_url": f"/v/{review_token}/audio", "transcript": transcript}
        )

    return app
