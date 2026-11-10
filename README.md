# Bling

Text or call Bling where you're going. It checks live traffic and transit with **Exa**, lets
**Jev** decide, and tells you whether to **drive** or **take transit**, and why. Over text you can
ask for a **voice link**: hear the recommendation (Deepgram TTS), or record your situation and
let Bling re-decide with it (Deepgram transcription).

This branch (`fast-27`) is a **27-minute single-session build**: `SPEC.md` + `fix_plan.md` (7 items).

## Build it

```sh
claude --dangerously-skip-permissions "$(cat PROMPT.md)"
```

Claude works through `fix_plan.md`, committing after each item, and wraps up at the 25-minute
mark. `--dangerously-skip-permissions` means it runs every command without asking, so only run
it in this repo. Esc interrupts it; if anything is left, say "continue with PROMPT.md".

## Set up the services (after the build)

1. `cp .env.example .env` and fill in the keys (Exa, TypeSafe, Deepgram, Vapi, a server secret).
2. Expose the server: `bling serve`, plus a tunnel (e.g. `cloudflared tunnel --url http://localhost:8000`).
   Put its https URL in `PUBLIC_BASE_URL`.
3. `bling vapi-sync` creates the assistant (Deepgram transcriber + voice, tools, webhook). Add the
   printed `VAPI_ASSISTANT_ID` to `.env`.
4. **Texting needs a Twilio number**: import an A2P 10DLC-registered Twilio number into Vapi with
   SMS enabled, then attach the Bling assistant under Inbound Settings. Vapi SMS is US-to-US only,
   you must text first, and the Vapi account needs a payment method (otherwise replies silently
   don't send).
5. Text it: "Oakland to Salesforce Transit Center by 6, can I get a voice review?" or
   "I'm going to SFO, I want to explain my situation by voice."
