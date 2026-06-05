(function(){
  var url = document.currentScript && document.currentScript.getAttribute('data-track-url');
  if (!url) return;
  try {
    var payload = {
      r: document.referrer || '',
      p: location.pathname,
      s: screen.width + 'x' + screen.height,
      t: Date.now()
    };
    navigator.sendBeacon(url, JSON.stringify(payload));
  } catch(e) {}
})();
