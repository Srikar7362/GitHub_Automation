"use strict";

// ---- tiny helpers ---------------------------------------------------------
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { /* ignore */ }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function banner(message, kind = "") {
  const el = $("banner");
  if (!message) { el.classList.add("hidden"); return; }
  el.textContent = message;
  el.className = "banner " + kind;
}

function logLinesHtml(logs) {
  if (!logs || !logs.length) return "";
  const text = logs.map((l) => l.replace(/&/g, "&amp;").replace(/</g, "&lt;")).join("\n");
  return `<div class="loglines">${text}</div>`;
}

// ---- state ----------------------------------------------------------------
let allRepos = [];
let selectedRepo = "";

// ---- status / chips -------------------------------------------------------
async function refreshStatus() {
  try {
    const s = await api("/api/status");

    const token = $("chipToken");
    token.textContent = s.token_present ? "token: set" : "token: missing";
    token.className = "chip " + (s.token_present ? "chip-ok" : "chip-bad");

    const user = $("chipUser");
    user.textContent = s.user ? `@${s.user}` : (s.user_error ? "user: error" : "user: –");
    user.className = "chip " + (s.user ? "chip-ok" : "chip-muted");

    const kill = $("chipKill");
    kill.dataset.engaged = s.kill_switch.engaged ? "1" : "0";
    kill.textContent = "kill switch: " + (s.kill_switch.engaged ? "ON" : "off");
    kill.className = "chip chip-kill " + (s.kill_switch.engaged ? "chip-bad" : "chip-ok");

    // Populate language selectors.
    for (const sel of [$("langSelect"), $("projLang")]) {
      if (sel.options.length === 0) {
        for (const lang of s.languages) {
          const o = document.createElement("option");
          o.value = lang; o.textContent = lang;
          sel.appendChild(o);
        }
        sel.value = s.default_language;
      }
    }

    if (s.kill_switch.engaged) banner("Kill switch is ON — commit and create actions are blocked.", "");
    else if (!s.token_present) banner("No GITHUB_TOKEN found. Add it to your .env, then refresh.", "error");
    else if (s.user_error) banner("Token present but GitHub rejected it: " + s.user_error, "error");
    else banner("");
  } catch (e) {
    banner(e.message, "error");
  }
}

// ---- kill switch toggle ---------------------------------------------------
$("chipKill").addEventListener("click", async () => {
  const engaged = $("chipKill").dataset.engaged === "1";
  try {
    await api("/api/killswitch", { method: "POST", body: JSON.stringify({ engaged: !engaged }) });
    await refreshStatus();
  } catch (e) { banner(e.message, "error"); }
});

// ---- repositories ---------------------------------------------------------
$("loadReposBtn").addEventListener("click", loadRepos);

async function loadRepos() {
  const btn = $("loadReposBtn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Loading';
  try {
    const data = await api("/api/repos");
    allRepos = data.repos;
    $("repoSearch").classList.remove("hidden");
    renderRepos("");
    banner(allRepos.length ? "" : "No eligible (non-fork, non-archived) repositories found.", "");
  } catch (e) {
    banner(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Reload repositories";
  }
}

function renderRepos(filter) {
  const list = $("repoList");
  const f = filter.toLowerCase();
  const repos = allRepos.filter((r) => r.full_name.toLowerCase().includes(f));
  list.classList.add("show");
  list.innerHTML = "";
  if (!repos.length) { list.innerHTML = '<div class="repo-item muted">No matches</div>'; return; }
  for (const r of repos) {
    const div = document.createElement("div");
    div.className = "repo-item" + (r.full_name === selectedRepo ? " selected" : "");
    div.innerHTML = `<span>${r.full_name}</span><span class="tag">${r.private ? "private" : "public"} · ${r.default_branch}</span>`;
    div.addEventListener("click", () => {
      selectedRepo = r.full_name;
      $("commitBtn").disabled = false;
      renderRepos($("repoSearch").value);
    });
    list.appendChild(div);
  }
}

$("repoSearch").addEventListener("input", (e) => renderRepos(e.target.value));

// ---- commit ---------------------------------------------------------------
$("commitBtn").addEventListener("click", async () => {
  const btn = $("commitBtn");
  const out = $("commitResult");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Committing';
  out.innerHTML = "";
  try {
    const res = await api("/api/commit", {
      method: "POST",
      body: JSON.stringify({ repo: selectedRepo, force: $("forceCommit").checked }),
    });
    if (res.status === "skipped") {
      out.innerHTML = `<span class="err">Skipped:</span> ${res.reason}` + logLinesHtml(res.logs);
    } else {
      const link = res.commit_url ? ` <a href="${res.commit_url}" target="_blank">view commit</a>` : "";
      out.innerHTML = `<span class="ok">✓ Made ${res.count} commit(s)</span> to <b>${res.repo}</b> (${res.file}).${link}` + logLinesHtml(res.logs);
    }
    refreshLogs();
  } catch (e) {
    out.innerHTML = `<span class="err">${e.message}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Commit to selected repo";
  }
});

// ---- propose / create -----------------------------------------------------
$("proposeBtn").addEventListener("click", propose);
$("reproposeBtn").addEventListener("click", propose);

async function propose() {
  const btn = $("proposeBtn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Thinking';
  $("projectResult").innerHTML = "";
  try {
    const p = await api("/api/project/propose", {
      method: "POST",
      body: JSON.stringify({ language: $("langSelect").value }),
    });
    $("projName").value = p.name;
    $("projIdea").value = p.idea;
    $("projLang").value = p.language;
    $("ideaSource").textContent = `(idea source: ${p.source})`;
    $("proposalForm").classList.remove("hidden");
  } catch (e) {
    $("projectResult").innerHTML = `<span class="err">${e.message}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Propose a project";
  }
}

$("createBtn").addEventListener("click", async () => {
  const btn = $("createBtn");
  const out = $("projectResult");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Creating';
  out.innerHTML = "";
  try {
    const res = await api("/api/project/create", {
      method: "POST",
      body: JSON.stringify({
        name: $("projName").value.trim(),
        language: $("projLang").value,
        idea: $("projIdea").value.trim(),
        source: $("ideaSource").textContent.includes("user") ? "user-provided" : "auto",
      }),
    });
    const link = res.html_url ? `<a href="${res.html_url}" target="_blank">${res.full_name}</a>` : res.full_name;
    out.innerHTML = `<span class="ok">✓ Created</span> ${link}` + logLinesHtml(res.logs);
    $("proposalForm").classList.add("hidden");
    refreshStatus();
    refreshLogs();
  } catch (e) {
    out.innerHTML = `<span class="err">${e.message}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Create repository";
  }
});

// ---- logs -----------------------------------------------------------------
$("refreshLogsBtn").addEventListener("click", refreshLogs);

async function refreshLogs() {
  try {
    const data = await api("/api/logs?lines=120");
    $("logBox").textContent = data.lines.length ? data.lines.join("\n") : "(log file is empty)";
    $("logBox").scrollTop = $("logBox").scrollHeight;
  } catch (e) {
    $("logBox").textContent = e.message;
  }
}

// ---- init -----------------------------------------------------------------
refreshStatus();
refreshLogs();
