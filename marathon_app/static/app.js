"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MAGIC = "Magic Speed 5";

const state = { weekShown: null, openDay: null, current: "today" };

function localToday() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

async function api(path, opts = {}) {
  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch(`${path}${sep}today=${localToday()}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed");
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 2800);
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function fmtDate(iso, opts = { weekday: "short", day: "numeric", month: "short" }) {
  return new Date(iso + "T12:00:00").toLocaleDateString(undefined, opts);
}

/* ---------- workout rendering (shared by Today and Week) ---------- */

function stepLabel(s) {
  const amount = s.km ? `${+s.km.toFixed(2)} km` : `${s.sec >= 60 ? s.sec / 60 + " min" : s.sec + " s"}`;
  const names = { warmup: "Warm-up", cooldown: "Cool-down", recovery: "Jog recovery" };
  if (names[s.type]) return `${names[s.type]} ${amount}`;
  if (s.zone === "R") return `Stride ${amount}`;
  if (!s.zone) return `${amount} hard effort`;
  return `${amount} ${s.zone_name || ""}`.trim();
}

function renderSteps(steps) {
  return `<ul class="steps">${steps.map((s) => s.type === "repeat"
    ? `<li class="repeat"><div class="rep-head">Repeat ${s.reps}×</div><ul>${s.steps.map(stepLi).join("")}</ul></li>`
    : stepLi(s)).join("")}</ul>`;
}

function stepLi(s) {
  const pace = s.pace ? s.pace : s.zone === "R" ? "fast, relaxed" : s.type === "recovery" ? "easy jog" : !s.zone ? "all out" : "";
  return `<li><span>${esc(stepLabel(s))}</span><span class="pace">${esc(pace)}</span></li>`;
}

function shoeChip(shoe) {
  if (!shoe) return "";
  return `<span class="chip ${shoe === MAGIC ? "fast" : ""}"><span class="dot"></span>${esc(shoe)}</span>`;
}

function statusChip(w) {
  const map = { done: ["✓ Done", "status-done"], partial: ["½ Partial", ""], missed: ["✕ Missed", "status-missed"] };
  const s = w.state === "missed" ? "missed" : w.status;
  return map[s] ? `<span class="chip ${map[s][1]}">${map[s][0]}</span>` : "";
}

function workoutCard(w, { hero = false, garmin = false } = {}) {
  if (w.kind === "rest") {
    return `<div class="card"><h2>Rest day</h2><p class="muted">${esc(w.notes || "Recover well.")}</p></div>`;
  }
  const isTest = w.test_distance_km && w.kind !== "race";
  return `
  <div class="card ${hero ? "hero" : ""}" data-date="${w.date}">
    <div class="row between wrap">
      <span class="eyebrow">${esc(w.kind === "quality" ? "Workout" : w.kind)} · ${fmtDate(w.date)}</span>
      ${statusChip(w)}
    </div>
    <h2 style="margin-top:6px">${esc(w.title)}</h2>
    <div class="row between" style="margin-top:8px">
      <div class="big-km">${w.planned_km}<small> km</small></div>
      ${shoeChip(w.shoe)}
    </div>
    ${w.notes ? `<p class="muted small">${esc(w.notes)}</p>` : ""}
    ${renderSteps(w.steps)}
    <div class="btn-row">
      <button class="btn ${w.status === "done" ? "selected primary" : ""}" data-act="done">✓ Done</button>
      <button class="btn ${w.status === "partial" ? "selected" : ""}" data-act="partial">½ Partial</button>
      <button class="btn ${w.status === "skipped" ? "selected" : ""}" data-act="skipped">✕ Skip</button>
    </div>
    <details ${isTest && w.status !== "done" ? "open" : ""}>
      <summary>${isTest ? "Log your test result" : "Add details"}</summary>
      <form class="log">
        ${isTest ? `<label class="full">Test result (${w.test_distance_km} km time, h:mm:ss)
          <input name="test_time" inputmode="numeric" placeholder="${w.test_distance_km > 10 ? "2:20:00" : "28:30"}"></label>` : ""}
        <label>Distance (km)<input name="actual_km" type="number" step="0.01" inputmode="decimal" value="${w.actual_km ?? ""}"></label>
        <label>Total time<input name="actual_time" inputmode="numeric" placeholder="1:05:00"></label>
        <label>Effort (1–10)<input name="rpe" type="number" min="1" max="10" inputmode="numeric" value="${w.rpe ?? ""}"></label>
        <label>Note<input name="comment" value="${esc(w.comment ?? "")}"></label>
        <button class="btn primary full" style="grid-column:1/-1" data-act="save">Save as done</button>
      </form>
    </details>
    ${garmin && w.state !== "missed" && !["done", "partial"].includes(w.status) ? `
      <button class="btn block" data-act="garmin">${w.garmin_workout_id ? "↻ Re-send to watch" : "⌚ Send to watch"}</button>` : ""}
  </div>`;
}

function bindWorkoutCard(root, onChange) {
  root.querySelectorAll(".card[data-date]").forEach((card) => {
    const day = card.dataset.date;
    card.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      e.preventDefault();
      const act = btn.dataset.act;
      try {
        if (act === "garmin") {
          btn.disabled = true;
          btn.textContent = "Sending…";
          await api("/api/garmin/push", { method: "POST", body: JSON.stringify({ date: day }) });
          toast("Sent to Garmin — sync your watch");
        } else if (act === "save") {
          const f = new FormData(card.querySelector("form"));
          const body = { status: "done" };
          for (const [k, v] of f.entries()) if (v !== "") body[k] = k === "actual_km" || k === "rpe" ? Number(v) : v;
          await api(`/api/workouts/${day}/log`, { method: "POST", body: JSON.stringify(body) });
          toast(body.test_time ? "Result saved — paces updated" : "Saved");
        } else {
          const current = card.querySelector(`[data-act="${act}"]`).classList.contains("selected");
          const status = current ? "planned" : act;
          await api(`/api/workouts/${day}/log`, { method: "POST", body: JSON.stringify({ status }) });
          toast(status === "done" ? "Nice work! 🔥" : status === "planned" ? "Cleared" : "Logged");
        }
        onChange();
      } catch (err) {
        toast(err.message);
        btn.disabled = false;
        if (act === "garmin") btn.textContent = "⌚ Send to watch";
      }
    });
  });
}

/* ---------- Today ---------- */

async function renderToday() {
  const d = await api("/api/dashboard");
  $("#topWeek").textContent = `Week ${d.week} of 26 · ${d.days_to_race} days to race`;
  $("#topTitle").textContent = fmtDate(d.today, { weekday: "long", day: "numeric", month: "long" });
  $("#streakPill span").textContent = d.streaks.current_days;

  const el = $("#view-today");
  if (!d.workout) {
    el.innerHTML = `<div class="card"><h2>No workout today</h2><p class="muted">Your plan runs from week 1 to race day.</p></div>`;
    return;
  }
  el.innerHTML = `
    ${workoutCard(d.workout, { hero: true, garmin: d.garmin_configured })}
    ${d.tomorrow ? `<div class="card"><div class="eyebrow">Tomorrow</div>
      <div class="row between" style="margin-top:4px"><h3>${esc(d.tomorrow.title)}</h3>
      <span class="muted small">${d.tomorrow.planned_km ? d.tomorrow.planned_km + " km" : ""}</span></div>
      ${d.tomorrow.shoe ? `<div style="margin-top:8px">${shoeChip(d.tomorrow.shoe)}</div>` : ""}</div>` : ""}
    <div class="stats">
      <div class="stat"><div class="v">${d.streaks.runs_done}/${d.streaks.runs_due}</div><div class="l">Runs completed</div></div>
      <div class="stat"><div class="v">${d.predicted_marathon}</div><div class="l">Predicted marathon</div></div>
    </div>`;
  bindWorkoutCard(el, refresh);
}

/* ---------- Week ---------- */

async function renderWeek() {
  const q = state.weekShown ? `?week=${state.weekShown}` : "";
  const d = await api(`/api/week${q}`);
  state.weekShown = d.week;
  const today = localToday();
  const dash = await api("/api/dashboard");
  const pct = d.planned_km ? Math.min(100, (d.done_km / d.planned_km) * 100) : 0;

  const el = $("#view-week");
  el.innerHTML = `
    <div class="week-nav">
      <button class="btn" data-nav="-1" ${d.week <= 1 ? "disabled" : ""} aria-label="Previous week">‹</button>
      <div style="text-align:center"><h2>Week ${d.week}</h2><div class="muted small">${esc(d.phase)}</div></div>
      <button class="btn" data-nav="1" ${d.week >= 26 ? "disabled" : ""} aria-label="Next week">›</button>
    </div>
    <div class="card">
      <div class="row between small"><span>${d.done_km} of ${d.planned_km} km</span><span class="muted">${Math.round(d.completion * 100)}% of runs</span></div>
      <div class="bar" style="margin-top:8px"><span style="width:${pct}%"></span></div>
    </div>
    <div class="card" style="padding:4px 16px">
      ${d.workouts.map((w, i) => {
        const icon = { done: "✓", partial: "½", missed: "✕" }[w.state] || (w.kind === "rest" ? "" : "○");
        const open = state.openDay === w.date;
        return `
        <div class="day ${w.kind === "rest" ? "rest" : ""} ${w.date === today ? "is-today" : ""}" data-day="${w.date}">
          <div class="dow"><span>${DOW[i]}</span><b>${new Date(w.date + "T12:00:00").getDate()}</b></div>
          <div class="info"><div class="t">${esc(w.title)}</div>
            ${w.shoe ? `<div class="muted small">${esc(w.shoe)}</div>` : ""}</div>
          <div class="km">${w.planned_km ? w.planned_km + " km" : ""}</div>
          <div class="state-icon ${w.state}">${icon}</div>
        </div>
        ${open && w.kind !== "rest" ? `<div class="day-detail">${workoutCard(w, { garmin: dash.garmin_configured })}</div>` : ""}`;
      }).join("")}
    </div>
    ${dash.garmin_configured ? `<button class="btn primary block" id="pushWeek">⌚ Send this week to watch</button>` : ""}`;

  el.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => {
    state.weekShown += Number(b.dataset.nav);
    state.openDay = null;
    renderWeek().catch((e) => toast(e.message));
  }));
  el.querySelectorAll(".day").forEach((row) => row.addEventListener("click", () => {
    state.openDay = state.openDay === row.dataset.day ? null : row.dataset.day;
    renderWeek().catch((e) => toast(e.message));
  }));
  const pw = $("#pushWeek", el);
  if (pw) pw.addEventListener("click", async () => {
    pw.disabled = true;
    pw.textContent = "Sending…";
    try {
      const r = await api("/api/garmin/push", { method: "POST", body: JSON.stringify({ week: d.week }) });
      toast(`Sent ${r.pushed.length} workouts — sync your watch`);
    } catch (e) { toast(e.message); }
    renderWeek();
  });
  bindWorkoutCard(el, refresh);
}

/* ---------- Streaks / heatmap ---------- */

const STATE_LABEL = { done: "Done", partial: "Partial", rest: "Rest day", missed: "Missed", today: "Today — pending", future: "Upcoming" };

async function renderStreaks() {
  const d = await api("/api/heatmap");
  const s = d.streaks;
  const el = $("#view-streaks");
  el.innerHTML = `
    <div class="stats">
      <div class="stat"><div class="v">🔥 ${s.current_days}</div><div class="l">Current streak (days)</div></div>
      <div class="stat"><div class="v">${s.longest_days}</div><div class="l">Longest streak (days)</div></div>
      <div class="stat"><div class="v">${s.perfect_weeks}</div><div class="l">Perfect weeks in a row</div></div>
      <div class="stat"><div class="v">${s.runs_due ? Math.round((s.runs_done / s.runs_due) * 100) : 100}%</div><div class="l">Runs completed</div></div>
    </div>
    <div class="card">
      <h3 style="margin-bottom:10px">Training heatmap · 26 weeks</h3>
      <div class="hm-weeks">${Array.from({ length: 26 }, (_, i) => `<span>${(i + 1) % 4 === 1 ? i + 1 : ""}</span>`).join("")}</div>
      <div class="heatmap">
        <div class="hm-days">${DOW.map((n, i) => `<span>${i % 2 === 0 ? n[0] : ""}</span>`).join("")}</div>
        <div class="hm-grid" role="grid" aria-label="Workout completion heatmap">
          ${d.days.map((c, i) => `<button class="hm-cell ${c.state}" data-i="${i}"
              aria-label="${fmtDate(c.date)}: ${esc(c.title)} — ${STATE_LABEL[c.state]}"></button>`).join("")}
        </div>
      </div>
      <div class="legend">
        <span><i style="background:var(--hm-done)"></i>Done</span>
        <span><i style="background:var(--hm-partial)"></i>Partial</span>
        <span><i style="background:var(--hm-rest)"></i>Rest</span>
        <span><i style="box-shadow:inset 0 0 0 1.5px var(--critical)"></i>Missed</span>
        <span><i style="box-shadow:inset 0 0 0 1px var(--border)"></i>Upcoming</span>
      </div>
      <div class="hm-tip muted" id="hmTip">Tap a square to see that day. Rest days keep your streak alive.</div>
    </div>`;

  el.querySelectorAll(".hm-cell").forEach((cell) => cell.addEventListener("click", () => {
    el.querySelectorAll(".hm-cell.sel").forEach((c) => c.classList.remove("sel"));
    cell.classList.add("sel");
    const c = d.days[cell.dataset.i];
    $("#hmTip").innerHTML = `<b>${fmtDate(c.date)}</b> · Week ${c.week}<br>${esc(c.title)}${c.km ? ` · ${c.km} km` : ""} — <b>${STATE_LABEL[c.state]}</b>`;
  }));
}

/* ---------- Progress ---------- */

async function renderProgress() {
  const d = await api("/api/progress");
  const el = $("#view-progress");
  el.innerHTML = `
    <div class="card hero">
      <div class="eyebrow">Predicted marathon today</div>
      <div class="hero-time">${d.predicted_marathon}</div>
      <div class="muted small">Half marathon equivalent ${d.predicted_half} · fitness (VDOT) ${d.vdot}</div>
      <div class="goal-bar" aria-label="Progress toward goal"><span style="width:${Math.min(100, d.goal_progress * 100)}%"></span></div>
      <div class="row between small"><span class="muted">Start</span><span><b>${Math.round(d.goal_progress * 100)}%</b> of the way to <b>${d.goal}</b> (VDOT ${d.goal_vdot})</span></div>
      <p class="small muted" style="margin-bottom:0">
        ${d.bonus > 0 ? `Your paces are <b>+${d.bonus} VDOT</b> faster than your last test because you kept up with training. ` : ""}
        ${d.next_bonus_in ? `Complete ${d.next_bonus_in} more full week${d.next_bonus_in > 1 ? "s" : ""} (90%+ of runs) to speed your paces up again.` : "Maximum consistency bonus reached — your next test sets new paces."}
      </p>
    </div>

    <div class="card">
      <h3>Your training paces</h3>
      <table style="margin-top:8px"><thead><tr><th>Zone</th><th>Pace /km</th></tr></thead><tbody>
        ${d.zones.map((z) => `<tr><td>${z.name}</td><td>${z.fast} – ${z.slow}</td></tr>`).join("")}
      </tbody></table>
    </div>

    <div class="card">
      <h3>Shoes</h3>
      ${d.shoes.map((s) => `
        <div style="margin-top:12px">
          <div class="row between small"><span>${shoeChip(s.name)}</span><span class="muted">${s.km} / ${s.retire_km} km</span></div>
          <div class="bar" style="margin-top:6px"><span style="width:${Math.min(100, (s.km / s.retire_km) * 100)}%;${s.name === MAGIC ? "background:var(--shoe-fast)" : ""}"></span></div>
        </div>`).join("")}
    </div>

    <div class="card">
      <h3>Race &amp; test results</h3>
      <table style="margin-top:8px"><thead><tr><th>Date</th><th>Distance</th><th>Time</th><th>VDOT</th></tr></thead><tbody>
        ${d.tests.map((t) => `<tr><td>${fmtDate(t.date, { day: "numeric", month: "short" })}</td><td>${+t.distance_km.toFixed(2)} km</td><td>${t.time}</td><td>${t.vdot}</td></tr>`).join("")}
      </tbody></table>
      <details><summary>Add a race result</summary>
        <form class="inline" id="fitForm" style="margin-top:10px">
          <label>Distance<select name="distance_km">
            <option value="5">5K</option><option value="10">10K</option>
            <option value="21.0975">Half</option><option value="42.195">Marathon</option></select></label>
          <label>Time<input name="time" placeholder="28:30" inputmode="numeric" required></label>
          <button class="btn primary">Add</button>
        </form>
      </details>
    </div>`;

  $("#fitForm", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api("/api/fitness", { method: "POST", body: JSON.stringify({
        date: localToday(), distance_km: Number(f.get("distance_km")), time: f.get("time") }) });
      toast("Result added — paces updated");
      renderProgress();
    } catch (err) { toast(err.message); }
  });
}

/* ---------- shell ---------- */

const RENDER = { today: renderToday, week: renderWeek, streaks: renderStreaks, progress: renderProgress };

function show(view) {
  state.current = view;
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  RENDER[view]().catch((e) => toast(e.message));
}

function refresh() {
  RENDER[state.current]().catch((e) => toast(e.message));
  if (state.current !== "today") api("/api/dashboard").then((d) => { $("#streakPill span").textContent = d.streaks.current_days; });
}

document.querySelectorAll(".tabbar button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
show("today");
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
