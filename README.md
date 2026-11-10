# Bling

Call Bling and say where you're going. It checks live Bay Area traffic and transit with **Exa**,
lets **Jev** decide, and tells you whether to **drive** or **take transit**, and why. **Vapi**
runs the call, and **Deepgram** is its ears and voice.

This branch (`fast-27`) is a **single-session build**: `SPEC.md` + `fix_plan.md`.

## Build it

```sh
claude --dangerously-skip-permissions "$(cat PROMPT.md)"
```

Claude works through the unchecked `fix_plan.md` items, committing after each one, and wraps up
at the 25-minute mark. `--dangerously-skip-permissions` means it runs every command without
asking, so only run it in this repo. Esc interrupts it; if anything is left, say "continue
with PROMPT.md".

## Set up the services (after the build)

1. Fill in `.env` (Exa, TypeSafe, Deepgram, Vapi, a server secret from `openssl rand -hex 32`).
2. Expose the server: `bling serve`, plus a tunnel (e.g. `cloudflared tunnel --url http://localhost:8000`).
   Put its https URL in `PUBLIC_BASE_URL`.
3. `bling vapi-sync --dry-run` to check the assistant, then `bling vapi-sync` to create it (Deepgram
   transcriber + voice + your Deepgram key, the plan_trip tool, the webhook). Add the printed
   `VAPI_ASSISTANT_ID` to `.env`.
4. Test with **Talk to Assistant** in the Vapi dashboard (a browser call, no phone number needed).
5. Get a phone number: Vapi dashboard → Phone Numbers → Create Phone Number → **Free Vapi Number**
   (not Free Vapi SIP), area code `415` (or `628`/`510`). Open it, set **Inbound Settings →
   Assistant** to Bling, save, and call it from your phone.

## Run it

```sh
uv sync
.venv/bin/bling ask "Salesforce Transit Center" --from "Oakland" --by 6pm
.venv/bin/bling ask "SFO" --situation "I have two big suitcases" --say reply.mp3   # hear the Deepgram voice
.venv/bin/bling ask "SFO" --audio me.m4a      # Deepgram transcribes your recording as the situation
.venv/bin/bling serve --port 8000             # webhook at /vapi/webhook
.venv/bin/bling vapi-sync --dry-run           # print the assistant body, secrets masked
.venv/bin/pytest -q                           # tests never touch the network
```

Without `EXA_API_KEY`/`TYPESAFE_API_KEY`, `ask` still runs and says it couldn't check or decide.
