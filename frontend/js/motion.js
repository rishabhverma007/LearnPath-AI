/* LearnPath AI — Cinematic Motion Engine v2
   Spring physics · magnetic hover · staggered reveals · cursor glow · parallax */
"use strict";

const Motion = (() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* ================================================================
     SPRING PHYSICS ENGINE
     ================================================================ */
  class Spring {
    constructor({ stiffness = 400, damping = 30, mass = 0.8 } = {}) {
      this.stiffness = stiffness;
      this.damping = damping;
      this.mass = mass;
      this.value = 0;
      this.target = 0;
      this.velocity = 0;
      this.settled = true;
    }
    setTarget(t) { this.target = t; this.settled = false; }
    step(dt) {
      if (this.settled) return this.value;
      const displacement = this.value - this.target;
      const springForce = -this.stiffness * displacement;
      const dampingForce = -this.damping * this.velocity;
      const acceleration = (springForce + dampingForce) / this.mass;
      this.velocity += acceleration * dt;
      this.value += this.velocity * dt;
      if (Math.abs(this.velocity) < 0.01 && Math.abs(displacement) < 0.01) {
        this.value = this.target;
        this.velocity = 0;
        this.settled = true;
      }
      return this.value;
    }
  }

  /* Global spring config for page transitions */
  const SPRING_CONFIG = { stiffness: 400, damping: 30, mass: 0.8 };
  const SPRING_SOFT = { stiffness: 200, damping: 22, mass: 1 };
  const SPRING_SNAPPY = { stiffness: 600, damping: 35, mass: 0.6 };

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
        layer: Math.random(),
        tw: Math.random() * Math.PI * 2,
        ts: 0.4 + Math.random() * 1.6,
        hue: Math.random() < 0.18 ? 1 : 0,
      });
    }

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
        if (s.layer > 0.75 && twinkle > 0.94) {
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
     CUSTOM CURSOR — morphing dot + trailing ring with spring physics
     ================================================================ */
  function startCursor() {
    if (!finePointer) return;
    const cursor = document.getElementById("cursor");
    const dot = cursor.querySelector(".cursor-dot");
    const ring = cursor.querySelector(".cursor-ring");
    let mx = innerWidth / 2, my = innerHeight / 2;
    let visible = false;

    /* Spring-animated ring position */
    const ringX = new Spring({ stiffness: 180, damping: 22, mass: 1 });
    const ringY = new Spring({ stiffness: 180, damping: 22, mass: 1 });
    ringX.value = mx; ringX.target = mx;
    ringY.value = my; ringY.target = my;

    window.addEventListener("pointermove", (e) => {
      mx = e.clientX; my = e.clientY;
      ringX.setTarget(mx); ringY.setTarget(my);
      if (!visible) { visible = true; cursor.style.opacity = 1; }
      dot.style.left = mx + "px"; dot.style.top = my + "px";
      const t = e.target.closest ? e.target.closest("button, a, [data-action], input, textarea, select, .persona, .card[data-tilt], .page-card") : null;
      cursor.classList.toggle("hovering", !!t);
    }, { passive: true });
    window.addEventListener("pointerdown", () => cursor.classList.add("pressed"));
    window.addEventListener("pointerup", () => cursor.classList.remove("pressed"));
    document.addEventListener("mouseleave", () => { visible = false; cursor.style.opacity = 0; });

    let lastTime = performance.now();
    (function ringLoop(now) {
      const dt = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;
      ringX.step(dt); ringY.step(dt);
      ring.style.left = ringX.value + "px";
      ring.style.top = ringY.value + "px";
      if (!reduceMotion) requestAnimationFrame(ringLoop);
    })(performance.now());
  }

  /* ================================================================
     MAGNETIC BUTTONS + TILT CARDS + CURSOR-PROXIMITY GLOW
     ================================================================ */
  function startMicroInteractions() {
    if (reduceMotion) return;

    /* Magnetic pull on buttons */
    document.addEventListener("pointermove", (e) => {
      const mag = e.target.closest("[data-magnetic]");
      if (mag) {
        const r = mag.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const dx = e.clientX - cx, dy = e.clientY - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const strength = Math.min(dist / 80, 1);
        mag.style.transform = `translate(${(dx * 0.2 * strength).toFixed(1)}px, ${(dy * 0.24 * strength).toFixed(1)}px) scale(${1 + strength * 0.02})`;
        mag.style.setProperty("--mx", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
        mag.style.setProperty("--my", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
      }
    });

    /* Tilt cards with perspective */
    document.addEventListener("pointermove", (e) => {
      const tilt = e.target.closest("[data-tilt]");
      document.querySelectorAll("[data-tilt]").forEach((el) => {
        if (el === tilt) {
          const r = el.getBoundingClientRect();
          const px = (e.clientX - r.left) / r.width - 0.5;
          const py = (e.clientY - r.top) / r.height - 0.5;
          el.style.transform = `perspective(900px) rotateX(${(-py * 8).toFixed(2)}deg) rotateY(${(px * 10).toFixed(2)}deg) translateY(-4px) scale(1.01)`;
          el.style.setProperty("--gx", ((px + 0.5) * 100).toFixed(1) + "%");
          el.style.setProperty("--gy", ((py + 0.5) * 100).toFixed(1) + "%");
        } else if (!el.classList.contains("page-card")) {
          el.style.transform = "";
        }
      });
    });
    document.addEventListener("mouseleave", () => {
      document.querySelectorAll("[data-tilt]").forEach((el) => (el.style.transform = ""));
    });

    /* Cursor-proximity glow on glass panels */
    document.addEventListener("pointermove", (e) => {
      document.querySelectorAll(".page-card, .glass, .rec-card").forEach((el) => {
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const dx = e.clientX - cx, dy = e.clientY - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const glow = Math.max(0, 1 - dist / 300);
        el.style.setProperty("--glow", glow.toFixed(3));
        if (glow > 0.05) {
          const nx = ((e.clientX - r.left) / r.width * 100).toFixed(1);
          const ny = ((e.clientY - r.top) / r.height * 100).toFixed(1);
          el.style.setProperty("--glow-x", nx + "%");
          el.style.setProperty("--glow-y", ny + "%");
        }
      });
    });

    /* Button press spring compression */
    document.addEventListener("pointerdown", (e) => {
      const btn = e.target.closest("button, [data-action]");
      if (btn) {
        btn.style.transition = "transform 0.08s cubic-bezier(0.34, 1.56, 0.64, 1)";
        btn.style.transform = "scale(0.95)";
        /* Fire ripple */
        const ripple = document.createElement("span");
        ripple.className = "btn-ripple";
        const r = btn.getBoundingClientRect();
        ripple.style.left = (e.clientX - r.left) + "px";
        ripple.style.top = (e.clientY - r.top) + "px";
        btn.style.position = btn.style.position || "relative";
        btn.style.overflow = "hidden";
        btn.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
      }
    });
    document.addEventListener("pointerup", () => {
      document.querySelectorAll("button, [data-action]").forEach((btn) => {
        btn.style.transition = "transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)";
        btn.style.transform = "";
      });
    });

    /* Reset magnetic on leave */
    document.addEventListener("pointerup", () => {
      document.querySelectorAll("[data-magnetic]").forEach((el) => {
        el.style.transition = "transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)";
        el.style.transform = "";
        setTimeout(() => { el.style.transition = ""; }, 500);
      });
    });
  }

  /* ================================================================
     SCENE CURTAIN — cinematic page transitions (dual-layer)
     ================================================================ */
  const curtainEl = document.getElementById("curtain");
  let curtainResolve = null;

  function playCurtain() {
    if (reduceMotion || !curtainEl) return Promise.resolve();
    return new Promise((resolve) => {
      curtainResolve = resolve;
      curtainEl.classList.remove("on");
      void curtainEl.offsetWidth;
      curtainEl.classList.add("on");
      /* Dual-phase: curtain sweeps in, then out */
      setTimeout(() => {
        curtainEl.classList.add("phase-out");
        setTimeout(() => {
          curtainEl.classList.remove("on", "phase-out");
          curtainResolve = null;
          resolve();
        }, 420);
      }, 380);
    });
  }

  /* ================================================================
     STAGGERED REVEALS — spring-physics scroll reveals
     ================================================================ */
  function observeReveals(root) {
    if (!("IntersectionObserver" in window)) {
      root.querySelectorAll(".reveal").forEach((el) => el.classList.add("in"));
      root.querySelectorAll("[data-stagger]").forEach((el) => el.classList.add("in"));
      return;
    }

    /* Standard reveals */
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

    /* Staggered children — each child animates in sequence */
    const staggerGroups = root.querySelectorAll("[data-stagger]");
    staggerGroups.forEach((group) => {
      const delay = parseFloat(group.dataset.staggerDelay || 60);
      const children = group.children;
      const sio = new IntersectionObserver((entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) {
            Array.from(children).forEach((child, i) => {
              child.style.setProperty("--stagger", i);
              child.style.transitionDelay = (i * delay) + "ms";
              child.classList.add("stagger-in");
            });
            sio.unobserve(en.target);
          }
        });
      }, { threshold: 0.05 });
      sio.observe(group);
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

  /* ================================================================
     PAGE GRID ENTRANCE — spring-physics staggered card reveal
     ================================================================ */
  function animatePageGrid(container) {
    if (reduceMotion) return;
    const cards = container.querySelectorAll(".page-card");
    const header = container.querySelector(".page-grid-header");
    if (header) {
      header.style.opacity = "0";
      header.style.transform = "translateY(20px)";
      requestAnimationFrame(() => {
        header.style.transition = "opacity 0.6s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)";
        header.style.opacity = "1";
        header.style.transform = "translateY(0)";
      });
    }
    cards.forEach((card, i) => {
      card.style.opacity = "0";
      card.style.transform = "translateY(30px) scale(0.95)";
      setTimeout(() => {
        card.style.transition = "opacity 0.5s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)";
        card.style.opacity = "1";
        card.style.transform = "translateY(0) scale(1)";
      }, 120 + i * 70);
    });
  }

  /* ================================================================
     SCROLL PARALLAX — tie elements to scroll progress
     ================================================================ */
  function startScrollParallax() {
    if (reduceMotion) return;
    let ticking = false;
    window.addEventListener("scroll", () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          const scrollY = window.scrollY;
          /* Parallax hero text */
          document.querySelectorAll("[data-parallax]").forEach((el) => {
            const speed = parseFloat(el.dataset.parallax || 0.3);
            const y = scrollY * speed;
            el.style.transform = `translateY(${y.toFixed(1)}px) scale(${(1 - scrollY * 0.0002).toFixed(4)})`;
            el.style.opacity = Math.max(0, 1 - scrollY * 0.002).toFixed(3);
          });
          /* Glass cards parallax at varying speeds */
          document.querySelectorAll("[data-parallax-card]").forEach((el) => {
            const speed = parseFloat(el.dataset.parallaxCard || 0.1);
            const rect = el.getBoundingClientRect();
            if (rect.top < window.innerHeight && rect.bottom > 0) {
              el.style.transform = `translateY(${((window.innerHeight - rect.top) * speed * 0.05).toFixed(1)}px)`;
            }
          });
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  /* ================================================================
     TEXT STAGGER — word-by-word mask reveal
     ================================================================ */
  function staggerText(el) {
    if (reduceMotion || !el) return;
    const text = el.textContent;
    const words = text.split(/\s+/);
    el.innerHTML = words.map((w, i) =>
      `<span class="stagger-word" style="--tw:${i}">${w}</span>`
    ).join(" ");
    el.classList.add("stagger-text-active");
  }

  return {
    startUniverse, startCursor, startMicroInteractions,
    playCurtain, observeReveals, animateBars,
    animatePageGrid, startScrollParallax, staggerText,
    reduceMotion, Spring, SPRING_CONFIG, SPRING_SOFT, SPRING_SNAPPY,
  };
})();
