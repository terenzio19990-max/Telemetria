var u=new URLSearchParams(location.search).get('url')||'', o='';
try { o=new URL(u).origin+'/*'; } catch(e){}
document.getElementById('sito').textContent=o||u;
document.getElementById('ok').onclick=function(){
  chrome.permissions.request({ origins:[o] }, function(si){
    document.getElementById('esito').textContent=si? '✓ fatto: torna al programma' : 'permesso negato';
    if(si) chrome.runtime.sendMessage({ tipo:'lt-permesso-ok', url:u });
    if(si) setTimeout(function(){ window.close(); }, 1200);
  });
};
