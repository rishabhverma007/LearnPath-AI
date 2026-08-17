/* LearnPath AI — application shell: router, nav, action dispatch, boot. */
"use strict";

const NAV_ORDER = ["journey", "skills", "recommendations", "coach", "assessments", "dashboard", "career", "settings"];
const AUTH_PAGES = ["onboarding", ...NAV_ORDER];

const App = (() => {
  let viewRoot = null;

  /* ---------------------------------------------------------------
     NAVIGATION
     --------------------------------------------------------------- */
  function buildNav() {
    const nav = document.getElementById("nav");
    const items = ["landing", ...(Store.authed ? AUTH_PAGES : ["signin", "signup"])];
    nav.innerHTML = items.map((key) => {
      const p = Pages[key];
      const gateOk = !p.gate || !!Store.learner;
      return `<button class="nav-item" data-action="goto" data-page="${key}" ${!gateOk && p.gate ? "disabled" : ""}>
        <span class="nav-ico">${p.nav.icon}</span><span>${p.nav.label}</span>
      </button>`;
    }).join("");
    markNav();
  }

  function markNav() {
    document.querySelectorAll(".nav-item").forEach((b) => {
      b.classList.toggle("active", b.dataset.page === Store.page);
    });
    const crumb = document.getElementById("crumb");
    if (crumb && Pages[Store.page]) {
      crumb.textContent = `${Pages[Store.page].nav.icon}  ${Pages[Store.page].nav.label.toUpperCase()}`;
    }
    document.title = `${Pages[Store.page] ? Pages[Store.page].nav.label : "Home"} · LearnPath AI`;
  }

  async function navigate(page) {
    let target = Pages[page] ? page : "landing";
    if (Pages[target].gate && !Store.learner) { target = "onboarding"; }
    // auth gate: app pages require a signed-in user
    if (!Store.authed && AUTH_PAGES.includes(target)) { target = "landing"; }
    if (Store.authed && (target === "signin" || target === "signup")) { target = "landing"; }
    Store.page = target;
    if (target === "onboarding") Store.recFilter = null;

    await Motion.playCurtain();
    markNav();

    const view = document.getElementById("view");
    view.innerHTML = UI.skeletons(3);
    try {
      const html = await Pages[target].render();
      viewRoot = UI.setView(html);
      Motion.observeReveals(viewRoot);
      Motion.animateBars(viewRoot);
      if (Pages[target].mount) Pages[target].mount(viewRoot);
    } catch (err) {
      console.error("render error:", err);
      view.innerHTML = `<div class="scene"><div class="note" style="margin-top:40px">Something went wrong: ${UI.esc(err.message)}<br><button class="btn btn-ghost btn-sm" style="margin-top:10px" data-action="goto" data-page="dashboard">Back to dashboard</button></div></div>`;
    }
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  /* ---------------------------------------------------------------
     LEARNER HELPERS
     --------------------------------------------------------------- */
  function renderLearnerChip() {
    const chip = document.getElementById("learner-chip");
    const btn = document.getElementById("new-demo-btn");
    if (!Store.learner || !Store.authed) {
      chip.hidden = true;
      btn.hidden = true;
      return;
    }
    chip.hidden = false;
    btn.hidden = false;
    const meta = Store.meta || {};
    const role = (meta.roles || {})[Store.learner.target_role] || { title: Store.learner.target_role };
    const who = Store.guest ? "guest" : (Store.user ? UI.esc(Store.user.name) : "learner");
    chip.innerHTML = `<span class="lc-role"><span class="lc-emoji">${ROLE_EMOJI[Store.learner.target_role] || "🎯"}</span>${UI.esc(role.title)}</span>
      <span class="lc-label">${who}</span>`;
  }

  async function refreshLearner() {
    const l = await loadLearner();
    if (l) {
      try {
        const r = await API.roadmap(l.learner_id);
        Store.roadmap = r.generated ? r : null;
      } catch (_) { /* no roadmap yet */ }
    }
    renderLearnerChip();
    return l;
  }

  /* ---------------------------------------------------------------
     ACTIONS
     --------------------------------------------------------------- */
  const actions = {
    async goto(btn) {
      await navigate(btn.dataset.page);
    },

    /* --- onboarding --- */
    async analyze() {
      const ta = document.getElementById("goal-input");
      const text = (ta ? ta.value : "").trim();
      if (text.length < 3) { UI.toast("Tell me a bit more about your goal first."); return; }
      Store.lastGoal = text;
      UI.toast("Analyzing your goal…", 1400);
      try {
        Store.analysis = await API.analyze(text);
        const view = document.getElementById("view");
        const html = await Pages.onboarding.render();
        viewRoot = UI.setView(html);
        Motion.observeReveals(viewRoot);
        Motion.animateBars(viewRoot);
        Pages.onboarding.mount();
      } catch (err) {
        UI.toast(err.message, 4000);
      }
    },

    async persona(btn) {
      const id = btn.dataset.id;
      if (Store.learner) {
        try { await API.deleteLearner(Store.learnerId); } catch (_) { /* ignore */ }
      }
      UI.toast("Building your learner digital twin…", 1600);
      try {
        const learner = await API.createLearner({ persona_id: id });
        Store.learnerId = learner.learner_id;
        Store.learner = learner;
        Store.roadmap = null;
        Store.chat = [];
        Store.recs = null;
        Store.assessmentActive = null;
        Store.assessmentResult = null;
        Store.analysis = null;
        const roadmap = await API.generateRoadmap(learner.learner_id, "balanced");
        Store.roadmap = roadmap;
        renderLearnerChip();
        buildNav();
        await navigate("journey");
        UI.toast(`Twin created for ${learner.goal_text.slice(0, 50)}…`);
      } catch (err) {
        UI.toast(err.message, 4000);
      }
    },

    seg(btn) {
      const group = btn.dataset.group;
      btn.parentElement.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
    },

    async createLearner() {
      const meta = Store.meta || {};
      const text = (document.getElementById("goal-input") || {}).value || Store.analysis.goal;
      const profile = {
        target_role: document.getElementById("f-role") ? document.getElementById("f-role").value : Store.analysis.target_role,
        experience_level: document.querySelector('#understanding [data-group="exp"].active') ? document.querySelector('#understanding [data-group="exp"].active').dataset.value : Store.analysis.experience_level,
        weekly_hours: parseFloat((document.getElementById("f-hours") || {}).value) || 8,
        deadline_weeks: parseInt((document.getElementById("f-weeks") || {}).value, 10) || 26,
        preferences: Array.from(document.querySelectorAll('#understanding [data-group="prefs"].active')).map((b) => b.dataset.value),
        skills: {},
        remove_skills: [],
      };
      document.querySelectorAll("#understanding [data-skill-check]").forEach((cb) => {
        if (cb.checked) {
          const sid = cb.dataset.skillCheck;
          const slider = document.querySelector(`[data-skill-slider="${sid}"]`);
          profile.skills[sid] = slider ? parseFloat(slider.value) / 100 : 0.5;
        } else {
          profile.remove_skills.push(cb.dataset.skillCheck);
        }
      });
      if (!profile.preferences.length) profile.preferences = ["hands-on"];
      if (Store.learner) {
        try { await API.deleteLearner(Store.learnerId); } catch (_) { /* ignore */ }
      }
      try {
        const learner = await API.createLearner({ text, profile });
        Store.learnerId = learner.learner_id;
        Store.learner = learner;
        Store.roadmap = null;
        Store.chat = [];
        Store.recs = null;
        Store.assessmentActive = null;
        Store.assessmentResult = null;
        Store.analysis = null;
        const roadmap = await API.generateRoadmap(learner.learner_id, "balanced");
        Store.roadmap = roadmap;
        renderLearnerChip();
        buildNav();
        await navigate("journey");
      } catch (err) {
        UI.toast(err.message, 4000);
      }
    },

    /* --- journey --- */
    async roadmapMode(btn) {
      const mode = btn.dataset.mode;
      btn.parentElement.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
      const l = Store.learner;
      UI.toast(`Re-planning at ${mode} pace…`, 1600);
      try {
        Store.roadmap = await API.generateRoadmap(l.learner_id, mode);
        await navigate("journey");
      } catch (err) { UI.toast(err.message, 4000); }
    },

    async completeItem(btn) {
      const l = Store.learner;
      try {
        await API.completeItem(l.learner_id, btn.dataset.type, btn.dataset.id);
        UI.toast("Completed — proficiency updated. ✨");
        await refreshLearner();
        await navigate("journey");
      } catch (err) { UI.toast(err.message, 4000); }
    },

    /* --- recommendations --- */
    recFilter(btn) {
      Store.recFilter = btn.dataset.filter;
      btn.parentElement.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
      navigate("recommendations");
    },
    whyToggle(btn) {
      const panel = document.getElementById(btn.dataset.id);
      if (panel) panel.hidden = !panel.hidden;
    },
    async recFeedback(btn) {
      const l = Store.learner;
      try {
        await API.feedback(l.learner_id, btn.dataset.id, btn.dataset.type, btn.dataset.signal);
        UI.toast(btn.dataset.signal === "like" ? "Noted — will surface more like this." : "Noted — will surface less like this.");
      } catch (err) { UI.toast(err.message, 4000); }
    },
    async recComplete(btn) {
      const l = Store.learner;
      try {
        await API.feedback(l.learner_id, btn.dataset.id, btn.dataset.type, "complete");
        UI.toast("Completed — twin updated. ✨");
        Store.recs = null;
        await refreshLearner();
        await navigate("recommendations");
      } catch (err) { UI.toast(err.message, 4000); }
    },

    /* --- coach --- */
    async coachSend(message) {
      const l = Store.learner;
      const input = document.getElementById("coach-input");
      if (input) input.value = "";
      Store.chat.push({ role: "user", text: message });
      Store.chat.push({ role: "coach", text: "…", typing: true });
      await navigate("coach");
      try {
        const reply = await API.coach(l.learner_id, message);
        Store.chat.pop();
        Store.chat.push({ role: "coach", text: reply.text, sources: reply.sources, actions: reply.actions });
      } catch (err) {
        Store.chat.pop();
        Store.chat.push({ role: "coach", text: "I hit a snag reaching the engine — please try again." });
      }
      await navigate("coach");
    },
    coachChip(btn) {
      this.coachSend(btn.dataset.q);
    },
    async coachAction(btn) {
      if (!btn.dataset.id) return;
      await this.completeItem(btn);
    },

    /* --- assessments --- */
    async assessmentStart(btn) {
      try {
        const a = await API.assessment(btn.dataset.id);
        Store.assessmentActive = a;
        Store.assessmentResult = null;
        await navigate("assessments");
      } catch (err) { UI.toast(err.message, 4000); }
    },
    assessmentCancel() {
      Store.assessmentActive = null;
      navigate("assessments");
    },
    assessmentDone() {
      Store.assessmentActive = null;
      Store.assessmentResult = null;
      navigate("assessments");
    },
    async assessmentSubmit(btn) {
      const a = Store.assessmentActive;
      if (!a) return;
      const answers = {};
      for (const q of a.questions) {
        const els = document.querySelectorAll(`input[name="q_${q.id}"]:checked`);
        if (!els.length) continue;
        answers[q.id] = q.type === "multi" ? Array.from(els).map((e) => parseInt(e.value, 10)) : parseInt(els[0].value, 10);
      }
      const answered = Object.keys(answers).length;
      if (answered < a.questions.length) {
        UI.toast(`Answer all questions first (${answered}/${a.questions.length}).`, 3500);
        return;
      }
      UI.toast("Grading & adapting your roadmap…", 1600);
      try {
        const l = Store.learner;
        const result = await API.submitAssessment(l.learner_id, a.assessment_id, answers);
        Store.assessmentResult = result;
        Store.assessmentActive = null;
        Store.recs = null;
        await refreshLearner();
        await navigate("assessments");
      } catch (err) { UI.toast(err.message, 4000); }
    },
    async lessonGen(btn) {
      const l = Store.learner;
      let concepts = [];
      try { concepts = JSON.parse(btn.dataset.concepts || "[]"); } catch (_) { /* ignore */ }
      try {
        const lesson = await API.microLesson(l.learner_id, btn.dataset.skill, concepts);
        Store.microLesson = lesson;
        Store.assessmentResult = null;
        await navigate("assessments");
        const view = document.getElementById("view");
        const box = document.createElement("div");
        box.innerHTML = "";
        view.querySelector(".scene").insertAdjacentHTML("afterbegin", this.lessonHtml(lesson));
        Motion.observeReveals(view.querySelector(".scene"));
      } catch (err) { UI.toast(err.message, 4000); }
    },
    lessonHtml(lesson) {
      const res = (lesson.resources || []).map((r) => `<a class="tag" style="text-decoration:none;color:var(--brand-2)" href="${UI.esc(r.url)}" target="_blank" rel="noopener">${UI.esc(r.title)} · ${r.minutes}min ↗</a>`).join("");
      return `<div class="glass reveal" style="padding:22px;margin:18px 0">
        <div class="card-title">⚡ ${UI.esc(lesson.title)}</div>
        <div class="card-sub" style="margin-top:6px">${UI.esc(lesson.summary || "")}</div>
        <div style="margin-top:12px"><b style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:var(--ink-dim)">Key concepts</b><div style="margin-top:6px">${(lesson.key_concepts || []).map((c) => UI.chip(UI.esc(c))).join("")}</div></div>
        <div style="margin-top:12px"><b style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:var(--ink-dim)">Exercise</b><div class="card-sub" style="margin-top:4px">${UI.esc(lesson.exercise || "")}</div></div>
        ${res ? `<div style="margin-top:12px">${res}</div>` : ""}
        <span class="tag" style="margin-top:12px">${UI.esc(lesson.source || "local knowledge base")}</span>
      </div>`;
    },

    /* --- dashboard --- */
    async sessionMissed() {
      const l = Store.learner;
      try {
        await API.sessionMissed(l.learner_id);
        UI.toast("Session logged — weekend hours rebalanced.");
        await refreshLearner();
        await navigate("dashboard");
      } catch (err) { UI.toast(err.message, 4000); }
    },

    /* --- career --- */
    whatif(btn) {
      if (App.actions.whatifRender) App.actions.whatifRender();
    },

    /* --- settings --- */
    async saveProfile() {
      const l = Store.learner;
      const profile = {
        goal_text: (document.getElementById("s-goal") || {}).value,
        target_role: (document.getElementById("s-role") || {}).value,
        experience_level: document.querySelector('[data-group="exp"].active') ? document.querySelector('[data-group="exp"].active').dataset.value : l.experience_level,
        weekly_hours: parseFloat((document.getElementById("s-hours") || {}).value) || 8,
        deadline_weeks: parseInt((document.getElementById("s-weeks") || {}).value, 10) || 26,
        preferences: Array.from(document.querySelectorAll('[data-group="prefs"].active')).map((b) => b.dataset.value),
        skills: {},
      };
      document.querySelectorAll("[data-skill-slider]").forEach((s) => {
        profile.skills[s.dataset.skillSlider] = parseFloat(s.value) / 100;
      });
      try {
        const learner = await API.updateLearner(l.learner_id, profile);
        Store.learner = learner;
        Store.roadmap = null;
        Store.recs = null;
        UI.toast("Profile saved — recomputing your journey.");
        const roadmap = await API.generateRoadmap(l.learner_id, "balanced");
        Store.roadmap = roadmap;
        renderLearnerChip();
        await navigate("settings");
      } catch (err) { UI.toast(err.message, 4000); }
    },

    /* --- auth --- */
    async guestDemo() {
      try {
        const res = await API.guest();
        Store.token = res.token;
        Store.user = res.user;
        Store.guest = true;
        // fresh guest session — drop any leftover learner
        Store.learnerId = null;
        Store.learner = null;
        Store.roadmap = null;
        Store.chat = [];
        Store.recs = null;
        buildNav();
        renderLearnerChip();
        UI.toast("Guest mode — explore a persona below. ✨");
        await navigate("onboarding");
      } catch (err) {
        UI.toast(err.message, 4000);
      }
    },
    async signup() {
      const name = (document.getElementById("su-name") || {}).value || "";
      const email = (document.getElementById("su-email") || {}).value || "";
      const password = (document.getElementById("su-pass") || {}).value || "";
      const errBox = document.getElementById("su-error");
      try {
        const res = await API.signup(name.trim(), email.trim(), password);
        Store.token = res.token;
        Store.user = res.user;
        Store.guest = false;
        // a fresh account starts clean — drop any leftover demo learner
        Store.learnerId = null;
        Store.learner = null;
        Store.roadmap = null;
        Store.chat = [];
        Store.recs = null;
        buildNav();
        renderLearnerChip();
        UI.toast(`Welcome aboard, ${res.user.name.split(" ")[0]}! ✨`);
        await navigate("onboarding");
      } catch (err) {
        if (errBox) { errBox.hidden = false; errBox.textContent = err.message; }
      }
    },
    async signin() {
      const email = (document.getElementById("si-email") || {}).value || "";
      const password = (document.getElementById("si-pass") || {}).value || "";
      const errBox = document.getElementById("si-error");
      try {
        const res = await API.signin(email.trim(), password);
        Store.token = res.token;
        Store.user = res.user;
        await loadLearner();
        buildNav();
        renderLearnerChip();
        UI.toast(`Welcome back, ${res.user.name.split(" ")[0]}!`);
        await navigate(Store.learner ? (Store.roadmap ? "dashboard" : "journey") : "onboarding");
      } catch (err) {
        if (errBox) { errBox.hidden = false; errBox.textContent = err.message; }
      }
    },
    async signout() {
      await API.signout();
      Store.token = null;
      Store.user = null;
      Store.guest = false;
      Store.learnerId = null;
      Store.learner = null;
      Store.roadmap = null;
      Store.chat = [];
      Store.recs = null;
      buildNav();
      renderLearnerChip();
      UI.toast("Signed out. See you soon!");
      await navigate("landing");
    },

    /* --- global --- */
    async newDemo() {
      if (Store.learnerId) {
        try { await API.deleteLearner(Store.learnerId); } catch (_) { /* ignore */ }
      }
      Store.learnerId = null;
      Store.learner = null;
      Store.roadmap = null;
      Store.chat = [];
      Store.recs = null;
      Store.analysis = null;
      Store.assessmentActive = null;
      Store.assessmentResult = null;
      Store.lastGoal = "";
      renderLearnerChip();
      buildNav();
      await navigate("onboarding");
    },

    async toggleMenu() {
      document.getElementById("topnav").classList.toggle("open");
    },
  };

  /* ---------------------------------------------------------------
     EVENT DELEGATION
     --------------------------------------------------------------- */
  function wireEvents() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn || btn.disabled) return;
      // data-action="assessment-submit" -> actions.assessmentSubmit
      const key = btn.dataset.action.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      const action = actions[key];
      if (action) action.call(actions, btn);
    });
    // mobile menu closes after choosing a destination
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-action='goto']")) {
        document.getElementById("topnav").classList.remove("open");
      }
    });
  }

  /* ---------------------------------------------------------------
     BOOT
     --------------------------------------------------------------- */
  async function boot() {
    Motion.startUniverse();
    Motion.startCursor();
    Motion.startMicroInteractions();
    wireEvents();
    try {
      Store.meta = await bootMeta();
    } catch (err) {
      console.error("meta failed:", err);
      document.getElementById("view").innerHTML = `<div class="scene"><div class="note" style="margin-top:40px">Could not reach the backend — is the server running?<br><span class="mono">${UI.esc(err.message)}</span></div></div>`;
      return;
    }
    document.getElementById("mode-pill").textContent = Store.meta.llm_mode === "openai" ? "openai provider" : "local engine · offline";
    // restore session
    if (Store.token) {
      try {
        const { user } = await API.me();
        Store.user = user;
        if (!Store.guest && user.email && user.email.endsWith("@local.demo")) Store.guest = true;
      } catch (_) {
        Store.token = null;
        Store.user = null;
        Store.learnerId = null;
        Store.guest = false;
      }
    }
    await refreshLearner();
    buildNav();
    let start = "landing";
    if (Store.authed) start = Store.learner ? (Store.roadmap ? "dashboard" : "journey") : "onboarding";
    await navigate(start);
  }

  return { boot, navigate, actions, refreshLearner, renderLearnerChip };
})();

document.addEventListener("DOMContentLoaded", () => App.boot());
