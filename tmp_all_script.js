

      // CDN fallback: if Chart is not available, load local fallback script
      (function(){
        function ensureChart(){
          if(typeof Chart === 'undefined'){
            var s = document.createElement('script');
            s.src = '/chart.min.js';
            s.async = true;
            s.onload = function(){ console.log('Loaded local Chart fallback'); };
            s.onerror = function(){ console.warn('Local Chart fallback failed to load'); };
            document.head.appendChild(s);
          }
        }
        if(document.readyState === 'loading'){
          document.addEventListener('DOMContentLoaded', ensureChart);
        } else { ensureChart(); }
      })();
    

      // state
      const state = { paused: false, filter: 'all', posts: [], counts: {positive:0,negative:0,neutral:0,total:0}, emotions:{}, trendWindow:[] };

      const apiBase = (location.hostname === 'localhost') ? 'http://localhost:8000' : `${location.protocol}//${location.host}`;

      // helpers
      function normSentiment(post){
        if(!post) return 'neutral';
        return (post.sentiment_label || (post.sentiment && post.sentiment.label) || post.label || 'neutral').toString().toLowerCase();
      }

      function makePostElement(p, highlight=false){
        const div = document.createElement('div');
        div.className = 'post' + (highlight? ' new':'');
        const label = normSentiment(p);
        const pillClass = label==='positive' ? 'sent-positive' : label==='negative' ? 'sent-negative' : 'sent-neutral';
        div.innerHTML = `<div class="meta"><div style="font-weight:600">${p.source||p.author||'source'}</div><div>${new Date(p.timestamp||p.created_at||Date.now()).toLocaleString()}</div></div>
          <div class="text">${escapeHtml(p.content||p.text||p.body||'')}</div>
          <div style="margin-top:8px;display:flex;justify-content:space-between;align-items:center"><div class="sent-pill ${'sent-'+label}">${label}</div><div style="font-size:12px;color:#9fb4c9">score: ${Number((p.score||p.sentiment_score||p.confidence)||0).toFixed(2)}</div></div>`;
        return div;
      }

      function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"})[c]); }

      // charts
      let distChart, trendChart, emotionChart;

      function initCharts(){
        const ctxD = document.getElementById('distChart').getContext('2d');
        distChart = new Chart(ctxD, {
          type: 'pie',
          data: { labels: ['Positive','Negative','Neutral'], datasets: [{ data: [0,0,0], backgroundColor: ['#10b981','#ef4444','#94a3b8'] }] },
          options: { plugins: { legend: { position: 'bottom' } } }
        });
        // attach onClick after creation to avoid long inline expression
        distChart.options.onClick = function(e){
          try{
            const el = distChart.getElementsAtEventForMode(e, 'nearest', { intersect: true }, true);
            if(el && el.length){ const idx = el[0].index; const label = distChart.data.labels[idx].toLowerCase(); setFilter(label); }
          }catch(err){ console.error('distChart onClick', err); }
        };

        const ctxE = document.getElementById('emotionChart').getContext('2d');
        emotionChart = new Chart(ctxE, {type:'bar',data:{labels:[],datasets:[{label:'Count',data:[],backgroundColor:'#06b6d4'}]},options:{indexAxis:'y',plugins:{legend:{display:false}}}});

        const ctxT = document.getElementById('trendChart').getContext('2d');
        trendChart = new Chart(ctxT, {type:'line',data:{labels:[],datasets:[{label:'Positive',data:[],borderColor:'#10b981',fill:false},{label:'Negative',data:[],borderColor:'#ef4444',fill:false},{label:'Neutral',data:[],borderColor:'#94a3b8',fill:false}]},options:{interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom'}}}});
      }

      function setFilter(f){ document.getElementById('filterSelect').value = f; state.filter = f; renderPosts(); }

      function updateChartsOnNew(p){
        const label = normSentiment(p);
        state.counts[label] = (state.counts[label]||0)+1;
        state.counts.total = (state.counts.total||0)+1;

        // update dist pie
        const data = [state.counts.positive||0, state.counts.negative||0, state.counts.neutral||0];
        distChart.data.datasets[0].data = data; distChart.update('none');

        // update emotion chart
        if(p.emotion){ state.emotions[p.emotion] = (state.emotions[p.emotion]||0)+1; emotionChart.data.labels = Object.keys(state.emotions); emotionChart.data.datasets[0].data = Object.values(state.emotions); emotionChart.update('none'); }

        // trend: accumulate brief window
        const t = new Date(p.timestamp||p.created_at||Date.now()).toISOString();
        const labelTime = new Date(t).toLocaleTimeString();
        let lastLabels = trendChart.data.labels; let lastPos = trendChart.data.datasets[0].data, lastNeg = trendChart.data.datasets[1].data, lastNeu = trendChart.data.datasets[2].data;
        if(lastLabels.length===0 || lastLabels[lastLabels.length-1] !== labelTime){ lastLabels.push(labelTime); lastPos.push(0); lastNeg.push(0); lastNeu.push(0); if(lastLabels.length>50){ lastLabels.shift(); lastPos.shift(); lastNeg.shift(); lastNeu.shift(); } }
        const idx = lastLabels.length-1;
        if(label==='positive') lastPos[idx] = (lastPos[idx]||0)+1;
        if(label==='negative') lastNeg[idx] = (lastNeg[idx]||0)+1;
        if(label==='neutral') lastNeu[idx] = (lastNeu[idx]||0)+1;
        trendChart.update('none');
      }

      // rendering
      function renderPosts(){
        const container = document.getElementById('postsList'); container.innerHTML='';
        const q = document.getElementById('searchInput').value.trim().toLowerCase();
        const filtered = state.posts.filter(p=>{
          const s = normSentiment(p);
          if(state.filter!=='all' && s!==state.filter) return false;
          if(q && !( (p.content||p.text||'').toLowerCase().includes(q) )) return false;
          return true;
        });
        filtered.slice(0,200).forEach(p=> container.appendChild(makePostElement(p)));
      }

      function renderMetrics(summary){
        const el = document.getElementById('metrics'); el.innerHTML='';
        const items = [
          {title:'Total',value:state.counts.total||0},
          {title:'Positive',value:state.counts.positive||0},
          {title:'Negative',value:state.counts.negative||0},
          {title:'Neutral',value:state.counts.neutral||0}
        ];
        items.forEach(it=>{ const d=document.createElement('div'); d.style.padding='8px 12px'; d.style.background='rgba(255,255,255,0.02)'; d.style.borderRadius='8px'; d.innerHTML=`<div style="font-size:12px;color:#9fb4c9">${it.title}</div><div style="font-weight:700;font-size:18px">${it.value}</div>`; el.appendChild(d); });
      }

      // initial API loads
      async function loadInitial(){
        try{
          const [postsRes, distRes, trendRes] = await Promise.all([
            fetch(apiBase + '/api/posts'),
            fetch(apiBase + '/api/sentiment/distribution?hours=24'),
            fetch(apiBase + '/api/sentiment/aggregate?period=hour')
          ]);
          if(postsRes.ok){ const j=await postsRes.json(); state.posts = (j.posts||j||[]).slice().reverse(); state.posts.forEach(p=>{ state.counts[normSentiment(p)] = (state.counts[normSentiment(p)]||0)+1; state.counts.total = (state.counts.total||0)+1; if(p.emotion) state.emotions[p.emotion] = (state.emotions[p.emotion]||0)+1 }); }
          if(distRes.ok){ const j=await distRes.json(); const dist = j.distribution||{}; distChart.data.datasets[0].data = [dist.positive||0, dist.negative||0, dist.neutral||0]; distChart.update(); }
          if(trendRes.ok){ const j=await trendRes.json(); const arr = j.data||[]; trendChart.data.labels = arr.map(d=>new Date(d.timestamp).toLocaleTimeString()); trendChart.data.datasets[0].data = arr.map(d=>d.positive_count||0); trendChart.data.datasets[1].data = arr.map(d=>d.negative_count||0); trendChart.data.datasets[2].data = arr.map(d=>d.neutral_count||0); trendChart.update(); }
          renderMetrics(); renderPosts();
          // populate emotion chart
          emotionChart.data.labels = Object.keys(state.emotions); emotionChart.data.datasets[0].data = Object.values(state.emotions); emotionChart.update();
        }catch(e){console.error('initial load',e)}
      }

      // websocket
      let ws, backoff=1000;
      function startWS(){
        ws = new WebSocket((location.protocol==='https:'?'wss://':'ws://') + location.hostname + ':8000/ws/sentiment');
        ws.onopen = ()=>{ backoff=1000; document.getElementById('pauseBtn').innerText = state.paused ? 'Resume' : 'Pause'; };
        ws.onmessage = (ev)=>{ if(state.paused) return; try{ const msg = JSON.parse(ev.data); const payload = msg.data || msg.post || msg; const post = { content: payload.content || payload.text || payload.body, sentiment_label: payload.sentiment_label || (payload.sentiment && payload.sentiment.label), timestamp: payload.timestamp || payload.created_at, source: payload.source || payload.author, score: payload.score || payload.sentiment_score || payload.confidence, emotion: payload.emotion }; state.posts.unshift(post); if(state.posts.length>1000) state.posts.pop(); updateChartsOnNew(post); renderPosts(); renderMetrics(); setTimeout(()=>{ const el = document.getElementById('postsList').firstChild; if(el) el.classList.add('new'); setTimeout(()=>el && el.classList.remove('new'),2500); },40);}catch(e){console.error('ws parse',e)} };
        ws.onclose = ()=>{ console.warn('ws closed'); setTimeout(()=>{ backoff = Math.min(16000, backoff*2); startWS(); }, backoff); };
        ws.onerror = (e)=>{ console.error('ws error', e); ws.close(); };
      }

      // controls
      document.addEventListener('DOMContentLoaded', ()=>{
        function startApp(){
          try{ initCharts(); loadInitial(); startWS(); }catch(e){console.error('startApp',e)}
          document.getElementById('pauseBtn').addEventListener('click', ()=>{ state.paused = !state.paused; document.getElementById('pauseBtn').innerText = state.paused ? 'Resume' : 'Pause'; });
          document.getElementById('clearBtn').addEventListener('click', ()=>{ state.posts=[]; document.getElementById('postsList').innerHTML=''; state.counts={positive:0,negative:0,neutral:0,total:0}; distChart.data.datasets[0].data=[0,0,0]; distChart.update(); renderMetrics(); });
          document.getElementById('filterSelect').addEventListener('change', (e)=>{ state.filter = e.target.value; renderPosts(); });
          document.getElementById('searchInput').addEventListener('input', ()=>renderPosts());
          document.getElementById('rangeSelect').addEventListener('change', ()=>{ loadInitial(); });
        }
        if(typeof Chart === 'undefined'){
          let tries = 0;
          const iv = setInterval(()=>{
            if(typeof Chart !== 'undefined' || ++tries>25){ clearInterval(iv); startApp(); }
          }, 200);
        } else {
          startApp();
        }
      });
    
