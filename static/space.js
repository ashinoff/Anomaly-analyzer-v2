'use strict';
/* Живой космический фон: мерцающие дрейфующие звёзды + редкие электрические
   дуги между узлами (синие, иногда красные). Порт из канваса «Космос РОССЕТИ»
   (dc-runtime). Рисуется на <canvas id="space">, фиксированном за контентом. */
(function () {
  const cv = document.getElementById('space');
  if (!cv || !cv.getContext) return;
  const ctx = cv.getContext('2d');
  let W = 0, H = 0, dpr = 1, last = 0;
  const stars = [];
  let nodes = [];
  let arcs = [];

  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    stars.length = 0;
    const n = Math.floor(W * H / 6200);
    for (let i = 0; i < n; i++) stars.push({
      x: Math.random() * W, y: Math.random() * H, r: Math.random() * 1.3 + 0.3,
      tw: Math.random() * Math.PI * 2, sp: Math.random() * 0.02 + 0.004, vy: Math.random() * 0.05 + 0.02,
    });
    nodes = [];
    const m = Math.floor(W / 240) + 3;
    for (let i = 0; i < m; i++) nodes.push({ x: Math.random() * W, y: Math.random() * H * 0.85 });
  }

  function spawnArc() {
    if (nodes.length < 2) return;
    const a = nodes[Math.floor(Math.random() * nodes.length)];
    let b = nodes[Math.floor(Math.random() * nodes.length)], g = 0;
    while (b === a && g++ < 5) b = nodes[Math.floor(Math.random() * nodes.length)];
    if (a === b) return;
    const segs = 8, pts = [];
    for (let i = 0; i <= segs; i++) {
      const t = i / segs, k = t * (1 - t) * 4;
      pts.push([a.x + (b.x - a.x) * t + (Math.random() - 0.5) * 36 * k,
                a.y + (b.y - a.y) * t + (Math.random() - 0.5) * 36 * k]);
    }
    arcs.push({ pts, life: 1, hue: Math.random() < 0.15 ? 'red' : 'blue' });
  }

  function draw(now) {
    ctx.clearRect(0, 0, W, H);
    for (const s of stars) {
      s.tw += s.sp; s.y += s.vy; if (s.y > H) { s.y = 0; s.x = Math.random() * W; }
      const a = 0.35 + 0.45 * Math.sin(s.tw);
      ctx.beginPath(); ctx.fillStyle = 'rgba(200,222,255,' + a.toFixed(3) + ')';
      ctx.arc(s.x, s.y, s.r, 0, 7); ctx.fill();
    }
    for (const nd of nodes) {
      const gr = ctx.createRadialGradient(nd.x, nd.y, 0, nd.x, nd.y, 7);
      gr.addColorStop(0, 'rgba(120,180,255,.7)'); gr.addColorStop(1, 'rgba(120,180,255,0)');
      ctx.beginPath(); ctx.fillStyle = gr; ctx.arc(nd.x, nd.y, 7, 0, 7); ctx.fill();
    }
    if (now - last > 640 + Math.random() * 900) { spawnArc(); last = now; }
    arcs = arcs.filter(ar => ar.life > 0);
    for (const ar of arcs) {
      ar.life -= 0.045;
      const col = ar.hue === 'red' ? '255,70,90' : '150,200,255';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = 'rgba(' + col + ',' + (ar.life * 0.28).toFixed(3) + ')'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(ar.pts[0][0], ar.pts[0][1]);
      for (let i = 1; i < ar.pts.length; i++) ctx.lineTo(ar.pts[i][0], ar.pts[i][1]); ctx.stroke();
      ctx.strokeStyle = 'rgba(' + col + ',' + ar.life.toFixed(3) + ')'; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(ar.pts[0][0], ar.pts[0][1]);
      for (let i = 1; i < ar.pts.length; i++) ctx.lineTo(ar.pts[i][0], ar.pts[i][1]); ctx.stroke();
    }
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  resize();
  requestAnimationFrame(draw);
})();
