/* REP Rally-Maps — il lavoro vero.
   1. apre la pagina del rally in una scheda in secondo piano;
   2. ogni secondo guarda se la mappa ha caricato le prove
      (sl.leaflet.data.storage.stages, come il segnalibro);
   3. dopo 12 s senza prove porta la scheda in primo piano: di solito
      manca il consenso ai cookie, che va dato una volta a mano;
   4. appena le prove ci sono, chiude la scheda e le restituisce.
   Legge solo rally-maps.com e non manda niente da nessun'altra parte. */
'use strict';

/* gira DENTRO la pagina di rally-maps: deve bastare a sé stessa */
function lettore(){
  var st = null;
  try { st = window.sl.leaflet.data.storage.stages; } catch(e){}
  if(!st || !st.length){
    try {
      var vis = [], coda = [[window.sl || {}, 0]];
      while(coda.length && !st){
        var x = coda.shift(), v = x[0];
        if(!v || typeof v !== 'object' || vis.indexOf(v) >= 0 || x[1] > 5) continue;
        vis.push(v);
        for(var k in v){
          var w; try { w = v[k]; } catch(e){ continue; }
          if(Array.isArray(w) && w.length && w[0] && w[0].geometries){ st = w; break; }
          if(w && typeof w === 'object') coda.push([w, x[1] + 1]);
        }
      }
    } catch(e){}
  }
  if(!st || !st.length) return null;
  function tratti(c, out){
    if(!c || !c.length || typeof c[0] === 'number') return out;
    if(c[0] && typeof c[0][0] === 'number'){ out.push(c.map(function(p){ return [+(+p[0]).toFixed(6), +(+p[1]).toFixed(6)]; })); return out; }
    for(var i = 0; i < c.length; i++) tratti(c[i], out);
    return out;
  }
  var prove = [];
  for(var i = 0; i < st.length; i++){
    var s = st[i] || {}, gs = s.geometries || [], usa = [], j;
    for(j = 0; j < gs.length; j++) if(gs[j] && gs[j].type === 'SL') usa.push(gs[j]);
    if(!usa.length) for(j = 0; j < gs.length; j++) if(gs[j] && gs[j].type !== 'PG' && gs[j].type !== 'PT') usa.push(gs[j]);
    var L = [];
    for(j = 0; j < usa.length; j++) tratti(usa[j].geometry && usa[j].geometry.coordinates, L);
    if(L.length) prove.push({ nome:String(s.fullName || s.name || ('SS' + (i + 1))), breve:String(s.name || ''), linee:L });
  }
  if(!prove.length) return null;
  var ev = (document.title || '').replace(/\s*[|–—-]\s*rally-?maps.*$/i, '').trim();
  return { rep:'rallymaps-1', evento:ev, url:location.href, preso:new Date().toISOString(), prove:prove, via:'estensione' };
}

function linkValido(u){ return /^https:\/\/(www\.)?rally-?maps\.com\//i.test(String(u || '')); }
function aspetta(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
function avvisa(tabProgramma, msg){ if(tabProgramma != null) chrome.tabs.sendMessage(tabProgramma, { tipo:'stato', msg:msg }).catch(function(){}); }

async function prendi(url, tabProgramma){
  if(!linkValido(url)) return { ok:false, msg:'serve un link di rally-maps.com (https://www.rally-maps.com/…)' };
  var tab = await chrome.tabs.create({ url:url, active:false });
  var inPrimoPiano = false, t0 = Date.now(), LIMITE = (globalThis.__REP_LIMITE || 120000);
  avvisa(tabProgramma, 'Apro la pagina del rally…');
  try {
    while(Date.now() - t0 < LIMITE){
      await aspetta(1000);
      var info;
      try { info = await chrome.tabs.get(tab.id); } catch(e){ return { ok:false, msg:'la scheda di rally-maps è stata chiusa' }; }
      if(info.status !== 'complete') continue;
      var r = null;
      try {
        var ris = await chrome.scripting.executeScript({ target:{ tabId:tab.id }, world:'MAIN', func:lettore });
        r = ris && ris[0] && ris[0].result;
      } catch(e){}
      if(r && r.prove && r.prove.length){
        if(!inPrimoPiano || !globalThis.__REP_LASCIA) chrome.tabs.remove(tab.id).catch(function(){});
        if(tabProgramma != null) chrome.tabs.update(tabProgramma, { active:true }).catch(function(){});
        return { ok:true, dati:r };
      }
      if(!inPrimoPiano && Date.now() - t0 > (globalThis.__REP_PRIMO || 12000)){
        inPrimoPiano = true;
        chrome.tabs.update(tab.id, { active:true }).catch(function(){});
        avvisa(tabProgramma, 'La mappa non carica le prove: nella scheda di rally-maps accetta i cookie (serve solo la prima volta). Il resto continua da solo.');
      }
    }
    chrome.tabs.remove(tab.id).catch(function(){});
    return { ok:false, msg:'nessuna prova trovata sulla pagina in ' + Math.round(LIMITE / 1000) + ' s: il link è la pagina di un rally?' };
  } catch(e){
    chrome.tabs.remove(tab.id).catch(function(){});
    return { ok:false, msg:String(e && e.message || e) };
  }
}

/* ═══ LIVE TIMING (v1.1) ═══════════════════════════════════════════════════
   Le pagine di live timing ricevono i tempi dal loro server (spesso con un
   collegamento continuo) e li disegnano in una tabella: un programma
   esterno non può leggerle direttamente. L'estensione apre la pagina in una
   scheda in secondo piano e, quando il programma lo chiede, legge la
   tabella dei tempi così come la vedi tu. Nessun dato va da altre parti. */
function lettoreTabella(){
  var RT=/\d{1,2}:\d{2}[.,]\d{1,3}|\b\d{2,3}[.,]\d{3}\b/;
  function testo(el){ return String(el.innerText||el.textContent||'').replace(/\s+/g, ' ').trim(); }
  var cand=[];
  document.querySelectorAll('table').forEach(function(t){
    var righe=[].slice.call(t.rows||[]).map(function(r){ return [].slice.call(r.cells).map(testo); }).filter(function(r){ return r.some(Boolean); });
    if(righe.length>=2) cand.push(righe);
  });
  document.querySelectorAll('[role=table],[role=grid],[role=treegrid]').forEach(function(t){
    var righe=[].slice.call(t.querySelectorAll('[role=row]')).map(function(r){ return [].slice.call(r.querySelectorAll('[role=cell],[role=gridcell],[role=columnheader],[role=rowheader]')).map(testo); });
    if(righe.length>=2) cand.push(righe);
  });
  /* griglie fatte di <div>: un contenitore con molti figli uguali, ognuno con più celle */
  document.querySelectorAll('div,ul,tbody,section').forEach(function(c){
    var f=c.children; if(!f || f.length<4 || f.length>400) return;
    var cls={}; for(var i=0;i<f.length;i++){ var k=f[i].tagName+'.'+(f[i].className||''); cls[k]=(cls[k]||0)+1; }
    var top=Object.keys(cls).sort(function(a,b){ return cls[b]-cls[a]; })[0];
    if(cls[top]<f.length*0.6) return;
    var righe=[];
    for(var j=0;j<f.length;j++){ var r=f[j]; if((r.tagName+'.'+(r.className||''))!==top) continue; if(r.children.length<3) continue; righe.push([].slice.call(r.children).map(testo)); }
    if(righe.length>=4) cand.push(righe);
  });
  var best=null, bs=0;
  cand.forEach(function(R){
    var conT=R.filter(function(r){ return r.some(function(c){ return RT.test(c); }); }).length;
    var col=Math.max.apply(null, R.map(function(r){ return r.length; }));
    var sc=conT*Math.min(col, 12);
    if(sc>bs){ bs=sc; best=R; }
  });
  if(!best) return { righe:[], titolo:document.title, punti:0 };
  var intest=null;
  if(best.length && !best[0].some(function(c){ return RT.test(c); })) intest=best.shift();
  return { intest:intest, righe:best.slice(0, 300), titolo:document.title, punti:bs, url:location.href };
}
async function statoLT(){ try { return (await chrome.storage.session.get('lt')).lt || {}; } catch(e){ return globalThis.__LT || (globalThis.__LT={}); } }
async function salvaLT(o){ try { await chrome.storage.session.set({ lt:o }); } catch(e){ globalThis.__LT=o; } }
function origine(u){ try { return new URL(u).origin+'/*'; } catch(e){ return null; } }
async function haPermesso(u){
  var o=origine(u); if(!o) return false;
  try { return await chrome.permissions.contains({ origins:[o] }); } catch(e){ return true; }
}
async function ltAvvia(url, tabProgramma){
  if(!/^https?:\/\//i.test(String(url||''))) return { ok:false, msg:'serve l\'indirizzo completo della pagina di live timing (https://…)' };
  if(!(await haPermesso(url))){
    chrome.tabs.create({ url:chrome.runtime.getURL('permesso.html')+'?url='+encodeURIComponent(url), active:true }).catch(function(){});
    return { ok:false, permesso:true, msg:'Consenti all\'estensione di leggere questo sito nella scheda che si è aperta, poi premi di nuovo CONNETTI.' };
  }
  var S=await statoLT();
  if(S.tab!=null){ try { await chrome.tabs.get(S.tab); if(S.url===url) return { ok:true, gia:true }; chrome.tabs.remove(S.tab).catch(function(){}); } catch(e){} }
  var tab=await chrome.tabs.create({ url:url, active:false });
  await salvaLT({ tab:tab.id, url:url, programma:tabProgramma });
  return { ok:true };
}
async function ltLeggi(){
  var S=await statoLT();
  if(S.tab==null) return { ok:false, msg:'live timing non avviato' };
  try { await chrome.tabs.get(S.tab); } catch(e){ return { ok:false, chiusa:true, msg:'la scheda del live timing è stata chiusa' }; }
  try {
    var ris=await chrome.scripting.executeScript({ target:{ tabId:S.tab, allFrames:true }, func:lettoreTabella });
    var best=null; (ris||[]).forEach(function(r){ var x=r && r.result; if(x && (!best || x.punti>best.punti)) best=x; });
    return { ok:true, dati:best || { righe:[] } };
  } catch(e){ return { ok:false, msg:String(e && e.message || e) }; }
}
async function ltFerma(){ var S=await statoLT(); if(S.tab!=null) chrome.tabs.remove(S.tab).catch(function(){}); await salvaLT({}); return { ok:true }; }

chrome.runtime.onMessage.addListener(function(m, mittente, rispondi){
  if(!m || !/^lt-/.test(m.tipo || '')) return false;
  var tp=mittente && mittente.tab ? mittente.tab.id : null;
  var f=m.tipo==='lt-avvia'? ltAvvia(m.url, tp) : (m.tipo==='lt-leggi'? ltLeggi() : (m.tipo==='lt-ferma'? ltFerma() : Promise.resolve({ ok:true })));
  f.then(rispondi, function(e){ rispondi({ ok:false, msg:String(e && e.message || e) }); });
  return true;
});

chrome.runtime.onMessage.addListener(function(m, mittente, rispondi){
  if(!m || m.tipo !== 'prendi') return false;
  var tabProgramma = mittente && mittente.tab ? mittente.tab.id : null;
  prendi(m.url, tabProgramma).then(rispondi, function(e){ rispondi({ ok:false, msg:String(e && e.message || e) }); });
  return true;   /* risposta asincrona */
});
