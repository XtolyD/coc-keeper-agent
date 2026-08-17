const state = {
  view: "characters",
  status: null,
  characters: [],
  modules: [],
  games: [],
  activeGame: null,
  draft: null,
  selectedCandidate: null,
};

const content = document.querySelector("#content");
const modal = document.querySelector("#modal");
const modalContent = document.querySelector("#modal-content");
const toast = document.querySelector("#toast");

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
}

function icon(name) { return `<i data-lucide="${name}"></i>`; }
function refreshIcons() { if (window.lucide) window.lucide.createIcons(); }

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `请求失败 (${response.status})`);
  return payload;
}

function notify(message, error = false) {
  toast.textContent = message;
  toast.className = `toast show${error ? " error" : ""}`;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { toast.className = "toast"; }, 3200);
}

function derivedValue(sheet, key) {
  return sheet?.derived?.[key] ?? "-";
}

function attributesHTML(sheet, names = ["STR", "CON", "DEX", "POW", "INT", "EDU"]) {
  return `<div class="stat-line">${names.map((name) => `<div class="stat"><span>${name}</span><strong>${esc(sheet.attributes[name])}</strong></div>`).join("")}</div>`;
}

function setView(view) {
  state.view = view;
  state.activeGame = null;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  render();
}

function render() {
  if (state.activeGame) renderGame();
  else if (state.view === "characters") renderCharacters();
  else if (state.view === "modules") renderModules();
  else renderGames();
  refreshIcons();
}

function renderCharacters() {
  const rows = state.characters.map((record) => {
    const sheet = record.sheet;
    return `<div class="collection-row">
      <div><div class="row-title">${esc(sheet.name)}</div><div class="row-meta">${esc(sheet.age)} 岁 · 永久角色卡 · ${esc(record.skill_points_spent)}/${esc(record.skill_budget)} 技能点</div></div>
      ${attributesHTML(sheet)}
      <button class="button edit-skills" data-id="${record.id}" type="button">${icon("sliders-horizontal")}技能</button>
    </div>`;
  }).join("");
  content.innerHTML = `<section class="page">
    <header class="page-header"><h1>角色卡</h1><div class="page-actions"><button class="button primary" id="new-character" type="button">${icon("plus")}新建角色</button></div></header>
    ${rows ? `<div class="collection">${rows}</div>` : `<div class="empty-state"><div>${icon("contact-round")}<h2>角色库为空</h2><button class="button primary" id="empty-new-character" type="button">${icon("plus")}新建角色</button></div></div>`}
  </section>`;
  document.querySelector("#new-character")?.addEventListener("click", openCharacterWizard);
  document.querySelector("#empty-new-character")?.addEventListener("click", openCharacterWizard);
  document.querySelectorAll(".edit-skills").forEach((button) => button.addEventListener("click", () => openSkillEditor(button.dataset.id)));
}

function openCharacterWizard() {
  state.draft = null;
  state.selectedCandidate = null;
  modalContent.innerHTML = `<form class="modal-body" id="character-start">
    <h2 class="modal-title">新建调查员</h2>
    <div class="form-grid">
      <div class="field"><label for="character-name">姓名</label><input id="character-name" name="name" value="调查员" maxlength="40" required></div>
      <div class="field"><label for="character-age">年龄</label><input id="character-age" name="age" type="number" value="30" min="15" max="90" required></div>
    </div>
    <div class="form-footer"><button class="button primary" type="submit">${icon("dices")}生成五组属性</button></div>
  </form>`;
  modal.showModal();
  refreshIcons();
  document.querySelector("#character-start").addEventListener("submit", generateCandidates);
}

async function generateCandidates(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  event.currentTarget.classList.add("loading");
  try {
    state.draft = await api("/api/character-drafts", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: form.get("name"), age: Number(form.get("age"))}),
    });
    renderCandidates();
  } catch (error) { notify(error.message, true); event.currentTarget.classList.remove("loading"); }
}

function candidateCard(candidate) {
  const sheet = candidate.sheet;
  const bars = ["STR","CON","DEX","APP","POW","SIZ","INT","EDU","LUCK"].map((name) => `<div class="attribute-row"><span>${name}</span><span class="bar-track"><span class="bar-fill" style="width:${Math.min(100, sheet.attributes[name])}%"></span></span><strong>${sheet.attributes[name]}</strong></div>`).join("");
  return `<button class="candidate${state.selectedCandidate === candidate.index ? " selected" : ""}" type="button" data-index="${candidate.index}">
    <h3>候选 ${candidate.index + 1}</h3><div class="attribute-bars">${bars}</div>
    <div class="derived-strip">HP ${esc(sheet.derived.HP)} · SAN ${esc(sheet.derived.SAN)}<br>DB ${esc(sheet.derived.DB)} · MOV ${esc(sheet.derived.MOV)}<br>技能点 ${candidate.skill_budget}</div>
  </button>`;
}

function renderCandidates() {
  modalContent.innerHTML = `<div class="modal-body"><h2 class="modal-title">选择属性</h2>
    <div class="candidate-grid">${state.draft.candidates.map(candidateCard).join("")}</div>
    <div class="form-footer"><button class="button primary" id="choose-candidate" type="button" disabled>${icon("arrow-right")}分配技能</button></div>
  </div>`;
  refreshIcons();
  document.querySelectorAll(".candidate").forEach((candidate) => candidate.addEventListener("click", () => {
    state.selectedCandidate = Number(candidate.dataset.index);
    renderCandidates();
  }));
  const next = document.querySelector("#choose-candidate");
  next.disabled = state.selectedCandidate === null;
  next.addEventListener("click", () => renderSkillAllocation());
}

function renderSkillAllocation(existingRecord = null) {
  const candidate = existingRecord ? {
    sheet: existingRecord.sheet,
    base_skills: existingRecord.base_skills,
    skill_budget: existingRecord.skill_budget,
  } : state.draft.candidates[state.selectedCandidate];
  const bases = candidate.base_skills;
  const values = existingRecord ? existingRecord.sheet.skills : bases;
  const rows = Object.keys(values).sort((a, b) => a.localeCompare(b, "zh-CN")).map((name) => `<label class="skill-row" data-name="${esc(name)}"><span class="skill-label"><strong title="${esc(name)}">${esc(name)}</strong><span>基础 ${esc(bases[name] ?? 0)}</span></span><input class="skill-input" type="number" min="${esc(bases[name] ?? 0)}" max="100" value="${esc(values[name])}" data-skill="${esc(name)}"></label>`).join("");
  modalContent.innerHTML = `<div class="modal-body"><h2 class="modal-title">分配技能</h2>
    <div class="wizard-toolbar"><input class="search-input" id="skill-search" placeholder="搜索技能" aria-label="搜索技能"><div class="budget" id="skill-budget"><div class="budget-line"><span>技能点</span><strong><span id="spent">0</span> / ${candidate.skill_budget}</strong></div><div class="budget-track"><div class="budget-fill" id="budget-fill"></div></div></div></div>
    <div class="skill-grid" id="skill-grid">${rows}</div>
    <div class="form-footer"><button class="button primary" id="save-character" type="button">${icon("save")}永久保存</button></div>
  </div>`;
  refreshIcons();
  const updateBudget = () => {
    let spent = 0;
    document.querySelectorAll(".skill-input").forEach((input) => { spent += Math.max(0, Number(input.value) - Number(input.min)); });
    document.querySelector("#spent").textContent = spent;
    document.querySelector("#budget-fill").style.width = `${Math.min(100, spent / candidate.skill_budget * 100)}%`;
    document.querySelector("#skill-budget").classList.toggle("over", spent > candidate.skill_budget);
    document.querySelector("#save-character").disabled = spent > candidate.skill_budget;
  };
  document.querySelectorAll(".skill-input").forEach((input) => input.addEventListener("input", updateBudget));
  document.querySelector("#skill-search").addEventListener("input", (event) => {
    const term = event.target.value.trim();
    document.querySelectorAll(".skill-row").forEach((row) => { row.hidden = term && !row.dataset.name.includes(term); });
  });
  document.querySelector("#save-character").addEventListener("click", async () => {
    const skills = Object.fromEntries([...document.querySelectorAll(".skill-input")].map((input) => [input.dataset.skill, Number(input.value)]));
    try {
      if (existingRecord) {
        await api(`/api/characters/${existingRecord.id}/skills`, {method: "PUT", headers: {"Content-Type":"application/json"}, body: JSON.stringify({skills})});
      } else {
        await api("/api/characters", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({draft_id: state.draft.draft_id, candidate_index: state.selectedCandidate, skills})});
      }
      modal.close();
      await loadCharacters();
      notify("角色卡已永久保存");
    } catch (error) { notify(error.message, true); }
  });
  updateBudget();
}

function openSkillEditor(id) {
  const record = state.characters.find((item) => item.id === id);
  if (!record) return;
  modal.showModal();
  renderSkillAllocation(record);
}

function renderModules() {
  const rows = state.modules.map((item) => `<div class="collection-row"><div><div class="row-title">${esc(item.title)}</div><div class="row-meta">${esc(item.source_name)} · ${item.pages} 页</div></div><div class="row-meta">${item.sections} 个场景</div><span class="context-badge">Keeper 私密</span></div>`).join("");
  content.innerHTML = `<section class="page"><header class="page-header"><h1>模组库</h1></header>
    <form class="upload-band" id="module-upload"><div class="field"><label for="module-title">模组名称</label><input id="module-title" name="title" placeholder="默认使用文件名"></div><div class="field"><label for="module-file">PDF 文件</label><input class="file-field" id="module-file" name="file" type="file" accept="application/pdf" required></div><button class="button primary" type="submit">${icon("upload")}导入模组</button></form>
    ${rows ? `<div class="collection">${rows}</div>` : `<div class="empty-state"><div>${icon("book-open-text")}<h2>模组库为空</h2></div></div>`}
  </section>`;
  document.querySelector("#module-upload").addEventListener("submit", uploadModule);
}

async function uploadModule(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  form.classList.add("loading");
  try {
    await api("/api/modules/upload", {method: "POST", body: data});
    form.reset();
    await loadModules();
    notify("模组已导入");
  } catch (error) { notify(error.message, true); }
  finally { form.classList.remove("loading"); }
}

function renderGames() {
  const canCreate = state.characters.length && state.modules.length;
  const rows = state.games.map((game) => `<div class="collection-row"><div><div class="row-title">${esc(game.title)}</div><div class="row-meta">${esc(game.character.name)} · ${esc(game.module?.module || "无模组")}</div></div><div class="row-meta">${esc(game.module?.scene || "未开始")} · ${esc(game.module?.progress || "-")}</div><button class="button secondary open-game" data-id="${game.id}" type="button">${icon("play")}继续</button></div>`).join("");
  content.innerHTML = `<section class="page"><header class="page-header"><h1>战役</h1></header>
    <form class="new-game-band" id="new-game"><div class="field"><label for="game-character">角色卡</label><select id="game-character" name="character_id" required><option value="">选择角色</option>${state.characters.map((record) => `<option value="${record.id}">${esc(record.sheet.name)}</option>`).join("")}</select></div><div class="field"><label for="game-module">模组</label><select id="game-module" name="module_id" required><option value="">选择模组</option>${state.modules.map((item) => `<option value="${item.id}">${esc(item.title)}</option>`).join("")}</select></div><button class="button primary" type="submit" ${canCreate ? "" : "disabled"}>${icon("plus")}创建战役</button><div class="field"><label for="game-title">战役名称</label><input id="game-title" name="title" value="新战役" maxlength="80"></div></form>
    ${rows ? `<div class="collection">${rows}</div>` : `<div class="empty-state"><div>${icon("messages-square")}<h2>暂无战役</h2></div></div>`}
  </section>`;
  document.querySelector("#new-game").addEventListener("submit", createGame);
  document.querySelectorAll(".open-game").forEach((button) => button.addEventListener("click", () => openGame(button.dataset.id)));
}

async function createGame(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const game = await api("/api/games", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({title:form.get("title"), character_id:form.get("character_id"), module_id:form.get("module_id")})});
    state.games.unshift(game);
    state.activeGame = game;
    render();
  } catch (error) { notify(error.message, true); }
}

async function openGame(id) {
  try { state.activeGame = await api(`/api/games/${id}`); render(); }
  catch (error) { notify(error.message, true); }
}

function renderGame() {
  const game = state.activeGame;
  const sheet = game.character;
  const transcript = game.transcript || [];
  const skills = Object.entries(sheet.skills).filter(([, value]) => value >= 40).sort((a,b) => b[1]-a[1]).slice(0, 12);
  const progress = game.module?.progress || "1/1";
  const [current, total] = progress.split("/").map(Number);
  content.innerHTML = `<div class="game-layout">
    <aside class="game-panel game-aside"><h2>${esc(sheet.name)}</h2><div class="row-meta">${esc(sheet.age)} 岁</div><div class="vitals"><div class="vital"><span>HP</span><strong>${esc(derivedValue(sheet,"HP"))}</strong></div><div class="vital"><span>SAN</span><strong>${esc(derivedValue(sheet,"SAN"))}</strong></div><div class="vital"><span>MP</span><strong>${esc(derivedValue(sheet,"MP"))}</strong></div><div class="vital"><span>LUCK</span><strong>${esc(sheet.current?.luck ?? sheet.attributes.LUCK)}</strong></div></div><h3>主要技能</h3><div class="skill-list">${skills.map(([name,value]) => `<div><span>${esc(name)}</span><strong>${value}</strong></div>`).join("")}</div></aside>
    <section class="game-panel chat"><header class="chat-header"><button class="icon-button" id="back-games" type="button" aria-label="返回战役列表" title="返回">${icon("arrow-left")}</button><h1>${esc(game.title)}</h1><span class="row-meta">${esc(game.module?.scene || "")}</span></header>
      <div class="chat-log" id="chat-log">${transcript.length ? transcript.map((message) => `<article class="message ${message.role}"><div class="message-role">${message.role === "user" ? "调查员" : "Keeper"}</div><div class="message-content">${esc(message.content)}</div></article>`).join("") : `<div class="chat-empty"><div>${icon("lamp-desk")}<div>等待开场</div></div></div>`}</div>
      <form class="composer" id="composer"><textarea name="content" aria-label="调查员行动" placeholder="描述调查员的行动…" required></textarea><button class="icon-button" type="submit" aria-label="发送" title="发送">${icon("send")}</button></form>
    </section>
    <aside class="game-panel game-aside"><h2>${esc(game.module?.module || "模组")}</h2><div class="module-progress"><div class="progress-label"><span>${esc(game.module?.scene || "当前场景")}</span><span>${esc(progress)}</span></div><div class="progress-track"><div class="progress-fill" style="width:${Math.max(0, Math.min(100, current / total * 100))}%"></div></div></div><span class="context-badge">当前场景上下文</span><h3>模型</h3><div class="row-meta">${esc(state.status?.model || "-")}<br>${state.status?.context_window ? `${Number(state.status.context_window).toLocaleString()} context` : ""}</div></aside>
  </div>`;
  document.querySelector("#back-games").addEventListener("click", () => { state.activeGame = null; renderGames(); refreshIcons(); });
  document.querySelector("#composer").addEventListener("submit", sendMessage);
  const log = document.querySelector("#chat-log");
  log.scrollTop = log.scrollHeight;
}

async function sendMessage(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const textarea = form.querySelector("textarea");
  const text = textarea.value.trim();
  if (!text) return;
  form.classList.add("loading");
  textarea.value = "";
  try {
    const result = await api(`/api/games/${state.activeGame.id}/messages`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({content:text})});
    state.activeGame = result.game;
    renderGame();
    refreshIcons();
  } catch (error) { textarea.value = text; notify(error.message, true); form.classList.remove("loading"); }
}

async function loadCharacters() { state.characters = await api("/api/characters"); render(); }
async function loadModules() { state.modules = await api("/api/modules"); render(); }
async function loadGames() { state.games = await api("/api/games"); render(); }

async function bootstrap() {
  try {
    [state.status, state.characters, state.modules, state.games] = await Promise.all([
      api("/api/status"), api("/api/characters"), api("/api/modules"), api("/api/games"),
    ]);
    const provider = document.querySelector("#provider-status");
    provider.className = `provider-status ${state.status.configured ? "ready" : "error"}`;
    provider.innerHTML = `<span class="status-dot"></span><span>${esc(state.status.model)} · ${Number(state.status.context_window).toLocaleString()}</span>`;
    render();
  } catch (error) { notify(error.message, true); }
}

document.addEventListener("click", (event) => {
  const viewTarget = event.target.closest("[data-view]");
  if (viewTarget) setView(viewTarget.dataset.view);
});
document.querySelector(".modal-close").addEventListener("click", () => modal.close());
modal.addEventListener("click", (event) => { if (event.target === modal) modal.close(); });
bootstrap();
