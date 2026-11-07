"""Replace the dashboard's app grid with a paginated, icon-aware version."""
import pathlib

p = pathlib.Path("tony/ui.py")
s = p.read_text()

i = s.index("async function loadApps(){")
j = s.index("async function loadConns(){")

NEW = r"""const PAGE = 60;
let APPS = [], CATS = [], CUR = null, CURACT = null, CONNS = [], TOTAL = 0, OFFSET = 0, Q = '', CAT = '', TIER = '';

function initials(name){
  const w = String(name||'').replace(/[^A-Za-z0-9 ]/g,' ').trim().split(/\s+/).filter(Boolean);
  if(!w.length) return '?';
  return (w.length===1 ? w[0].slice(0,2) : w[0][0]+w[1][0]).toUpperCase();
}
function hue(slug){let x=0;for(const ch of String(slug))x=(x*31+ch.charCodeAt(0))%360;return x}
function iconHTML(a, size){
  const s = size || 30;
  const mono = '<span class="mono" style="width:'+s+'px;height:'+s+'px;background:hsl('+hue(a.slug)+',58%,46%);font-size:'+Math.round(s*0.38)+'px">'+esc(initials(a.name))+'</span>';
  if(!a.logo) return mono;
  return '<span class="ico">'+mono+'<img src="'+esc(a.logo)+'" alt="" loading="lazy" decoding="async" onload="this.previousElementSibling.style.display=\'none\'" onerror="this.remove()">'+'</span>';
}

async function loadApps(reset){
  if(reset){OFFSET=0; APPS=[];}
  const url = BASE+'/v1/apps?limit='+PAGE+'&offset='+OFFSET+
    '&search='+encodeURIComponent(Q)+'&category='+encodeURIComponent(CAT)+'&tier='+encodeURIComponent(TIER);
  const d = await (await fetch(url)).json();
  CATS = d.categories || CATS; TOTAL = d.total||0;
  APPS = APPS.concat(d.apps||[]); OFFSET = APPS.length;
  document.getElementById('appcount').textContent = TOTAL.toLocaleString()+' apps';
  renderChips(); renderApps(); loadConns();
}
function renderChips(){
  const chips = document.getElementById('cats');
  if(chips){
    chips.innerHTML = '<div class="chip'+(CAT===''?' on':'')+'" data-c="">All</div>' +
      CATS.map(c=>'<div class="chip'+(CAT===c?' on':'')+'" data-c="'+esc(c)+'">'+esc(c)+'</div>').join('');
    chips.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{CAT=ch.dataset.c; loadApps(true)});
  }
  const t = document.getElementById('tiers');
  if(t){
    const opts=[['','All apps'],['actions','Built-in actions'],['proxy','API proxy'],['directory','Directory']];
    t.innerHTML = opts.map(([v,l])=>'<div class="chip'+(TIER===v?' on':'')+'" data-t="'+v+'">'+l+'</div>').join('');
    t.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{TIER=ch.dataset.t; loadApps(true)});
  }
}
function tierLabel(t){return t==='actions'?'actions':(t==='proxy'?'proxy':'directory')}
function renderApps(){
  const grid = document.getElementById('appgrid');
  if(!APPS.length){grid.innerHTML='<div class="empty" style="grid-column:1/-1">Nothing matched.</div>';return}
  grid.innerHTML = APPS.map(a=>{
    const c = CONNS.find(x=>x.app===a.slug && x.status==='active');
    return '<div class="app" data-slug="'+esc(a.slug)+'">'+
      '<div class="row">'+iconHTML(a,30)+
      '<div style="min-width:0"><div class="nm">'+esc(a.name)+'</div><div class="cat">'+esc(a.category)+'</div></div></div>'+
      '<p class="desc">'+esc(a.description||'')+'</p>'+
      '<div class="foot">'+(c?'<span class="badge ok">connected</span>':'')+
      '<span class="badge">'+a.actions_count+' act</span>'+
      '<span class="badge '+a.tier+'">'+tierLabel(a.tier)+'</span></div></div>';
  }).join('');
  grid.querySelectorAll('.app').forEach(el=>el.onclick=()=>openApp(el.dataset.slug));
  const more = document.getElementById('more');
  if(more){
    more.style.display = OFFSET < TOTAL ? 'block' : 'none';
    more.textContent = 'Load more ('+OFFSET.toLocaleString()+' of '+TOTAL.toLocaleString()+')';
  }
}
let _qt;
document.getElementById('q').addEventListener('input',e=>{
  clearTimeout(_qt);
  _qt = setTimeout(()=>{Q = e.target.value.trim(); loadApps(true)}, 220);
});
"""

s = s[:i] + NEW + s[j:]
p.write_text(s)
print("apps UI replaced")
