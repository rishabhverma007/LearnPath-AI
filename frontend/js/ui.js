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
    const el = document.createElement("div");
    el.className = "badge-toast";
    el.innerHTML = `<div class="bt-icon">${badge.icon}</div>
      <div><div class="bt-name">🏆 BADGE UNLOCKED — ${esc(badge.name)}</div>
      <div class="bt-desc">${esc(badge.description)}</div></div>`;
    document.body.appendChild(el);
    setTimeout(() => { el.style.transition = "opacity .4s, transform .4s"; el.style.opacity = "0"; el.style.transform = "translateX(-50%) translateY(-14px)"; }, 2600);
    setTimeout(() => el.remove(), 3100);
  }

  function levelUp(lu) {
    const el = document.createElement("div");
    el.className = "levelup-overlay";
    el.innerHTML = `<div class="levelup-card">
      <div class="lu-emoji">🎉</div>
      <div class="lu-kicker">LEVEL UP</div>
      <div class="lu-title">${esc(lu.title)} — Level ${lu.to}</div>
      <div class="lu-sub">You earned +${lu.xp_earned} XP on this activity.</div>
      <button class="btn btn-primary" data-lu-close>Continue learning →</button>
    </div>`;
    document.body.appendChild(el);
    el.querySelector("[data-lu-close]").addEventListener("click", () => el.remove());
    el.addEventListener("click", (e) => { if (e.target === el) el.remove(); });
  }

  function xpFX(xpResult, anchor) {
    if (!xpResult) return;
    xpFloat(xpResult.xp_awarded, anchor);
    (xpResult.new_badges || []).forEach(badgeToast);
    if (xpResult.level_up) levelUp(xpResult.level_up);
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

  return { esc, fmtPct, TYPE_ICON, FORMAT_LABEL, SEV, el, metric, badge, chip, tag, bar, card, rating, toast, skeletons, empty, emptyState, setView, radarSVG, gaugeSVG, hBars, xpFX, xpFloat, badgeToast, levelUp };
})();
