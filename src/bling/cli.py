"""The `bling` command: ask, serve, vapi-sync."""

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
import typer

from .config import Settings, require
from .deepgram import DeepgramClient
from .domain import TripRequest
from .pipeline import plan_trip, reply_text
from .vapi import KEYTERMS, VapiApi, assistant_body, mask_secrets

app = typer.Typer(no_args_is_help=True, add_completion=False)

CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


async def _ask(
    trip: TripRequest, settings: Settings, audio: Path | None = None, say: Path | None = None
) -> str:
    async with AsyncExitStack() as stack:
        exa = jev = deepgram = None
        if audio is not None or say is not None:
            http = await stack.enter_async_context(httpx.AsyncClient())
            deepgram = DeepgramClient(
                require(settings.deepgram_api_key, "DEEPGRAM_API_KEY"),
                http,
                settings.deepgram_stt_model,
                settings.deepgram_tts_model,
            )
        if audio is not None:
            heard = await deepgram.transcribe(audio.read_bytes(), content_type_for(audio), KEYTERMS)
            typer.echo(f"heard: {heard}")
            parts = [p for p in (trip.situation, heard.strip()) if p]
            trip = trip.model_copy(update={"situation": " ".join(parts) or None})
        if settings.exa_api_key is not None:
            from exa_py import AsyncExa

            exa = AsyncExa(api_key=settings.exa_api_key.get_secret_value())
            stack.push_async_callback(exa.aclose)
        if settings.typesafe_api_key is not None:
            from .decision import make_jev

            jev = make_jev(settings)
            stack.push_async_callback(jev.aclose)
        rec = await plan_trip(trip, exa=exa, jev=jev, settings=settings)
        text = reply_text(rec)
        if say is not None:
            say.write_bytes(await deepgram.speak(text))
        return text


@app.command()
def ask(
    destination: str,
    origin: str | None = typer.Option(None, "--from", help="Where you're starting from."),
    by: str | None = typer.Option(None, "--by", help="When you need to arrive."),
    situation: str | None = typer.Option(None, "--situation", help="Anything else relevant."),
    audio: Path | None = typer.Option(
        None, "--audio", exists=True, dir_okay=False, help="Recording of your situation."
    ),
    say: Path | None = typer.Option(None, "--say", dir_okay=False, help="Write the reply as MP3."),
) -> None:
    """Drive or take transit to DESTINATION?"""
    settings = Settings()
    if (audio is not None or say is not None) and settings.deepgram_api_key is None:
        typer.echo("DEEPGRAM_API_KEY is not set", err=True)
        raise typer.Exit(1)
    trip = TripRequest(destination=destination, origin=origin, arrive_by=by, situation=situation)
    typer.echo(asyncio.run(_ask(trip, settings, audio, say)))
    if say is not None:
        typer.echo(f"wrote {say}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the web server (the Vapi webhook)."""
    import uvicorn

    from .app import create_app

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=host, port=port)


@app.command("vapi-sync")
def vapi_sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the body (secrets masked)."),
) -> None:
    """Create or update the Bling assistant in Vapi."""
    settings = Settings()
    try:
        key = require(settings.vapi_api_key, "VAPI_API_KEY")
        require(settings.vapi_server_secret, "VAPI_SERVER_SECRET")
        if not settings.public_base_url:
            raise RuntimeError("PUBLIC_BASE_URL is not set")
    except RuntimeError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e
    body = assistant_body(settings)
    if dry_run:
        typer.echo(json.dumps(mask_secrets(body), indent=2))
        return
    with httpx.Client() as http:
        api = VapiApi(key, http)
        try:
            if settings.vapi_assistant_id:
                api.update_assistant(settings.vapi_assistant_id, body)
                typer.echo(f"Updated assistant {settings.vapi_assistant_id}")
            else:
                created = api.create_assistant(body)
                typer.echo(f"Add VAPI_ASSISTANT_ID={created['id']} to .env")
        except (RuntimeError, httpx.HTTPError) as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1) from e
