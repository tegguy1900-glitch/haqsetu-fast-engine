const DEFAULT_API = "http://127.0.0.1:8000";

let currentCaseId = null;
let publicTimer = null;

document.addEventListener("DOMContentLoaded", init);

function init() {
  const page = document.body.dataset.page;

  const apiBaseInput = document.getElementById("apiBase");
  if (apiBaseInput && !apiBaseInput.value) {
    apiBaseInput.value = DEFAULT_API;
  }

  if (page === "facilitator") {
    initFacilitator();
  } else if (page === "public") {
    initPublic();
  }
}

// -------------------------
// Helpers
// -------------------------

function apiBase() {
  const el = document.getElementById("apiBase");
  return el && el.value.trim() ? el.value.trim() : DEFAULT_API;
}

async function api(path, options = {}) {
  const res = await fetch(apiBase() + path, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  const text = await res.text();
  let data = {};

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }

  if (!res.ok) {
    let detail = data.detail || data.error || `HTTP ${res.status}`;

    if (typeof detail !== "string") {
      detail = JSON.stringify(detail);
    }

    throw new Error(detail);
  }

  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatTime(value) {
  if (!value) return "";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function showMessage(text, kind = "ok") {
  const el = document.getElementById("message");
  if (!el) return;

  el.textContent = text;
  el.className = `message ${kind}`;

  setTimeout(() => {
    el.textContent = "";
    el.className = "message";
  }, 8000);
}

function errorText(err) {
  return err && err.message ? err.message : String(err);
}

function ledHtml(led) {
  const color = led || "gray";
  return `<span class="led ${escapeHtml(color)}"></span>${escapeHtml(color)}`;
}

function statusLabel(status) {
  const map = {
    open: "Open",
    passed: "Passed",
    official_rejected: "Official decision recorded",
    verify_requested: "Verification requested",
    citizen_contacted: "Citizen contacted",
    closed: "Closed",
  };

  return map[status] || status || "Unknown";
}

// -------------------------
// Facilitator page
// -------------------------

function initFacilitator() {
  document
    .getElementById("refreshCases")
    .addEventListener("click", loadCases);

  document
    .getElementById("createCase")
    .addEventListener("click", createCase);

  document.querySelectorAll(".action-button").forEach((button) => {
    button.addEventListener("click", () => sendAction(button));
  });

  loadCases();
}

async function loadCases() {
  try {
    const data = await api("/cases?limit=100");
    renderCases(data.cases || []);
  } catch (err) {
    showMessage(errorText(err), "error");
  }
}

function renderCases(cases) {
  const tbody = document.getElementById("casesTbody");
  tbody.innerHTML = "";

  for (const c of cases) {
    const tr = document.createElement("tr");

    const routeOutcome = c.outcomes && c.outcomes[c.route]
      ? c.outcomes[c.route]
      : "";

    tr.innerHTML = `
      <td>${escapeHtml(c.case_id)}</td>
      <td>${escapeHtml(c.route)}</td>
      <td>${escapeHtml(c.status)}</td>
      <td>${escapeHtml(routeOutcome)}</td>
      <td>${escapeHtml(formatTime(c.updated_at))}</td>
      <td><button class="open-case">Open</button></td>
    `;

    tr.querySelector(".open-case").addEventListener("click", () => {
      loadCase(c.case_id);
    });

    tbody.appendChild(tr);
  }
}

async function createCase() {
  const route = document.getElementById("route").value;
  const actor = document.getElementById("actor").value.trim() || "facilitator";
  const factsText = document.getElementById("facts").value || "{}";

  let facts;

  try {
    facts = JSON.parse(factsText);
  } catch {
    showMessage("Facts JSON is invalid.", "error");
    return;
  }

  const payload = {
    route,
    actor,
    role: "facilitator",
    facts,
  };

  try {
    const result = await api("/cases", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    showMessage("Case created.", "ok");

    await loadCases();

    if (result.case && result.case.case_id) {
      await loadCase(result.case.case_id);
    }
  } catch (err) {
    showMessage(errorText(err), "error");
  }
}

async function loadCase(caseId) {
  currentCaseId = caseId;

  try {
    const c = await api(`/cases/${caseId}`);
    renderCaseDetail(c);

    const events = await api(`/cases/${caseId}/events`);
    renderEvents(events.events || []);
  } catch (err) {
    showMessage(errorText(err), "error");
  }
}

function renderCaseDetail(c) {
  const detail = document.getElementById("caseDetail");

  const clock = c.clock || {};
  const routeClock = clock.clock || {};
  const stall = clock.stall || {};

  const led = clock.led || "gray";
  const deadline = clock.deadline ? formatTime(clock.deadline) : "";

  const outcomes = Object.entries(c.outcomes || {})
    .map(([scheme, outcome]) => {
      return `<li><strong>${escapeHtml(scheme)}</strong>: ${escapeHtml(outcome)}</li>`;
    })
    .join("");

  detail.innerHTML = `
    <p><strong>Case:</strong> ${escapeHtml(c.case_id)}</p>
    <p><strong>Route:</strong> ${escapeHtml(c.route)}</p>
    <p><strong>Status:</strong> ${escapeHtml(statusLabel(c.status))}</p>
    <p><strong>Opened:</strong> ${escapeHtml(formatTime(c.opened_at))}</p>
    <p><strong>Last event:</strong> ${escapeHtml(formatTime(c.last_event_at))}</p>
    <p><strong>LED:</strong> ${ledHtml(led)}</p>
    <p><strong>Clock state:</strong> ${escapeHtml(routeClock.state || "unknown")}</p>
    <p><strong>Stall state:</strong> ${escapeHtml(stall.state || "unknown")}</p>
    <p><strong>Deadline:</strong> ${escapeHtml(deadline)}</p>

    <h3>Outcomes</h3>
    <ul>${outcomes || "<li>No outcomes yet.</li>"}</ul>

    <h3>Facts</h3>
    <pre>${escapeHtml(JSON.stringify(c.facts || {}, null, 2))}</pre>
  `;
}

function renderEvents(events) {
  const container = document.getElementById("caseEvents");

  if (!events.length) {
    container.innerHTML = "<p>No events yet.</p>";
    return;
  }

  container.innerHTML = events
    .map((event) => {
      return `
        <div class="event">
          <p>
            <strong>${escapeHtml(event.event_type)}</strong>
            by ${escapeHtml(event.actor)}
          </p>
          <p>${escapeHtml(formatTime(event.created_at))}</p>
          <pre>${escapeHtml(JSON.stringify(event.data || {}, null, 2))}</pre>
        </div>
      `;
    })
    .join("");
}

async function sendAction(button) {
  if (!currentCaseId) {
    alert("Open a case first.");
    return;
  }

  const eventType = button.dataset.event;
  const boardAction = button.dataset.board;
  const requireNote = button.dataset.requireNote === "true";
  const promptText = button.dataset.prompt || "Note:";

  let note = prompt(promptText, "");

  if (note === null) {
    return;
  }

  note = note.trim();

  if (requireNote && !note) {
    alert("A reason is required for this action.");
    return;
  }

  const actor = document.getElementById("actor").value.trim() || "facilitator";

  const payload = {
    actor,
    role: "facilitator",
    event_type: eventType,
    data: {
      board_action: boardAction,
      note,
      source_ui: "facilitator",
    },
  };

  try {
    await api(`/cases/${currentCaseId}/events`, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    showMessage("Action recorded.", "ok");

    await loadCase(currentCaseId);
    await loadCases();
  } catch (err) {
    showMessage(errorText(err), "error");
  }
}

// -------------------------
// Public board page
// -------------------------

function initPublic() {
  document
    .getElementById("refreshPublic")
    .addEventListener("click", loadPublic);

  loadPublic();

  publicTimer = setInterval(loadPublic, 10000);
}

async function loadPublic() {
  const board = document.getElementById("publicBoard");

  try {
    const data = await api("/cases?limit=30");
    const cases = data.cases || [];

    const detailed = await Promise.all(
      cases.map(async (c) => {
        try {
          return await api(`/cases/${c.case_id}`);
        } catch {
          return c;
        }
      })
    );

    renderPublic(detailed);
  } catch (err) {
    board.innerHTML = `<div class="panel">${escapeHtml(errorText(err))}</div>`;
  }
}

function renderPublic(cases) {
  const board = document.getElementById("publicBoard");

  if (!cases.length) {
    board.innerHTML = `<div class="panel">No cases yet.</div>`;
    return;
  }

  board.innerHTML = cases
    .map((c) => {
      const led = c.clock && c.clock.led ? c.clock.led : "gray";

      return `
        <div class="card">
          <div class="card-top">
            ${ledHtml(led)}
            <strong>${escapeHtml(c.case_id)}</strong>
          </div>

          <div>Route: ${escapeHtml(c.route || "")}</div>
          <div>Status: ${escapeHtml(statusLabel(c.status))}</div>
          <div>Updated: ${escapeHtml(formatTime(c.updated_at))}</div>
        </div>
      `;
    })
    .join("");
}