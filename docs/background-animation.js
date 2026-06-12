(function () {

  // ── Canvas ────────────────────────────────────────────────────────────────
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  document.body.insertBefore(canvas, document.body.firstChild);
  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  // ── Palette ───────────────────────────────────────────────────────────────
  const PALETTE = [
    [220, 140, 140], // rose
    [235, 175, 140], // peach
    [195, 158,  88], // gold
    [180, 145, 210], // lavender
    [220, 175, 185], // blush
    [215, 198, 135], // champagne
  ];
  const SHAPES = ['circle', 'heart', 'diamond'];

  // ── Particle factory ──────────────────────────────────────────────────────
  function makeParticle(spreadY) {
    return {
      x:            Math.random() * window.innerWidth,
      y:            spreadY
                      ? Math.random() * window.innerHeight
                      : window.innerHeight + 40 + Math.random() * 160,
      vy:           -(0.18 + Math.random() * 0.32),
      vx:           (Math.random() - 0.5) * 0.10,
      color:        PALETTE[Math.floor(Math.random() * PALETTE.length)],
      baseSize:     12 + Math.random() * 28,
      shape:        SHAPES[Math.floor(Math.random() * SHAPES.length)],
      sizePhase:    Math.random() * Math.PI * 2,
      sizeSpeed:    0.004 + Math.random() * 0.006,
      sizeAmp:      0.10  + Math.random() * 0.14,
      opacityPhase: Math.random() * Math.PI * 2,
      opacitySpeed: 0.002 + Math.random() * 0.005,
      baseOpacity:  0.15  + Math.random() * 0.18,
      opacityAmp:   0.07  + Math.random() * 0.08,
      focusPhase:   Math.random() * Math.PI * 2,
      focusSpeed:   0.002 + Math.random() * 0.004,
    };
  }

  const particles = Array.from({ length: 28 }, () => makeParticle(true));

  // ── Shape paths ───────────────────────────────────────────────────────────
  function tracePath(shape, cx, cy, r) {
    switch (shape) {
      case 'circle':
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        break;
      case 'heart':
        traceHeart(cx, cy, r);
        break;
      case 'diamond':
        ctx.beginPath();
        ctx.moveTo(cx,           cy - r);
        ctx.lineTo(cx + r * 0.6, cy);
        ctx.lineTo(cx,           cy + r);
        ctx.lineTo(cx - r * 0.6, cy);
        ctx.closePath();
        break;
    }
  }

  function traceHeart(cx, cy, r) {
    const s = r * 0.88, sx = 0.68;
    ctx.beginPath();
    ctx.moveTo(cx, cy + s * 1.1);
    ctx.bezierCurveTo(cx - s*2*sx, cy + s*0.35,  cx - s*2*sx, cy - s*0.85, cx - s*sx, cy - s*0.85);
    ctx.bezierCurveTo(cx - s*0.35*sx, cy - s*0.85, cx, cy - s*0.35,         cx, cy - s*0.05);
    ctx.bezierCurveTo(cx, cy - s*0.35,  cx + s*0.35*sx, cy - s*0.85,        cx + s*sx, cy - s*0.85);
    ctx.bezierCurveTo(cx + s*2*sx, cy - s*0.85,  cx + s*2*sx, cy + s*0.35,  cx, cy + s*1.1);
  }

  // ── Draw loop ─────────────────────────────────────────────────────────────
  // Using ctx.filter = 'blur(Xpx)' on a flat fill so every edge of every
  // shape blurs uniformly — avoids the radial-gradient artefact where wide
  // lobes (heart tips) fade out before the centre.

  const MAX_BLUR = 14; // px, fully out-of-focus state

  let frame = 0;

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const p of particles) {
      const size    = p.baseSize * (1 + Math.sin(p.sizePhase    + frame * p.sizeSpeed)    * p.sizeAmp);
      const opacity = Math.max(0.02,
                        p.baseOpacity + Math.sin(p.opacityPhase + frame * p.opacitySpeed) * p.opacityAmp);
      // focusT: 0 = blurry, 1 = sharp
      const focusT  = (Math.sin(p.focusPhase + frame * p.focusSpeed) + 1) / 2;
      const blurPx  = (1 - focusT) * MAX_BLUR;

      const [r, g, b] = p.color;

      ctx.save();
      ctx.filter    = blurPx > 0.4 ? 'blur(' + blurPx.toFixed(1) + 'px)' : 'none';
      ctx.fillStyle = 'rgba(' + r + ',' + g + ',' + b + ',' + opacity.toFixed(3) + ')';
      tracePath(p.shape, p.x, p.y, size);
      ctx.fill();
      ctx.restore();

      // Move
      p.x += p.vx;
      p.y += p.vy;
      p.vx += (Math.random() - 0.5) * 0.007;
      p.vx  = Math.max(-0.22, Math.min(0.22, p.vx));

      if (p.y < -size * 4) Object.assign(p, makeParticle(false));
    }

    frame++;
    requestAnimationFrame(draw);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', draw);
  } else {
    draw();
  }

})();
