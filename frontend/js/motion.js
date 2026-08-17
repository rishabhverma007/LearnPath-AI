/* LearnPath AI — cinematic motion engine
   Universe canvas · custom cursor · magnetic buttons · tilt cards · curtains */
"use strict";

const Motion = (() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* ================================================================
     UNIVERSE — live aurora nebula + starfield + shooting stars
     ================================================================ */
  function startUniverse() {
    const canvas = document.getElementById("universe");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let W, H, DPR = Math.min(window.devicePixelRatio || 1, 2);
    const mouse = { x: 0.5, y: 0.5 };

    const stars = [];
    const STARS = 240;
    for (let i = 0; i < STARS; i++) {
      stars.push({
        x: Math.random(), y: Math.random(),
        r: Math.random() * 1.4 + 0.3,
        layer: Math.random(),                       // 0 far … 1 near (parallax)
        tw: Math.random() * Math.PI * 2,
        ts: 0.4 + Math.random() * 1.6,
        hue: Math.random() < 0.18 ? 1 : 0,          // occasional tinted star
      });
    }

    // aurora blobs: center, radius, colors
    const blobs = [
      { x: 0.2, y: 0.18, r: 0.46, c: "124,108,255", a: 0.16, dx: 0.00035, dy: 0.00022 },
      { x: 0.8, y: 0.14, r: 0.4, c: "34,211,238", a: 0.13, dx: -0.00028, dy: 0.0003 },
      { x: 0.68, y: 0.86, r: 0.5, c: "217,70,239", a: 0.10, dx: 0.00022, dy: -0.00025 },
      { x: 0.12, y: 0.78, r: 0.36, c: "34,211,238", a: 0.08, dx: -0.00032, dy: -0.0002 },
    ];
    const shooters = [];
    let t = 0;

    function resize() {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", (e) => {
      mouse.x = e.clientX / W; mouse.y = e.clientY / H;
    }, { passive: true });
    resize();

    function drawAurora() {
      const px = (mouse.x - 0.5) * 24, py = (mouse.y - 0.5) * 24;
      for (const b of blobs) {
        b.x += b.dx; b.y += b.dy;
        if (b.x < -0.1) b.x = 1.1; if (b.x > 1.1) b.x = -0.1;
        if (b.y < -0.1) b.y = 1.1; if (b.y > 1.1) b.y = -0.1;
        const cx = b.x * W + px * (b.r * 2), cy = b.y * H + py * (b.r * 2);
        const rr = Math.max(W, H) * b.r;
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rr);
        const breath = 0.85 + 0.15 * Math.sin(t * 0.35 + b.x * 9);
        g.addColorStop(0, `rgba(${b.c},${(b.a * breath).toFixed(3)})`);
        g.addColorStop(1, `rgba(${b.c},0)`);
        ctx.fillStyle = g;
        ctx.fillRect(cx - rr, cy - rr, rr * 2, rr * 2);
      }
    }

    function drawStars() {
      const px = (mouse.x - 0.5), py = (mouse.y - 0.5);
      for (const s of stars) {
        const depth = 0.25 + s.layer * 0.75;
        const sx = (s.x * W - px * depth * 26) % (W + 8);
        const sy = (s.y * H - py * depth * 16) % (H + 8);
        const x = sx < -4 ? sx + W + 8 : sx, y = sy < -4 ? sy + H + 8 : sy;
        const twinkle = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * s.ts + s.tw));
        const alpha = (0.25 + depth * 0.6) * twinkle;
        ctx.beginPath();
        ctx.arc(x, y, s.r * (0.8 + depth * 0.6), 0, Math.PI * 2);
        ctx.fillStyle = s.hue
          ? `rgba(190,227,255,${alpha.toFixed(3)})`
          : `rgba(230,236,255,${alpha.toFixed(3)})`;
        ctx.fill();
        if (s.layer > 0.75 && twinkle > 0.94) {   // faint cross glow on bright stars
          ctx.strokeStyle = `rgba(255,255,255,${(twinkle * 0.14).toFixed(3)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x - 5 * s.r, y); ctx.lineTo(x + 5 * s.r, y);
          ctx.moveTo(x, y - 5 * s.r); ctx.lineTo(x, y + 5 * s.r);
          ctx.stroke();
        }
      }
    }

    function maybeShoot() {
      if (Math.random() > 0.0035) return;
      shooters.push({
        x: 0.15 + Math.random() * 0.75, y: Math.random() * 0.35,
        vx: 0.004 + Math.random() * 0.006, vy: 0.0016 + Math.random() * 0.002,
        life: 1, max: 90 + Math.random() * 60,
      });
    }

    function drawShooters() {
      for (let i = shooters.length - 1; i >= 0; i--) {
        const s = shooters[i];
        s.x += s.vx; s.y += s.vy; s.life -= 1 / s.max;
        if (s.life <= 0) { shooters.splice(i, 1); continue; }
        const x = s.x * W, y = s.y * H;
        const tail = 90;
        const g = ctx.createLinearGradient(x, y, x - s.vx * tail * 60, y - s.vy * tail * 60);
        g.addColorStop(0, `rgba(190,235,255,${(0.55 * s.life).toFixed(3)})`);
        g.addColorStop(1, "rgba(190,235,255,0)");
        ctx.strokeStyle = g; ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x - s.vx * tail * 60, y - s.vy * tail * 60);
        ctx.stroke();
      }
    }

    function frame() {
      t += 0.008;
      ctx.clearRect(0, 0, W, H);
      drawAurora();
      drawStars();
      maybeShoot();
      drawShooters();
      if (!reduceMotion) requestAnimationFrame(frame);
    }
    frame();
  }

  /* ================================================================
     CUSTOM CURSOR — morphing dot + trailing ring
     ================================================================ */
  function startCursor() {
    if (!finePointer) return;
    const cursor = document.getElementById("cursor");
    const dot = cursor.querySelector(".cursor-dot");
    const ring = cursor.querySelector(".cursor-ring");
    let mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
    let visible = false;

    window.addEventListener("pointermove", (e) => {
      mx = e.clientX; my = e.clientY;
      if (!visible) { visible = true; cursor.style.opacity = 1; }
      dot.style.left = mx + "px"; dot.style.top = my + "px";
      const t = e.target.closest ? e.target.closest("button, a, [data-action], input, textarea, select, .persona, .card[data-tilt]") : null;
      cursor.classList.toggle("hovering", !!t);
    }, { passive: true });
    window.addEventListener("pointerdown", () => cursor.classList.add("pressed"));
    window.addEventListener("pointerup", () => cursor.classList.remove("pressed"));
    document.addEventListener("mouseleave", () => { visible = false; cursor.style.opacity = 0; });

    (function ringLoop() {
      rx += (mx - rx) * 0.16; ry += (my - ry) * 0.16;
      ring.style.left = rx + "px"; ring.style.top = ry + "px";
      if (!reduceMotion) requestAnimationFrame(ringLoop);
    })();
  }

  /* ================================================================
     MAGNETIC BUTTONS + TILT CARDS
     ================================================================ */
  function startMicroInteractions() {
    if (reduceMotion) return;
    document.addEventListener("pointermove", (e) => {
      // magnetic
      const mag = e.target.closest("[data-magnetic]");
      if (mag) {
        const r = mag.getBoundingClientRect();
        const dx = e.clientX - (r.left + r.width / 2);
        const dy = e.clientY - (r.top + r.height / 2);
        mag.style.transform = `translate(${dx * 0.18}px, ${dy * 0.22}px)`;
      }
      // tilt cards
      const tilt = e.target.closest("[data-tilt]");
      document.querySelectorAll("[data-tilt]").forEach((el) => {
        if (el === tilt) {
          const r = el.getBoundingClientRect();
          const px = (e.clientX - r.left) / r.width - 0.5;
          const py = (e.clientY - r.top) / r.height - 0.5;
          el.style.transform = `perspective(900px) rotateX(${(-py * 6).toFixed(2)}deg) rotateY(${(px * 8).toFixed(2)}deg) translateY(-3px)`;
          el.style.setProperty("--gx", ((px + 0.5) * 100).toFixed(1) + "%");
          el.style.setProperty("--gy", ((py + 0.5) * 100).toFixed(1) + "%");
        } else {
          el.style.transform = "";
        }
      });
    });
    document.addEventListener("mouseleave", () => {
      document.querySelectorAll("[data-tilt]").forEach((el) => (el.style.transform = ""));
    });
  }

  /* ================================================================
     SCENE CURTAIN — cinematic page transitions
     ================================================================ */
  const curtainEl = document.getElementById("curtain");
  function playCurtain() {
    if (reduceMotion || !curtainEl) return Promise.resolve();
    return new Promise((resolve) => {
      curtainEl.classList.remove("on");
      void curtainEl.offsetWidth;               // restart animation
      curtainEl.classList.add("on");
      setTimeout(resolve, 500);
    });
  }

  /* ================================================================
     REVEAL-ON-SCROLL
     ================================================================ */
  function observeReveals(root) {
    if (!("IntersectionObserver" in window)) {
      root.querySelectorAll(".reveal").forEach((el) => el.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          en.target.classList.add("in");
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
    root.querySelectorAll(".reveal:not(.in)").forEach((el) => {
      const d = parseFloat(el.dataset.delay || 0);
      el.style.transitionDelay = d + "ms";
      io.observe(el);
    });
  }

  /* ================================================================
     ANIMATE BARS
     ================================================================ */
  function animateBars(root) {
    requestAnimationFrame(() => {
      root.querySelectorAll(".bar-fill").forEach((b) => {
        const w = b.dataset.w;
        if (w) b.style.width = w + "%";
      });
    });
  }

  return { startUniverse, startCursor, startMicroInteractions, playCurtain, observeReveals, animateBars, reduceMotion };
})();
