function storedFlag(key) {
  try { return localStorage.getItem(key) === "true"; }
  catch (_) { return false; }
}

function storeFlag(key, value) {
  try { localStorage.setItem(key, String(value)); }
  catch (_) { /* Preferences remain available for the current page. */ }
}

const state = {
  view: "characters",
  status: null,
  occupations: [],
  characters: [],
  modules: [],
  games: [],
  activeGame: null,
  draft: null,
  selectedCandidate: null,
  occupationPreview: null,
  selectedOccupationSkills: [],
  editingModule: null,
  navigationCollapsed: storedFlag("keeper-navigation-collapsed"),
  investigatorCollapsed: storedFlag("keeper-investigator-collapsed"),
};

const content = document.querySelector("#content");
const modal = document.querySelector("#modal");
const modalContent = document.querySelector("#modal-content");
const toast = document.querySelector("#toast");

const ATTRIBUTE_LABELS = {
  STR: "力量",
  CON: "体质",
  DEX: "敏捷",
  APP: "外貌",
  POW: "意志",
  SIZ: "体型",
  INT: "智力",
  EDU: "教育",
  LUCK: "幸运",
};

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

function attributeLabel(name) {
  return `${ATTRIBUTE_LABELS[name] || name} | ${name}`;
}

function attributeTotal(sheet, includeLuck = true) {
  const names = Object.keys(ATTRIBUTE_LABELS).filter((name) => includeLuck || name !== "LUCK");
  return names.reduce((total, name) => total + Number(sheet.attributes[name] || 0), 0);
}

function attributesHTML(sheet, names = ["STR", "CON", "DEX", "POW", "INT", "EDU"]) {
  return `<div class="stat-line">${names.map((name) => `<div class="stat"><span>${attributeLabel(name)}</span><strong>${esc(sheet.attributes[name])}</strong></div>`).join("")}</div>`;
}

function renderNavigationState() {
  const shell = document.querySelector(".app-shell");
  const toggle = document.querySelector("#sidebar-toggle");
  shell.classList.toggle("sidebar-collapsed", state.navigationCollapsed);
  toggle.setAttribute("aria-expanded", String(!state.navigationCollapsed));
  toggle.setAttribute("aria-label", state.navigationCollapsed ? "展开主导航" : "收起主导航");
  toggle.title = state.navigationCollapsed ? "展开主导航" : "收起主导航";
  toggle.innerHTML = icon(state.navigationCollapsed ? "panel-left-open" : "panel-left-close");
  refreshIcons();
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
      <div><div class="row-title">${esc(sheet.name)}</div><div class="row-meta">${esc(sheet.age)} 岁 · ${esc(sheet.occupation?.name || "旧版未设职业")} · 永久角色卡</div><div class="row-meta">职业 ${esc(record.occupation_points_spent)}/${esc(record.occupation_point_budget)} · 兴趣 ${esc(record.interest_points_spent)}/${esc(record.interest_point_budget)}</div></div>
      ${attributesHTML(sheet)}
      <div class="row-actions"><button class="button edit-skills" data-id="${record.id}" type="button">${icon("sliders-horizontal")}技能</button><button class="icon-button danger delete-character" data-id="${record.id}" data-name="${esc(sheet.name)}" type="button" aria-label="删除角色卡 ${esc(sheet.name)}" title="删除角色卡">${icon("trash-2")}</button></div>
    </div>`;
  }).join("");
  content.innerHTML = `<section class="page">
    <header class="page-header"><h1>角色卡</h1><div class="page-actions"><button class="button primary" id="new-character" type="button">${icon("plus")}新建角色</button></div></header>
    ${rows ? `<div class="collection">${rows}</div>` : `<div class="empty-state"><div>${icon("contact-round")}<h2>角色库为空</h2><button class="button primary" id="empty-new-character" type="button">${icon("plus")}新建角色</button></div></div>`}
  </section>`;
  document.querySelector("#new-character")?.addEventListener("click", openCharacterWizard);
  document.querySelector("#empty-new-character")?.addEventListener("click", openCharacterWizard);
  document.querySelectorAll(".edit-skills").forEach((button) => button.addEventListener("click", () => openSkillEditor(button.dataset.id)));
  document.querySelectorAll(".delete-character").forEach((button) => button.addEventListener("click", () => deleteCharacter(button.dataset.id, button.dataset.name)));
}

async function deleteCharacter(id, name) {
  if (!window.confirm(`确定永久删除角色卡「${name}」吗？此操作无法撤销。`)) return;
  try {
    await api(`/api/characters/${id}`, {method: "DELETE"});
    state.characters = state.characters.filter((record) => record.id !== id);
    renderCharacters();
    refreshIcons();
    notify("角色卡已删除");
  } catch (error) { notify(error.message, true); }
}

function openCharacterWizard() {
  state.draft = null;
  state.selectedCandidate = null;
  state.occupationPreview = null;
  state.selectedOccupationSkills = [];
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
  const bars = ["STR","CON","DEX","APP","POW","SIZ","INT","EDU","LUCK"].map((name) => `<div class="attribute-row"><span>${attributeLabel(name)}</span><span class="bar-track"><span class="bar-fill" style="width:${Math.min(100, sheet.attributes[name])}%"></span></span><strong>${sheet.attributes[name]}</strong></div>`).join("");
  return `<button class="candidate${state.selectedCandidate === candidate.index ? " selected" : ""}" type="button" data-index="${candidate.index}">
    <h3>候选 ${candidate.index + 1}</h3><div class="attribute-bars">${bars}</div>
    <div class="derived-strip">HP ${esc(sheet.derived.HP)} · SAN ${esc(sheet.derived.SAN)}<br>DB ${esc(sheet.derived.DB)} · MOV ${esc(sheet.derived.MOV)}<br>属性总和（含幸运） ${attributeTotal(sheet)}<br>属性总和（不含幸运） ${attributeTotal(sheet, false)}</div>
  </button>`;
}

function renderCandidates() {
  modalContent.innerHTML = `<div class="modal-body"><h2 class="modal-title">选择属性</h2>
    <div class="candidate-grid">${state.draft.candidates.map(candidateCard).join("")}</div>
    <div class="form-footer"><button class="button primary" id="choose-candidate" type="button" disabled>${icon("arrow-right")}选择职业</button></div>
  </div>`;
  refreshIcons();
  document.querySelectorAll(".candidate").forEach((candidate) => candidate.addEventListener("click", () => {
    state.selectedCandidate = Number(candidate.dataset.index);
    renderCandidates();
  }));
  const next = document.querySelector("#choose-candidate");
  next.disabled = state.selectedCandidate === null;
  next.addEventListener("click", renderOccupationSelection);
}

function renderOccupationSelection() {
  const selectedId = state.occupationPreview?.id || "";
  const options = state.occupations.map((occupation) => `<option value="${occupation.id}" ${occupation.id === selectedId ? "selected" : ""}>${esc(occupation.name)}</option>`).join("");
  const preview = state.occupationPreview;
  const fixed = preview?.fixed_skills || [];
  const allSkills = preview ? Object.keys(preview.base_skills).filter((name) => name !== "克苏鲁神话") : [];
  const groups = preview ? preview.choice_groups.map((group, groupIndex) => `<div class="occupation-choice"><strong>组选技能：选择 ${group.count} 项</strong>${Array.from({length: group.count}, (_, slot) => `<select class="occupation-skill-select" data-kind="group" data-group="${groupIndex}" data-slot="${slot}" required><option value="">选择技能</option>${group.skills.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join("")}</select>`).join("")}</div>`).join("") : "";
  const free = preview ? Array.from({length: preview.free_choice_count}, (_, slot) => `<select class="occupation-skill-select" data-kind="free" data-slot="${slot}" required><option value="">选择任意个人或时代特长</option>${allSkills.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join("")}</select>`).join("") : "";
  modalContent.innerHTML = `<div class="modal-body"><h2 class="modal-title">选择职业</h2>
    <div class="field"><label for="occupation-search">查找职业</label><input id="occupation-search" placeholder="输入名称筛选"></div>
    <div class="field"><label for="occupation-select">具体职业</label><select id="occupation-select"><option value="">选择职业</option>${options}</select></div>
    ${preview ? `<section class="occupation-detail"><div class="occupation-head"><div><h3>${esc(preview.name)}</h3><div class="row-meta">信用评级 ${preview.credit_min}-${preview.credit_max} · ${esc(preview.point_formula_label)}</div></div><strong>${preview.occupation_point_budget} 职业点</strong></div><p>${esc(preview.skill_template)}</p><div class="occupation-fixed"><strong>固定本职技能</strong><div>${fixed.map((name) => `<span class="skill-chip">${esc(name)}</span>`).join("")}</div></div>${groups}${preview.free_choice_count ? `<div class="occupation-choice"><strong>任意特长：选择 ${preview.free_choice_count} 项</strong>${free}</div>` : ""}</section>` : ""}
    <div class="form-footer"><button class="button primary" id="confirm-occupation" type="button" ${preview ? "" : "disabled"}>${icon("arrow-right")}分配技能点</button></div>
  </div>`;
  refreshIcons();
  const select = document.querySelector("#occupation-select");
  document.querySelector("#occupation-search").addEventListener("input", (event) => {
    const term = event.target.value.trim();
    [...select.options].forEach((option, index) => { if (index) option.hidden = term && !option.textContent.includes(term); });
  });
  select.addEventListener("change", async () => {
    if (!select.value) return;
    try {
      state.occupationPreview = await api(`/api/character-drafts/${state.draft.draft_id}/candidates/${state.selectedCandidate}/occupations/${select.value}`);
      renderOccupationSelection();
    } catch (error) { notify(error.message, true); }
  });
  document.querySelector("#confirm-occupation").addEventListener("click", () => {
    const selected = [...fixed];
    const selectors = [...document.querySelectorAll(".occupation-skill-select")];
    if (selectors.some((item) => !item.value)) { notify("请完成所有本职技能选择", true); return; }
    selectors.forEach((item) => selected.push(item.value));
    if (new Set(selected).size !== selected.length) { notify("本职技能不能重复选择", true); return; }
    state.selectedOccupationSkills = selected;
    renderSkillAllocation();
  });
}

function renderSkillAllocation(existingRecord = null) {
  if (existingRecord && !existingRecord.sheet.occupation?.id) { renderLegacySkillAllocation(existingRecord); return; }
  const candidate = existingRecord ? {
    sheet: existingRecord.sheet,
    base_skills: existingRecord.base_skills,
    occupation_point_budget: existingRecord.occupation_point_budget,
    interest_point_budget: existingRecord.interest_point_budget,
  } : state.draft.candidates[state.selectedCandidate];
  const occupation = existingRecord
    ? {...state.occupations.find((item) => item.id === existingRecord.sheet.occupation.id), occupation_point_budget: existingRecord.occupation_point_budget, interest_point_budget: existingRecord.interest_point_budget}
    : state.occupationPreview;
  const mainSkills = new Set(existingRecord ? existingRecord.sheet.occupation.skills : state.selectedOccupationSkills);
  const occupationValues = existingRecord ? existingRecord.sheet.allocation.occupation_points : {"信用评级": occupation.credit_min};
  const interestValues = existingRecord ? existingRecord.sheet.allocation.interest_points : {};
  const bases = candidate.base_skills;
  const rows = Object.keys(bases).sort((a, b) => a.localeCompare(b, "zh-CN")).map((name) => {
    const main = mainSkills.has(name);
    const configuredCap = main ? 70 : 60;
    const cap = Math.max(bases[name], configuredCap);
    const locked = name === "克苏鲁神话";
    return `<div class="skill-row allocation-row${main ? " main-skill" : ""}" data-name="${esc(name)}" data-base="${bases[name]}" data-cap="${cap}"><span class="skill-label"><strong title="${esc(name)}">${esc(name)}</strong><span>基础 ${bases[name]} · ${main ? "本职" : "非本职"}上限 ${cap}</span></span><label><span>职业</span><input class="point-input occupation-input" type="number" min="0" value="${occupationValues[name] || 0}" data-skill="${esc(name)}" ${main && !locked ? "" : "disabled"}></label><label><span>兴趣</span><input class="point-input interest-input" type="number" min="0" value="${interestValues[name] || 0}" data-skill="${esc(name)}" ${locked ? "disabled" : ""}></label><strong class="skill-total">${bases[name]}</strong></div>`;
  }).join("");
  modalContent.innerHTML = `<div class="modal-body"><h2 class="modal-title">${esc(occupation.name)}技能分配</h2>
    <div class="wizard-toolbar"><input class="search-input" id="skill-search" placeholder="搜索技能" aria-label="搜索技能"><div class="dual-budget"><div class="budget" id="occupation-budget"><div class="budget-line"><span>职业点</span><strong><span id="occupation-spent">0</span> / ${occupation.occupation_point_budget}</strong></div><div class="budget-track"><div class="budget-fill"></div></div></div><div class="budget" id="interest-budget"><div class="budget-line"><span>兴趣点</span><strong><span id="interest-spent">0</span> / ${occupation.interest_point_budget}</strong></div><div class="budget-track"><div class="budget-fill"></div></div></div></div></div>
    <div class="allocation-head"><span>技能</span><span>职业点</span><span>兴趣点</span><span>最终值</span></div><div class="skill-grid allocation-grid" id="skill-grid">${rows}</div>
    <div class="form-footer"><span class="row-meta">本职上限 70 · 非本职上限 60 · 信用评级 ${occupation.credit_min}-${occupation.credit_max}</span><button class="button primary" id="save-character" type="button">${icon("save")}永久保存</button></div>
  </div>`;
  refreshIcons();
  const updateBudget = () => {
    let occupationSpent = 0;
    let interestSpent = 0;
    let invalid = false;
    document.querySelectorAll(".allocation-row").forEach((row) => {
      const occupational = Number(row.querySelector(".occupation-input").value || 0);
      const interest = Number(row.querySelector(".interest-input").value || 0);
      occupationSpent += occupational;
      interestSpent += interest;
      const total = Number(row.dataset.base) + occupational + interest;
      row.querySelector(".skill-total").textContent = total;
      const over = total > Number(row.dataset.cap) || occupational < 0 || interest < 0;
      row.classList.toggle("invalid", over);
      invalid ||= over;
    });
    const creditOccupation = Number(document.querySelector('.occupation-input[data-skill="信用评级"]').value || 0);
    const creditTotal = Number(document.querySelector('.skill-row[data-name="信用评级"] .skill-total').textContent);
    invalid ||= creditOccupation < occupation.credit_min || creditTotal > occupation.credit_max;
    for (const [kind, spent, budget] of [["occupation", occupationSpent, occupation.occupation_point_budget], ["interest", interestSpent, occupation.interest_point_budget]]) {
      document.querySelector(`#${kind}-spent`).textContent = spent;
      const box = document.querySelector(`#${kind}-budget`);
      box.querySelector(".budget-fill").style.width = `${Math.min(100, spent / budget * 100)}%`;
      box.classList.toggle("over", spent > budget);
      invalid ||= spent > budget;
    }
    document.querySelector("#save-character").disabled = invalid;
  };
  document.querySelectorAll(".point-input").forEach((input) => input.addEventListener("input", updateBudget));
  document.querySelector("#skill-search").addEventListener("input", (event) => {
    const term = event.target.value.trim();
    document.querySelectorAll(".skill-row").forEach((row) => { row.hidden = term && !row.dataset.name.includes(term); });
  });
  document.querySelector("#save-character").addEventListener("click", async () => {
    const occupation_points = Object.fromEntries([...document.querySelectorAll(".occupation-input:not(:disabled)")].map((input) => [input.dataset.skill, Number(input.value)]));
    const interest_points = Object.fromEntries([...document.querySelectorAll(".interest-input:not(:disabled)")].map((input) => [input.dataset.skill, Number(input.value)]));
    const payload = {occupation_skills: [...mainSkills], occupation_points, interest_points};
    try {
      if (existingRecord) {
        await api(`/api/characters/${existingRecord.id}/skills`, {method: "PUT", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload)});
      } else {
        await api("/api/characters", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({...payload, draft_id: state.draft.draft_id, candidate_index: state.selectedCandidate, occupation_id: occupation.id})});
      }
      modal.close();
      await loadCharacters();
      notify("角色卡已永久保存");
    } catch (error) { notify(error.message, true); }
  });
  updateBudget();
}

function renderLegacySkillAllocation(existingRecord) {
  const bases = existingRecord.base_skills;
  const values = existingRecord.sheet.skills;
  const rows = Object.keys(values).sort((a, b) => a.localeCompare(b, "zh-CN")).map((name) => `<label class="skill-row" data-name="${esc(name)}"><span class="skill-label"><strong>${esc(name)}</strong><span>基础 ${esc(bases[name] ?? 0)}</span></span><input class="skill-input" type="number" min="${esc(bases[name] ?? 0)}" max="100" value="${esc(values[name])}" data-skill="${esc(name)}"></label>`).join("");
  modalContent.innerHTML = `<div class="modal-body"><h2 class="modal-title">旧版技能分配</h2><div class="wizard-toolbar"><input class="search-input" id="skill-search" placeholder="搜索技能"><div class="budget" id="skill-budget"><div class="budget-line"><span>技能点</span><strong><span id="spent">0</span> / ${existingRecord.skill_budget}</strong></div></div></div><div class="skill-grid">${rows}</div><div class="form-footer"><button class="button primary" id="save-character" type="button">${icon("save")}保存</button></div></div>`;
  refreshIcons();
  const update = () => { let spent = 0; document.querySelectorAll(".skill-input").forEach((input) => { spent += Math.max(0, Number(input.value) - Number(input.min)); }); document.querySelector("#spent").textContent = spent; document.querySelector("#save-character").disabled = spent > existingRecord.skill_budget; };
  document.querySelectorAll(".skill-input").forEach((input) => input.addEventListener("input", update));
  document.querySelector("#skill-search").addEventListener("input", (event) => { const term = event.target.value.trim(); document.querySelectorAll(".skill-row").forEach((row) => { row.hidden = term && !row.dataset.name.includes(term); }); });
  document.querySelector("#save-character").addEventListener("click", async () => { const skills = Object.fromEntries([...document.querySelectorAll(".skill-input")].map((input) => [input.dataset.skill, Number(input.value)])); try { await api(`/api/characters/${existingRecord.id}/skills`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({skills})}); modal.close(); await loadCharacters(); notify("角色卡已保存"); } catch (error) { notify(error.message, true); } });
  update();
}

function openSkillEditor(id) {
  const record = state.characters.find((item) => item.id === id);
  if (!record) return;
  modal.showModal();
  renderSkillAllocation(record);
}

function renderModules() {
  const rows = state.modules.map((item) => `<div class="collection-row module-row"><div><div class="row-title">${esc(item.title)}</div><div class="row-meta">${esc(item.source_name)} · ${item.pages} 页</div></div><span class="context-badge">Keeper 私密</span><div class="row-actions"><button class="button edit-module" data-id="${item.id}" type="button">${icon("file-pen-line")}检查 / 编辑</button><button class="icon-button danger delete-module" data-id="${item.id}" data-title="${esc(item.title)}" type="button" aria-label="删除模组 ${esc(item.title)}" title="删除模组">${icon("trash-2")}</button></div></div>`).join("");
  content.innerHTML = `<section class="page"><header class="page-header"><h1>模组库</h1></header>
    <form class="upload-band" id="module-upload"><div class="field"><label for="module-title">模组名称</label><input id="module-title" name="title" placeholder="默认使用文件名"></div><div class="field"><label for="module-file">PDF 文件</label><input class="file-field" id="module-file" name="file" type="file" accept="application/pdf" required></div><button class="button primary" type="submit">${icon("upload")}导入模组</button></form>
    ${rows ? `<div class="collection">${rows}</div>` : `<div class="empty-state"><div>${icon("book-open-text")}<h2>模组库为空</h2></div></div>`}
  </section>`;
  document.querySelector("#module-upload").addEventListener("submit", uploadModule);
  document.querySelectorAll(".edit-module").forEach((button) => button.addEventListener("click", () => openModuleEditor(button.dataset.id)));
  document.querySelectorAll(".delete-module").forEach((button) => button.addEventListener("click", () => deleteModule(button.dataset.id, button.dataset.title)));
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

function moduleSectionEditorHTML(section, index) {
  return `<details class="module-editor-section" data-index="${index}" ${index === 0 ? "open" : ""}><summary><span>${esc(section.keeper_title || section.id)}</span><span class="row-meta">第 ${esc(section.page_start)}-${esc(section.page_end)} 页</span></summary><div class="module-section-fields">
    <div class="form-grid module-meta-grid"><div class="field"><label>场景 ID</label><input data-field="id" value="${esc(section.id)}" maxlength="100" required></div><div class="field"><label>Keeper 标题</label><input data-field="keeper_title" value="${esc(section.keeper_title)}" maxlength="200" required></div><div class="field"><label>玩家可见标题</label><input data-field="public_title" value="${esc(section.public_title)}" maxlength="200" required></div><div class="field"><label>起始页</label><input data-field="page_start" type="number" min="0" value="${esc(section.page_start)}" required></div><div class="field"><label>结束页</label><input data-field="page_end" type="number" min="0" value="${esc(section.page_end)}" required></div></div>
    <div class="field"><label>Keeper 原文</label><textarea data-field="text" rows="10" required>${esc(section.text)}</textarea></div>
    <div class="module-list-grid"><div class="field"><label>推进目标（每行一项）</label><textarea data-field="objectives" rows="4">${esc((section.objectives || []).join("\n"))}</textarea></div><div class="field"><label>显式秘密（每行一项）</label><textarea data-field="secrets" rows="4">${esc((section.secrets || []).join("\n"))}</textarea></div></div>
    <div class="module-section-actions"><button class="button remove-module-section" data-index="${index}" type="button">${icon("trash-2")}删除场景</button></div>
  </div></details>`;
}

function splitModuleLines(value) {
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function collectModuleEditor() {
  return {
    title: document.querySelector("#edit-module-title").value.trim(),
    source_name: document.querySelector("#edit-module-source").value.trim(),
    sections: [...document.querySelectorAll(".module-editor-section")].map((element) => ({
      id: element.querySelector('[data-field="id"]').value.trim(),
      keeper_title: element.querySelector('[data-field="keeper_title"]').value.trim(),
      public_title: element.querySelector('[data-field="public_title"]').value.trim(),
      page_start: Number(element.querySelector('[data-field="page_start"]').value),
      page_end: Number(element.querySelector('[data-field="page_end"]').value),
      text: element.querySelector('[data-field="text"]').value.trim(),
      objectives: splitModuleLines(element.querySelector('[data-field="objectives"]').value),
      secrets: splitModuleLines(element.querySelector('[data-field="secrets"]').value),
    })),
  };
}

function renderModuleEditor() {
  const module = state.editingModule.module;
  modalContent.innerHTML = `<form class="modal-body" id="module-editor"><h2 class="modal-title">检查与编辑模组</h2><div class="module-editor-notice">Keeper 私密内容 · 修改仅影响之后创建的战役</div><div class="form-grid module-header-grid"><div class="field"><label for="edit-module-title">模组名称</label><input id="edit-module-title" value="${esc(module.title)}" maxlength="200" required></div><div class="field"><label for="edit-module-source">来源文件</label><input id="edit-module-source" value="${esc(module.source_name)}" maxlength="260"></div></div><div class="module-editor-toolbar"><strong>场景内容</strong><button class="button" id="add-module-section" type="button">${icon("plus")}添加场景</button></div><div class="module-sections">${module.sections.map(moduleSectionEditorHTML).join("")}</div><div class="form-footer"><button class="button primary" type="submit">${icon("save")}保存模组</button></div></form>`;
  refreshIcons();
  document.querySelector("#module-editor").addEventListener("submit", saveModuleEditor);
  document.querySelector("#add-module-section").addEventListener("click", () => {
    const current = collectModuleEditor();
    const used = new Set(current.sections.map((section) => section.id));
    let number = current.sections.length + 1;
    while (used.has(`scene-${String(number).padStart(3, "0")}`)) number += 1;
    current.sections.push({id: `scene-${String(number).padStart(3, "0")}`, keeper_title: "新场景", public_title: "当前场景", page_start: 0, page_end: 0, text: "待补充", objectives: [], secrets: []});
    state.editingModule.module = {...state.editingModule.module, ...current};
    renderModuleEditor();
  });
  document.querySelectorAll(".remove-module-section").forEach((button) => button.addEventListener("click", () => {
    const current = collectModuleEditor();
    if (current.sections.length === 1) { notify("模组至少需要一个场景", true); return; }
    current.sections.splice(Number(button.dataset.index), 1);
    state.editingModule.module = {...state.editingModule.module, ...current};
    renderModuleEditor();
  }));
}

async function openModuleEditor(id) {
  try {
    state.editingModule = await api(`/api/modules/${id}`);
    renderModuleEditor();
    modal.showModal();
  } catch (error) { notify(error.message, true); }
}

async function saveModuleEditor(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = collectModuleEditor();
  form.classList.add("loading");
  try {
    await api(`/api/modules/${state.editingModule.id}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    state.editingModule = null;
    modal.close();
    await loadModules();
    notify("模组已保存");
  } catch (error) { notify(error.message, true); form.classList.remove("loading"); }
}

async function deleteModule(id, title) {
  if (!window.confirm(`确定永久删除模组「${title}」吗？该 Keeper 私密内容将无法恢复。`)) return;
  try {
    await api(`/api/modules/${id}`, {method: "DELETE"});
    state.modules = state.modules.filter((item) => item.id !== id);
    renderModules();
    refreshIcons();
    notify("模组已删除");
  } catch (error) { notify(error.message, true); }
}

function renderGames() {
  const canCreate = state.characters.length && state.modules.length;
  const rows = state.games.map((game) => `<div class="collection-row"><div><div class="row-title">${esc(game.title)}</div><div class="row-meta">${esc(game.character.name)} · ${esc(game.module?.module || "无模组")}</div></div><span class="context-badge">进行中</span><div class="row-actions"><button class="button secondary open-game" data-id="${game.id}" type="button">${icon("play")}继续</button><button class="icon-button danger delete-game" data-id="${game.id}" data-title="${esc(game.title)}" type="button" aria-label="删除战役 ${esc(game.title)}" title="删除战役">${icon("trash-2")}</button></div></div>`).join("");
  content.innerHTML = `<section class="page"><header class="page-header"><h1>战役</h1></header>
    <form class="new-game-band" id="new-game"><div class="field"><label for="game-character">角色卡</label><select id="game-character" name="character_id" required><option value="">选择角色</option>${state.characters.map((record) => `<option value="${record.id}">${esc(record.sheet.name)}</option>`).join("")}</select></div><div class="field"><label for="game-module">模组</label><select id="game-module" name="module_id" required><option value="">选择模组</option>${state.modules.map((item) => `<option value="${item.id}">${esc(item.title)}</option>`).join("")}</select></div><button class="button primary" type="submit" ${canCreate ? "" : "disabled"}>${icon("plus")}创建战役</button><div class="field"><label for="game-title">战役名称</label><input id="game-title" name="title" value="新战役" maxlength="80"></div></form>
    ${rows ? `<div class="collection">${rows}</div>` : `<div class="empty-state"><div>${icon("messages-square")}<h2>暂无战役</h2></div></div>`}
  </section>`;
  document.querySelector("#new-game").addEventListener("submit", createGame);
  document.querySelectorAll(".open-game").forEach((button) => button.addEventListener("click", () => openGame(button.dataset.id)));
  document.querySelectorAll(".delete-game").forEach((button) => button.addEventListener("click", () => deleteGame(button.dataset.id, button.dataset.title)));
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

async function deleteGame(id, title) {
  if (!window.confirm(`确定永久删除战役「${title}」吗？角色卡和模组不会被删除。`)) return;
  try {
    await api(`/api/games/${id}`, {method: "DELETE"});
    state.games = state.games.filter((game) => game.id !== id);
    renderGames();
    refreshIcons();
    notify("战役已删除");
  } catch (error) { notify(error.message, true); }
}

function renderGame() {
  const game = state.activeGame;
  const sheet = game.character;
  const transcript = game.transcript || [];
  const skills = Object.entries(sheet.skills).filter(([, value]) => value >= 40).sort((a,b) => b[1]-a[1]).slice(0, 12);
  content.innerHTML = `<div class="game-layout${state.investigatorCollapsed ? " investigator-collapsed" : ""}">
    <aside class="game-panel game-aside investigator-panel"><div class="aside-toolbar"><button class="icon-button investigator-toggle" id="investigator-toggle" type="button" aria-label="${state.investigatorCollapsed ? "展开调查员详情" : "收起调查员详情"}" title="${state.investigatorCollapsed ? "展开调查员详情" : "收起调查员详情"}" aria-expanded="${!state.investigatorCollapsed}">${icon(state.investigatorCollapsed ? "panel-left-open" : "panel-left-close")}</button></div><div class="investigator-details"><h2>${esc(sheet.name)}</h2><div class="row-meta">${esc(sheet.age)} 岁</div><div class="vitals"><div class="vital"><span>HP</span><strong>${esc(derivedValue(sheet,"HP"))}</strong></div><div class="vital"><span>SAN</span><strong>${esc(derivedValue(sheet,"SAN"))}</strong></div><div class="vital"><span>MP</span><strong>${esc(derivedValue(sheet,"MP"))}</strong></div><div class="vital"><span>幸运 | LUCK</span><strong>${esc(sheet.current?.luck ?? sheet.attributes.LUCK)}</strong></div></div><h3>主要技能</h3><div class="skill-list">${skills.map(([name,value]) => `<div><span>${esc(name)}</span><strong>${value}</strong></div>`).join("")}</div></div></aside>
    <section class="game-panel chat"><header class="chat-header"><button class="icon-button" id="back-games" type="button" aria-label="返回战役列表" title="返回">${icon("arrow-left")}</button><h1>${esc(game.title)}</h1></header>
      <div class="chat-log" id="chat-log">${transcript.length ? transcript.map((message) => `<article class="message ${message.role}"><div class="message-role">${message.role === "user" ? "调查员" : "Keeper"}</div><div class="message-content">${esc(message.content)}</div></article>`).join("") : `<div class="chat-empty"><div>${icon("lamp-desk")}<div>等待开场</div></div></div>`}</div>
      <form class="composer" id="composer"><textarea name="content" aria-label="调查员行动" placeholder="描述调查员的行动…" required></textarea><button class="icon-button" type="submit" aria-label="发送" title="发送">${icon("send")}</button></form>
    </section>
    <aside class="game-panel game-aside"><h2>${esc(game.module?.module || "模组")}</h2><span class="context-badge">模组已载入</span><h3>模型</h3><div class="row-meta">${esc(state.status?.model || "-")}<br>${state.status?.context_window ? `${Number(state.status.context_window).toLocaleString()} context` : ""}</div></aside>
  </div>`;
  document.querySelector("#back-games").addEventListener("click", () => { state.activeGame = null; renderGames(); refreshIcons(); });
  document.querySelector("#investigator-toggle").addEventListener("click", () => {
    state.investigatorCollapsed = !state.investigatorCollapsed;
    storeFlag("keeper-investigator-collapsed", state.investigatorCollapsed);
    renderGame();
    refreshIcons();
  });
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
    [state.status, state.occupations, state.characters, state.modules, state.games] = await Promise.all([
      api("/api/status"), api("/api/occupations"), api("/api/characters"), api("/api/modules"), api("/api/games"),
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
document.querySelector("#sidebar-toggle").addEventListener("click", () => {
  state.navigationCollapsed = !state.navigationCollapsed;
  storeFlag("keeper-navigation-collapsed", state.navigationCollapsed);
  renderNavigationState();
});
document.querySelector(".modal-close").addEventListener("click", () => modal.close());
modal.addEventListener("click", (event) => { if (event.target === modal) modal.close(); });
renderNavigationState();
bootstrap();
