/* LearnPath AI — application shell: router, page grid, action dispatch, boot. */
"use strict";

/* Pages that appear as buttons in the page grid (after learner exists). */
const GRID_PAGES = [
  { key: "journey",         icon: "🗺️", label: "My Journey",         desc: "Your personalized roadmap — phase by phase, prerequisite-first." },
  { key: "skills",          icon: "⚡", label: "Skill Intelligence",  desc: "Gaps, radar chart, heatmap and before/after proficiency bars." },
  { key: "recommendations", icon: "🎯", label: "Recommendations",     desc: "Courses, projects & checks ranked across 8 explainable factors." },
  { key: "coach",           icon: "💬", label: "AI Coach",            desc: "Ask anything — grounded in your profile, roadmap and gaps." },
  { key: "assessments",     icon: "🧠", label: "Assessments",         desc: "Knowledge checks that power adaptive remediation." },
  { key: "dashboard",       icon: "📊", label: "Dashboard",           desc: "Today's mission, weekly planner, progress and analytics." },
  { key: "career",          icon: "🚀", label: "Career Readiness",    desc: "Readiness index, dimension bars and what-if simulator." },
  { key: "achievements",    icon: "🏅", label: "Achievements",        desc: "XP, level, badges, streaks and weekly challenges." },
  { key: "leaderboard",     icon: "🏆", label: "Leaderboard",         desc: "Compare XP, mastery and progress against the cohort." },
  { key: "settings",        icon: "⚙️", label: "Settings",            desc: "Profile, preferences, skill sliders and system insights." },
];
const AUTH_PAGES = ["onboarding", ...GRID_PAGES.map(g => g.key)];

/* Empty-state copy per learner-gated page — shown when no learner exists yet. */
const EMPTY_STATE = {
  journey:        { icon: "🗺️", title: "No journey yet",          msg: "Your personalized roadmap will appear here once we know your goal, skills and time budget. It's planned phase-by-phase, prerequisite-first." },
  skills:         { icon: "⚡", title: "No skill profile yet",    msg: "Skill gaps, the competency radar and the heatmap are computed from your goal and your current skills — nothing is guessed." },
  recommendations:{ icon: "🎯", title: "No recommendations yet",  msg: "Courses, projects and knowledge checks are ranked against your skill gaps across 8 explainable factors. Build a profile to unlock them." },
  coach:          { icon: "💬", title: "No coach yet",            msg: "Your AI coach answers from your actual profile, roadmap and gaps. Create a learner first so it knows who it's advising." },
  assessments:    { icon: "🧠", title: "No assessments yet",      msg: "Knowledge checks unlock once your roadmap exists — they power the adaptive remediation that keeps your path on track." },
  dashboard:      { icon: "📊", title: "No dashboard yet",        msg: "Progress, today's mission, weekly planning and live analytics light up after you create your learner digital twin." },
  career:         { icon: "🚀", title: "No career data yet",      msg: "The readiness gauge, dimension bars and what-if simulator need your goal and skills to measure anything." },
  achievements:   { icon: "🏅", title: "No achievements yet",     msg: "Your XP, level, badges and streaks live here — they start accruing the moment you complete your first learning activity." },
  leaderboard:    { icon: "🏆", title: "No leaderboard yet",     msg: "Compare your XP, weekly progress and skill mastery against the cohort. Create a learner to join the board." },
  settings:       { icon: "⚙️", title: "No profile yet",          msg: "Fine-tune your digital twin here — skill confidence sliders, preference weights and system insights." },
};

const App = (() => {
  let viewRoot = null;

  /* ---------------------------------------------------------------
     PAGE GRID
     --------------------------------------------------------------- */
  function renderPageGrid() {
    const view = document.getElementById("view");
    const pageKey = Store.page;
    view.innerHTML = `
      <div class="page-grid-header">
        <h2>Navigate your journey</h2>
        <p>Pick a section to explore — every page is one click away.</p>
      </div>
      <div class="page-grid" data-stagger stagger-delay="70">
        ${GRID_PAGES.map(g => `
          <button class="page-card${pageKey === g.key ? " active-card" : ""}" data-action="goto" data-page="${g.key}" data-magnetic data-tilt>
            <div class="page-card-icon">${g.icon}</div>
            <div class="page-card-label">${g.label}</div>
            <div class="page-card-desc">${g.desc}</div>
          </button>
        `).join("")}
      </div>
    `;
    viewRoot = view;
    Motion.observeReveals(viewRoot);
    Motion.animatePageGrid(view);
  }

  function updatePageTitle() {
    const p = Pages[Store.page];
    document.title = `${p ? p.nav.label : "Home"} · LearnPath AI`;
  }

  /* ---------------------------------------------------------------
     NAVIGATION
     --------------------------------------------------------------- */
  async function navigate(page) {
    let target = Pages[page] ? page : "landing";
    // auth gate: app pages require a signed-in user
    if (!Store.authed && AUTH_PAGES.includes(target)) { target = "landing"; }
    if (Store.authed && (target === "signin" || target === "signup")) { target = "landing"; }
    const needsLearner = Pages[target].gate && !Store.learner;
    Store.page = target;
    if (target === "onboarding") Store.recFilter = null;

    await Motion.playCurtain();
    updatePageTitle();

    const view = document.getElementById("view");

    // If the user has a learner and hits "home" (landing), show the page grid instead
    if (target === "landing" && Store.authed && Store.learner && Store.roadmap) {
      renderPageGrid();
      return;
    }

    view.innerHTML = UI.skeletons(3);
    try {
      let html;
      if (needsLearner) {
        // learner-gated page with no learner yet → show a guided empty state
        const es = EMPTY_STATE[target] || EMPTY_STATE.dashboard;
        html = UI.emptyState({
          icon: es.icon, title: es.title, msg: es.msg,
          ctas: [
            { label: "Create my learning journey →", page: "onboarding", primary: true },
            { label: "⚡ Try a demo persona", action: "guest-demo" },
          ],
        });
      } else {
        html = await Pages[target].render();
      }
      // Prepend a "back to grid" button for app pages (not landing, onboarding, signin, signup)
      const showBack = Store.authed && Store.learner && Store.roadmap
        && !["landing", "onboarding", "signin", "signup"].includes(target);
      const backBtn = showBack
        ? `<button class="back-to-grid" data-action="goto" data-page="landing">← Back to all pages</button>`
        : "";
      viewRoot = UI.setView(backBtn + html);
      Motion.observeReveals(viewRoot);
      Motion.animateBars(viewRoot);
      if (!needsLearner && Pages[target].mount) Pages[target].mount(viewRoot);
    } catch (err) {
      console.error("render error:", err);
      view.innerHTML = `<div class="scene"><div class="note" style="margin-top:40px">Something went wrong: ${UI.esc(err.message)}<br><button class="btn btn-ghost btn-sm" style="margin-top:10px" data-action="goto" data-page="landing">← Back to all pages</button></div></div>`;
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
        await navigate("landing");
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
        await navigate("landing");
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
        const res = await API.completeItem(l.learner_id, btn.dataset.type, btn.dataset.id);
        if (res.xp) UI.xpFX(res.xp, btn);
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
        const res = await API.feedback(l.learner_id, btn.dataset.id, btn.dataset.type, "complete");
        if (res.xp) UI.xpFX(res.xp, btn);
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
        if (result.xp) {
          if (result.xp.xp_awarded > 0) UI.xpFloat(result.xp.xp_awarded, btn);
          (result.xp.new_badges || []).forEach(UI.badgeToast);
          if (result.xp.level_up) UI.levelUp(result.xp.level_up);
          if (result.xp.streak_milestone) UI.toast(`🔥 ${result.xp.streak_milestone}-day streak milestone!`);
        }
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

    /* --- leaderboard privacy --- */
    async toggleLeaderboardOptOut(btn) {
      const l = Store.learner;
      if (!l) return;
      const checkbox = document.getElementById("opt-out-toggle");
      if (!checkbox) return;
      const optOut = checkbox.checked;
      try {
        await API.setLeaderboardOptOut(l.learner_id, optOut);
        if (Store.gamification) {
          Store.gamification.leaderboard_opt_out = optOut ? 1 : 0;
        }
        UI.toast(optOut ? "Hidden from leaderboards" : "Visible on leaderboards");
      } catch (err) {
        checkbox.checked = !optOut;
        UI.toast(err.message, 4000);
      }
    },

    /* --- gamification --- */
    async lbScope(btn) {
      Store.leaderboardScope = btn.dataset.value;
      await navigate("leaderboard");
    },
    async claimChallenge(btn) {
      const l = Store.learner;
      if (!l) return;
      try {
        const res = await API.claimChallenge(l.learner_id, btn.dataset.id);
        if (res.ok) {
          UI.toast("Challenge reward claimed — +" + res.xp_awarded + " XP 🎉");
          await navigate("achievements");
        } else {
          UI.toast(res.error || "Cannot claim yet");
        }
      } catch (err) { UI.toast(err.message, 4000); }
    },
    async completeMission() {
      const l = Store.learner;
      if (!l) return;
      try {
        const res = await API.completeMission(l.learner_id);
        if (res.xp_awarded > 0) {
          UI.toast("Daily mission complete — +" + res.xp_awarded + " XP 🎯");
          if (res.level_up) UI.toast("🎉 Level up! You reached " + res.level_up.title + " — Level " + res.level_up.to);
        } else {
          UI.toast("Mission already claimed today — repeat completions earn 0 XP.");
        }
        await navigate("dashboard");
      } catch (err) { UI.toast(err.message, 4000); }
    },

    /* --- auth --- */
    async guestDemo() {
      try {
        const res = await API.guest();
        Store.token = res.token;
        Store.user = res.user;
        Store.guest = true;
        Store.learnerId = null;
        Store.learner = null;
        Store.roadmap = null;
        Store.chat = [];
        Store.recs = null;
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
        Store.learnerId = null;
        Store.learner = null;
        Store.roadmap = null;
        Store.chat = [];
        Store.recs = null;
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
      await navigate("onboarding");
    },

  };

  /* ---------------------------------------------------------------
     EVENT DELEGATION
     --------------------------------------------------------------- */
  function wireEvents() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn || btn.disabled) return;
      const key = btn.dataset.action.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      const action = actions[key];
      if (action) action.call(actions, btn);
    });
  }

  /* ---------------------------------------------------------------
     BOOT
     --------------------------------------------------------------- */
  async function boot() {
    Motion.startUniverse();
    Motion.startCursor();
    Motion.startMicroInteractions();
    Motion.startScrollParallax();
    wireEvents();
    try {
      Store.meta = await bootMeta();
    } catch (err) {
      console.error("meta failed:", err);
      document.getElementById("view").innerHTML = `<div class="scene"><div class="note" style="margin-top:40px">Could not reach the backend — is the server running?<br><span class="mono">${UI.esc(err.message)}</span></div></div>`;
      return;
    }
    // sync mode pill
    const pillText = (Store.meta && Store.meta.llm_mode === "openai") ? "openai provider" : "local engine · offline";
    const pill = document.getElementById("mode-pill");
    if (pill) pill.textContent = pillText;
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
    // Always start on the landing page — the page grid is accessed from there
    await navigate("landing");
  }

  return { boot, navigate, actions, refreshLearner, renderLearnerChip };
})();

document.addEventListener("DOMContentLoaded", () => App.boot());
