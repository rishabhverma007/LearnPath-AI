/* LearnPath AI — page views. Each module: { nav, gate, render(), mount() }.
   render() is async and returns an HTML string; app.js injects it into #view. */
"use strict";

const Pages = {};

const ROLE_EMOJI = {
  ml_engineer: "🤖", ai_engineer: "🧠", data_scientist: "📊", data_analyst: "📈",
  cybersecurity_analyst: "🛡️", penetration_tester: "⚔️", cloud_engineer: "☁️",
  devops_engineer: "🚀", software_engineer: "💻", web_developer: "🌐",
};

const PERSONA_EMOJI = { ml_engineer: "🤖", data_scientist: "📊", cybersecurity: "🛡️", cloud_engineer: "☁️" };

const fmtH = (h) => {
  h = Number(h) || 0;
  return h >= 1 ? (Math.round(h * 10) / 10) + "h" : Math.max(1, Math.round(h * 60)) + "min";
};

/* Minimal safe markdown: escape HTML, then allow **bold**, `code` and newlines. */
const md = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;")
  .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
  .replace(/`([^`]+)`/g, '<span class="mono">$1</span>');

const REASON_LABELS = {
  semantic_relevance: "Semantic match", skill_gap_coverage: "Gap coverage",
  goal_alignment: "Goal alignment", prerequisite_fit: "Prerequisite fit",
  difficulty_fit: "Difficulty fit", preference_fit: "Preference fit",
  time_fit: "Time fit", feedback_signal: "History signal",
};

/* ================================================================
   1 · ONBOARDING
   ================================================================ */
Pages.onboarding = {
  nav: { icon: "✦", label: "Start" },
  gate: null,
  async render() {
    const meta = await bootMeta();
    const personas = (meta.personas || []).map((p) => {
      const emoji = PERSONA_EMOJI[p.id] || "🎓";
      return `<button class="persona" data-tilt data-action="persona" data-id="${p.id}">
        <div class="p-emoji">${emoji}</div>
        <div class="p-name">${UI.esc(p.name)}</div>
        <div class="p-desc">${UI.esc(p.goal_text.slice(0, 120))}…</div>
      </button>`;
    }).join("");

    const existing = Store.learner
      ? `<div class="glass note" style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap">
           <div><b>You're already learning as</b> — ${UI.esc(Store.learner.goal_text.slice(0, 90))}${Store.learner.goal_text.length > 90 ? "…" : ""}</div>
           <div style="display:flex;gap:8px">
             <button class="btn btn-primary btn-sm" data-action="goto" data-page="dashboard">Continue →</button>
             <button class="btn btn-ghost btn-sm" data-action="new-demo">Start over</button>
           </div>
         </div><div class="divider"></div>`
      : "";

    const analysis = Store.analysis ? this._understandingHtml(meta) : "";

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">LearnPath AI · Adaptive Learning OS</div>
        <div class="steps" style="margin-bottom:18px">
          <span class="step on"><b>1</b> Describe your goal</span>
          <span class="step-line"></span>
          <span class="step"><b>2</b> Review your twin</span>
          <span class="step-line"></span>
          <span class="step"><b>3</b> Start your journey</span>
        </div>
        <h1 class="display">What are you<br><span class="grad">trying to achieve?</span></h1>
        <p class="sub">Tell us your goal in plain language. LearnPath AI builds your learner profile, maps your skill gaps against a living skill graph, and designs a learning journey that adapts to how you actually learn.</p></div>
      </section>
      ${existing}
      <div class="grid grid-2" style="align-items:start">
        <div>
          <div class="card reveal" style="padding:22px">
            <div class="card-title">Describe your goal</div>
            <div class="card-sub">Try: <i>“I am a third-year CS student. I know Python and basic ML. I want to become an ML Engineer and get an internship within six months. I prefer practical projects and can study about 8 hours per week.”</i></div>
            <div style="height:14px"></div>
            <textarea id="goal-input" class="input" rows="5" placeholder="I want to become… I know… I can study…" data-magnetic>${Store.lastGoal || ""}</textarea>
            <div style="height:12px"></div>
            <button class="btn btn-primary btn-block" data-action="analyze" data-magnetic>✦ Analyze my goal</button>
          </div>
          ${analysis}
        </div>
        <div>
          <div class="card reveal" style="padding:22px" data-delay="80">
            <div class="card-title">Or jump straight in — demo personas</div>
            <div class="card-sub">One click, fully-loaded learner digital twins across four careers.</div>
            <div style="height:14px"></div>
            <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">${personas}</div>
          </div>
          <div class="note reveal" data-delay="140" style="margin-top:14px">
            <b>No API keys needed.</b> Profile understanding, skill-gap analysis, roadmap generation and coaching run fully on-device with a hybrid rules + embedding + graph engine. A real LLM is used only when you configure one (see <span class="mono">.env</span>).
          </div>
        </div>
      </div>`;
  },
  mount() {
    // Enter-to-analyze
    const ta = document.getElementById("goal-input");
    if (ta) ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); App.actions.analyze(); }
    });
  },
  _understandingHtml(meta) {
    const a = Store.analysis;
    const roleOpts = Object.values(meta.roles || {})
      .map((r) => `<option value="${r.role_id}" ${r.role_id === a.target_role ? "selected" : ""}>${ROLE_EMOJI[r.role_id] || ""} ${UI.esc(r.title)}</option>`)
      .join("");
    const expSeg = (["beginner", "intermediate", "advanced"]).map((l) =>
      `<button class="${l === a.experience_level ? "active" : ""}" data-action="seg" data-group="exp" data-value="${l}">${l[0].toUpperCase() + l.slice(1)}</button>`).join("");
    const prefs = (["hands-on", "video", "reading", "interactive"]).map((p) =>
      `<button class="${(a.preferences || []).includes(p) ? "active" : ""}" data-action="seg" data-group="prefs" data-value="${p}">${p}</button>`).join("");
    const skills = (a.skills || []).map(([sid, conf], i) => {
      const name = sid.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");
      return `<div class="opt-row" style="align-items:center">
        <input type="checkbox" checked data-skill-check="${sid}">
        <label style="flex:1">${UI.esc(name)}</label>
        <input type="range" min="0" max="100" value="${Math.round(conf * 100)}" data-skill-slider="${sid}" style="width:110px">
        <span class="mono faint" data-skill-val="${sid}">${Math.round(conf * 100)}%</span>
      </div>`;
    }).join("");
    return `
      <div class="glass understanding reveal" style="padding:22px;margin-top:16px" id="understanding">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap">
          <h4 style="margin:0">AI UNDERSTANDING</h4>
          <span class="tag">${a.extraction_source === "rules+llm" ? "rules + LLM" : a.extraction_source} · confidence ${Math.round((a.confidence || 0.7) * 100)}%</span>
        </div>
        <div class="u-row"><div class="u-k">Goal</div><div>${UI.esc(a.goal)}</div></div>
        <div class="u-row"><div class="u-k">Target role</div>
          <select id="f-role" class="input" style="max-width:280px">${roleOpts}</select></div>
        <div class="u-row"><div class="u-k">Experience</div><div class="seg">${expSeg}</div></div>
        <div class="u-row"><div class="u-k">Weekly hours</div>
          <input id="f-hours" type="number" class="input" min="1" max="40" value="${a.weekly_hours || 8}" style="max-width:110px"></div>
        <div class="u-row"><div class="u-k">Deadline</div>
          <div style="display:flex;align-items:center;gap:8px"><input id="f-weeks" type="number" class="input" min="4" max="104" value="${a.deadline_weeks || 26}" style="max-width:90px"><span class="faint" style="font-size:12px">weeks</span></div></div>
        <div class="u-row"><div class="u-k">Preferences</div><div class="seg" style="flex-wrap:wrap">${prefs}</div></div>
        <div class="u-row" style="display:block"><div class="u-k" style="margin-bottom:8px">Known skills — edit confidence</div>${skills}</div>
        <div style="height:8px"></div>
        <button class="btn btn-primary btn-block" data-action="create-learner" data-magnetic>Create my learning journey →</button>
      </div>`;
  },
};

/* ================================================================
   2 · MY JOURNEY
   ================================================================ */
Pages.journey = {
  nav: { icon: "🗺️", label: "My Journey" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    let roadmap = Store.roadmap;
    if (!roadmap) {
      roadmap = await API.generateRoadmap(learner.learner_id, "balanced");
      Store.roadmap = roadmap;
    }
    const meta = await bootMeta();
    const role = (meta.roles || {})[learner.target_role] || { title: learner.target_role };
    const mode = (["balanced", "accelerated", "flexible"]).map((m) =>
      `<button class="${m === roadmap.mode ? "active" : ""}" data-action="roadmap-mode" data-mode="${m}">${m[0].toUpperCase() + m.slice(1)}</button>`).join("");

    const done = roadmap.phases.reduce((n, p) => n + p.items.filter((i) => i.status === "completed").length, 0);
    const total = roadmap.phases.reduce((n, p) => n + p.items.length, 0);
    const pct = total ? done / total : 0;

    const adapt = (roadmap.adaptation_notes || []).length
      ? `<div class="glass adapt-banner">
           <div class="adapt-ico">🔄</div>
           <div><b>Your path was updated</b> — the roadmap re-planned itself based on your latest signals.
             <ul style="margin:8px 0 0;padding-left:18px;color:var(--ink-dim);font-size:12.8px">${roadmap.adaptation_notes.map((n) => `<li>${UI.esc(n)}</li>`).join("")}</ul></div>
         </div><div class="divider"></div>`
      : "";

    const phases = roadmap.phases.map((p) => {
      const items = p.items.map((it) => {
        const mark = it.status === "completed" ? `<span class="mark done">✓</span>`
          : it.status === "in_progress" ? `<span class="mark cur">●</span>`
          : `<span class="mark next">○</span>`;
        const canComplete = ["course", "project", "resource"].includes(it.item_type) && it.status !== "completed";
        return `<div class="rt-item reveal">
          ${mark}
          <div style="flex:1">
            <div><span class="title">${UI.esc(it.title)}</span> <span class="meta">${UI.badge(UI.TYPE_ICON[it.item_type] + " " + (it.resource_type || it.item_type), it.item_type)}</span></div>
            <div class="meta">${it.duration_hours ? `~${fmtH(it.duration_hours)} · ` : ""}${it.skill_ids.map((s) => UI.chip(UI.esc(s))).join("")}${it.focus_concept ? ` · <span class="mono">focus: ${UI.esc(it.focus_concept)}</span>` : ""}</div>
            ${canComplete ? `<button class="btn btn-ghost btn-sm" style="margin-top:6px" data-action="complete-item" data-type="${it.item_type}" data-id="${it.item_id}">✓ Mark complete</button>` : ""}
          </div>
        </div>`;
      }).join("");
      const stBadge = p.status === "completed" ? "done" : p.status === "in_progress" ? "cur" : "";
      return `<div class="phase">
        <div class="phase-head">
          <span class="phase-title">${UI.esc(p.label)}</span>
          <span class="phase-weeks">weeks ${p.week_start}–${p.week_end} · ${p.hours}h</span>
          ${p.status !== "upcoming" ? `<span class="badge ${stBadge}">${p.status}</span>` : ""}
        </div>
        ${items}
      </div>`;
    }).join("");

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">${ROLE_EMOJI[learner.target_role] || "🎯"} ${UI.esc(role.title || learner.target_role)} · ${learner.deadline_weeks}-week target</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Your <span class="grad">personalized journey</span></h1>
        <p class="sub">${UI.esc(learner.goal_text)}</p></div>
        <div style="margin-top:18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap" class="reveal" data-delay="60">
          <span class="faint" style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em">Pace</span>
          <div class="seg">${mode}</div>
          <button class="btn btn-ghost btn-sm" data-action="goto" data-page="recommendations">See why these were chosen →</button>
        </div>
      </section>
      ${adapt}
      <div class="metrics-row reveal" data-delay="40">
        ${UI.metric("Path progress", Math.round(pct * 100) + "%", `${done}/${total} items done`, "glow-brand")}
        ${UI.metric("Total effort", roadmap.total_hours + "h", `${roadmap.total_weeks} weeks planned`)}
        ${UI.metric("Deadline", learner.deadline_weeks + " wks", roadmap.feasible ? "on track" : "tight")}
        ${UI.metric("Weekly", roadmap.weekly_hours + "h", roadmap.mode + " pace")}
      </div>
      ${roadmap.feasibility_note ? `<div class="note">${UI.esc(roadmap.feasibility_note)}</div>` : ""}
      <div class="glass reveal" data-delay="60" style="padding:18px 20px;margin-top:22px">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:8px">
          <span class="faint">ROADMAP COMPLETION</span><span class="mono">${Math.round(pct * 100)}% · ${done}/${total} items</span>
        </div>
        <div class="bar" style="height:10px"><div class="bar-fill" data-w="${Math.round(pct * 100)}" style="width:${Math.round(pct * 100)}%"></div></div>
      </div>
      <div class="section-head"><h2 class="h2">Roadmap</h2></div>
      <div class="glass" style="padding:26px 22px">${phases || UI.empty("No phases yet — adjust your profile in Settings.")}</div>`;
  },
};

/* ================================================================
   3 · SKILL INTELLIGENCE
   ================================================================ */
Pages.skills = {
  nav: { icon: "⚡", label: "Skill Intelligence" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    const data = await API.skills(learner.learner_id);
    const role = data.role;
    const sev = data.severity_summary || {};
    const order = ["critical", "high", "medium", "low", "none"];
    const heatRows = (data.gaps || []).map((g) => {
      const [label, cls] = UI.SEV[g.severity] || ["—", "none"];
      const action = g.severity === "none" ? "Maintain & reinforce"
        : g.severity === "low" ? "Quick review"
        : g.severity === "medium" ? "Structured module"
        : "Priority remediation";
      return `<div class="rt-item reveal">
        <span class="badge ${cls}">${label}</span>
        <div style="flex:1">
          <div style="display:flex;justify-content:space-between;font-size:13px"><b>${UI.esc(g.name)}</b><span class="faint">${UI.esc(action)}</span></div>
          <div style="display:flex;align-items:center;gap:10px;margin-top:5px">
            ${UI.bar("you", g.current, { style: true }).replace('<div class="bar-row">', '<div style="flex:1">').replace(/<div class="bar-head">.*?<\/div>/, `<div style="display:flex;justify-content:space-between;font-size:11px"><span class="faint">you ${Math.round(g.current * 100)}%</span><span class="faint">need ${Math.round(g.required * 100)}%</span></div>`)}
            <span class="mono" style="white-space:nowrap">gap ${Math.round(g.gap * 100)}%</span>
          </div>
        </div>
      </div>`;
    }).join("");

    const radar = data.radar || { skills: [], current: [], required: [] };
    const radarHtml = radar.skills.length ? UI.radarSVG(radar.skills, radar.current, radar.required) : UI.empty("No radar data yet");

    // before / after
    const baseline = data.baseline || {};
    const current = data.known_skills || {};
    const allKeys = [...new Set([...Object.keys(baseline), ...Object.keys(current)])].slice(0, 8);
    const ba = allKeys.map((k) => {
      const before = baseline[k] || 0, after = current[k] || 0;
      return `<div style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:4px"><span>${UI.esc(k)}</span><span class="faint">${Math.round(before * 100)}% → ${Math.round(after * 100)}%</span></div>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="faint" style="font-size:10px;width:34px">before</span>
          <div class="bar" style="flex:1"><div class="bar-fill" data-w="${Math.round(before * 100)}" style="width:${Math.round(before * 100)}%;background:rgba(148,163,184,0.5)"></div></div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;margin-top:4px">
          <span class="faint" style="font-size:10px;width:34px">now</span>
          <div class="bar" style="flex:1"><div class="bar-fill" data-w="${Math.round(after * 100)}" style="width:${Math.round(after * 100)}%;background:linear-gradient(90deg,var(--brand),var(--brand-2));box-shadow:0 0 12px -2px rgba(124,108,255,0.7)"></div></div>
        </div>
      </div>`;
    }).join("");

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">${ROLE_EMOJI[role.role_id] || "🎯"} ${UI.esc(role.title)} · ${UI.esc(role.domain || "")}</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Skill <span class="grad">intelligence</span></h1>
        <p class="sub">Required competencies minus demonstrated proficiency — a living gap analysis updated with every assessment, completion, and feedback signal.</p></div>
      </section>
      <div class="metrics-row reveal" data-delay="40">
        ${UI.metric("Critical gaps", sev.critical || 0, "block learning progress")}
        ${UI.metric("High priority", sev.high || 0, "schedule next")}
        ${UI.metric("Medium", sev.medium || 0, "structured modules")}
        ${UI.metric("Learning velocity", Math.round((data.learning_velocity || 0) * 100) + "%", "avg proficiency")}
      </div>
      <div class="grid grid-2" style="align-items:start;margin-top:26px">
        <div class="glass reveal" style="padding:22px">
          <div class="card-title">Skill gap heatmap</div>
          <div class="card-sub">Current proficiency vs target for the ${UI.esc(role.title)} competency map.</div>
          <div style="height:12px"></div>
          ${heatRows || UI.empty("No gaps — you're at target for this role.")}
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="80">
          <div class="card-title">Competency radar</div>
          <div class="card-sub"><span style="color:var(--brand)">you</span> vs <span style="color:var(--brand-2)">required</span></div>
          <div style="display:flex;justify-content:center;padding:10px 0">${radarHtml}</div>
        </div>
      </div>
      <div class="grid grid-2" style="align-items:start;margin-top:26px">
        <div class="glass reveal" style="padding:22px">
          <div class="card-title">Before → after</div>
          <div class="card-sub">Proficiency at onboarding vs your digital twin today.</div>
          <div style="height:12px"></div>
          ${ba || UI.empty("No baseline captured yet.")}
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="80">
          <div class="card-title">How gaps are computed</div>
          <div class="card-sub">Every skill lives in a prerequisite graph. Gaps are weighted by the role's competency map and proficiency is updated by completions, assessments, and feedback.</div>
          <div style="height:12px"></div>
          <div class="mono faint" style="line-height:1.9;font-size:11.5px">
            gap = required − current<br>
            severity: critical &gt; 0.6 · high &gt; 0.4 · medium &gt; 0.2<br>
            prerequisite check: each module unlocks the next
          </div>
        </div>
      </div>`;
  },
};

/* ================================================================
   4 · RECOMMENDATIONS
   ================================================================ */
Pages.recommendations = {
  nav: { icon: "🎯", label: "Recommendations" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    if (!Store.recs) Store.recs = await API.recommend(learner.learner_id, 12);
    const recs = Store.recs;
    const filter = Store.recFilter || "all";
    const filters = ["all", "course", "project", "resource", "assessment"].map((f) =>
      `<button class="${f === filter ? "active" : ""}" data-action="rec-filter" data-filter="${f}">${f[0].toUpperCase() + f.slice(1)}</button>`).join("");

    const cards = recs.filter((r) => filter === "all" || r.item_type === filter).map((r, i) => {
      const reasons = r.reasons || {};
      const reasonBars = Object.entries(reasons).map(([k, v]) =>
        `<div style="margin-bottom:8px">
           <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:3px"><span class="faint">${REASON_LABELS[k] || k}</span><span class="mono">${Math.round(v * 100)}%</span></div>
           <div class="bar"><div class="bar-fill" data-w="${Math.round(v * 100)}" style="width:${Math.round(v * 100)}%"></div></div>
         </div>`).join("");
      const why = `<div class="why-panel" id="why-${i}" hidden>
        <div class="divider"></div>
        <div style="font-size:12px;color:var(--ink);line-height:1.75;margin-bottom:12px">${(r.explanation_lines || []).map((l) => `<div style="display:flex;gap:8px"><span style="color:var(--brand-2)">▸</span><span>${UI.esc(l)}</span></div>`).join("")}</div>
        <div class="reason-grid">${reasonBars}</div>
      </div>`;
      const actions = [];
      if (r.url) actions.push(`<a class="btn btn-sm" style="text-decoration:none" href="${UI.esc(r.url)}" target="_blank" rel="noopener">Open ↗</a>`);
      if (["course", "project", "resource"].includes(r.item_type)) actions.push(`<button class="btn btn-sm" data-action="rec-complete" data-type="${r.item_type}" data-id="${r.item_id}">✓ Complete</button>`);
      actions.push(`<button class="btn btn-ghost btn-sm" data-action="rec-feedback" data-signal="like" data-type="${r.item_type}" data-id="${r.item_id}">👍</button>`);
      actions.push(`<button class="btn btn-ghost btn-sm" data-action="rec-feedback" data-signal="dislike" data-type="${r.item_type}" data-id="${r.item_id}">👎</button>`);
      return `<div class="glass recommendation reveal" data-delay="${Math.min(i * 40, 200)}">
        <div class="rec-head">
          <div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
              ${UI.badge(UI.TYPE_ICON[r.item_type] + " " + (r.format || r.item_type), r.item_type)}
              ${UI.badge("difficulty " + r.difficulty + "/5", "diff")}
            </div>
            <div class="card-title" style="font-size:16.5px">${UI.esc(r.title)}</div>
            <div class="card-sub">${UI.esc(r.provider || "")}${r.duration_hours ? ` · ~${fmtH(r.duration_hours)}` : ""}</div>
          </div>
          <div class="rec-score"><div class="big ${r.score >= 0.7 ? "hot" : r.score >= 0.5 ? "warm" : "cool"}">${Math.round(r.score * 100)}</div><div class="lbl">match</div></div>
        </div>
        <div class="card-sub" style="margin-top:10px">${UI.esc(r.description || "")}</div>
        <div style="margin-top:10px">${(r.skills || []).map((s) => UI.chip(UI.esc(s))).join("")}</div>
        ${why}
        <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" data-action="why-toggle" data-id="why-${i}">💡 Why this?</button>
          ${actions.join("")}
        </div>
      </div>`;
    }).join("");

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">Explainable hybrid ranking · 8 factors</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Recommendations, <span class="grad">explained</span></h1>
        <p class="sub">Every item is scored by semantic relevance, skill-gap coverage, goal alignment, prerequisite fit, difficulty, preference, time budget and your feedback history — then diversified so you get a course, a project, a resource and a knowledge check, not five copies of the same course.</p></div>
      </section>
      <div class="seg reveal" style="margin:16px 0 24px">${filters}</div>
      <div class="grid" style="gap:18px">${cards || UI.empty("No recommendations yet — complete onboarding first.")}</div>`;
  },
};

/* ================================================================
   5 · AI COACH
   ================================================================ */
Pages.coach = {
  nav: { icon: "💬", label: "AI Coach" },
  gate: "learner",
  async render() {
    if (!Store.chat.length) {
      Store.chat = [{
        role: "coach",
        text: "I'm your learning coach — I know your profile, your roadmap, your skill gaps and your assessment history. Ask me anything, for example:",
      }];
    }
    const bubbles = Store.chat.map((m) => {
      if (m.role === "user") {
        return `<div class="msg user"><div class="bubble user">${UI.esc(m.text)}</div></div>`;
      }
      const srcs = (m.sources || []).length
        ? `<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">${m.sources.slice(0, 4).map((s) => UI.tag(UI.esc(s))).join("")}</div>` : "";
      const acts = (m.actions || []).length
        ? `<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">${m.actions.map((a) => `<button class="btn btn-ghost btn-sm" data-action="coach-action" data-type="${a.type || ""}" data-id="${a.item_id || ""}">${UI.esc(a.label || "Go")}</button>`).join("")}</div>` : "";
      return `<div class="msg coach"><div class="avatar">LP</div><div class="bubble">${md(m.text)}${srcs}${acts}</div></div>`;
    }).join("");

    const chips = ["What should I do today?", "Which skill should I focus on today?", "Explain cross-validation", "Can I skip this module?", "I'm struggling with classification", "Why should I learn statistics?"]
      .map((c) => `<button class="chip-btn" data-action="coach-chip" data-q="${UI.esc(c)}">${UI.esc(c)}</button>`).join("");

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">Context-aware RAG assistant</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">AI <span class="grad">coach</span></h1>
        <p class="sub">Retrieval-grounded answers from the skill graph, course catalogue and your roadmap. It knows your context — and it will tell you when it doesn't know something instead of inventing it.</p></div>
      </section>
      <div class="glass reveal" style="padding:22px">
        <div class="chat" id="chat">${bubbles}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">${chips}</div>
        <form class="chat-input" id="coach-form">
          <input class="input" id="coach-input" placeholder="Ask your coach… e.g. “What should I do today?”" autocomplete="off">
          <button class="btn btn-primary" type="submit">Send ↵</button>
        </form>
      </div>`;
  },
  mount() {
    const form = document.getElementById("coach-form");
    const input = document.getElementById("coach-input");
    const chat = document.getElementById("chat");
    if (!form || !input) return;
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const msg = input.value.trim();
      if (!msg) return;
      App.actions.coachSend(msg);
    });
    const scroll = () => { if (chat) chat.scrollTop = chat.scrollHeight; };
    scroll();
    setTimeout(scroll, 60);
  },
};

/* ================================================================
   6 · ASSESSMENTS
   ================================================================ */
Pages.assessments = {
  nav: { icon: "🧠", label: "Assessments" },
  gate: "learner",
  async render() {
    const meta = await bootMeta();
    const ass = meta.assessments || [];
    const list = ass.map((a) => `
      <div class="glass recommendation reveal" style="padding:18px 20px">
        <div class="rec-head">
          <div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
              ${UI.badge("🧠 knowledge check", "assessment")}${UI.badge("difficulty " + a.difficulty + "/5", "diff")}
            </div>
            <div class="card-title" style="font-size:15.5px">${UI.esc(a.title)}</div>
            <div class="card-sub">${UI.esc(a.description)}</div>
            <div style="margin-top:8px">${(a.concepts || []).map((c) => UI.tag(UI.esc(c))).join("")}</div>
          </div>
          <button class="btn btn-sm" data-action="assessment-start" data-id="${a.assessment_id}">Start · ${a.num_questions}q</button>
        </div>
      </div>`).join("");

    if (Store.assessmentActive) return this._assessmentView(Store.assessmentActive);
    if (Store.assessmentResult) return this._resultView();

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">Knowledge checks · adaptive roadmap</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Assessments & <span class="grad">adaptation</span></h1>
        <p class="sub">Short concept-tagged checks. Score below 60% and the roadmap inserts a remediation block before you advance — score above 85% and it accelerates. Your digital twin learns either way.</p></div>
      </section>
      <div class="grid" style="gap:16px;margin-top:10px">${list || UI.empty("No assessments available.")}</div>`;
  },
  _assessmentView(a) {
    const qs = a.questions.map((q, qi) => {
      const type = q.type === "multi" ? "checkbox" : "radio";
      const opts = q.options.map((o, oi) =>
        `<label class="opt-row"><input type="${type}" name="q_${q.id}" value="${oi}"><label style="flex:1">${UI.esc(o)}</label></label>`).join("");
      return `<div class="glass reveal" style="padding:18px 20px">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline;margin-bottom:8px">
          <div class="card-title" style="font-size:14.5px">${qi + 1}. ${UI.esc(q.question)}</div>
          <span class="tag">${UI.esc(q.concept)}${q.type === "multi" ? " · select all" : ""}</span>
        </div>
        ${opts}
      </div>`;
    }).join("");
    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">${UI.esc(a.skill_id.replace(/_/g, " "))} · ${a.questions.length} questions</div>
        <h1 class="display" style="font-size:clamp(28px,3.8vw,46px)">${UI.esc(a.title)}</h1>
        <p class="sub">${UI.esc(a.description)}</p></div>
      </section>
      <div class="grid" style="gap:14px">${qs}</div>
      <div style="display:flex;gap:10px;margin-top:24px;flex-wrap:wrap">
        <button class="btn btn-primary" data-action="assessment-submit" data-id="${a.assessment_id}">Submit answers</button>
        <button class="btn btn-ghost" data-action="assessment-cancel">Cancel</button>
      </div>`;
  },
  _resultView() {
    const r = Store.assessmentResult;
    const pass = r.pass;
    const weak = (r.weak_concepts || []).map((c) => UI.tag(UI.esc(c))).join("");
    const conceptBars = Object.entries(r.concept_scores || {}).map(([c, s]) => UI.bar(c, s, { style: true })).join("");
    const adapt = r.roadmap_adapted && (r.adaptation_notes || []).length
      ? `<div class="glass adapt-banner">
           <div class="adapt-ico">🔄</div>
           <div><b>Your path was updated</b>
             <ul style="margin:8px 0 0;padding-left:18px;color:var(--ink-dim);font-size:12.8px">${r.adaptation_notes.map((n) => `<li>${UI.esc(n)}</li>`).join("")}</ul></div>
         </div><div style="height:16px"></div>`
      : "";
    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">Result · ${UI.esc(r.assessment_title || "assessment")}</div>
        <h1 class="display" style="font-size:clamp(28px,3.8vw,46px)">${pass ? "<span class='grad'>Strong.</span> Knowledge confirmed." : "<span class='grad'>Not yet.</span> That's exactly what adaptation is for."}</h1>
        <p class="sub">${r.correct}/${r.total} correct${pass ? " — the roadmap continues (and may accelerate)." : " — the roadmap will insert a remediation block before you advance."}</p></div>
      </section>
      ${adapt}
      <div class="grid grid-2" style="align-items:start">
        <div class="glass reveal" style="padding:24px;text-align:center">
          <div class="card-title" style="text-align:left">Score</div>
          <div style="display:flex;justify-content:center">${UI.gaugeSVG(r.score, pass ? "pass" : "below pass mark · remediation added")}</div>
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="60">
          <div class="card-title">Concept breakdown</div>
          <div class="card-sub">Where you're solid, and where to refocus.</div>
          <div style="height:10px"></div>
          ${conceptBars}
          <div style="height:14px"></div>
          <div class="card-title" style="font-size:13.5px">Weak areas detected</div>
          <div style="margin-top:8px">${weak || UI.tag("none — balanced performance")}</div>
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:22px;flex-wrap:wrap">
        ${!pass ? `<button class="btn btn-primary" data-action="lesson-gen" data-skill="${r.skill_id || ""}" data-concepts='${JSON.stringify(r.weak_concepts || [])}'>⚡ Learn this in 10 minutes</button>` : ""}
        <button class="btn btn-ghost" data-action="goto" data-page="journey">View updated roadmap →</button>
        <button class="btn btn-ghost" data-action="assessment-done">Back to assessments</button>
      </div>`;
  },
};

/* ================================================================
   7 · DASHBOARD
   ================================================================ */
Pages.dashboard = {
  nav: { icon: "📊", label: "Dashboard" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    const meta = await bootMeta();
    const [missionData, careerData, skillsData, insightsData, gamData] = await Promise.all([
      API.mission(learner.learner_id).catch(() => null),
      API.career(learner.learner_id).catch(() => null),
      API.skills(learner.learner_id).catch(() => null),
      API.insights(learner.learner_id).catch(() => null),
      API.gamification(learner.learner_id).catch(() => null),
    ]);
    const role = (meta.roles || {})[learner.target_role] || { title: learner.target_role };

    // roadmap completion
    const rm = Store.roadmap;
    const doneItems = rm ? rm.phases.reduce((n, p) => n + p.items.filter((i) => i.status === "completed").length, 0) : 0;
    const totalItems = rm ? rm.phases.reduce((n, p) => n + p.items.length, 0) : 0;

    // mission
    let missionHtml = UI.empty("Generate your roadmap to get a daily mission.");
    let scheduleHtml = "";
    if (missionData && missionData.mission) {
      const m = missionData.mission;
      missionHtml = `
        <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:10px">
          <div class="card-title">${UI.esc(m.date_label)} · ${m.total_minutes} min</div>
          <span class="tag">${m.focus ? "focus: " + UI.esc(m.focus) : "steady progress"}</span>
        </div>
        <button class="btn btn-primary btn-sm" data-action="complete-mission" style="margin-top:10px">✓ Complete today's mission (+25 XP)</button>
        <div style="display:flex;flex-direction:column;gap:10px">
          ${m.steps.map((s, i) => `<div class="rt-item reveal" data-delay="${i * 50}">
            <span class="mark cur">${i + 1}</span>
            <div style="flex:1">
              <div class="title" style="font-size:13.5px">${UI.esc(s.title)}</div>
              <div class="meta">${s.minutes} min${s.url ? ` · <a href="${UI.esc(s.url)}" target="_blank" rel="noopener" style="color:var(--brand-2)">open ↗</a>` : ""}</div>
            </div>
            <span class="mono" style="white-space:nowrap">${s.minutes}m</span>
          </div>`).join("")}
        </div>`;
      const sched = missionData.schedule || [];
      scheduleHtml = UI.hBars(sched.map((d) => ({ label: d.day, score: Math.min(1, d.minutes / 180) })));
    }

    const activity = [...(learner.recent_activity || [])].reverse().slice(0, 8)
      .map((a) => `<div class="rt-item"><span class="mark ${a.event === "assessment_completed" ? "done" : "next"}">·</span><div style="flex:1"><span style="font-size:13px">${UI.esc(a.event.replace(/_/g, " "))}</span><span class="meta">${UI.esc((a.detail || "").slice(0, 70))}</span></div></div>`).join("");

    const insights = insightsData && insightsData.metrics ? insightsData.metrics : null;
    const analytics = insights ? `
      <div class="metrics-row">
        ${UI.metric("Precision@5", insights.precision_at_5 != null ? Math.round(insights.precision_at_5 * 100) + "%" : "—")}
        ${UI.metric("Recall@5", insights.recall_at_5 != null ? Math.round(insights.recall_at_5 * 100) + "%" : "—")}
        ${UI.metric("NDCG@5", insights.ndcg_at_5 != null ? insights.ndcg_at_5.toFixed(2) : "—")}
        ${UI.metric("Acceptance", insightsData.acceptance_rate != null ? Math.round(insightsData.acceptance_rate * 100) + "%" : "—")}
      </div>` : "";

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">${ROLE_EMOJI[learner.target_role] || "🎯"} ${UI.esc(role.title)} · your digital twin</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Progress <span class="grad">dashboard</span></h1>
        <p class="sub">Everything your AI mentor knows about you — one screen. ${UI.esc(learner.goal_text.slice(0, 110))}…</p></div>
      </section>
      <div class="metrics-row reveal" data-delay="40">
        ${UI.metric("Career readiness", careerData ? Math.round(careerData.overall * 100) + "%" : "—", careerData ? "toward " + UI.esc(role.title) : "set a goal first")}
        ${UI.metric("Path progress", totalItems ? Math.round((doneItems / totalItems) * 100) + "%" : "—", `${doneItems}/${totalItems} items`)}
        ${UI.metric("Velocity", skillsData ? Math.round((skillsData.learning_velocity || 0) * 100) + "%" : "—", "avg proficiency")}
        ${UI.metric("Weekly time", learner.weekly_hours + "h", "planned")}
      </div>

      <div class="gam-dash glass-strong reveal" data-delay="30">
        <div class="gd-level">
          <div class="gd-level-badge">LEVEL ${gamData ? gamData.level : "—"}</div>
          <div class="gd-title">${gamData ? UI.esc(gamData.level_title) : "Explorer"}</div>
          <div class="gd-xp">⚡ ${gamData ? gamData.total_xp.toLocaleString() : "0"} <span class="faint">XP</span></div>
          ${gamData ? `<div class="xp-bar" style="margin-top:8px"><div class="xp-fill" data-w="${Math.round(gamData.level_progress * 100)}" style="width:${Math.round(gamData.level_progress * 100)}%"></div></div>
          <div class="faint" style="font-size:11.5px;margin-top:5px">${Math.round(gamData.level_progress * 100)}% into level ${gamData.level} · ${gamData.xp_to_next_level > 0 ? gamData.xp_to_next_level.toLocaleString() + " XP to " + (gamData.level + 1) : "max level"}</div>` : ""}
        </div>
        <div class="gd-stats">
          ${UI.metric("Global rank", gamData && gamData.leaderboard_position ? "#" + gamData.leaderboard_position : "—", gamData && gamData.leaderboard_size ? "of " + gamData.leaderboard_size + " learners" : "no cohort yet")}
          ${UI.metric("Streak", gamData ? "🔥 " + gamData.current_streak + "d" : "—", gamData && gamData.longest_streak ? "longest " + gamData.longest_streak + "d" : "start today")}
          ${UI.metric("Weekly XP", gamData ? gamData.weekly_xp.toLocaleString() : "—", "this week")}
          ${UI.metric("Badges", gamData ? gamData.badge_count : "—", gamData ? "earned" : "")}
        </div>
        <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" data-action="goto" data-page="achievements">🏅 Achievements</button>
          <button class="btn btn-ghost btn-sm" data-action="goto" data-page="leaderboard">🏆 Leaderboard</button>
        </div>
      </div>

      <div class="grid grid-2" style="align-items:start;margin-top:26px">
        <div class="glass reveal" style="padding:22px">
          <div class="card-title">Today's learning mission</div>
          <div style="height:8px"></div>${missionHtml}
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="70">
          <div class="card-title">Weekly time plan</div>
          <div class="card-sub">Distributed from your ${learner.weekly_hours}h/week budget${learner.recent_activity.some((a) => a.event === "session_missed") ? " — missed sessions redistributed to weekends" : ""}.</div>
          <div style="height:12px"></div>${scheduleHtml || UI.empty("No schedule yet.")}
          <div style="height:12px"></div>
          <button class="btn btn-ghost btn-sm" data-action="session-missed">Missed a session → rebalance</button>
        </div>
      </div>
      <div class="grid grid-2" style="align-items:start;margin-top:26px">
        <div class="glass reveal" style="padding:22px">
          <div class="card-title">Learning analytics</div>
          <div class="card-sub">Live evaluation of the recommender on your twin. No invented numbers.</div>
          <div style="height:12px"></div>${analytics || UI.empty("Complete onboarding to start analytics.")}
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="70">
          <div class="card-title">Recent activity</div>
          <div style="display:flex;flex-direction:column;gap:4px;margin-top:6px">${activity || UI.empty("No activity yet.")}</div>
        </div>
      </div>`;
  },
};

/* ================================================================
   8 · CAREER READINESS
   ================================================================ */
Pages.career = {
  nav: { icon: "🚀", label: "Career" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    const meta = await bootMeta();
    const [careerData] = await Promise.all([API.career(learner.learner_id).catch(() => null)]);
    const role = (meta.roles || {})[learner.target_role] || { title: learner.target_role };
    if (!careerData) return `<div class="note">Set a target role first.</div>`;

    const dims = careerData.dimensions.map((d) => UI.bar(d.label, d.score, { style: true })).join("");
    const to90 = careerData.to_reach_90.map((t) => `<div class="rt-item"><span class="mark next">▸</span><div style="flex:1;font-size:13px">${UI.esc(t)}</div></div>`).join("");

    const roleOpts = Object.values(meta.roles || {}).map((r) =>
      `<option value="${r.role_id}" ${r.role_id === learner.target_role ? "selected" : ""}>${UI.esc(r.title)}</option>`).join("");

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">${ROLE_EMOJI[learner.target_role] || "🎯"} ${UI.esc(role.title)} · job-readiness index</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Career <span class="grad">readiness</span></h1>
        <p class="sub">A weighted, honest estimate across technical skills, projects, problem solving, deployment and portfolio — plus exactly what it takes to reach 90%.</p></div>
      </section>
      <div class="grid grid-2" style="align-items:start">
        <div class="glass reveal" style="padding:24px;text-align:center">
          <div class="card-title" style="text-align:left">Readiness index</div>
          <div style="display:flex;justify-content:center;margin-top:6px">${UI.gaugeSVG(careerData.overall, UI.esc(role.title))}</div>
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="70">
          <div class="card-title">Dimensions</div>
          <div style="height:8px"></div>${dims}
        </div>
      </div>
      <div class="grid grid-2" style="align-items:start;margin-top:26px">
        <div class="glass reveal" style="padding:22px">
          <div class="card-title">To reach 90% job-ready</div>
          <div class="card-sub">Concrete next actions, computed from your twin.</div>
          <div style="height:8px"></div>${to90 || UI.empty("You're already past 90% — incredible.")}
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="70">
          <div class="card-title">What-if simulator</div>
          <div class="card-sub">“What if I change my goal?” — see transferable skills and the cost of switching.</div>
          <div style="height:12px"></div>
          <div style="display:flex;gap:10px">
            <select id="whatif-role" class="input">${roleOpts}</select>
            <button class="btn btn-primary" data-action="whatif">Simulate</button>
          </div>
          <div id="whatif-result"></div>
        </div>
      </div>`;
  },
  mount() {
    App.actions.whatifRender = () => {
      const box = document.getElementById("whatif-result");
      if (!box) return;
      const sel = document.getElementById("whatif-role");
      if (!sel) return;
      const newRole = sel.value;
      if (newRole === Store.learner.target_role) {
        box.innerHTML = `<div class="note" style="margin-top:14px">That's your current goal — pick a different role to simulate a switch.</div>`;
        return;
      }
      box.innerHTML = UI.skeletons(1);
      API.whatIf(Store.learner.learner_id, newRole).then((w) => {
        box.innerHTML = `
          <div class="divider"></div>
          <div style="font-size:13px;line-height:1.7;color:var(--ink);margin-bottom:12px">${UI.esc(w.summary)}</div>
          <div class="card-title" style="font-size:13px">Transferable</div>
          <div style="margin:6px 0 12px">${w.retained_skills.map((s) => UI.tag(UI.esc(s))).join("") || UI.tag("none")}</div>
          <div class="card-title" style="font-size:13px">Additional requirements</div>
          <div style="margin:6px 0 12px">${w.additional_skills.map((s) => UI.tag(UI.esc(s))).join("") || UI.tag("none")}</div>
          <div class="metrics-row">
            ${UI.metric("Extra effort", w.extra_hours + "h", "to close gaps")}
            ${UI.metric("Extra time", Math.round(w.extra_weeks) + " wks", `at ${Store.learner.weekly_hours}h/week`)}
          </div>`;
        Motion.observeReveals(box);
      }).catch((e) => { box.innerHTML = UI.empty(e.message); });
    };
  },
};

/* ================================================================
   9 · SETTINGS / PROFILE
   ================================================================ */
Pages.settings = {
  nav: { icon: "⚙️", label: "Settings" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    const meta = await bootMeta();
    const roleOpts = Object.values(meta.roles || {}).map((r) =>
      `<option value="${r.role_id}" ${r.role_id === learner.target_role ? "selected" : ""}>${ROLE_EMOJI[r.role_id] || ""} ${UI.esc(r.title)}</option>`).join("");
    const expSeg = (["beginner", "intermediate", "advanced"]).map((l) =>
      `<button class="${l === learner.experience_level ? "active" : ""}" data-action="seg" data-group="exp" data-value="${l}">${l[0].toUpperCase() + l.slice(1)}</button>`).join("");
    const prefs = (["hands-on", "video", "reading", "interactive"]).map((p) =>
      `<button class="${(learner.learning_preferences || []).includes(p) ? "active" : ""}" data-action="seg" data-group="prefs" data-value="${p}">${p}</button>`).join("");
    const skillRows = Object.entries(learner.known_skills || {}).map(([sid, v]) => `
      <div class="opt-row" style="align-items:center">
        <label style="flex:1">${UI.esc(sid.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join(" "))}</label>
        <input type="range" min="0" max="100" value="${Math.round(v * 100)}" data-skill-slider="${sid}" style="width:130px">
        <span class="mono faint" style="width:36px;text-align:right" data-skill-val="${sid}">${Math.round(v * 100)}%</span>
      </div>`).join("");

    let insights = "";
    try {
      const ins = await API.insights(learner.learner_id);
      const m = ins.metrics || {};
      insights = `<div class="metrics-row">
          ${UI.metric("Precision@5", m.precision_at_5 != null ? Math.round(m.precision_at_5 * 100) + "%" : "—")}
          ${UI.metric("Recall@5", m.recall_at_5 != null ? Math.round(m.recall_at_5 * 100) + "%" : "—")}
          ${UI.metric("NDCG@5", m.ndcg_at_5 != null ? m.ndcg_at_5.toFixed(2) : "—")}
          ${UI.metric("Coverage", m.coverage != null ? Math.round(m.coverage * 100) + "%" : "—")}
          ${UI.metric("Diversity", m.diversity != null ? m.diversity.toFixed(2) : "—")}
          ${UI.metric("Acceptance", ins.acceptance_rate != null ? Math.round(ins.acceptance_rate * 100) + "%" : "—")}
        </div>
        <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">${(ins.top_skills || []).map((s) => UI.tag(UI.esc(s))).join("")}</div>`;
    } catch (_) { /* insights optional */ }

    const weights = Object.entries(meta.weights || {}).map(([k, v]) => UI.bar(REASON_LABELS[k] || k, v, { style: true })).join("");

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">Learner digital twin · source: ${learner.profile_source || "manual"}</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Profile & <span class="grad">twin</span></h1>
        <p class="sub">Edit what the AI believes about you — the roadmap, recommendations and readiness recompute from this state.</p></div>
      </section>
      <div class="grid grid-2" style="align-items:start">
        <div class="glass reveal" style="padding:22px">
          <div class="card-title">Profile editor</div>
          <div style="height:12px"></div>
          <div class="field"><label>Goal</label><textarea id="s-goal" class="input" rows="3">${UI.esc(learner.goal_text)}</textarea></div>
          <div class="field"><label>Target role</label><select id="s-role" class="input">${roleOpts}</select></div>
          <div class="field"><label>Experience</label><div class="seg">${expSeg}</div></div>
          <div class="input-row">
            <div class="field"><label>Weekly hours</label><input id="s-hours" type="number" class="input" min="1" max="40" value="${learner.weekly_hours}"></div>
            <div class="field"><label>Deadline (weeks)</label><input id="s-weeks" type="number" class="input" min="4" max="104" value="${learner.deadline_weeks}"></div>
          </div>
          <div class="field"><label>Preferences</label><div class="seg" style="flex-wrap:wrap">${prefs}</div></div>
          <button class="btn btn-primary btn-block" data-action="save-profile" data-magnetic>Save & recompute</button>
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="70">
          <div class="card-title">Skill proficiencies</div>
          <div class="card-sub">0–100% confidence per skill in your twin.</div>
          <div style="height:10px"></div>${skillRows || UI.empty("No skills recorded yet.")}
        </div>
      </div>
      <div class="section-head"><h2 class="h2">System insights <span class="faint" style="font-weight:400;font-size:13px">— evaluator view</span></h2></div>
      <div class="grid grid-2" style="align-items:start">
        <div class="glass reveal" style="padding:22px">
          <div class="card-title">Recommender evaluation</div>
          <div class="card-sub">Synthetic benchmark on your twin (see README for methodology).</div>
          <div style="height:12px"></div>${insights}
        </div>
        <div class="glass reveal" style="padding:22px" data-delay="70">
          <div class="card-title">Active weights</div>
          <div class="card-sub">Configurable ranking factors — sum to ${Object.values(meta.weights || {}).reduce((a, b) => a + b, 0).toFixed(2)}.</div>
          <div style="height:12px"></div>${weights}
          <div style="margin-top:12px"><span class="tag">llm mode: ${meta.llm_mode}</span><span class="tag">provider: local-first</span></div>
        </div>
      </div>
      <div class="divider"></div>
      <div class="note">Raw twin JSON lives in <span class="mono">data/learnpath.db</span> (SQLite). Resetting starts a fresh demo learner.</div>
      <button class="btn btn-ghost" data-action="new-demo">↺ Reset demo & start over</button>`;
  },
  mount() {
    document.querySelectorAll("[data-skill-slider]").forEach((s) => {
      s.addEventListener("input", () => {
        const v = document.querySelector(`[data-skill-val="${s.dataset.skillSlider}"]`);
        if (v) v.textContent = s.value + "%";
      });
    });
  },
};
/* ================================================================
   ACHIEVEMENTS — LearnPath XP, level, badges, streaks, history
   ================================================================ */
Pages.achievements = {
  nav: { icon: "🏅", label: "Achievements" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    const [g, history, badgeData] = await Promise.all([
      API.gamification(learner.learner_id).catch(() => null),
      API.xpHistory(learner.learner_id).catch(() => null),
      API.badges(learner.learner_id).catch(() => null),
    ]);
    if (!g) return UI.empty("Gamification data unavailable.");

    const pct = Math.round(g.level_progress * 100);
    const bar = `<div class="xp-bar"><div class="xp-fill" data-w="${pct}" style="width:${pct}%"></div></div>`;
    const next = g.xp_to_next_level > 0
      ? `<div class="xp-next">${g.xp_to_next_level.toLocaleString()} XP to <b>${g.level + 1}</b></div>`
      : `<div class="xp-next ok">Max level reached — incredible!</div>`;

    // badges grid
    const defs = badgeData && badgeData.badges ? badgeData.badges : (g.badge_definitions || []);
    const earnedSet = new Set(g.badges || []);
    const badgeHtml = defs.map((b) => `
      <div class="badge-card ${earnedSet.has(b.badge_id) ? "earned" : "locked"}" data-tilt>
        <div class="bc-icon">${b.icon}</div>
        <div class="bc-name">${UI.esc(b.name)}</div>
        <div class="bc-desc">${UI.esc(b.description)}</div>
        ${earnedSet.has(b.badge_id) ? `<div class="bc-earned">✓ earned</div>` : `<div class="bc-locked">locked</div>`}
      </div>`).join("");

    // challenges
    const ch = (g.challenges || []).map((c) => {
      const p = Math.min(100, Math.round((c.progress / Math.max(1, c.target)) * 100));
      const done = c.completed;
      return `<div class="glass challenge-card reveal" style="padding:18px 20px">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap">
          <div>
            <div class="card-title">${UI.esc(c.title)} ${done ? "✓" : ""}</div>
            <div class="card-sub">${UI.esc(c.description)}</div>
          </div>
          <span class="badge ${done ? "ok" : "type"}">+${c.xp_reward} XP</span>
        </div>
        <div style="margin-top:12px"><div class="xp-bar"><div class="xp-fill" style="width:${p}%"></div></div></div>
        <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11.5px" class="faint">
          <span>${p}% · ${c.progress.toFixed(1)} / ${c.target} ${c.challenge_type.replace(/_/g, " ")}</span>
          ${done && !c.claimed ? `<button class="chip-btn" data-action="claim-challenge" data-id="${c.challenge_id}">Claim reward →</button>` : (c.claimed ? `<span class="mono ok">claimed</span>` : "")}
        </div>
      </div>`;
    }).join("");

    // xp history (recent 12)
    const txs = (history && history.transactions ? history.transactions : []).slice(0, 12);
    const histHtml = txs.length ? txs.map((t, i) => `
      <div class="rt-item reveal" data-delay="${i * 30}">
        <span class="mark done">+${t.final_xp}</span>
        <div style="flex:1">
          <div class="title" style="font-size:13px">${UI.esc((t.reason || t.activity_type || "xp").replace(/_/g, " "))}</div>
          <div class="meta">${UI.esc((t.created_at || "").slice(0, 10))} · base ${t.base_xp} · bonus ${t.bonus_xp} · ×${t.multiplier}</div>
        </div>
      </div>`).join("") : UI.empty("No XP yet — complete your first learning activity.");

    // breakdown chart
    const breakdown = g.breakdown || [];
    const bdHtml = breakdown.length ? breakdown.map((b) => UI.bar(b.activity_type.replace(/_/g, " "), Math.min(1, b.xp / Math.max(1, breakdown[0].xp)), { pct: b.xp })).join("") : "";

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">Learn · Build · Master · Rise</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">Achieve <span class="grad">& rise</span></h1>
        <p class="sub">Outcome-based learning gamification — XP rewards mastery and consistency, never busywork.</p></div>

        <div class="level-card glass-strong reveal" data-delay="40">
          <div class="lc-row">
            <div>
              <div class="lc-level">LEVEL ${g.level}</div>
              <div class="lc-title">${UI.esc(g.level_title)}</div>
            </div>
            <div class="lc-xp">⚡ ${g.total_xp.toLocaleString()} <span class="faint">XP</span></div>
          </div>
          <div style="margin-top:14px">${bar}</div>
          <div style="display:flex;justify-content:space-between;margin-top:8px;align-items:center;flex-wrap:wrap;gap:6px">
            <span class="mono">${pct}% into level ${g.level}</span>${next}
          </div>
          <div class="lc-stats">
            ${UI.metric("Global rank", g.leaderboard_position ? "#" + g.leaderboard_position : "—", g.leaderboard_size ? `of ${g.leaderboard_size} learners` : "no cohort yet")}
            ${UI.metric("Streak", "🔥 " + g.current_streak + "d", g.longest_streak ? `longest ${g.longest_streak}d` : "start today")}
            ${UI.metric("Weekly XP", g.weekly_xp.toLocaleString(), "this week")}
            ${UI.metric("Badges", g.badge_count, `of ${defs.length}`)}
          </div>
        </div>

        <div class="section-head"><h2 class="h2">Weekly challenges</h2></div>
        <div class="grid grid-2" style="align-items:start">${ch || UI.empty("No challenges this week.")}</div>

        <div class="section-head"><h2 class="h2">Badges</h2></div>
        <div class="grid grid-4" style="align-items:start">${badgeHtml || UI.empty("No badges defined yet.")}</div>

        <div class="section-head"><h2 class="h2">XP history</h2></div>
        <div class="grid grid-2" style="align-items:start">
          <div class="glass reveal" style="padding:22px">${histHtml}</div>
          <div class="glass reveal" data-delay="60" style="padding:22px">
            <div class="card-title">XP by activity</div>
            <div style="height:12px"></div>${bdHtml || UI.empty("No XP breakdown yet.")}
          </div>
        </div>
      </section>`;
  },
};

/* ================================================================
   LEADERBOARD — global / weekly / monthly / skill / mastery
   ================================================================ */
Pages.leaderboard = {
  nav: { icon: "🏆", label: "Leaderboard" },
  gate: "learner",
  async render() {
    const learner = await loadLearner();
    const scopes = [
      ["global", "🌍 Global"], ["weekly", "📅 This Week"], ["monthly", "🗓️ This Month"],
      ["mastery", "🧠 Mastery"], ["skill", "⚡ My Skill"],
    ];
    const current = Store.leaderboardScope || "global";
    const segHtml = scopes.map(([id, label]) =>
      `<button class="${id === current ? "active" : ""}" data-action="lb-scope" data-value="${id}">${label}</button>`).join("");
    const lb = await API.leaderboard(learner.learner_id, current).catch(() => null);
    if (!lb) return UI.empty("Leaderboard unavailable.");

    const medal = ["🥇", "🥈", "🥉"];
    const rows = (lb.rows || []).map((r, i) => {
      const isMe = r.learner_id === learner.learner_id;
      const val = lb.scope === "mastery"
        ? `${r.skills_mastered} skills · ${r.readiness}%`
        : lb.scope === "skill"
          ? `${r.value}%`
          : `${r.xp.toLocaleString()} XP`;
      return `<div class="lb-row ${isMe ? "me" : ""} ${i < 3 ? "podium" : ""}">
        <div class="lb-rank">${i < 3 ? medal[i] : "#" + r.rank}</div>
        <div class="lb-name">${isMe ? `<b>You</b>` : UI.esc(r.name)}</div>
        <div class="lb-level">Lv ${r.level}</div>
        <div class="lb-val mono">${val}</div>
        <div class="lb-streak">${r.streak ? "🔥" + r.streak : ""}</div>
      </div>`;
    }).join("");

    return `
      <section class="hero">
        <div class="reveal"><div class="eyebrow">Competitive standing · fair weekly resets</div>
        <h1 class="display" style="font-size:clamp(30px,4.2vw,52px)">🏆 Leader<span class="grad">board</span></h1>
        <p class="sub">Weekly and monthly boards reset so new learners can always compete. The mastery board ranks real skill development, not just points.</p></div>
        <div style="margin-top:16px" class="reveal" data-delay="40"><div class="seg" style="flex-wrap:wrap">${segHtml}</div></div>
        <div class="glass reveal" data-delay="60" style="padding:20px 22px;margin-top:22px">
          <div class="lb-head"><span class="faint" style="text-transform:uppercase;font-size:11px;letter-spacing:0.08em">${lb.scope === "mastery" ? "🧠 Mastery board — by skills mastered" : lb.scope === "skill" ? "⚡ Skill board — by proficiency" : lb.scope === "weekly" ? "📅 This week's XP" : lb.scope === "monthly" ? "🗓️ This month's XP" : "🌍 All-time XP"}</span></div>
          ${rows || UI.empty("No learners on this board yet.")}
        </div>
      </section>`;
  },
  mount(root) {
    // persist scope choice when switching tabs (handled by lb-scope action)
  },
};

/* ================================================================
   LANDING — cinematic marketing page
   ================================================================ */
Pages.landing = {
  nav: { icon: "✦", label: "Home" },
  gate: null,
  async render() {
    const meta = await bootMeta();
    const authed = Store.authed;

    const cta = authed
      ? `<button class="btn btn-primary" data-action="goto" data-page="${Store.learner ? "dashboard" : "onboarding"}" data-magnetic>Enter your journey →</button>
         <button class="btn btn-ghost" data-action="goto" data-page="signin">Account</button>`
      : `<button class="btn btn-primary" data-action="goto" data-page="signup" data-magnetic>Get started — it's free</button>
         <button class="btn btn-ghost" data-action="goto" data-page="signin">Sign in</button>
         <button class="btn" data-action="guest-demo" data-magnetic style="border-color:rgba(34,211,238,0.4);color:var(--brand-2)">⚡ Try the demo — no account</button>`;

    const personas = (meta.personas || []).slice(0, 4).map((p, i) => {
      const emoji = PERSONA_EMOJI[p.id] || "🎓";
      return `<div class="glass reveal" style="padding:18px" data-delay="${i * 60}" data-tilt>
        <div style="font-size:26px;filter:drop-shadow(0 6px 16px rgba(124,108,255,0.4))">${emoji}</div>
        <div class="p-name" style="font-family:var(--font-display);font-weight:700;font-size:13.5px;margin-top:8px">${UI.esc(p.name.replace(/^[^—]+—\s*/, ""))}</div>
        <div class="card-sub" style="margin-top:5px">${UI.esc(p.goal_text.slice(0, 96))}…</div>
      </div>`;
    }).join("");

    const features = [
      ["🧬", "Learner Digital Twin", "A living representation of your skills, confidence, preferences, constraints and history — updated by every signal you give it."],
      ["⚡", "Skill Intelligence", "A 62-skill prerequisite graph. Gaps are computed against your goal's competency map, not guessed."],
      ["💡", "Explainable Recommendations", "Every course, project and check is scored across 8 factors — and tells you exactly why, with real numbers."],
      ["🔄", "Adaptive Roadmap", "Fail a knowledge check and a remediation phase appears before you advance. Excel and the path accelerates."],
      ["💬", "AI Learning Coach", "A retrieval-grounded coach that knows your profile, roadmap and gaps — and says “I don't know” instead of inventing."],
      ["🚀", "Career Readiness", "A weighted job-readiness index, a today-mission, and a what-if simulator for switching goals."],
    ].map(([ico, t, d], i) => `
      <div class="card reveal" data-delay="${(i % 3) * 70}" data-tilt>
        <div style="font-size:24px;filter:drop-shadow(0 4px 12px rgba(124,108,255,0.4))">${ico}</div>
        <div class="card-title" style="margin-top:10px">${t}</div>
        <div class="card-sub">${d}</div>
      </div>`).join("");

    const pipeline = [
      ["Goal", "You say what you want to achieve"],
      ["Twin", "The system builds your learner profile"],
      ["Gaps", "Skill gaps are computed & prioritized"],
      ["Path", "A prerequisite-aware roadmap is planned"],
      ["Learn", "Courses, projects & daily missions"],
      ["Adapt", "Assessments re-plan your journey"],
      ["Ready", "Career-readiness you can measure"],
    ].map(([t, d], i) => `
      <div class="pipe-step reveal" data-delay="${i * 60}">
        <div class="pipe-num">${String(i + 1).padStart(2, "0")}</div>
        <div class="pipe-title">${t}</div>
        <div class="pipe-desc">${d}</div>
      </div>`).join("");

    return `
      <section class="hero landing-hero">
        <div class="reveal" style="max-width:880px">
          <div class="eyebrow">LearnPath AI · Adaptive Learning Operating System</div>
          <h1 class="display" style="font-size:clamp(2.6rem,6.5vw,5.2rem);line-height:1.02">Stop guessing what to learn.<br><span class="grad">Learn exactly what's next.</span></h1>
          <p class="sub" style="font-size:17px;max-width:600px;margin-top:18px">Thousands of courses exist — but nobody tells you what <em>you</em> should learn next. LearnPath AI understands your goal, maps your skill gaps, and builds a journey that adapts to how you actually learn.</p>
          <div style="display:flex;gap:12px;margin-top:28px;flex-wrap:wrap">${cta}</div>
          <div class="faint" style="margin-top:16px;font-size:12px">✦ No credit card · ✦ Works fully offline · ✦ Optional LLM upgrade</div>
        </div>
      </section>

      <div class="grid grid-3 reveal" data-delay="60" style="margin-top:8px">
        ${[
          ["📚", "Thousands of courses", "But no one tells you which one is right for <em>your</em> goal, at <em>your</em> level."],
          ["🧩", "No sequencing", "Random playlists ignore prerequisites — so learners get stuck or lost."],
          ["🚫", "No adaptation", "One-size-fits-all paths never change when you struggle — or when you fly."],
        ].map(([ico, t, d]) => `<div class="card"><div style="font-size:22px">${ico}</div><div class="card-title" style="margin-top:8px">${t}</div><div class="card-sub">${d}</div></div>`).join("")}
      </div>

      <div class="section-head"><h2 class="h2">Everything a mentor would do,<br>in one <span class="grad">living system</span></h2></div>
      <div class="grid grid-3" style="align-items:stretch">${features}</div>

      <div class="section-head"><h2 class="h2">Goal → <span class="grad">journey</span> → readiness</h2></div>
      <div class="glass reveal" style="padding:28px 24px">
        <div class="pipeline">${pipeline}</div>
      </div>

      <div class="section-head"><h2 class="h2">Four journeys, <span class="grad">one click</span> each</h2></div>
      <div class="grid grid-4">${personas}</div>
      <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap" class="reveal">
        <button class="btn btn-primary" data-action="goto" data-page="${authed ? "onboarding" : "signup"}" data-magnetic>${authed ? "Choose a persona →" : "Sign up to start your journey →"}</button>
        ${authed ? "" : `<button class="btn" data-action="guest-demo" data-magnetic style="border-color:rgba(34,211,238,0.4);color:var(--brand-2)">⚡ Explore instantly as guest</button>`}
      </div>

      <div class="divider"></div>
      <div class="glass reveal" style="padding:36px;text-align:center;position:relative;overflow:hidden">
        <div class="card-title" style="font-size:22px">LearnPath AI is not a course recommender.<br>It's an <span class="grad">adaptive learning companion</span>.</div>
        <div class="card-sub" style="margin-top:10px;max-width:560px;margin-left:auto;margin-right:auto">It continuously transforms your goal into an executable, personalized, measurable journey — and re-plans it as you grow.</div>
        <div style="margin-top:20px">${cta}</div>
      </div>`;
  },
};

/* ================================================================
   SIGN IN
   ================================================================ */
Pages.signin = {
  nav: { icon: "→", label: "Sign in" },
  gate: null,
  render() {
    const demo = Store.authed
      ? `<div class="note" style="margin-top:16px;text-align:center">Signed in as <b>${UI.esc(Store.user.name)}</b> — <button class="ghost-btn" data-action="signout">sign out</button></div>`
      : "";
    return `
      <section class="hero auth-hero">
        <div class="reveal" style="max-width:420px;margin:0 auto;width:100%">
          <div style="text-align:center;margin-bottom:22px">
            <div class="brand-logo" style="margin:0 auto 14px;width:52px;height:52px;font-size:22px">LP</div>
            <h1 class="display" style="font-size:clamp(1.9rem,4.5vw,2.6rem)">Welcome <span class="grad">back</span></h1>
            <p class="sub" style="font-size:13.5px;margin-top:6px">Sign in to continue your adaptive journey.</p>
          </div>
          <div class="glass" style="padding:26px 24px">
            <div class="field"><label>Email</label><input id="si-email" class="input" type="email" placeholder="you@example.com" autocomplete="email"></div>
            <div class="field"><label>Password</label><input id="si-pass" class="input" type="password" placeholder="••••••••" autocomplete="current-password"></div>
            <div id="si-error" class="note" hidden></div>
            <button class="btn btn-primary btn-block" data-action="signin" data-magnetic>Sign in →</button>
            <div style="margin-top:16px;font-size:12.5px;color:var(--ink-dim);text-align:center">
              New to LearnPath? <a href="#" data-action="goto" data-page="signup" style="color:var(--brand-2)">Create an account</a>
            </div>
            <div style="margin-top:8px;font-size:12.5px;color:var(--ink-dim);text-align:center">
              <a href="#" data-action="guest-demo" style="color:var(--brand-2)">⚡ Explore instantly as guest</a>
            </div>
            <div style="margin-top:8px;font-size:12.5px;color:var(--ink-dim);text-align:center">
              <a href="#" data-action="goto" data-page="landing" style="color:var(--ink-faint)">← Back to home</a>
            </div>
          </div>
          ${demo}
        </div>
      </section>`;
  },
  mount() {
    const p = document.querySelector("#si-pass");
    if (p) p.addEventListener("keydown", (e) => { if (e.key === "Enter") App.actions.signin(); });
  },
};

/* ================================================================
   SIGN UP
   ================================================================ */
Pages.signup = {
  nav: { icon: "✚", label: "Sign up" },
  gate: null,
  render() {
    return `
      <section class="hero auth-hero">
        <div class="reveal" style="max-width:420px;margin:0 auto;width:100%">
          <div style="text-align:center;margin-bottom:22px">
            <div class="brand-logo" style="margin:0 auto 14px;width:52px;height:52px;font-size:22px">LP</div>
            <h1 class="display" style="font-size:clamp(1.9rem,4.5vw,2.6rem)">Create your <span class="grad">journey</span></h1>
            <p class="sub" style="font-size:13.5px;margin-top:6px">Free, offline-first, no credit card. Your learning twin is private.</p>
          </div>
          <div class="glass" style="padding:26px 24px">
            <div class="field"><label>Name</label><input id="su-name" class="input" placeholder="Ada Lovelace" autocomplete="name"></div>
            <div class="field"><label>Email</label><input id="su-email" class="input" type="email" placeholder="you@example.com" autocomplete="email"></div>
            <div class="field"><label>Password</label><input id="su-pass" class="input" type="password" placeholder="6+ characters" autocomplete="new-password"></div>
            <div id="su-error" class="note" hidden></div>
            <button class="btn btn-primary btn-block" data-action="signup" data-magnetic>Create account →</button>
            <div style="margin-top:16px;font-size:12.5px;color:var(--ink-dim);text-align:center">
              Already have an account? <a href="#" data-action="goto" data-page="signin" style="color:var(--brand-2)">Sign in</a>
            </div>
            <div style="margin-top:8px;font-size:12.5px;color:var(--ink-dim);text-align:center">
              <a href="#" data-action="guest-demo" style="color:var(--brand-2)">⚡ Explore instantly as guest</a>
            </div>
            <div style="margin-top:8px;font-size:12.5px;color:var(--ink-dim);text-align:center">
              <a href="#" data-action="goto" data-page="landing" style="color:var(--ink-faint)">← Back to home</a>
            </div>
          </div>
        </div>
      </section>`;
  },
  mount() {
    const p = document.querySelector("#su-pass");
    if (p) p.addEventListener("keydown", (e) => { if (e.key === "Enter") App.actions.signup(); });
  },
};
