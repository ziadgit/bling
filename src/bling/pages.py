"""The two voice-link pages, as small inline HTML. Every value is HTML-escaped."""

from html import escape

_HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bling</title><style>
body{font-family:system-ui,sans-serif;max-width:32rem;margin:0 auto;padding:1.5rem 1rem;
line-height:1.5;background:#fff;color:#111}
@media (prefers-color-scheme:dark){body{background:#111;color:#eee}}
h1{font-size:1.4rem}p.verdict{font-size:1.2rem}audio{width:100%;margin-top:1rem}
button{font-size:1.1rem;padding:.8rem 1.4rem;border-radius:.6rem;border:0;background:#2563eb;
color:#fff;width:100%}button:disabled{opacity:.5}
</style></head><body>"""
_TAIL = "</body></html>"


def review_page(token: str, text: str) -> str:
    t = escape(token, quote=True)
    return (
        f"{_HEAD}<h1>Bling</h1><p class=\"verdict\">{escape(text)}</p>"
        f'<audio controls autoplay src="/v/{t}/audio"></audio>{_TAIL}'
    )


def not_found_page() -> str:
    return f"{_HEAD}<h1>Link not found</h1><p>This link is invalid or has expired.</p>{_TAIL}"


_EXPLAIN_JS = """<script>
const btn=document.getElementById('rec'),out=document.getElementById('out'),
pl=document.getElementById('player');let mr=null,chunks=[];
btn.onclick=async()=>{
 if(mr&&mr.state==='recording'){mr.stop();btn.disabled=true;btn.textContent='Thinking…';return;}
 let stream;try{stream=await navigator.mediaDevices.getUserMedia({audio:true});}
 catch(e){out.textContent='I need microphone access to hear you.';return;}
 chunks=[];mr=new MediaRecorder(stream);
 mr.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
 mr.onstop=async()=>{
  stream.getTracks().forEach(t=>t.stop());
  const blob=new Blob(chunks,{type:mr.mimeType||'audio/webm'});
  const fd=new FormData();fd.append('audio',blob,'audio.webm');
  try{
   const r=await fetch(location.pathname.replace(/\\/$/,'')+'/audio',{method:'POST',body:fd});
   const j=await r.json();
   if(r.ok){out.textContent=j.text;pl.src=j.audio_url;pl.hidden=false;pl.play().catch(()=>{});
    btn.hidden=true;}
   else{out.textContent=j.error||'Something went wrong.';btn.disabled=false;
    btn.textContent='Record';}
  }catch(e){out.textContent='Something went wrong.';btn.disabled=false;btn.textContent='Record';}
 };
 mr.start();btn.textContent='Stop';out.textContent='Listening…';
};
</script>"""


def explain_page(destination: str) -> str:
    return (
        f"{_HEAD}<h1>Tell me about your trip to {escape(destination)}</h1>"
        "<p>Tap record, say what's going on, then tap stop.</p>"
        '<button id="rec">Record</button><p id="out" class="verdict" aria-live="polite"></p>'
        f'<audio id="player" controls hidden></audio>{_EXPLAIN_JS}{_TAIL}'
    )
