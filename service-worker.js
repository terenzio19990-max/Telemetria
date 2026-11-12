var CACHE='rep-telefono-v5.5';
var ASSETS=["./", "./index.html", "./manifest.json", "./icon-192.svg", "./icon-512.svg"];
self.addEventListener('install',function(ev){
  ev.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(ASSETS).catch(function(){}); }));
  self.skipWaiting();
});
self.addEventListener('activate',function(ev){
  ev.waitUntil(caches.keys().then(function(ks){
    return Promise.all(ks.filter(function(k){return k!==CACHE;}).map(function(k){return caches.delete(k);}));
  }).then(function(){ return self.clients.claim(); }));
});
self.addEventListener('fetch',function(ev){
  if(ev.request.method!=='GET') return;
  var acc=(ev.request.headers.get('accept')||'');
  var isHTML = ev.request.destination==='document' || acc.indexOf('text/html')>=0;
  if(isHTML){
    /* rete per prima: cosi' l'aggiornamento arriva appena c'e' linea */
    ev.respondWith(fetch(ev.request).then(function(r){
      var cp=r.clone(); caches.open(CACHE).then(function(c){ c.put(ev.request,cp); }).catch(function(){});
      return r;
    }).catch(function(){ return caches.match(ev.request).then(function(m){ return m||caches.match('./'); }); }));
  } else {
    ev.respondWith(caches.match(ev.request).then(function(m){
      return m||fetch(ev.request).then(function(r){
        if(r.ok){ var cp=r.clone(); caches.open(CACHE).then(function(c){ c.put(ev.request,cp); }).catch(function(){}); }
        return r;
      }).catch(function(){ return m; });
    }));
  }
});
