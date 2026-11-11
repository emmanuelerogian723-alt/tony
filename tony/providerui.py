"""A setup screen for hosted OAuth: paste a provider's client id and secret once."""
from __future__ import annotations

def provider_setup_html() -> str:
    return """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Provider setup · Tony</title>
<style>
*{box-sizing:border-box}
:root{--bg:#000;--line:#1b1b1b;--dim:#8e8e8e;--hot:#E2542B;--ink:#F3F0E9}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Inter,sans-serif;-webkit-font-smoothing:antialiased}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.wrap{max-width:960px;margin:0 auto;padding:0 22px}
header{border-bottom:1px solid #141414;position:sticky;top:0;background:rgba(0,0,0,.88);
 backdrop-filter:blur(10px);z-index:5}
header .wrap{height:62px;display:flex;align-items:center;gap:14px}
header b{font-size:14px;letter-spacing:-.01em}
header a{color:var(--dim);text-decoration:none;font-size:13px}
header a:hover{color:var(--ink)}
.grow{flex:1}
h1{font-size:34px;line-height:1.1;letter-spacing:-.03em;margin:44px 0 12px}
p.lede{color:#9a9a9a;max-width:60ch;margin:0 0 26px;font-size:15px}
.meter{display:flex;align-items:center;gap:14px;padding:16px 18px;border:1px solid var(--line);
 border-radius:14px;background:linear-gradient(180deg,#0a0a0a,#050505);margin-bottom:26px}
.meter b{font-size:22px;letter-spacing:-.02em}
.bar{flex:1;height:6px;border-radius:99px;background:#151515;overflow:hidden}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#E2542B,#ff8a5c);width:0%}
input,button{font:inherit}
.search{width:100%;padding:11px 14px;border-radius:11px;border:1px solid #232323;background:#0a0a0a;
 color:var(--ink);margin-bottom:16px;outline:none}
.search:focus{border-color:#3a3a3a}
.row{border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:10px;background:#050505}
.row.ready{border-color:#243024;background:#050805}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.name{font-weight:600;font-size:15px}
.cat{color:#6f6f6f;font-size:12px}
.pill{margin-left:auto;font-size:11px;letter-spacing:.05em;text-transform:uppercase;padding:4px 9px;
 border-radius:99px;border:1px solid #2a2a2a;color:#a5a5a5}
.pill.ok{border-color:#2c4a2c;color:#8fe08f}
.form{display:none;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.form.on{display:grid}
.field{display:flex;flex-direction:column;gap:6px}
.field label{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#7d7d7d}
.field input,.field textarea{padding:10px 12px;border-radius:9px;border:1px solid #232323;background:#0b0b0b;
 color:var(--ink);outline:none;width:100%}
.field input:focus{border-color:#3d3d3d}
.field.wide{grid-column:1/-1}
.actions{display:flex;gap:10px;grid-column:1/-1;margin-top:4px}
.btn{cursor:pointer;border-radius:999px;padding:9px 16px;font-size:13px;border:1px solid #2c2c2c;
 background:#0e0e0e;color:var(--ink)}
.btn.hot{background:var(--ink);color:#000;border-color:var(--ink);font-weight:600}
.btn.hot:hover{transform:translateY(-1px)}
.btn.link{background:transparent;border-color:transparent;color:#8e8e8e;padding:4px 6px;font-size:12px}
.btn.link:hover{color:var(--ink)}
.hint{color:#6d6d6d;font-size:12px;margin-top:10px}
code{background:#0e0e0e;border:1px solid #202020;border-radius:6px;padding:2px 6px;font-size:12.5px}
@media(max-width:700px){.form{grid-template-columns:1fr}h1{font-size:27px}}
</style></head><body>
<header><div class="wrap"><b>Tony</b><a href="/">Home</a><a href="/account">Console</a>
<span class="grow"></span><a class="mono" href="/docs">Docs</a></div></header>
<main class="wrap">
  <h1>Hosted OAuth providers</h1>
  <p class="lede">Each provider needs its own OAuth app once. Paste the client id and secret and its
     Connect button starts working for every user of this workspace. Secrets are encrypted and never
     returned again.</p>
  <div class="meter"><b id="ready">–</b><span class="mono" style="color:#7d7d7d;font-size:12px">ready</span>
    <div class="bar"><i id="fill"></i></div><span class="mono" style="color:#7d7d7d;font-size:12px" id="total"></span></div>
  <input class="search" id="q" placeholder="Filter providers, e.g. github, slack, google">
  <div id="list"></div>
  <p class="hint">Authorized redirect URI to paste into the provider: <code id="cb">/oauth/callback</code>
    <button class="btn link" id="copycb">copy</button></p>
</main>
<script>
var store={providers:[]};
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function card(p){
  var el=document.createElement('div');
  el.className='row'+(p.ready?' ready':'');
  el.innerHTML='<div class="top"><span class="name">'+esc(p.name)+'</span>'
   +'<span class="cat">'+esc(p.category||'')+'</span>'
   +'<span class="pill '+(p.ready?'ok':'')+'">'+(p.ready?'ready':'not set')+'</span></div>'
   +'<button class="btn link" type="button">'+(p.ready?'Update credentials':'Add credentials')+'</button>'
   +'<div class="form"><div class="field"><label>client id</label><input class="cid" placeholder="Iv1.abc123"></div>'
   +'<div class="field"><label>client secret</label><input class="sec" type="password" placeholder="optional for public clients"></div>'
   +'<div class="actions"><button class="btn hot save" type="button">Save</button>'
   +'<button class="btn cancel" type="button">Cancel</button>'
   +'<span class="hint" style="margin:0;align-self:center">scopes: '+esc((p.scopes||[]).join(' '))+'</span></div></div>';
  var form=el.querySelector('.form'), status=el.querySelector('.pill');
  el.querySelector('.btn.link').onclick=function(){form.classList.toggle('on')};
  el.querySelector('.cancel').onclick=function(){form.classList.remove('on')};
  el.querySelector('.save').onclick=async function(){
    var cid=el.querySelector('.cid').value.trim(), sec=el.querySelector('.sec').value;
    if(!cid){status.textContent='client id needed';return}
    status.textContent='saving…';
    var r=await fetch('/v1/account/providers/'+encodeURIComponent(p.slug),{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:cid,client_secret:sec})});
    if(r.ok){p.ready=true;status.textContent='ready';status.classList.add('ok');
      el.classList.add('ready');el.querySelector('.sec').value='';form.classList.remove('on');count()}
    else{var j=await r.json().catch(function(){return {}});status.textContent=(j.detail||'failed')}
  };
  return el;
}
function render(){
  var q=document.getElementById('q').value.toLowerCase(), list=document.getElementById('list');
  list.innerHTML='';
  store.providers.filter(function(p){return !q||p.name.toLowerCase().includes(q)||p.slug.includes(q)})
    .slice(0,60).forEach(function(p){list.appendChild(card(p))});
}
function count(){
  var r=store.providers.filter(function(p){return p.ready}).length;
  document.getElementById('ready').textContent=r;
  document.getElementById('total').textContent='of '+store.providers.length;
  document.getElementById('fill').style.width=(100*r/Math.max(1,store.providers.length))+'%';
}
fetch('/v1/account/providers').then(function(r){return r.json()}).then(function(d){
  store.providers=d.providers||[];
  document.getElementById('cb').textContent=location.origin+'/oauth/callback';
  count();render();
}).catch(function(){document.getElementById('list').textContent='Sign in to manage providers.'});
document.getElementById('q').oninput=render;
document.getElementById('copycb').onclick=function(){
  navigator.clipboard.writeText(location.origin+'/oauth/callback');
  this.textContent='copied';var b=this;setTimeout(function(){b.textContent='copy'},1200)};
</script></body></html>"""
