# ruff: noqa: E501 - inline HTML
"""The landing page at `/`: inline HTML and CSS, no external scripts."""

LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bling · drive or transit, by voice</title>
<meta name="description" content="Call Bling, say where you're going, and hear whether to drive or take transit. Live Bay Area conditions from Exa, decided by Jev, spoken through Vapi and Deepgram.">
<style>
:root{--bg:#0b0d12;--panel:#12151d;--line:#232836;--text:#eef1f7;--muted:#9aa3b5;
--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--accent:#7c6cff;color-scheme:dark}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fb;--panel:#fff;--line:#e3e6ee;--text:#10131a;
--muted:#5b6475;color-scheme:light}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:0 20px}
header{padding:72px 0 40px;text-align:center}
.light{display:inline-flex;gap:8px;padding:10px 14px;border-radius:999px;background:var(--panel);border:1px solid var(--line)}
.light i{width:14px;height:14px;border-radius:50%;display:block}
.light i:nth-child(1){background:var(--red);animation:pulse 3s infinite}
.light i:nth-child(2){background:var(--amber);animation:pulse 3s infinite 1s}
.light i:nth-child(3){background:var(--green);animation:pulse 3s infinite 2s}
@keyframes pulse{0%,100%{opacity:.25}15%,30%{opacity:1}}
@media (prefers-reduced-motion:reduce){.light i{animation:none}}
h1{font-size:clamp(2.6rem,7vw,4.4rem);line-height:1.05;margin:24px 0 12px;letter-spacing:-.03em}
h1 span{background:linear-gradient(90deg,var(--green),var(--accent));-webkit-background-clip:text;background-clip:text;color:transparent}
.lede{font-size:1.2rem;color:var(--muted);max-width:620px;margin:0 auto 28px}
.cta{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.btn{display:inline-block;padding:12px 20px;border-radius:12px;font-weight:600;text-decoration:none;border:1px solid var(--line);color:var(--text);background:var(--panel)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
section{padding:40px 0}
h2{font-size:1.5rem;margin:0 0 20px;letter-spacing:-.01em}
.call{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:24px;max-width:640px;margin:0 auto}
.msg{display:flex;gap:12px;margin:12px 0;align-items:flex-start}
.who{flex:none;width:64px;font-size:.8rem;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding-top:3px}
.bubble{padding:10px 14px;border-radius:12px;background:var(--bg);border:1px solid var(--line)}
.msg.you .bubble{border-color:var(--accent)}
.verdict{font-weight:700;color:var(--green)}
.note{color:var(--muted);font-size:.85rem;text-align:center;margin-top:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px}
.card b{display:block;margin-bottom:4px}
.card p{margin:0;color:var(--muted);font-size:.95rem}
.step{font-size:.75rem;font-weight:700;color:var(--accent);letter-spacing:.08em}
ul.rules{list-style:none;padding:0;margin:0;display:grid;gap:10px}
ul.rules li{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 16px}
ul.rules b{color:var(--text)}
footer{padding:40px 0 60px;text-align:center;color:var(--muted);font-size:.9rem}
footer a{color:var(--text)}
code{font:.9em ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--panel);border:1px solid var(--line);padding:1px 6px;border-radius:6px}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="light" aria-hidden="true"><i></i><i></i><i></i></div>
  <h1>Drive or transit?<br><span>Just ask Bling.</span></h1>
  <p class="lede">Call a phone number and say where you're going. Bling checks live Bay Area traffic and transit, a decision model makes the call, and you hear the answer with the reason, in seconds.</p>
  <div class="cta">
    <a class="btn primary" href="https://github.com/ziadgit/bling">View on GitHub</a>
    <a class="btn" href="#how">How it works</a>
  </div>
</header>

<section aria-label="Example call">
  <div class="call">
    <div class="msg"><div class="who">Bling</div><div class="bubble">Hey, it's Bling. Where are you headed?</div></div>
    <div class="msg you"><div class="who">You</div><div class="bubble">Salesforce Transit Center, from Oakland. I need to be there by six, and I've got two suitcases.</div></div>
    <div class="msg"><div class="who">Bling</div><div class="bubble">Let me check the roads and transit.</div></div>
    <div class="msg"><div class="who">Bling</div><div class="bubble"><span class="verdict">Take transit.</span> There's a crash blocking two lanes on the Bay Bridge approach, and BART is running normally.</div></div>
  </div>
  <p class="note">An example call. Real answers come from live conditions.</p>
</section>

<section id="how">
  <h2>How it works</h2>
  <div class="grid">
    <div class="card"><div class="step">01 · VAPI</div><b>You call</b><p>Vapi runs the phone call: the number, turn-taking and interruptions, and calling Bling's one tool.</p></div>
    <div class="card"><div class="step">02 · DEEPGRAM</div><b>It listens</b><p>Nova-3 transcribes you, tuned for 24 Bay Area names like BART, Caltrain, I-880 and SFO.</p></div>
    <div class="card"><div class="step">03 · EXA</div><b>It looks</b><p>Two live searches run at once, for today's traffic incidents and today's transit alerts, returned as structured data.</p></div>
    <div class="card"><div class="step">04 · JEV</div><b>It decides</b><p>Jev weighs the conditions and anything you mentioned (luggage, kids, budget, a hurry) and picks drive, transit or either.</p></div>
    <div class="card"><div class="step">05 · DEEPGRAM</div><b>It answers</b><p>An Aura voice says the verdict first, then the worst road issue and the worst transit issue.</p></div>
  </div>
</section>

<section>
  <h2>Ground rules</h2>
  <ul class="rules">
    <li><b>Code never picks the verdict.</b> If the decision model is unavailable, Bling says it couldn't make the call and still tells you what it found.</li>
    <li><b>It never invents conditions.</b> A search that fails or runs slow is reported as unchecked, never guessed.</li>
    <li><b>It answers fast.</b> Everything runs under an 8-second limit, so you aren't left on hold.</li>
    <li><b>It's private.</b> No transcripts, phone numbers or keys are logged.</li>
  </ul>
</section>

<footer>
  Built at a hackathon by Claude Code, from a written spec, in a timed session ·
  <a href="https://github.com/ziadgit/bling">source</a> · <a href="/healthz">status</a>
</footer>
</div>
</body>
</html>
"""
