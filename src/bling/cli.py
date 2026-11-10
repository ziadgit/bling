"""The `bling` command: ask, serve, vapi-sync."""

import asyncio
import logging
from contextlib import AsyncExitStack

import httpx
import typer

from .config import Settings, require
from .domain import TripRequest
from .pipeline import plan_trip, reply_text
from .vapi import VapiApi, assistant_body

app = typer.Typer(no_args_is_help=True, add_completion=False)


async def _ask(trip: TripRequest, settings: Settings) -> str:
    async with AsyncExitStack() as stack:
        exa = jev = None
        if settings.exa_api_key is not None:
            from exa_py import AsyncExa

            exa = AsyncExa(api_key=settings.exa_api_key.get_secret_value())
            stack.push_async_callback(exa.aclose)
        if settings.typesafe_api_key is not None:
            from .decision import make_jev

            jev = make_jev(settings)
            stack.push_async_callback(jev.aclose)
        rec = await plan_trip(trip, exa=exa, jev=jev, settings=settings)
        return reply_text(rec)


@app.command()
def ask(
    destination: str,
    origin: str | None = typer.Option(None, "--from", help="Where you're starting from."),
    by: str | None = typer.Option(None, "--by", help="When you need to arrive."),
    situation: str | None = typer.Option(None, "--situation", help="Anything else relevant."),
) -> None:
    """Drive or take transit to DESTINATION?"""
    trip = TripRequest(destination=destination, origin=origin, arrive_by=by, situation=situation)
    typer.echo(asyncio.run(_ask(trip, Settings())))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the web server (Vapi webhook and voice links)."""
    import uvicorn

    from .app import create_app

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=host, port=port)


@app.command("vapi-sync")
def vapi_sync() -> None:
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
    with httpx.Client() as http:
        api = VapiApi(key, http)
        if settings.vapi_assistant_id:
            api.update_assistant(settings.vapi_assistant_id, body)
            typer.echo(f"Updated assistant {settings.vapi_assistant_id}")
        else:
            created = api.create_assistant(body)
            typer.echo(f"Add VAPI_ASSISTANT_ID={created['id']} to .env")
