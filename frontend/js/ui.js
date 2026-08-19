/* LearnPath AI — UI helpers + hand-rolled SVG charts */
"use strict";

const UI = (() => {
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  const fmtPct = (v) => Math.round((v || 0) * 100) + "%";

  const TYPE_ICON = {
    course: "📚", project: "🛠️", resource: "🔖", assessment: "🧠",
    micro_lesson: "⚡", practice: "✏️", milestone: "🎯",
  };
  const FORMAT_LABEL = {
    video: "🎬 Video", interactive: "🖱️ Interactive", docs: "📄 Docs", book: "📖 Book",
    course: "🎓 Course", project: "🛠️ Project", article: "📰 Article",
    cheatsheet: "📋 Cheatsheet", tool: "🧰 Lab", assessment: "🧠 Check",
  };
  const SEV = {
    critical: ["CRITICAL", "critical"], high: ["HIGH", "high"], medium: ["MEDIUM", "medium"],
    low: ["LOW", "low"], none: ["AT TARGET", "none"],
  };

  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("data-")) node.setAttribute(k, v);
      else if (k === "value") node.value = v;
      else if (k in node && k !== "text") node[k] = v;
      else node.setAttribute(k, v);
    }
    for (const c of [].concat(children)) {
      if (c == null) continue;
      node.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function metric(label, value, sub = "", glow = "") {
    return `<div class="metric ${glow}"><div class="m-label">${esc(label)}</div><div class="m-value">${value}</div><div class="m-sub">${esc(sub)}</div></div>`;
  }

  function badge(text, kind = "type") {
    return `<span class="badge ${esc(kind)}">${esc(text)}</span>`;
  }
  const chip = (t) => `<span class="chip">${esc(t)}</span>`;
  const tag = (t) => `<span class="tag">${esc(t)}</span>`;

  function bar(name, pct, opts = {}) {
    const w = Math.max(0, Math.min(100, pct * 100));
    return `<div class="bar-row">
      <div class="bar-head"><span class="name">${esc(name)}</span><span class="pct">${fmtPct(pct)}</span></div>
      <div class="bar"><div class="bar-fill" data-w="${w.toFixed(1)}" ${opts.style ? `style="width:${w.toFixed(1)}%"` : ""}></div></div>
    </div>`;
  }

  function card(title, sub, extra = "") {
    return `<div class="card">${title ? `<div class="card-title">${title}</div>` : ""}${sub ? `<div class="card-sub">${sub}</div>` : ""}${extra}</div>`;
  }

  function rating(n) {
    return `<span class="mono">${"●".repeat(Math.max(1, Math.min(5, n || 1)))}${"○".repeat(Math.max(0, 5 - (n || 1)))}</span>`;
  }

  /* ------------------------------ toast ------------------------------ */
  let toastTimer = null;
  function toast(msg, ms = 3200) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), ms);
  }

  /* ------------------------- gamification FX ------------------------- */

  /* --- particle canvas helper for overlays --- */
  function _spawnParticles(canvas, colors, count) {
    const ctx = canvas.getContext("2d");
    const W = canvas.width = innerWidth;
    const H = canvas.height = innerHeight;
    const cx = W / 2, cy = H / 2;
    const particles = [];
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 2 + Math.random() * 8;
      const size = 3 + Math.random() * 6;
      particles.push({
        x: cx, y: cy,
        vx: Math.cos(angle) * speed * (0.5 + Math.random()),
        vy: Math.sin(angle) * speed * (0.5 + Math.random()) - 2,
        size,
        color: colors[Math.floor(Math.random() * colors.length)],
        life: 1,
        decay: 0.008 + Math.random() * 0.012,
        rot: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.15,
        shape: Math.random() < 0.4 ? "rect" : Math.random() < 0.6 ? "circle" : "star",
        gravity: 0.06 + Math.random() * 0.04,
      });
    }
    let raf;
    function tick() {
      ctx.clearRect(0, 0, W, H);
      let alive = false;
      for (const p of particles) {
        if (p.life <= 0) continue;
        alive = true;
        p.x += p.vx; p.y += p.vy;
        p.vy += p.gravity;
        p.vx *= 0.99;
        p.rot += p.rotSpeed;
        p.life -= p.decay;
        const a = Math.max(0, p.life);
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.globalAlpha = a;
        ctx.fillStyle = p.color;
        if (p.shape === "rect") {
          ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        } else if (p.shape === "star") {
          ctx.beginPath();
          for (let j = 0; j < 5; j++) {
            const r1 = p.size, r2 = p.size * 0.4;
            const a1 = (j * 72 - 90) * Math.PI / 180;
            const a2 = ((j * 72 + 36) - 90) * Math.PI / 180;
            ctx.lineTo(Math.cos(a1) * r1, Math.sin(a1) * r1);
            ctx.lineTo(Math.cos(a2) * r2, Math.sin(a2) * r2);
          }
          ctx.closePath();
          ctx.fill();
        } else {
          ctx.beginPath();
          ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }
      if (alive) raf = requestAnimationFrame(tick);
    }
    tick();
    return () => cancelAnimationFrame(raf);
  }

  /* --- ring burst (concentric expanding rings) --- */
  function _ringBurst(container) {
    const colors = ["rgba(124,108,255,0.5)", "rgba(34,211,238,0.4)", "rgba(217,70,239,0.35)", "rgba(52,211,153,0.3)"];
    for (let i = 0; i < 4; i++) {
      const ring = document.createElement("div");
      ring.className = "celebrate-ring";
      ring.style.cssText = `animation-delay: ${i * 0.12}s; border-color: ${colors[i]};`;
      container.appendChild(ring);
      setTimeout(() => ring.remove(), 2200);
    }
  }

  /* --- glint flash across the card --- */
  function _glintFlash(card) {
    const glint = document.createElement("div");
    glint.className = "celebrate-glint";
    card.style.position = "relative";
    card.style.overflow = "hidden";
    card.appendChild(glint);
    setTimeout(() => glint.remove(), 1200);
  }

  /* --- shared overlay builder --- */
  function _cinematicOverlay({ emoji, kicker, title, sub, badge, colors, onClose }) {
    // close any existing overlays first
    document.querySelectorAll(".cinematic-overlay").forEach((e) => e.remove());

    const overlay = document.createElement("div");
    overlay.className = "cinematic-overlay";
    overlay.innerHTML = `<canvas class="celebrate-particles"></canvas>
      <div class="celebrate-rings"></div>
      <div class="celebrate-card">
        <div class="ce-emoji">${emoji}</div>
        <div class="ce-kicker">${kicker}</div>
        <div class="ce-title">${title}</div>
        ${sub ? `<div class="ce-sub">${sub}</div>` : ""}
        ${badge ? `<div class="ce-badge">${badge}</div>` : ""}
        <button class="btn btn-primary" data-ce-close>Continue →</button>
      </div>`;
    document.body.appendChild(overlay);

    const card = overlay.querySelector(".celebrate-card");
    const ringsEl = overlay.querySelector(".celebrate-rings");
    const canvas = overlay.querySelector(".celebrate-particles");

    // animations
    requestAnimationFrame(() => {
      _spawnParticles(canvas, colors, 80);
      _ringBurst(ringsEl);
      setTimeout(() => _glintFlash(card), 350);
    });

    // dismiss
    const dismiss = () => {
      overlay.classList.add("celebrate-out");
      setTimeout(() => overlay.remove(), 500);
    };
    overlay.querySelector("[data-ce-close]").addEventListener("click", dismiss);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) dismiss(); });
    // auto-dismiss after 6s
    setTimeout(dismiss, 6000);
  }

  function xpFloat(xp, anchor) {
    if (!xp || xp <= 0) return;
    const el = document.createElement("div");
    el.className = "xp-float";
    el.textContent = `+${xp} XP`;
    document.body.appendChild(el);
    const rect = (anchor && anchor.getBoundingClientRect()) || null;
    el.style.left = (rect ? rect.left + rect.width / 2 : innerWidth / 2) + "px";
    el.style.top = (rect ? rect.top : innerHeight / 3) + "px";
    setTimeout(() => el.remove(), 1700);
  }

  function badgeToast(badge) {
    const colors = ["#7c6cff", "#22d3ee", "#d946ef", "#34d399", "#fbbf24"];
    _cinematicOverlay({
      emoji: badge.icon || "🏆",
      kicker: "BADGE UNLOCKED",
      title: esc(badge.name),
      sub: esc(badge.description),
      badge: `<span class="ce-badge-xp">+${badge.xp_reward || 0} XP</span>`,
      colors,
    });
  }

  function levelUp(lu) {
    const colors = ["#7c6cff", "#22d3ee", "#d946ef", "#fbbf24", "#34d399"];
    _cinematicOverlay({
      emoji: "🎉",
      kicker: "LEVEL UP",
      title: `${esc(lu.title)} — Level ${lu.to}`,
      sub: `You earned +${lu.xp_earned} XP on this activity.`,
      colors,
    });
  }

  function xpFX(xpResult, anchor) {
    if (!xpResult) return;
    xpFloat(xpResult.xp_awarded, anchor);
    // level-up takes priority (shows first); badges queue after
    const badges = xpResult.new_badges || [];
    if (xpResult.level_up) {
      levelUp(xpResult.level_up);
      // queue badges to show after overlay closes
      badges.forEach((b, i) => setTimeout(() => badgeToast(b), 6500 * (i + 1)));
    } else {
      badges.forEach((b, i) => setTimeout(() => badgeToast(b), i * 100));
    }
  }

  /* ------------------------------ loading ------------------------------ */
  function skeletons(n = 3) {
    return `<div class="loading-page">${'<div class="skeleton"></div>'.repeat(n)}</div>`;
  }
  function empty(msg) {
    return `<div class="note">${esc(msg)}</div>`;
  }

  /* ------------------------------ empty state ------------------------------ */
  /* Consistent “nothing here yet” view: animated skill-graph illustration,
     a short message, and clear next-step buttons. */
  function emptyState({ icon = "🎯", title = "Nothing here yet", msg = "", ctas = [] } = {}) {
    const btns = ctas.map((c) => {
      const cls = c.primary ? "btn btn-primary" : "btn btn-ghost";
      const extra = c.action ? `data-action="${c.action}"` : `data-action="goto" data-page="${c.page || "onboarding"}"`;
      return `<button class="${cls} btn-sm" ${extra} data-magnetic>${c.label}</button>`;
    }).join("");
    return `<div class="empty-state reveal in">
      <div class="es-art" aria-hidden="true">
        <svg viewBox="0 0 200 200" width="150" height="150">
          <circle cx="100" cy="100" r="54" fill="none" stroke="rgba(124,108,255,0.35)" stroke-width="1.2"/>
          <circle cx="100" cy="100" r="76" fill="none" stroke="rgba(34,211,238,0.22)" stroke-width="1" stroke-dasharray="4 7"/>
          <circle cx="100" cy="100" r="26" fill="rgba(124,108,255,0.12)" stroke="rgba(124,108,255,0.6)" stroke-width="1.4"/>
          <text x="100" y="108" text-anchor="middle" font-size="26">${icon}</text>
          ${[54, 76].map((r, i) => {
            const a = (i * 137.5) * Math.PI / 180;
            return `<circle class="es-orbit-dot" data-d="${i}" cx="${(100 + r * Math.cos(a)).toFixed(1)}" cy="${(100 + r * Math.sin(a)).toFixed(1)}" r="4.5" fill="${i ? "#22d3ee" : "#7c6cff"}"/>`;
          }).join("")}
          <path d="M 46 100 L 100 46 M 154 100 L 100 154 M 100 46 L 100 154" stroke="rgba(148,163,184,0.25)" stroke-width="1" stroke-dasharray="2 5"/>
        </svg>
      </div>
      <h2 class="es-title">${esc(title)}</h2>
      <p class="es-msg">${esc(msg)}</p>
      ${btns ? `<div class="es-ctas">${btns}</div>` : ""}
    </div>`;
  }
  function setView(html) {
    const view = document.getElementById("view");
    view.innerHTML = `<div class="scene">${html}</div>`;
    view.scrollIntoView({ block: "start" });
    return view.querySelector(".scene");
  }

  /* ------------------------------ radar chart (SVG) ------------------------------ */
  function radarSVG(labels, current, required, size = 360) {
    const cx = size / 2, cy = size / 2, R = size / 2 - 44;
    const n = labels.length;
    if (!n) return "";
    const pt = (i, r) => {
      const a = -Math.PI / 2 + (i / n) * Math.PI * 2;
      return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
    };
    let rings = "";
    for (const frac of [0.25, 0.5, 0.75, 1]) {
      let pts = "";
      for (let i = 0; i < n; i++) { const [x, y] = pt(i, R * frac); pts += `${x.toFixed(1)},${y.toFixed(1)} `; }
      rings += `<polygon points="${pts}" fill="none" stroke="rgba(148,163,184,0.16)" stroke-width="1"/>`;
    }
    let spokes = "";
    for (let i = 0; i < n; i++) {
      const [x, y] = pt(i, R);
      spokes += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(148,163,184,0.12)"/>`;
    }
    const poly = (vals, color, fill) => {
      let pts = "";
      for (let i = 0; i < n; i++) { const [x, y] = pt(i, R * Math.max(0.02, Math.min(1, vals[i]))); pts += `${x.toFixed(1)},${y.toFixed(1)} `; }
      return `<polygon points="${pts}" fill="${fill}" stroke="${color}" stroke-width="2" stroke-linejoin="round" style="filter:drop-shadow(0 0 10px ${color}55)"/>`;
    };
    let labelsHtml = "";
    labels.forEach((lb, i) => {
      const [x, y] = pt(i, R + 30);
      const anchor = Math.abs(x - cx) < 8 ? "middle" : (x > cx ? "start" : "end");
      labelsHtml += `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anchor}" font-size="10.5" fill="#9aa2bf" font-family="Inter">${esc(lb)}</text>`;
    });
    return `<svg viewBox="0 0 ${size} ${size}" role="img" style="width:100%;max-width:${size}px">
      ${rings}${spokes}
      ${required ? poly(required, "#22d3ee", "rgba(34,211,238,0.07)") : ""}
      ${poly(current, "#7c6cff", "rgba(124,108,255,0.22)")}
      ${labelsHtml}
    </svg>`;
  }

  /* ------------------------------ gauge (SVG) ------------------------------ */
  function gaugeSVG(score, label = "") {
    const size = 230, stroke = 16, r = (size - stroke * 2) / 2, cx = size / 2, cy = size / 2;
    const circ = 2 * Math.PI * r;
    const val = Math.max(0, Math.min(1, score));
    const color = val >= 0.7 ? "#34d399" : val >= 0.4 ? "#fbbf24" : "#fb7185";
    return `<svg viewBox="0 0 ${size} ${size}" style="width:100%;max-width:${size}px">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="rgba(148,163,184,0.14)" stroke-width="${stroke}"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}"
        stroke-linecap="round" stroke-dasharray="${(circ * val).toFixed(1)} ${circ.toFixed(1)}"
        transform="rotate(-90 ${cx} ${cy})" style="filter:drop-shadow(0 0 12px ${color}88); transition:stroke-dasharray 1s var(--ease-out)"/>
      <text x="${cx}" y="${cy - 4}" text-anchor="middle" font-size="40" font-weight="700" fill="#eef0ff" font-family="Space Grotesk">${(val * 100).toFixed(0)}%</text>
      ${label ? `<text x="${cx}" y="${cy + 26}" text-anchor="middle" font-size="11" fill="#9aa2bf" font-family="Inter">${esc(label)}</text>` : ""}
    </svg>`;
  }

  /* ------------------------------ horizontal bars ------------------------------ */
  function hBars(items, opts = {}) {
    // items: [{label, score(0..1), color?}]
    return `<div style="display:flex;flex-direction:column;gap:12px">
      ${items.map((it) => {
        const w = Math.round(it.score * 100);
        return `<div>
          <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:4px">
            <span>${esc(it.label)}</span><span class="pct faint">${w}%</span>
          </div>
          <div class="bar"><div class="bar-fill" data-w="${w}" style="width:${w}%;${it.color ? `background:${it.color};box-shadow:0 0 14px -2px ${it.color}` : ""}"></div></div>
        </div>`;
      }).join("")}
    </div>`;
  }

  /* ------------------------------ line chart (SVG) ------------------------------ */
  function lineSVG(data, opts = {}) {
    // data: [{date, cumulative_xp}] or [{label, value}]
    const w = opts.width || 400, h = opts.height || 180, pad = { top: 20, right: 20, bottom: 30, left: 50 };
    const innerW = w - pad.left - pad.right, innerH = h - pad.top - pad.bottom;
    if (!data || data.length < 2) return "<div class='faint' style='font-size:12px'>Not enough data for chart</div>";
    const values = data.map((d) => d.cumulative_xp != null ? d.cumulative_xp : d.value);
    const maxVal = Math.max(...values, 1);
    const minVal = 0;
    const range = maxVal - minVal || 1;

    // build points
    const points = data.map((d, i) => {
      const x = pad.left + (i / (data.length - 1)) * innerW;
      const val = d.cumulative_xp != null ? d.cumulative_xp : d.value;
      const y = pad.top + innerH - ((val - minVal) / range) * innerH;
      return { x, y, val, label: d.date || d.label || "" };
    });

    // polyline
    const polyline = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

    // area fill
    const areaPath = `M${points[0].x.toFixed(1)},${(pad.top + innerH).toFixed(1)} `
      + points.map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")
      + ` L${points[points.length - 1].x.toFixed(1)},${(pad.top + innerH).toFixed(1)} Z`;

    // grid lines
    const gridLines = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const y = pad.top + innerH - f * innerH;
      const val = Math.round(minVal + f * range);
      return `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${w - pad.right}" y2="${y.toFixed(1)}" stroke="rgba(148,163,184,0.12)"/>
        <text x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="10" fill="#6b7290" font-family="Inter">${val.toLocaleString()}</text>`;
    }).join("");

    // x-axis labels (show first, middle, last)
    const xLabels = [0, Math.floor(data.length / 2), data.length - 1].map((i) => {
      const p = points[i];
      const lbl = (p.label || "").slice(5); // strip year
      return `<text x="${p.x.toFixed(1)}" y="${(h - 8).toFixed(1)}" text-anchor="middle" font-size="10" fill="#6b7290" font-family="Inter">${lbl}</text>`;
    }).join("");

    // dots
    const dots = points.map((p) =>
      `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="#7c6cff" stroke="#0a0c16" stroke-width="1.5"/>
       <title>${p.label}: ${p.val.toLocaleString()} XP</title>`
    ).join("");

    return `<svg viewBox="0 0 ${w} ${h}" role="img" style="width:100%;max-width:${w}px">
      <defs><linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(124,108,255,0.35)"/>
        <stop offset="100%" stop-color="rgba(124,108,255,0.02)"/>
      </linearGradient></defs>
      ${gridLines}
      <path d="${areaPath}" fill="url(#areaGrad)"/>
      <polyline points="${polyline}" fill="none" stroke="#7c6cff" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" style="filter:drop-shadow(0 0 8px rgba(124,108,255,0.5))"/>
      ${dots}
      ${xLabels}
    </svg>`;
  }

  /* ------------------------------ vertical bar chart (SVG) ------------------------------ */
  function vBarSVG(data, opts = {}) {
    // data: [{label, xp or value, color?}]
    const w = opts.width || 400, h = opts.height || 180, pad = { top: 20, right: 16, bottom: 40, left: 50 };
    const innerW = w - pad.left - pad.right, innerH = h - pad.top - pad.bottom;
    if (!data || !data.length) return "<div class='faint' style='font-size:12px'>No data</div>";
    const maxVal = Math.max(...data.map((d) => d.xp || d.value || 0), 1);
    const barW = Math.min(40, (innerW / data.length) * 0.6);
    const gap = (innerW - barW * data.length) / (data.length + 1);

    const gridLines = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const y = pad.top + innerH - f * innerH;
      const val = Math.round(f * maxVal);
      return `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${w - pad.right}" y2="${y.toFixed(1)}" stroke="rgba(148,163,184,0.12)"/>
        <text x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="10" fill="#6b7290" font-family="Inter">${val.toLocaleString()}</text>`;
    }).join("");

    const bars = data.map((d, i) => {
      const val = d.xp || d.value || 0;
      const barH = (val / maxVal) * innerH;
      const x = pad.left + gap + i * (barW + gap);
      const y = pad.top + innerH - barH;
      const color = d.color || "#7c6cff";
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW}" height="${barH.toFixed(1)}" rx="4" fill="${color}" style="filter:drop-shadow(0 0 8px ${color}66)">
        <title>${esc(d.label)}: ${val.toLocaleString()} XP</title>
      </rect>
      <text x="${(x + barW / 2).toFixed(1)}" y="${(h - pad.bottom + 16).toFixed(1)}" text-anchor="middle" font-size="10" fill="#9aa2bf" font-family="Inter">${esc(d.label)}</text>
      ${val > 0 ? `<text x="${(x + barW / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" text-anchor="middle" font-size="9" fill="#9aa2bf" font-family="Inter">${val.toLocaleString()}</text>` : ""}`;
    }).join("");

    return `<svg viewBox="0 0 ${w} ${h}" role="img" style="width:100%;max-width:${w}px">
      ${gridLines}
      <line x1="${pad.left}" y1="${(pad.top + innerH).toFixed(1)}" x2="${w - pad.right}" y2="${(pad.top + innerH).toFixed(1)}" stroke="rgba(148,163,184,0.2)"/>
      ${bars}
    </svg>`;
  }

  return { esc, fmtPct, TYPE_ICON, FORMAT_LABEL, SEV, el, metric, badge, chip, tag, bar, card, rating, toast, skeletons, empty, emptyState, setView, radarSVG, gaugeSVG, hBars, lineSVG, vBarSVG, xpFX, xpFloat, badgeToast, levelUp };
})();
