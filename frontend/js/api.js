/* LearnPath AI — API client + client state */
"use strict";

const Store = {
  learner: null,        // current learner twin (cached)
  roadmap: null,        // current roadmap
  meta: null,           // catalogue meta
  chat: [],             // coach history
  user: null,           // signed-in user {user_id, name, email}
  page: "landing",
  get learnerId() { return localStorage.getItem("lp_learner_id"); },
  set learnerId(v) { v ? localStorage.setItem("lp_learner_id", v) : localStorage.removeItem("lp_learner_id"); },
  get token() { return localStorage.getItem("lp_token"); },
  set token(v) { v ? localStorage.setItem("lp_token", v) : localStorage.removeItem("lp_token"); },
  get guest() { return localStorage.getItem("lp_guest") === "1"; },
  set guest(v) { v ? localStorage.setItem("lp_guest", "1") : localStorage.removeItem("lp_guest"); },
  get authed() { return !!this.token && !!this.user; },
};

const API = {
  async request(method, path, body, auth = true) {
    const headers = { "Content-Type": "application/json" };
    if (auth && Store.token) headers["Authorization"] = `Bearer ${Store.token}`;
    const opts = { method, headers };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty */ }
    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  },
  get(path, auth = true) { return this.request("GET", path, undefined, auth); },
  post(path, body, auth = true) { return this.request("POST", path, body, auth); },
  put(path, body, auth = true) { return this.request("PUT", path, body, auth); },
  del(path, auth = true) { return this.request("DELETE", path, undefined, auth); },
  // no-auth shortcuts (signup/signin must work without a token)
  postAnon(path, body) { return this.request("POST", path, body, false); },

  // ----- auth -----
  signup(name, email, password) { return this.postAnon("/api/auth/signup", { name, email, password }); },
  signin(email, password) { return this.postAnon("/api/auth/signin", { email, password }); },
  guest() { return this.postAnon("/api/auth/guest", {}); },
  signout() { return this.post("/api/auth/signout", {}).catch(() => null); },
  me() { return this.get("/api/auth/me"); },

  // ----- typed endpoints -----
  meta() { return this.get("/api/meta"); },
  analyze(text) { return this.post("/api/profile/analyze", { text }); },
  createLearner(payload) { return this.post("/api/learners", payload); },
  listLearners() { return this.get("/api/learners"); },
  learner(id) { return this.get(`/api/learners/${id}`); },
  updateLearner(id, payload) { return this.put(`/api/learners/${id}`, payload); },
  deleteLearner(id) { return this.del(`/api/learners/${id}`); },
  generateRoadmap(id, mode) { return this.post(`/api/learners/${id}/roadmap`, { mode }); },
  roadmap(id) { return this.get(`/api/learners/${id}/roadmap`); },
  recommend(id, k) { return this.post(`/api/learners/${id}/recommendations`, { k }); },
  completeItem(id, itemType, itemId) { return this.post(`/api/learners/${id}/items/complete`, { item_type: itemType, item_id: itemId }); },
  feedback(id, itemId, itemType, signal) { return this.post(`/api/learners/${id}/feedback`, { item_id: itemId, item_type: itemType, signal }); },
  skills(id) { return this.get(`/api/learners/${id}/skills`); },
  assessment(id) { return this.get(`/api/assessments/${id}`); },
  submitAssessment(id, assessmentId, answers) { return this.post(`/api/learners/${id}/assessments/${assessmentId}/submit`, { answers }); },
  microLesson(id, skillId, weakConcepts) { return this.post(`/api/learners/${id}/micro-lesson`, { skill_id: skillId, weak_concepts: weakConcepts }); },
  project(id, skillId) { return this.post(`/api/learners/${id}/project`, { skill_id: skillId }); },
  coach(id, message) { return this.post(`/api/learners/${id}/coach`, { message }); },
  mission(id) { return this.get(`/api/learners/${id}/mission`); },
  career(id) { return this.get(`/api/learners/${id}/career`); },
  whatIf(id, newRole) { return this.post(`/api/learners/${id}/whatif`, { new_role: newRole }); },

  // ----- gamification (LearnPath XP) -----
  gamification(id) { return this.get(`/api/learners/${id}/gamification`); },
  xpHistory(id) { return this.get(`/api/learners/${id}/xp-history`); },
  badges(id) { return this.get(`/api/learners/${id}/badges`); },
  streak(id) { return this.get(`/api/learners/${id}/streak`); },
  leaderboard(id, scope) { return this.get(`/api/leaderboard?learner_id=${id}&scope=${scope}`); },
  challenges(id) { return this.get(`/api/challenges/current?learner_id=${id}`); },
  claimChallenge(learnerId, challengeId) { return this.post(`/api/challenges/${challengeId}/claim`, { learner_id: learnerId }); },
  completeMission(id) { return this.post(`/api/learners/${id}/mission/complete`, {}); },
  setLeaderboardOptOut(id, optOut) { return this.put(`/api/learners/${id}/settings/leaderboard-opt-out`, { opt_out: optOut }); },
  analytics(id) { return this.get(`/api/learners/${id}/analytics`); },
  insights(id) { return this.get(`/api/learners/${id}/insights`); },
  sessionMissed(id) { return this.post(`/api/learners/${id}/session-missed`, {}); },
};

async function bootMeta() {
  if (!Store.meta) Store.meta = await API.meta();
  return Store.meta;
}

async function loadLearner() {
  if (!Store.learnerId) { Store.learner = null; return null; }
  try {
    Store.learner = await API.learner(Store.learnerId);
    const r = await API.roadmap(Store.learnerId);
    Store.roadmap = r.generated ? r : null;
    return Store.learner;
  } catch (e) {
    Store.learnerId = null; Store.learner = null; Store.roadmap = null;
    return null;
  }
}
