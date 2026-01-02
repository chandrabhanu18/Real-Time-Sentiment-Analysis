// chart.min.js - local fallback loader for Chart.js
// This file attempts to fetch Chart.js from multiple CDNs and eval it.
(async function(){
  const cdns = [
    'https://cdn.jsdelivr.net/npm/chart.js',
    'https://unpkg.com/chart.js/dist/chart.umd.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.2.1/chart.umd.min.js'
  ];
  for(const url of cdns){
    try{
      const resp = await fetch(url, {mode:'cors'});
      if(!resp.ok) continue;
      const src = await resp.text();
      const s = document.createElement('script');
      s.type = 'text/javascript';
      try{
        s.appendChild(document.createTextNode(src));
        document.head.appendChild(s);
        console.info('Chart.js loaded from', url);
        return;
      }catch(e){
        // fallback for older browsers
        s.text = src;
        document.head.appendChild(s);
        console.info('Chart.js loaded (alt) from', url);
        return;
      }
    }catch(e){
      console.warn('Failed to load Chart.js from', url, e);
      continue;
    }
  }
  console.error('All Chart.js CDN fallbacks failed — please provide a local chart.min.js bundle in the frontend folder');
})();
