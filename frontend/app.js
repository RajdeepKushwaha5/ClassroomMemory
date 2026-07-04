/* Classroom Memory frontend, on the Track A design system.
   Graph sizing uses the fixes proven in Track A on 2026-07-01:
   autoResize:false, stabilization fit, absolute-fill CSS, fit({animation:false}). */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const state = {
  view: "app",
  student: "alice",
  offsetDays: 0,
  studentNet: null,
  teacherNet: null,
  question: null,
  teacherDrill: null,
  health: null,
  teacherHeatmap: null,
};

let activeMaximized = null;

const BAND_COLORS = {
  red: { background: "#5a1f1f", border: "#e04b4b" },
  amber: { background: "#4d3a17", border: "#f0b25a" },
  green: { background: "#20402a", border: "#7cc48c" },
  rusty: { background: "#3a2f1d", border: "#9a7c48" },
  retired: { background: "#1d1d19", border: "#55534b" },
};

/* balanced two-line label: "Variables & assignment" -> "Variables &\nassignment",
   never one word per line */
function wrapLabel(name) {
  const words = name.split(" ");
  if (words.length < 2 || name.length <= 12) return name;
  let best = name;
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(" ");
    const b = words.slice(i).join(" ");
    const d = Math.abs(a.length - b.length);
    if (d < bestDiff) { bestDiff = d; best = a + "\n" + b; }
  }
  return best;
}

function icons() {
  if (window.lucide) window.lucide.createIcons();
}

/* Never let one broken wiring block kill every other button. */
function safely(label, fn) {
  try {
    fn();
  } catch (err) {
    console.error(`[wire:${label}]`, err);
    const badge = $("#mode-badge");
    if (badge) badge.textContent = `ui error: ${label}`;
  }
}

/* Surface runtime errors instead of dying silently. */
window.addEventListener("error", (e) => {
  console.error("[runtime]", e.error || e.message);
});
window.addEventListener("unhandledrejection", (e) => {
  console.error("[promise]", e.reason);
});

const LIFECYCLE_EXPLAIN = {
  remember: ["remember()", "Seeds each student's Cognee Cloud dataset with the curriculum and writes a trace every time a concept is mastered."],
  recall: ["recall()", "Powers the ask box: answers come from this student's own cloud memory graph, with dataset provenance."],
  improve: ["improve semantics", "Every quiz answer re-weights concept mastery, following Cognee's feedback-weight design (app-side until Cloud exposes remote improve())."],
  forget: ["forget()", "Retiring a mastered concept and resetting a student are real deletions: forget(dataset) runs on the tenant."],
};

function viewFromHash() {
  if (location.hash === "#teacher") return "teacher";
  if (location.hash === "#about") return "about";
  return "app";
}

function fitVisibleGraphs() {
  window.requestAnimationFrame(() => {
    [state.studentNet, state.teacherNet].forEach((net) => {
      if (net && net.body) {
        net.redraw();
        net.fit({ animation: false });
      }
    });
  });
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let detail = `${path}: ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (err) {
      // Keep the status fallback.
    }
    throw new Error(detail);
  }
  return res.json();
}

/* ---------- lifecycle strip + log + kicker ---------- */

function lifecycle(step) {
  const el = $(`#life-${step}`);
  if (!el) return;
  el.classList.add("active");
  setTimeout(() => { if (step !== "remember") el.classList.remove("active"); }, 2600);
}

function log(html, cls = "") {
  const box = $("#session-log");
  const div = document.createElement("div");
  if (cls) div.className = cls;
  div.innerHTML = html;
  box.prepend(div);
  while (box.children.length > 14) box.removeChild(box.lastChild);
}

function kicker(k, r) {
  if (k) $("#case-kicker").textContent = k;
  if (r) $("#case-result").textContent = r;
}

/* ---------- graph rendering (shared, Track A centering fixes) ---------- */

function nodeStyle(n) {
  let key = n.band;
  if (n.retired) key = "retired";
  else if (n.rusty) key = "rusty";
  const c = BAND_COLORS[key];
  return {
    id: n.id,
    label: wrapLabel(n.name),
    title: `${n.name}: ${n.summary}\nmastery ${(n.weight * 100).toFixed(0)}%` +
      (n.rusty ? " (rusty)" : "") + (n.retired ? " (retired)" : ""),
    shape: "dot",
    size: 15 + n.weight * 18,
    color: { background: c.background, border: c.border, highlight: c },
    borderWidth: n.retired ? 1 : 3,
    font: {
      color: n.retired ? "#6f6d67" : "#f1f0e8",
      size: 12.5,
      face: "Cascadia Mono, Consolas, monospace",
      strokeWidth: 4,
      strokeColor: "#0d0e0c",
      vadjust: 2,
    },
    opacity: n.rusty ? 0.75 : 1,
  };
}

function renderGraph(el, current, payload) {
  const nodes = payload.nodes.map(nodeStyle);
  const edges = payload.edges.map((e) => ({
    from: e.from, to: e.to,
    arrows: { to: { enabled: true, scaleFactor: 0.55 } },
    color: { color: "#454540", highlight: "#6f6d67" },
    width: 1.5,
    smooth: { type: "continuous", roundness: 0.35 },
  }));

  if (current && current.body) {
    current.setData({ nodes, edges });
    setTimeout(() => current.fit({ animation: false }), 300);
    return current;
  }

  const net = new vis.Network(el, { nodes, edges }, {
    autoResize: false,
    physics: {
      barnesHut: {
        gravitationalConstant: -5200,
        springLength: 150,
        avoidOverlap: 0.35,
      },
      stabilization: { iterations: 240, fit: true },
    },
    interaction: { hover: true, tooltipDelay: 120 },
  });
  const rect = el.getBoundingClientRect();
  if (rect.width > 20 && rect.height > 20) net.setSize(rect.width + "px", rect.height + "px");
  net.once("stabilizationIterationsDone", () => {
    net.fit({ animation: false });
    setTimeout(() => net.fit({ animation: false }), 350);
  });
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      if (r.width > 20 && r.height > 20) {
        net.setSize(r.width + "px", r.height + "px");
        net.redraw();
        net.fit({ animation: false });
      }
    }).observe(el);
  }
  return net;
}

/* ---------- cockpit ---------- */

async function loadCockpit() {
  const h = await api("/api/health");
  state.health = h;
  $("#mode-badge").textContent = h.cloud_connected ? "cognee cloud" : `mode: ${h.mode}`;
  $("#ck-backend").textContent = h.cloud_connected ? "cognee cloud (live)" : h.mode;
  $("#ck-domain").textContent = h.domain;
  $("#ck-domain").title = h.title || h.domain;
  $("#ck-concepts").textContent = h.concepts;
  $("#ck-tenant").textContent = h.tenant ? h.tenant.slice(0, 18) + "…" : "local demo";
  const seeded = h.seeded || [];
  $("#ck-seeded").textContent = seeded.length ? `seeded: ${seeded.join(", ")}` : "seeded on first ask";

  const s = await api("/api/students");
  const box = $("#cockpit-students");
  box.innerHTML = "";
  s.students.forEach((st) => {
    const b = document.createElement("button");
    b.innerHTML = `<span class="who">${st.id}</span>` +
      `<span class="mini">${st.mastered} mastered · ${st.gaps} gaps · avg ${(st.avg_weight * 100).toFixed(0)}%</span>`;
    b.onclick = () => {
      state.student = st.id;
      $("#student-select").value = st.id;
      setView("app");
      loadStudentGraph();
      $("#workbench").scrollIntoView({ behavior: "smooth" });
    };
    box.appendChild(b);
  });
  return s;
}

/* ---------- student console ---------- */

async function loadStudents() {
  const data = await api("/api/students");
  const sel = $("#student-select");
  sel.innerHTML = "";
  data.students.forEach((s) => {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = s.id;
    sel.appendChild(o);
  });
  sel.value = state.student;
}

async function loadStudentGraph() {
  const g = await api(`/api/student/graph?student=${state.student}&offset_days=${state.offsetDays}`);
  state.studentNet = renderGraph($("#graph"), state.studentNet, g);

  const bands = { red: 0, amber: 0, green: 0 };
  let rusty = 0;
  let total = 0;
  let sum = 0;
  g.nodes.forEach((n) => {
    bands[n.band]++;
    if (n.rusty) rusty++;
    if (!n.retired) { total++; sum += n.weight; }
  });
  const pct = total ? Math.round((sum / total) * 100) : 0;

  $("#report-student").textContent = state.student;
  $("#mastery-label").textContent = `${state.student}'s mastery`;
  $("#mastery-score").textContent = pct + "%";
  $("#mastery-fill").style.width = pct + "%";
  $("#mb-mastered").textContent = bands.green;
  $("#mb-learning").textContent = bands.amber;
  $("#mb-gaps").textContent = bands.red;
  $("#mb-rusty").textContent = rusty;

  const next = g.next_step ? g.nodes.find((n) => n.id === g.next_step) : null;
  $("#next-step").textContent = next
    ? `${next.name}\n${next.summary}`
    : "all frontier concepts mastered.";
  $("#clock-label").textContent = state.offsetDays ? `+${state.offsetDays}d` : "today";
}

/* ---------- quiz ---------- */

async function quizNext() {
  const q = await api("/api/quiz/next", { method: "POST", body: JSON.stringify({ student: state.student }) });
  showQuiz(q);
}

function showQuiz(q) {
  $("#quiz-feedback").classList.add("hidden");
  if (q.done) {
    $("#quiz-concept").textContent = "done";
    $("#quiz-question").textContent = q.message;
    $("#quiz-options").innerHTML = "";
    $("#quiz-start").classList.remove("hidden");
    return;
  }
  state.question = q.question;
  $("#quiz-concept").textContent = q.concept.name;
  $("#quiz-question").textContent = q.question.text;
  const box = $("#quiz-options");
  box.innerHTML = "";
  q.question.options.forEach((opt, i) => {
    const b = document.createElement("button");
    b.textContent = opt;
    b.onclick = () => submitAnswer(i, b);
    box.appendChild(b);
  });
}

async function submitAnswer(index, btn) {
  const res = await api("/api/quiz/answer", {
    method: "POST",
    body: JSON.stringify({ student: state.student, concept: state.question.concept, answer_index: index }),
  });
  [...$("#quiz-options").children].forEach((b) => (b.disabled = true));
  btn.classList.add(res.correct ? "correct" : "wrong");
  const fb = $("#quiz-feedback");
  fb.classList.remove("hidden", "good", "bad");
  fb.classList.add(res.correct ? "good" : "bad");
  const before = (res.weight_before * 100).toFixed(0);
  const after = (res.weight_after * 100).toFixed(0);
  fb.textContent = res.correct
    ? `correct! mastery ${before}% -> ${after}%`
    : `not quite. answer: "${res.correct_option}". mastery ${before}% -> ${after}%`;

  lifecycle("improve");
  log(`<b>${res.concept.name}</b> ${res.correct ? "up" : "down"} ${before}% -> ${after}%`,
    res.correct ? "good" : "bad");
  if (res.concept.band === "green") {
    kicker(`${state.student} mastered ${res.concept.name}.`,
      "A learning trace was written to the cloud dataset with remember().");
    lifecycle("remember");
    log(`<b>remember()</b> trace: mastered ${res.concept.name}`, "good");
  }

  await loadStudentGraph();
  setTimeout(() => showQuiz(res.next), res.correct ? 900 : 1900);
}

/* ---------- ask (recall) ---------- */

async function askMemory() {
  const q = $("#ask-input").value.trim();
  if (!q) return;
  const btn = $("#ask-btn");
  const card = $("#ask-card");
  btn.disabled = true;
  card.classList.remove("hidden");
  $("#ask-source").textContent = "recalling";
  $("#ask-answer").textContent =
    "asking your memory... first question per student seeds the Cognee Cloud dataset (about 20s), then it is fast.";
  lifecycle("recall");
  try {
    const a = await api("/api/ask", { method: "POST", body: JSON.stringify({ student: state.student, question: q }) });
    $("#ask-answer").textContent = a.answer;
    $("#ask-source").textContent = a.cloud ? "cognee cloud" : "local";
    log(`<b>recall()</b> "${q.slice(0, 44)}"`, a.cloud ? "good" : "");
    loadCockpit(); // seeded list may have changed
  } catch (err) {
    $("#ask-answer").textContent = "memory unavailable. try again.";
    $("#ask-source").textContent = "error";
  } finally {
    btn.disabled = false;
  }
}

/* ---------- retire + reset (forget) ---------- */

async function retireMastered() {
  const g = await api(`/api/student/graph?student=${state.student}&offset_days=0`);
  const green = g.nodes.filter((n) => n.band === "green" && !n.retired)
    .sort((a, b) => b.weight - a.weight)[0];
  if (!green) {
    kicker("nothing to retire yet.", "Master a concept first, then retire it from active practice.");
    return;
  }
  const r = await api("/api/retire", {
    method: "POST",
    body: JSON.stringify({ student: state.student, concept: green.id }),
  });
  if (r.ok) {
    lifecycle("forget");
    kicker(`${green.name} retired.`, "Mastered and removed from active drilling. That is forget() as a feature.");
    log(`<b>forget()</b> retired ${green.name}`);
    loadStudentGraph();
  }
}

async function resetStudent() {
  if (!confirm(`Reset ${state.student}'s memory? This deletes their Cognee Cloud dataset (the transfer student demo).`)) return;
  await api("/api/reset-student", { method: "POST", body: JSON.stringify({ student: state.student }) });
  lifecycle("forget");
  kicker(`${state.student} reset.`, "Real forget(dataset) on the tenant. A brand new memory.");
  log(`<b>forget(dataset)</b> reset ${state.student}`, "bad");
  loadStudentGraph();
  loadCockpit();
}

/* ---------- teacher ---------- */

async function loadTeacher() {
  const hm = await api(`/api/class/heatmap?offset_days=${state.offsetDays}`);
  state.teacherHeatmap = hm;

  const tn = $("#teach-next");
  tn.innerHTML = "";
  (hm.teach_next.length ? hm.teach_next : hm.concepts.slice(0, 3)).forEach((c) => {
    const li = document.createElement("li");
    li.innerHTML = `<div class="teach-next-row"><span><span class="pct">${c.red_pct}% red</span> · ${c.name}</span>` +
      `<button class="assign-review" data-concept="${c.id}">assign</button></div>`;
    tn.appendChild(li);
  });
  $$(".assign-review").forEach((btn) => {
    btn.onclick = () => assignReview(btn.dataset.concept);
  });

  const list = $("#student-list");
  list.innerHTML = "";
  hm.students.forEach((s) => {
    const b = document.createElement("button");
    b.innerHTML = `<span class="who">${s.id}</span>` +
      `<span class="mini">${s.mastered} mastered · ${s.gaps} gaps · avg ${(s.avg_weight * 100).toFixed(0)}%</span>`;
    b.onclick = () => drillStudent(s.id);
    list.appendChild(b);
  });

  if (!state.teacherDrill) {
    const nodes = hm.concepts.map((c) => ({
      id: c.id,
      name: c.name,
      summary: `class avg ${(c.avg_weight * 100).toFixed(0)}%, ${c.red_pct}% of class red`,
      requires: c.requires,
      weight: c.avg_weight,
      band: bandOf(c.avg_weight),
      rusty: false,
      retired: false,
    }));
    const edges = [];
    hm.concepts.forEach((c) => c.requires.forEach((r) => edges.push({ from: r, to: c.id })));
    state.teacherNet = renderGraph($("#teacher-graph"), state.teacherNet, { nodes, edges });
    $("#teacher-graph-title").textContent = "class heat map";
    $("#back-to-class").classList.add("hidden");
    const worst = hm.concepts[0];
    $("#t-students").textContent = hm.students.length;
    $("#t-worst").textContent = worst.name.split(" ")[0];
    $("#t-red").textContent = worst.red_pct + "%";
  }
}

async function assignReview(concept) {
  const card = $("#intervention-card");
  card.innerHTML = `<b>Assigning review...</b><span>Creating a targeted list from the class heat map.</span>`;
  try {
    const res = await api("/api/teacher/assign-review", {
      method: "POST",
      body: JSON.stringify({ concept }),
    });
    const students = res.students || [];
    const list = students.length
      ? `<ul>${students.map((s) => `<li>${escapeHtml(s.student)} · ${escapeHtml(s.band)} · ${(s.weight * 100).toFixed(0)}%</li>`).join("")}</ul>`
      : "<span>No red or rusty students for this concept right now.</span>";
    card.innerHTML = `<b>${escapeHtml(res.message)}</b>` +
      `<span>Intervention ${res.intervention ? "#" + res.intervention.id : "created"} · ${escapeHtml(res.concept_name)}</span>${list}`;
    if (res.assigned_count > 0) {
      $("#class-ask-input").value = `why is ${res.concept_name} the next review?`;
    }
  } catch (err) {
    card.innerHTML = `<b>Could not assign review.</b><span>${escapeHtml(err.message)}</span>`;
  }
}

function bandOf(w) {
  if (w < 0.35) return "red";
  if (w > 0.75) return "green";
  return "amber";
}

async function drillStudent(sid) {
  state.teacherDrill = sid;
  const g = await api(`/api/student/graph?student=${sid}&offset_days=${state.offsetDays}`);
  state.teacherNet = renderGraph($("#teacher-graph"), state.teacherNet, g);
  $("#teacher-graph-title").textContent = `${sid} · mastery graph`;
  $("#back-to-class").classList.remove("hidden");
  const gaps = g.nodes.filter((n) => n.band === "red").length;
  const greens = g.nodes.filter((n) => n.band === "green").length;
  $("#t-students").textContent = sid;
  $("#t-worst").textContent = `${gaps} gaps`;
  $("#t-red").textContent = `${greens} done`;
}

/* ---------- views ---------- */

function setView(view, opts = {}) {
  const { scrollTop = true, syncHash = true } = opts;
  if (!$(`#${view}-view`)) view = "app";
  state.view = view;
  $$(".view").forEach((v) => v.classList.remove("active"));
  $(`#${view}-view`).classList.add("active");
  $$(".navlinks a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  if (syncHash) {
    const nextHash = view === "app" ? "#app" : `#${view}`;
    if (location.hash !== nextHash) history.replaceState(null, "", nextHash);
  }
  if (scrollTop) window.scrollTo({ top: 0 });
  if (view === "teacher") { state.teacherDrill = null; loadTeacher(); }
  if (view === "app") loadStudentGraph();
  fitVisibleGraphs();
}

function routeFromHash() {
  setView(viewFromHash(), { scrollTop: true, syncHash: false });
}

function wireViewLinks() {
  $$("[data-view]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      setView(el.dataset.view);
    });
  });
}

function maximizePanels() {
  return {
    workbench: $(".case-column"),
    graph: $(".graph-column"),
    report: $(".report-column"),
  };
}

function toggleMaximize(panelName) {
  const wb = $("#workbench");
  const carousel = $(".carousel-nav");
  if (!wb || !carousel) return;
  const panels = maximizePanels();
  const names = Object.keys(panels);
  const triggers = $$(".maximize-trigger");

  if (activeMaximized === panelName) {
    wb.classList.remove("maximized-mode");
    names.forEach((name) => {
      panels[name]?.classList.remove("maximized", "hidden-slide");
    });
    activeMaximized = null;
    carousel.classList.remove("visible");
  } else {
    wb.classList.add("maximized-mode");
    names.forEach((name) => {
      panels[name]?.classList.toggle("maximized", name === panelName);
      panels[name]?.classList.toggle("hidden-slide", name !== panelName);
    });
    activeMaximized = panelName;
    carousel.classList.add("visible");
  }

  const activeIndex = names.indexOf(activeMaximized || "workbench");
  $$(".carousel-tab").forEach((tab, i) => tab.classList.toggle("active", i === activeIndex));
  triggers.forEach((btn) => {
    const active = btn.dataset.panel === activeMaximized;
    btn.innerHTML = `<i data-lucide="${active ? "minimize-2" : "maximize-2"}"></i>`;
    btn.title = active ? "Restore grid" : `Maximize ${btn.dataset.panel}`;
  });
  icons();
  setTimeout(fitVisibleGraphs, 80);
}

function updateSlide(delta) {
  const names = Object.keys(maximizePanels());
  const current = names.indexOf(activeMaximized || "workbench");
  toggleMaximize(names[(current + delta + names.length) % names.length]);
}

function initCarousel() {
  $$(".maximize-trigger").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleMaximize(btn.dataset.panel);
    });
  });
  $$(".carousel-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const names = Object.keys(maximizePanels());
      const target = names[Number(tab.dataset.slide || 0)];
      if (activeMaximized !== target) toggleMaximize(target);
    });
  });
  $("#slide-prev")?.addEventListener("click", () => updateSlide(-1));
  $("#slide-next")?.addEventListener("click", () => updateSlide(1));
  document.addEventListener("keydown", (e) => {
    if (!activeMaximized || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
    if (e.key === "ArrowLeft") updateSlide(-1);
    if (e.key === "ArrowRight") updateSlide(1);
    if (e.key === "Escape") toggleMaximize(activeMaximized);
  });
}

/* ---------- init ---------- */

async function init() {
  wireViewLinks();
  window.addEventListener("hashchange", routeFromHash);

  try {
    await loadCockpit();
  } catch (err) {
    $("#mode-badge").textContent = "backend offline";
    console.error(err);
    return;
  }
  await loadStudents();
  await loadStudentGraph();
  initCarousel();
  routeFromHash();

  safely("core", () => {
    $("#refresh-cockpit").onclick = loadCockpit;

    $("#hero-start").onclick = () => {
      $("#workbench").scrollIntoView({ behavior: "smooth" });
      $("#quiz-start").click();
    };

    $("#student-select").onchange = (e) => {
      state.student = e.target.value;
      $("#quiz-start").classList.remove("hidden");
      $("#quiz-concept").textContent = "press start to begin";
      $("#quiz-question").textContent = "";
      $("#quiz-options").innerHTML = "";
      $("#quiz-feedback").classList.add("hidden");
      loadStudentGraph();
    };

    $("#quiz-start").onclick = () => {
      $("#quiz-start").classList.add("hidden");
      quizNext();
    };

    $("#ask-btn").onclick = askMemory;
    $("#ask-input").addEventListener("keydown", (e) => { if (e.key === "Enter") askMemory(); });

    $("#retire-btn").onclick = retireMastered;
    $("#reset-btn").onclick = resetStudent;
  });

  safely("lifecycle-strip", () => {
    Object.keys(LIFECYCLE_EXPLAIN).forEach((step) => {
      const el = $(`#life-${step}`);
      if (!el) return;
      el.onclick = () => {
        const [title, text] = LIFECYCLE_EXPLAIN[step];
        lifecycle(step);
        kicker(title + ".", text);
        log(`<b>${title}</b> explained`, "");
      };
    });
    // "today" tab: one click back to the present
    $("#clock-label").onclick = () => {
      if (!state.offsetDays) return;
      state.offsetDays = 0;
      const span = $("#decay-btn").querySelector("span");
      if (span) span.textContent = "age +30d";
      kicker("back to today.", "Decay view reset.");
      if (state.view === "teacher") { state.teacherDrill = null; loadTeacher(); }
      else loadStudentGraph();
    };
    $("#clock-label").style.cursor = "pointer";
    $("#clock-label").title = "click to return to today";
  });

  const openEnroll = () => {
    $("#enroll-error").classList.add("hidden");
    $("#enroll-error").textContent = "";
    $("#enroll-name").value = "";
    $("#enroll-modal").classList.remove("hidden");
    icons();
    setTimeout(() => $("#enroll-name").focus(), 40);
  };

  const closeEnroll = () => $("#enroll-modal").classList.add("hidden");

  const enrollStudent = async (name) => {
    if (!name) return;
    const r = await api("/api/student/add", {
      method: "POST", body: JSON.stringify({ student: name }),
    });
    if (!r.ok) {
      $("#enroll-error").textContent = r.reason || "Could not enroll that student.";
      $("#enroll-error").classList.remove("hidden");
      return;
    }
    closeEnroll();
    state.student = r.student;
    await loadStudents();
    await loadCockpit();
    setView("app");
    $("#student-select").value = r.student;
    await loadStudentGraph();
    kicker(`welcome, ${r.student}.`,
      "A brand new memory. The first question creates their Cognee Cloud dataset.");
    log(`<b>enrolled</b> ${r.student}`, "good");
    $("#workbench").scrollIntoView({ behavior: "smooth" });
  };
  safely("enroll", () => {
    $("#enroll-btn").onclick = openEnroll;
    $("#enroll-btn2").onclick = openEnroll;
    $("#enroll-close").onclick = closeEnroll;
    $("#enroll-modal").addEventListener("click", (e) => {
      if (e.target === $("#enroll-modal")) closeEnroll();
    });
    $("#enroll-form").addEventListener("submit", (e) => {
      e.preventDefault();
      enrollStudent($("#enroll-name").value.trim());
    });
  });

  const sampleCurriculum = {
    domain: "ai-literacy",
    title: "AI literacy fundamentals",
    concepts: [
      {
        id: "prompts",
        name: "Prompts",
        summary: "Clear instructions, context, examples, and constraints for an AI model.",
        requires: [],
        questions: [
          {
            q: "Which prompt is easiest for a model to follow?",
            options: ["Do it", "Summarize this in 3 bullet points for a teacher", "Help", "Make it nice"],
            answer: 1,
          },
        ],
      },
      {
        id: "hallucinations",
        name: "Hallucinations",
        summary: "Confident model outputs that are not grounded in reliable evidence.",
        requires: ["prompts"],
        questions: [
          {
            q: "What should you do with a surprising factual AI answer?",
            options: ["Trust it immediately", "Verify it against a source", "Delete the prompt", "Ask shorter questions"],
            answer: 1,
          },
        ],
      },
      {
        id: "retrieval",
        name: "Retrieval",
        summary: "Supplying relevant external context so the model can answer from evidence.",
        requires: ["hallucinations"],
        questions: [
          {
            q: "Why does retrieval help?",
            options: ["It adds grounded context", "It removes all tokens", "It turns AI off", "It only changes fonts"],
            answer: 0,
          },
        ],
      },
    ],
  };

  const openCurriculum = () => {
    $("#curriculum-error").classList.add("hidden");
    $("#curriculum-error").textContent = "";
    $("#curriculum-json").value = JSON.stringify(sampleCurriculum, null, 2);
    $("#curriculum-modal").classList.remove("hidden");
    icons();
    setTimeout(() => $("#curriculum-json").focus(), 40);
  };
  const closeCurriculum = () => $("#curriculum-modal").classList.add("hidden");
  safely("curriculum-modal", () => {
    $("#curriculum-btn").onclick = openCurriculum;
    $("#curriculum-close").onclick = closeCurriculum;
    $("#curriculum-sample").onclick = () => {
      $("#curriculum-json").value = JSON.stringify(sampleCurriculum, null, 2);
    };
    $("#curriculum-modal").addEventListener("click", (e) => {
      if (e.target === $("#curriculum-modal")) closeCurriculum();
    });
  });
  $("#curriculum-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#curriculum-error").classList.add("hidden");
    let payload;
    try {
      payload = JSON.parse($("#curriculum-json").value);
    } catch (err) {
      $("#curriculum-error").textContent = "Invalid JSON.";
      $("#curriculum-error").classList.remove("hidden");
      return;
    }
    try {
      const res = await api("/api/curriculum/import", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      closeCurriculum();
      state.student = "alice";
      state.studentNet = null;
      state.teacherNet = null;
      state.teacherDrill = null;
      await loadCockpit();
      await loadStudents();
      await loadStudentGraph();
      if (state.view === "teacher") await loadTeacher();
      kicker(`${res.title} imported.`, `${res.concepts} concepts are now live. Same app, new subject.`);
      log(`<b>curriculum imported</b> ${escapeHtml(res.domain)}`, "good");
    } catch (err) {
      $("#curriculum-error").textContent = err.message || "Import failed.";
      $("#curriculum-error").classList.remove("hidden");
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#enroll-modal").classList.contains("hidden")) closeEnroll();
    if (!$("#curriculum-modal").classList.contains("hidden")) closeCurriculum();
  });

  safely("decay+teacher", () => {
    $("#decay-btn").onclick = () => {
      state.offsetDays = (state.offsetDays + 30) % 120;
      const label = state.offsetDays ? `+${state.offsetDays}d` : "age +30d";
      $("#decay-btn").querySelector("span").textContent = state.offsetDays ? `viewing ${label}` : label;
      if (state.offsetDays) {
        kicker("memory rots.", `Viewing the graphs as if ${state.offsetDays} days passed. Untouched knowledge goes rusty.`);
      } else {
        kicker("back to today.", "Decay view reset.");
      }
      if (state.view === "teacher") { state.teacherDrill = null; loadTeacher(); }
      else loadStudentGraph();
    };

    $("#back-to-class").onclick = () => { state.teacherDrill = null; loadTeacher(); };
  });

  const classAsk = async () => {
    const q = $("#class-ask-input").value.trim();
    if (!q) return;
    const btn = $("#class-ask-btn");
    const card = $("#class-ask-card");
    btn.disabled = true;
    card.classList.remove("hidden");
    $("#class-ask-source").textContent = "recalling";
    $("#class-ask-answer").textContent =
      "one recall() across every student's dataset... unseeded students are seeded first (about 20s each), then it is fast.";
    try {
      const a = await api("/api/class/ask", { method: "POST", body: JSON.stringify({ question: q }) });
      if (a.per_student && a.per_student.length) {
        $("#class-ask-answer").innerHTML = a.per_student
          .map((p) => `<b>${escapeHtml(p.student)}:</b> ${escapeHtml(p.text)}`).join("<br><br>");
      } else {
        $("#class-ask-answer").textContent = a.answer;
      }
      $("#class-ask-source").textContent = a.cloud ? "cognee cloud" : "local";
    } catch (err) {
      $("#class-ask-answer").textContent = "class memory unavailable. try again.";
      $("#class-ask-source").textContent = "error";
    } finally {
      btn.disabled = false;
    }
  };
  safely("class-ask", () => {
    $("#class-ask-btn").onclick = classAsk;
    $("#class-ask-input").addEventListener("keydown", (e) => { if (e.key === "Enter") classAsk(); });
  });

  safely("chrome", () => {
    $("#theme-toggle").onclick = () => {
      document.body.classList.toggle("light");
      const icon = document.body.classList.contains("light") ? "sun" : "moon";
      $("#theme-toggle").innerHTML = `<i data-lucide="${icon}"></i>`;
      icons();
    };

    $("#footer-copy-command").onclick = () => {
      navigator.clipboard.writeText("python backend/verify_cloud.py");
      kicker("command copied.", "Run it to prove the cloud lifecycle end to end.");
    };
  });

  icons();
}

init();

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[ch]));
}
