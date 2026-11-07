/* REP Estensione — ponte fra la pagina del programma e l'estensione.
   Gira su ogni pagina, ma risponde solo se la pagina è Race Engineer Pro
   (c'è il riquadro «Prove da Rally-Maps» o il titolo del programma). */
(function(){
  'use strict';
  function eProgramma(){
    return !!document.getElementById('rm-panel') || !!document.getElementById('page-livetiming') || /Race Engineer Pro/i.test(document.title || '');
  }
  function annuncia(){ if(eProgramma()) window.postMessage({ rep:'rmext-pronto', v:'1.1', capacita:['rallymaps','livetiming'] }, '*'); }
  window.addEventListener('message', function(ev){
    if(ev.source !== window) return;
    var d = ev.data;
    if(!d || typeof d !== 'object') return;
    if(d.rep === 'rmext-ping'){ annuncia(); return; }
    if(/^ltext-(avvia|leggi|ferma)$/.test(d.rep || '') && eProgramma()){
      var lid = d.id;
      try {
        chrome.runtime.sendMessage({ tipo:d.rep.replace('ltext-', 'lt-'), url:String(d.url || '') }, function(r){
          var err = chrome.runtime.lastError ? chrome.runtime.lastError.message : null;
          window.postMessage({ rep:'ltext-risposta', id:lid, r:err? { ok:false, msg:err } : (r || { ok:false, msg:'nessuna risposta' }) }, '*');
        });
      } catch(e){ window.postMessage({ rep:'ltext-risposta', id:lid, r:{ ok:false, msg:String(e && e.message || e) } }, '*'); }
      return;
    }
    if(d.rep !== 'rmext-prendi' || !eProgramma()) return;
    var id = d.id;
    try {
      chrome.runtime.sendMessage({ tipo:'prendi', url:String(d.url || '') }, function(r){
        var errore = chrome.runtime.lastError ? chrome.runtime.lastError.message : null;
        if(errore || !r) window.postMessage({ rep:'rmext-errore', id:id, msg:errore || 'nessuna risposta dall’estensione' }, '*');
        else if(r.ok) window.postMessage({ rep:'rmext-dati', id:id, dati:r.dati }, '*');
        else window.postMessage({ rep:'rmext-errore', id:id, msg:r.msg }, '*');
      });
    } catch(e){ window.postMessage({ rep:'rmext-errore', id:id, msg:String(e && e.message || e) }, '*'); }
  });
  /* avvisi di avanzamento dalla scheda di rally-maps */
  try {
    chrome.runtime.onMessage.addListener(function(m){
      if(m && m.tipo === 'stato' && eProgramma()) window.postMessage({ rep:'rmext-stato', msg:m.msg }, '*');
    });
  } catch(e){}
  annuncia();
  setTimeout(annuncia, 1500);
  setTimeout(annuncia, 5000);
})();
