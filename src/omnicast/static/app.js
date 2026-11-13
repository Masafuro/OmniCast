const SAMPLE_SCRIPT = `# OmniCast サンプル台本
@Alice: こんにちは、OmniCast へようこそ！今日は台本からポッドキャストを作るデモをお送りします。
@Bob: よろしくお願いします。気になるセリフだけ後からリテイクしたり、間の秒数を調整できるのが便利ですね。
@Alice: そうなんです。まずは一括 Generate を押して、全体を聴きながら調整してみてください！`;

const SAMPLE_SCRIPT_EN = `# OmniCast English Sample Script
@Alice: Welcome back to OmniCast! Today we're demonstrating how easy it is to build a multi-speaker podcast from a simple script.
@Bob: Glad to be here! What I love is that you can retake a single line, switch takes, and fine-tune the pauses right in the browser.
@Carol: And once you lock in a character's base voice in the Cast tab, every line stays remarkably consistent.`;

const DESIGN_SAMPLE_JA = "こんにちは。新しいキャラクターのテスト音声です。よろしくお願いします。";
const DESIGN_SAMPLE_EN = "Hello everyone! I'm testing a brand new voice profile for OmniCast Studio.";
const CLONE_TEST_JA = "なるほど、この声なら長編のポッドキャストでも安定して聴けますね！";
const CLONE_TEST_EN = "Exactly! With a solid reference voice, every single line sounds natural and consistent.";

const STATUS_LABEL = {
  unbuilt: "未生成",
  dirty: "要再生成",
  ready: "準備完了",
  locked: "ロック中",
};

const state = {
  activeTab: "studio",
  characters: [],
  designOptions: {},
  selectedVoiceId: null,
  designPreviews: [],
  projects: [],
  currentProject: null,
  isBusy: false,
  playingAll: false,
  audioCtx: null,
  activeSources: [],
  playTimers: [],
  singleAudio: null,
};

const el = {
  tabStudio: document.getElementById("tab-studio"),
  tabCast: document.getElementById("tab-cast"),
  studioProjectBar: document.getElementById("studio-project-bar"),
  studioActionBar: document.getElementById("studio-action-bar"),
  studioView: document.getElementById("studio-view"),
  castView: document.getElementById("cast-view"),
  healthPill: document.getElementById("health-pill"),
  projectSelect: document.getElementById("project-select"),
  btnNewProject: document.getElementById("btn-new-project"),
  btnDeleteProject: document.getElementById("btn-delete-project"),
  btnOpenImport: document.getElementById("btn-open-import"),
  btnExportScript: document.getElementById("btn-export-script"),
  btnGenerateAll: document.getElementById("btn-generate-all"),
  btnPlayAll: document.getElementById("btn-play-all"),
  btnStopAll: document.getElementById("btn-stop-all"),
  btnExportWav: document.getElementById("btn-export-wav"),
  btnExportMp3: document.getElementById("btn-export-mp3"),
  settingsBar: document.getElementById("project-settings"),
  settingTitle: document.getElementById("setting-title"),
  settingLang: document.getElementById("setting-lang"),
  settingTurnPause: document.getElementById("setting-turn-pause"),
  settingTrim: document.getElementById("setting-trim"),
  settingNorm: document.getElementById("setting-norm"),
  statusMessage: document.getElementById("status-message"),
  emptyState: document.getElementById("empty-state"),
  btnCreateSample: document.getElementById("btn-create-sample"),
  btnCreateSampleEn: document.getElementById("btn-create-sample-en"),
  btnCreateBlank: document.getElementById("btn-create-blank"),
  blocksContainer: document.getElementById("blocks-container"),
  bottomAddWrap: document.getElementById("bottom-add-wrap"),
  btnAddBlockEnd: document.getElementById("btn-add-block-end"),
  importDialog: document.getElementById("import-dialog"),
  btnCloseImport: document.getElementById("btn-close-import"),
  importCharsHelp: document.getElementById("import-chars-help"),
  importTextarea: document.getElementById("import-textarea"),
  importWarnings: document.getElementById("import-warnings"),
  btnFillSample: document.getElementById("btn-fill-sample"),
  btnFillSampleEn: document.getElementById("btn-fill-sample-en"),
  btnConfirmImport: document.getElementById("btn-confirm-import"),
  // Cast elements
  voiceList: document.getElementById("voice-list"),
  btnOpenVoiceImport: document.getElementById("btn-open-voice-import"),
  btnNewVoice: document.getElementById("btn-new-voice"),
  voiceEditorTitle: document.getElementById("voice-editor-title"),
  voiceModeBadge: document.getElementById("voice-mode-badge"),
  castStatusMessage: document.getElementById("cast-status-message"),
  btnExportVoice: document.getElementById("btn-export-voice"),
  btnDeleteVoice: document.getElementById("btn-delete-voice"),
  voiceImportDialog: document.getElementById("voice-import-dialog"),
  btnCloseVoiceImport: document.getElementById("btn-close-voice-import"),
  voiceImportFile: document.getElementById("voice-import-file"),
  voiceImportOverwrite: document.getElementById("voice-import-overwrite"),
  btnConfirmVoiceImport: document.getElementById("btn-confirm-voice-import"),
  vName: document.getElementById("v-name"),
  vRole: document.getElementById("v-role"),
  vLang: document.getElementById("v-lang"),
  vSpeed: document.getElementById("v-speed"),
  vInstruct: document.getElementById("v-instruct"),
  vRefText: document.getElementById("v-reftext"),
  btnSaveVoice: document.getElementById("btn-save-voice"),
  vRefActions: document.getElementById("v-ref-actions"),
  vRefStatus: document.getElementById("v-ref-status"),
  vGender: document.getElementById("v-gender"),
  vAge: document.getElementById("v-age"),
  vPitch: document.getElementById("v-pitch"),
  vStyle: document.getElementById("v-style"),
  vAccent: document.getElementById("v-accent"),
  vDialect: document.getElementById("v-dialect"),
  btnSaveDesignAttrs: document.getElementById("btn-save-design-attrs"),
  designPreviewText: document.getElementById("design-preview-text"),
  btnDesignPreview: document.getElementById("btn-design-preview"),
  btnDesignSampleJa: document.getElementById("btn-design-sample-ja"),
  btnDesignSampleEn: document.getElementById("btn-design-sample-en"),
  btnClearDesignPreviews: document.getElementById("btn-clear-design-previews"),
  designPreviewList: document.getElementById("design-preview-list"),
  vUploadFile: document.getElementById("v-upload-file"),
  btnUploadRef: document.getElementById("btn-upload-ref"),
  cloneTestText: document.getElementById("clone-test-text"),
  cloneTestInstruct: document.getElementById("clone-test-instruct"),
  btnCloneTest: document.getElementById("btn-clone-test"),
  btnCloneSampleJa: document.getElementById("btn-clone-sample-ja"),
  btnCloneSampleEn: document.getElementById("btn-clone-sample-en"),
  cloneTestResult: document.getElementById("clone-test-result"),
};

function setStatus(msg) {
  el.statusMessage.textContent = msg || "";
}

function setCastStatus(msg) {
  el.castStatusMessage.textContent = msg || "";
}

async function apiFetch(url, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = isFormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {
      // ignore JSON parse failure
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function getSelectedTake(block) {
  if (!block.selected_take_id) return null;
  return block.takes.find((t) => t.id === block.selected_take_id) || null;
}

function takeUrl(projectId, filename) {
  return `/api/projects/${encodeURIComponent(projectId)}/takes/${encodeURIComponent(filename)}`;
}

async function switchTab(tab) {
  state.activeTab = tab;
  const isStudio = tab === "studio";
  el.tabStudio.classList.toggle("active", isStudio);
  el.tabCast.classList.toggle("active", !isStudio);
  el.studioProjectBar.classList.toggle("hidden", !isStudio);
  el.studioActionBar.classList.toggle("hidden", !isStudio);
  el.studioView.classList.toggle("hidden", !isStudio);
  el.castView.classList.toggle("hidden", isStudio);

  if (isStudio) {
    await refreshVoices();
    if (state.currentProject) {
      await loadProject(state.currentProject.id);
    } else {
      renderProject();
    }
  } else {
    stopAllPlayback();
    el.settingsBar.classList.add("hidden");
    await refreshVoices();
    renderCastView();
  }
}

async function refreshHealth() {
  try {
    const info = await apiFetch("/api/health");
    const ov = info.omnivoice || {};
    if (ov.mode === "mock") {
      el.healthPill.textContent = "Mock Mode";
      el.healthPill.className = "pill pill-dirty";
    } else {
      el.healthPill.textContent = `OmniVoice: ${ov.url}`;
      el.healthPill.className = "pill pill-ready";
    }
  } catch (err) {
    el.healthPill.textContent = `接続エラー: ${err.message}`;
    el.healthPill.className = "pill pill-dirty";
  }
}

async function refreshVoices() {
  state.characters = await apiFetch("/api/voices");
  if (!state.selectedVoiceId || !state.characters.some((v) => v.id === state.selectedVoiceId)) {
    state.selectedVoiceId = state.characters[0]?.id || null;
  }
  const names = state.characters.map((v) => v.name).join(", ");
  el.importCharsHelp.textContent = `使用可能キャラ: ${names}（# 始まりはコメント）`;
}

async function refreshProjects(selectId = null) {
  state.projects = await apiFetch("/api/projects");
  el.projectSelect.innerHTML = "";
  for (const proj of state.projects) {
    const opt = document.createElement("option");
    opt.value = proj.id;
    opt.textContent = `${proj.title} (${proj.block_count})`;
    el.projectSelect.appendChild(opt);
  }

  const targetId =
    selectId ||
    (state.currentProject && state.projects.some((p) => p.id === state.currentProject.id)
      ? state.currentProject.id
      : state.projects[0]?.id);

  if (targetId) {
    el.projectSelect.value = targetId;
    await loadProject(targetId);
  } else {
    state.currentProject = null;
    renderProject();
  }
}

async function loadProject(projectId) {
  stopAllPlayback();
  state.currentProject = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`);
  renderProject();
}

function renderProject() {
  const proj = state.currentProject;
  const hasProj = Boolean(proj);
  const isStudio = state.activeTab === "studio";

  el.settingsBar.classList.toggle("hidden", !hasProj || !isStudio);
  el.emptyState.classList.toggle("hidden", hasProj);
  el.bottomAddWrap.classList.toggle("hidden", !hasProj);
  el.btnDeleteProject.disabled = !hasProj;
  el.btnOpenImport.disabled = !hasProj;
  el.btnExportScript.disabled = !hasProj;
  el.btnGenerateAll.disabled = !hasProj || state.isBusy;
  el.btnPlayAll.disabled = !hasProj;
  el.btnExportWav.disabled = !hasProj || state.isBusy;
  el.btnExportMp3.disabled = !hasProj || state.isBusy;

  if (!proj) {
    el.blocksContainer.innerHTML = "";
    return;
  }

  el.settingTitle.value = proj.title;
  el.settingLang.value = proj.default_lang;
  el.settingTurnPause.value = proj.default_turn_pause;
  el.settingTrim.checked = proj.trim_silence;
  el.settingNorm.checked = proj.normalize_loudness;

  el.blocksContainer.innerHTML = "";
  proj.blocks.forEach((block, idx) => {
    el.blocksContainer.appendChild(renderBlockCard(proj, block, idx));
  });
}

function renderBlockCard(project, block, idx) {
  const card = document.createElement("article");
  card.className = `block-card${block.locked ? " is-locked" : ""}`;
  card.dataset.blockId = block.id;

  const header = document.createElement("div");
  header.className = "block-header";

  const idxSpan = document.createElement("span");
  idxSpan.className = "block-index";
  idxSpan.textContent = `#${String(idx + 1).padStart(2, "0")}`;

  const voiceSelect = document.createElement("select");
  for (const ch of state.characters) {
    const opt = document.createElement("option");
    opt.value = ch.id;
    opt.textContent = ch.mode === "clone" ? `${ch.name} [Clone]` : ch.name;
    voiceSelect.appendChild(opt);
  }
  voiceSelect.value = block.voice_id;
  voiceSelect.addEventListener("change", () =>
    patchBlock(block.id, { voice_id: voiceSelect.value })
  );

  const statusPill = document.createElement("span");
  statusPill.className = `pill pill-${block.status}`;
  statusPill.textContent = STATUS_LABEL[block.status] || block.status;

  const tools = document.createElement("div");
  tools.className = "block-header-tools";

  const btnUp = makeIconBtn("↑", "上へ移動", () => moveBlock(idx, -1), idx === 0);
  const btnDown = makeIconBtn(
    "↓",
    "下へ移動",
    () => moveBlock(idx, 1),
    idx === project.blocks.length - 1
  );
  const btnInsert = makeIconBtn("+ 行", "この下に空行を挿入", () =>
    insertBlock(idx + 1, block.voice_id)
  );
  const btnDel = makeIconBtn("🗑", "削除", () => deleteBlock(block.id));

  tools.append(btnUp, btnDown, btnInsert, btnDel);
  header.append(idxSpan, voiceSelect, statusPill, tools);

  const textarea = document.createElement("textarea");
  textarea.className = "block-textarea";
  textarea.value = block.text;
  textarea.rows = Math.max(2, Math.min(6, block.text.split("\n").length));
  textarea.addEventListener("change", () => {
    if (textarea.value !== block.text) {
      patchBlock(block.id, { text: textarea.value });
    }
  });

  const details = document.createElement("details");
  details.className = "block-details";
  if (
    block.tts_text ||
    block.speed ||
    block.lang ||
    block.instruct ||
    (block.style && block.style !== "Auto")
  ) {
    details.open = true;
  }
  const summary = document.createElement("summary");
  summary.textContent = "読み・話速・言語・指示の個別調整";
  const grid = document.createElement("div");
  grid.className = "details-grid";

  const ttsInput = document.createElement("input");
  ttsInput.type = "text";
  ttsInput.placeholder = "漢字の読み直し等（未入力なら本文）";
  ttsInput.value = block.tts_text || "";
  ttsInput.addEventListener("change", () =>
    patchBlock(block.id, { tts_text: ttsInput.value.trim() || null })
  );

  const speedInput = document.createElement("input");
  speedInput.type = "number";
  speedInput.step = "0.05";
  speedInput.min = "0.5";
  speedInput.max = "2.0";
  speedInput.placeholder = "キャラ既定";
  speedInput.value = block.speed ?? "";
  speedInput.addEventListener("change", () => {
    const val = speedInput.value.trim();
    patchBlock(block.id, { speed: val ? parseFloat(val) : null });
  });

  const langSelect = document.createElement("select");
  for (const optVal of ["", "Auto", "Japanese", "English", "Chinese", "Korean"]) {
    const o = document.createElement("option");
    o.value = optVal;
    o.textContent = optVal ? optVal : "キャラ/プロジェクト既定";
    langSelect.appendChild(o);
  }
  langSelect.value = block.lang || "";
  langSelect.addEventListener("change", () =>
    patchBlock(block.id, { lang: langSelect.value || null })
  );

  const instructInput = document.createElement("input");
  instructInput.type = "text";
  instructInput.placeholder = "Clone時の感情・話し方指示";
  instructInput.value = block.instruct || "";
  instructInput.addEventListener("change", () =>
    patchBlock(block.id, { instruct: instructInput.value.trim() || null })
  );

  const styleSelect = document.createElement("select");
  for (const [val, label] of [
    ["", "Auto"],
    ["Whisper / 耳语", "Whisper (ささやき)"],
  ]) {
    const o = document.createElement("option");
    o.value = val;
    o.textContent = label;
    styleSelect.appendChild(o);
  }
  styleSelect.value = block.style === "Whisper / 耳语" ? "Whisper / 耳语" : "";
  styleSelect.addEventListener("change", () =>
    patchBlock(block.id, { style: styleSelect.value || null })
  );

  grid.append(
    wrapField("読み上げテキスト (tts_text)", ttsInput),
    wrapField("話速 (0.5〜2.0)", speedInput),
    wrapField("言語", langSelect),
    wrapField("指示 (instruct / Clone時)", instructInput),
    wrapField("スタイル (Design時)", styleSelect)
  );
  details.append(summary, grid);

  const controls = document.createElement("div");
  controls.className = "block-controls";

  const selectedTake = getSelectedTake(block);
  const btnPlay = document.createElement("button");
  btnPlay.type = "button";
  btnPlay.className = "btn btn-secondary btn-sm";
  btnPlay.textContent = "▶ 再生";
  btnPlay.disabled = !selectedTake;
  btnPlay.addEventListener("click", () => playSingleBlock(project.id, block));

  const btnPlayFrom = document.createElement("button");
  btnPlayFrom.type = "button";
  btnPlayFrom.className = "btn btn-secondary btn-sm";
  btnPlayFrom.textContent = "⏭ ここから通し";
  btnPlayFrom.disabled = !selectedTake;
  btnPlayFrom.addEventListener("click", () => playAllFrom(idx));

  const btnRetake = document.createElement("button");
  btnRetake.type = "button";
  btnRetake.className = "btn btn-primary btn-sm";
  btnRetake.textContent = selectedTake ? "🔄 リテイク" : "✨ 生成";
  btnRetake.disabled = state.isBusy;
  btnRetake.addEventListener("click", () => generateSingleBlock(block.id));

  const takesGroup = document.createElement("div");
  takesGroup.className = "takes-group";
  block.takes.forEach((take, tIdx) => {
    const tBtn = document.createElement("button");
    tBtn.type = "button";
    tBtn.className = `take-pill${take.id === block.selected_take_id ? " active" : ""}`;
    tBtn.textContent = `T${tIdx + 1} (${take.duration.toFixed(1)}s)`;
    tBtn.addEventListener("click", () => patchBlock(block.id, { selected_take_id: take.id }));
    takesGroup.appendChild(tBtn);
  });

  const btnLock = document.createElement("button");
  btnLock.type = "button";
  btnLock.className = "btn btn-secondary btn-sm";
  btnLock.textContent = block.locked ? "🔒 ロック解除" : "🔓 ロック";
  btnLock.addEventListener("click", () => patchBlock(block.id, { locked: !block.locked }));

  const pauseWrap = document.createElement("div");
  pauseWrap.className = "pause-control";
  const pauseLabel = document.createElement("span");
  pauseLabel.textContent = "後の間:";
  const btnMinus = makeIconBtn("-0.1", "0.1秒縮める", () => {
    const next = Math.max(0, Math.round((block.pause_after - 0.1) * 100) / 100);
    patchBlock(block.id, { pause_after: next });
  });
  const pauseInput = document.createElement("input");
  pauseInput.type = "number";
  pauseInput.className = "pause-input";
  pauseInput.step = "0.05";
  pauseInput.min = "0";
  pauseInput.max = "10";
  pauseInput.value = block.pause_after;
  pauseInput.addEventListener("change", () => {
    const val = Math.max(0, Math.min(10, parseFloat(pauseInput.value) || 0));
    patchBlock(block.id, { pause_after: val });
  });
  const unitSpan = document.createElement("span");
  unitSpan.textContent = "s";
  const btnPlus = makeIconBtn("+0.1", "0.1秒延ばす", () => {
    const next = Math.min(10, Math.round((block.pause_after + 0.1) * 100) / 100);
    patchBlock(block.id, { pause_after: next });
  });
  pauseWrap.append(pauseLabel, btnMinus, pauseInput, unitSpan, btnPlus);

  controls.append(btnPlay, btnPlayFrom, btnRetake, takesGroup, btnLock, pauseWrap);
  card.append(header, textarea, details, controls);
  return card;
}

function makeIconBtn(label, title, onClick, disabled = false) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn-icon";
  btn.textContent = label;
  btn.title = title;
  btn.disabled = disabled;
  btn.addEventListener("click", onClick);
  return btn;
}

function wrapField(labelText, control) {
  const lbl = document.createElement("label");
  const span = document.createElement("span");
  span.textContent = labelText;
  lbl.append(span, control);
  return lbl;
}

async function patchBlock(blockId, body) {
  const proj = state.currentProject;
  if (!proj) return;
  try {
    state.currentProject = await apiFetch(
      `/api/projects/${encodeURIComponent(proj.id)}/blocks/${encodeURIComponent(blockId)}`,
      { method: "PATCH", body: JSON.stringify(body) }
    );
    renderProject();
  } catch (err) {
    setStatus(`更新失敗: ${err.message}`);
  }
}

async function insertBlock(index, voiceId = "Alice") {
  const proj = state.currentProject;
  if (!proj) return;
  state.currentProject = await apiFetch(
    `/api/projects/${encodeURIComponent(proj.id)}/blocks`,
    {
      method: "POST",
      body: JSON.stringify({ voice_id: voiceId, text: "", insert_index: index }),
    }
  );
  renderProject();
}

async function deleteBlock(blockId) {
  const proj = state.currentProject;
  if (!proj) return;
  state.currentProject = await apiFetch(
    `/api/projects/${encodeURIComponent(proj.id)}/blocks/${encodeURIComponent(blockId)}`,
    { method: "DELETE" }
  );
  renderProject();
}

async function moveBlock(index, delta) {
  const proj = state.currentProject;
  if (!proj) return;
  const target = index + delta;
  if (target < 0 || target >= proj.blocks.length) return;
  const ids = proj.blocks.map((b) => b.id);
  const [moved] = ids.splice(index, 1);
  ids.splice(target, 0, moved);
  state.currentProject = await apiFetch(
    `/api/projects/${encodeURIComponent(proj.id)}/blocks/reorder`,
    { method: "POST", body: JSON.stringify({ block_ids: ids }) }
  );
  renderProject();
}

async function generateSingleBlock(blockId) {
  const proj = state.currentProject;
  if (!proj || state.isBusy) return;
  state.isBusy = true;
  renderProject();
  setStatus("音声を生成中...");
  try {
    state.currentProject = await apiFetch(
      `/api/projects/${encodeURIComponent(proj.id)}/blocks/${encodeURIComponent(blockId)}/generate`,
      { method: "POST" }
    );
    setStatus("生成完了");
  } catch (err) {
    setStatus(`生成エラー: ${err.message}`);
  } finally {
    state.isBusy = false;
    renderProject();
  }
}

async function generateAllPending() {
  const proj = state.currentProject;
  if (!proj || state.isBusy) return;
  const targets = proj.blocks.filter(
    (b) => !b.locked && ((b.tts_text && b.tts_text.trim()) || b.text.trim())
  );
  if (targets.length === 0) {
    setStatus("ロックされていない有効なセリフはありません。");
    return;
  }

  state.isBusy = true;
  renderProject();
  try {
    for (let i = 0; i < targets.length; i++) {
      setStatus(`一括生成中 (${i + 1} / ${targets.length})...`);
      state.currentProject = await apiFetch(
        `/api/projects/${encodeURIComponent(proj.id)}/blocks/${encodeURIComponent(targets[i].id)}/generate`,
        { method: "POST" }
      );
      renderProject();
    }
    setStatus(`一括生成完了（${targets.length} 件）`);
  } catch (err) {
    setStatus(`生成途中でエラー: ${err.message}`);
  } finally {
    state.isBusy = false;
    renderProject();
  }
}

function playSingleBlock(projectId, block) {
  stopAllPlayback();
  const take = getSelectedTake(block);
  if (!take) return;
  const audio = new Audio(takeUrl(projectId, take.file));
  state.singleAudio = audio;
  const card = el.blocksContainer.querySelector(`[data-block-id="${block.id}"]`);
  if (card) card.classList.add("is-playing");
  audio.addEventListener("ended", () => {
    if (card) card.classList.remove("is-playing");
    state.singleAudio = null;
  });
  audio.play().catch((err) => setStatus(`再生失敗: ${err.message}`));
}

function stopAllPlayback() {
  if (state.singleAudio) {
    state.singleAudio.pause();
    state.singleAudio = null;
  }
  state.playingAll = false;
  for (const timer of state.playTimers) clearTimeout(timer);
  state.playTimers = [];
  for (const src of state.activeSources) {
    try {
      src.stop();
    } catch (_) {
      // already stopped
    }
  }
  state.activeSources = [];
  document
    .querySelectorAll(".block-card.is-playing")
    .forEach((node) => node.classList.remove("is-playing"));
  el.btnPlayAll.classList.remove("hidden");
  el.btnStopAll.classList.add("hidden");
}

async function playAllFrom(startIndex = 0) {
  const proj = state.currentProject;
  if (!proj) return;
  stopAllPlayback();

  const playable = proj.blocks
    .slice(startIndex)
    .map((b) => ({ block: b, take: getSelectedTake(b) }))
    .filter((item) => item.take !== null);

  if (playable.length === 0) {
    setStatus("再生できる生成済みセリフがありません。先に Generate してください。");
    return;
  }

  state.playingAll = true;
  el.btnPlayAll.classList.add("hidden");
  el.btnStopAll.classList.remove("hidden");
  setStatus("通し再生を準備中...");

  try {
    if (!state.audioCtx) {
      state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (state.audioCtx.state === "suspended") {
      await state.audioCtx.resume();
    }

    const buffers = await Promise.all(
      playable.map(async ({ take }) => {
        const res = await fetch(takeUrl(proj.id, take.file));
        const arr = await res.arrayBuffer();
        return state.audioCtx.decodeAudioData(arr);
      })
    );

    if (!state.playingAll) return;

    let offset = state.audioCtx.currentTime + 0.05;
    const baseTime = state.audioCtx.currentTime;
    setStatus("通し再生中...");

    playable.forEach(({ block }, idx) => {
      const buf = buffers[idx];
      const src = state.audioCtx.createBufferSource();
      src.buffer = buf;
      src.connect(state.audioCtx.destination);
      src.start(offset);
      state.activeSources.push(src);

      const startMs = Math.max(0, (offset - baseTime) * 1000);
      const endMs = Math.max(0, (offset + buf.duration - baseTime) * 1000);

      state.playTimers.push(
        setTimeout(() => {
          document
            .querySelectorAll(".block-card.is-playing")
            .forEach((n) => n.classList.remove("is-playing"));
          const card = el.blocksContainer.querySelector(`[data-block-id="${block.id}"]`);
          if (card) {
            card.classList.add("is-playing");
            card.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }
        }, startMs)
      );

      state.playTimers.push(
        setTimeout(() => {
          const card = el.blocksContainer.querySelector(`[data-block-id="${block.id}"]`);
          if (card) card.classList.remove("is-playing");
        }, endMs)
      );

      offset += buf.duration + (idx < playable.length - 1 ? block.pause_after : 0);
    });

    const totalMs = Math.max(0, (offset - baseTime) * 1000) + 80;
    state.playTimers.push(
      setTimeout(() => {
        stopAllPlayback();
        setStatus("通し再生完了");
      }, totalMs)
    );
  } catch (err) {
    stopAllPlayback();
    setStatus(`通し再生エラー: ${err.message}`);
  }
}

async function createProject(title, initialScript = null, defaultLang = "Auto") {
  const proj = await apiFetch("/api/projects", {
    method: "POST",
    body: JSON.stringify({ title, default_lang: defaultLang }),
  });
  if (initialScript) {
    await apiFetch(`/api/projects/${encodeURIComponent(proj.id)}/import-script`, {
      method: "POST",
      body: JSON.stringify({ script: initialScript, mode: "replace" }),
    });
  }
  await refreshProjects(proj.id);
}

async function exportEpisode(fmt) {
  const proj = state.currentProject;
  if (!proj || state.isBusy) return;
  state.isBusy = true;
  renderProject();
  setStatus(`${fmt.toUpperCase()} を結合書き出し中...`);
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(proj.id)}/export`, {
      method: "POST",
      body: JSON.stringify({ format: fmt }),
    });
    setStatus(`書き出し完了 (${res.duration.toFixed(1)}s)`);
    const link = document.createElement("a");
    link.href = res.download_url;
    link.download = res.file;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (err) {
    setStatus(`Export エラー: ${err.message}`);
  } finally {
    state.isBusy = false;
    renderProject();
  }
}

// --- Cast / Character Lab ---

function populateSelectOptions(selectEl, options) {
  selectEl.innerHTML = "";
  for (const val of options || []) {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = val;
    selectEl.appendChild(opt);
  }
}

function currentVoice() {
  return state.characters.find((v) => v.id === state.selectedVoiceId) || state.characters[0] || null;
}

function renderCastView() {
  el.voiceList.innerHTML = "";
  for (const v of state.characters) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `voice-item${v.id === state.selectedVoiceId ? " active" : ""}`;
    btn.addEventListener("click", () => {
      state.selectedVoiceId = v.id;
      el.cloneTestResult.classList.add("hidden");
      renderCastView();
    });

    const top = document.createElement("div");
    top.className = "voice-item-top";
    const nameSpan = document.createElement("span");
    nameSpan.textContent = v.name;
    const badge = document.createElement("span");
    badge.className = `pill ${v.mode === "clone" ? "pill-ready" : "pill-unbuilt"}`;
    badge.textContent = v.mode === "clone" ? "Clone" : "Design";
    top.append(nameSpan, badge);

    const roleSpan = document.createElement("span");
    roleSpan.className = "voice-item-role";
    roleSpan.textContent = v.role || (v.is_builtin ? "標準キャラクター" : "カスタムキャラクター");

    btn.append(top, roleSpan);
    el.voiceList.appendChild(btn);
  }

  const v = currentVoice();
  if (!v) return;

  el.voiceEditorTitle.textContent = v.name;
  el.voiceModeBadge.className = `pill ${v.mode === "clone" ? "pill-ready" : "pill-dirty"}`;
  el.voiceModeBadge.textContent =
    v.mode === "clone" ? "Clone（ベース音声固定中）" : "Design（属性プリセット）";

  if (v.is_builtin) {
    el.btnDeleteVoice.textContent = "初期プリセットに戻す";
    el.btnDeleteVoice.disabled = !v.is_customized;
  } else {
    el.btnDeleteVoice.textContent = "このキャラを削除";
    el.btnDeleteVoice.disabled = false;
  }

  el.vName.value = v.name;
  el.vName.disabled = v.is_builtin;
  el.vRole.value = v.role || "";
  el.vLang.value = v.lang || "Auto";
  el.vSpeed.value = v.default_speed ?? 1.0;
  el.vInstruct.value = v.default_instruct || "";
  el.vRefText.value = v.ref_text || "";

  el.vGender.value = v.gender || "Auto";
  el.vAge.value = v.age || "Auto";
  el.vPitch.value = v.pitch || "Auto";
  el.vStyle.value = v.style || "Auto";
  el.vAccent.value = v.english_accent || "Auto";
  el.vDialect.value = v.chinese_dialect || "Auto";

  // Ref audio status
  el.vRefActions.innerHTML = "";
  el.vRefStatus.innerHTML = "";
  if (v.ref_audio) {
    const dur = v.ref_audio_duration ? `${v.ref_audio_duration.toFixed(2)}s` : "";
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = `/api/voices/${encodeURIComponent(v.id)}/ref-audio?v=${v.ref_version}`;
    const info = document.createElement("div");
    info.textContent =
      v.mode === "clone"
        ? `この音声をベースとして Clone 合成を使用します (${dur})`
        : `ベース音声は保存済みですが、現在は Design モードになっています (${dur})`;
    el.vRefStatus.append(info, audio);

    if (v.mode === "clone") {
      const btnUseDesign = document.createElement("button");
      btnUseDesign.type = "button";
      btnUseDesign.className = "btn btn-secondary btn-sm";
      btnUseDesign.textContent = "一時的に Design モードへ切替";
      btnUseDesign.addEventListener("click", () => updateVoice(v.id, { mode: "design" }));
      el.vRefActions.appendChild(btnUseDesign);
    } else {
      const btnUseClone = document.createElement("button");
      btnUseClone.type = "button";
      btnUseClone.className = "btn btn-accent btn-sm";
      btnUseClone.textContent = "Clone モードを有効化";
      btnUseClone.addEventListener("click", () => updateVoice(v.id, { mode: "clone" }));
      el.vRefActions.appendChild(btnUseClone);
    }
  } else {
    el.vRefStatus.textContent =
      "まだベース音声が設定されていません。下の方法 A（Design で試作）または方法 B（音声アップロード）で登録できます。";
  }

  renderDesignPreviews();
}

function renderDesignPreviews() {
  el.designPreviewList.innerHTML = "";
  el.btnClearDesignPreviews.classList.toggle("hidden", state.designPreviews.length === 0);
  const v = currentVoice();
  state.designPreviews.forEach((item, idx) => {
    const row = document.createElement("div");
    row.className = "preview-row";

    const label = document.createElement("strong");
    label.textContent = `#${idx + 1} (${item.duration.toFixed(1)}s)`;

    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = item.audio_url;

    const btnAdopt = document.createElement("button");
    btnAdopt.type = "button";
    btnAdopt.className = "btn btn-accent btn-sm";
    btnAdopt.textContent = v ? `📌 「${v.name}」のベース音声に採用` : "📌 採用";
    btnAdopt.disabled = !v;
    btnAdopt.addEventListener("click", () => adoptDesignPreview(item));

    const btnDelete = document.createElement("button");
    btnDelete.type = "button";
    btnDelete.className = "btn btn-danger-outline btn-sm";
    btnDelete.textContent = "🗑️ 削除";
    btnDelete.addEventListener("click", () => removeDesignPreview(item, btnDelete));

    row.append(label, audio, btnAdopt, btnDelete);
    el.designPreviewList.appendChild(row);
  });
}

async function deleteDraftPreviewFile(previewFile) {
  const res = await fetch(`/api/voices/drafts/${encodeURIComponent(previewFile)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) {
    const payload = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(payload.detail || `HTTP ${res.status}`);
  }
}

async function removeDesignPreview(previewItem, buttonEl) {
  if (buttonEl) buttonEl.disabled = true;
  try {
    await deleteDraftPreviewFile(previewItem.preview_file);
    state.designPreviews = state.designPreviews.filter(
      (p) => p.preview_file !== previewItem.preview_file
    );
    renderDesignPreviews();
    setCastStatus("試作音声を削除しました");
  } catch (err) {
    if (buttonEl) buttonEl.disabled = false;
    setCastStatus(`試作削除エラー: ${err.message}`);
  }
}

async function updateVoice(voiceId, body) {
  setCastStatus("保存中...");
  try {
    const updated = await apiFetch(`/api/voices/${encodeURIComponent(voiceId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    await refreshVoices();
    state.selectedVoiceId = updated.id;
    renderCastView();
    setCastStatus("保存しました");
  } catch (err) {
    setCastStatus(`保存エラー: ${err.message}`);
  }
}

async function adoptDesignPreview(previewItem) {
  const v = currentVoice();
  if (!v) return;
  setCastStatus("ベース音声を登録中...");
  try {
    await apiFetch(`/api/voices/${encodeURIComponent(v.id)}/adopt-preview`, {
      method: "POST",
      body: JSON.stringify({ preview_file: previewItem.preview_file, ref_text: "" }),
    });
    await refreshVoices();
    renderCastView();
    setCastStatus(`「${v.name}」のベース音声を採用しました（Clone 有効）`);
  } catch (err) {
    setCastStatus(`採用エラー: ${err.message}`);
  }
}

function wireEvents() {
  el.tabStudio.addEventListener("click", () => switchTab("studio"));
  el.tabCast.addEventListener("click", () => switchTab("cast"));

  el.projectSelect.addEventListener("change", () => {
    if (el.projectSelect.value) loadProject(el.projectSelect.value);
  });

  el.btnNewProject.addEventListener("click", async () => {
    const title = window.prompt("新しいエピソードのタイトル", "New Episode");
    if (!title || !title.trim()) return;
    await createProject(title.trim());
  });

  el.btnDeleteProject.addEventListener("click", async () => {
    const proj = state.currentProject;
    if (!proj) return;
    if (!window.confirm(`「${proj.title}」を削除しますか？`)) return;
    await apiFetch(`/api/projects/${encodeURIComponent(proj.id)}`, { method: "DELETE" });
    await refreshProjects();
  });

  el.btnCreateSample.addEventListener("click", () =>
    createProject("Sample Episode (JP)", SAMPLE_SCRIPT, "Japanese")
  );
  el.btnCreateSampleEn.addEventListener("click", () =>
    createProject("Sample Episode (EN)", SAMPLE_SCRIPT_EN, "English")
  );
  el.btnCreateBlank.addEventListener("click", () => createProject("New Episode"));

  const saveProjectSettings = async () => {
    const proj = state.currentProject;
    if (!proj) return;
    state.currentProject = await apiFetch(`/api/projects/${encodeURIComponent(proj.id)}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: el.settingTitle.value.trim() || proj.title,
        default_lang: el.settingLang.value,
        default_turn_pause: parseFloat(el.settingTurnPause.value) || 0,
        trim_silence: el.settingTrim.checked,
        normalize_loudness: el.settingNorm.checked,
      }),
    });
    await refreshProjects(proj.id);
    setStatus("プロジェクト設定を保存しました");
  };

  el.settingTitle.addEventListener("change", saveProjectSettings);
  el.settingLang.addEventListener("change", saveProjectSettings);
  el.settingTurnPause.addEventListener("change", saveProjectSettings);
  el.settingTrim.addEventListener("change", saveProjectSettings);
  el.settingNorm.addEventListener("change", saveProjectSettings);

  el.btnAddBlockEnd.addEventListener("click", () => {
    const proj = state.currentProject;
    if (!proj) return;
    insertBlock(proj.blocks.length);
  });

  el.btnOpenImport.addEventListener("click", () => {
    el.importWarnings.classList.add("hidden");
    el.importWarnings.textContent = "";
    el.importDialog.showModal();
  });
  el.btnCloseImport.addEventListener("click", () => el.importDialog.close());
  el.btnFillSample.addEventListener("click", () => {
    el.importTextarea.value = SAMPLE_SCRIPT;
  });
  el.btnFillSampleEn.addEventListener("click", () => {
    el.importTextarea.value = SAMPLE_SCRIPT_EN;
  });

  el.btnConfirmImport.addEventListener("click", async () => {
    const proj = state.currentProject;
    if (!proj) return;
    const mode = document.querySelector('input[name="import-mode"]:checked')?.value || "replace";
    try {
      const res = await apiFetch(
        `/api/projects/${encodeURIComponent(proj.id)}/import-script`,
        {
          method: "POST",
          body: JSON.stringify({ script: el.importTextarea.value, mode }),
        }
      );
      state.currentProject = res.project;
      await refreshProjects(proj.id);
      if (res.warnings && res.warnings.length > 0) {
        el.importWarnings.textContent = res.warnings.join("\n");
        el.importWarnings.classList.remove("hidden");
      } else {
        el.importDialog.close();
      }
      setStatus(`${res.imported_count} セリフをインポートしました`);
    } catch (err) {
      el.importWarnings.textContent = err.message;
      el.importWarnings.classList.remove("hidden");
    }
  });

  el.btnExportScript.addEventListener("click", async () => {
    const proj = state.currentProject;
    if (!proj) return;
    const txt = await apiFetch(`/api/projects/${encodeURIComponent(proj.id)}/export-script`);
    const blob = new Blob([txt], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${proj.title}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  });

  el.btnGenerateAll.addEventListener("click", generateAllPending);
  el.btnPlayAll.addEventListener("click", () => playAllFrom(0));
  el.btnStopAll.addEventListener("click", stopAllPlayback);
  el.btnExportWav.addEventListener("click", () => exportEpisode("wav"));
  el.btnExportMp3.addEventListener("click", () => exportEpisode("mp3"));

  // Cast Events
  el.btnOpenVoiceImport.addEventListener("click", () => {
    el.voiceImportFile.value = "";
    el.voiceImportOverwrite.checked = false;
    el.voiceImportDialog.showModal();
  });

  el.btnCloseVoiceImport.addEventListener("click", () => {
    el.voiceImportDialog.close();
  });

  el.btnConfirmVoiceImport.addEventListener("click", async () => {
    const file = el.voiceImportFile.files?.[0];
    if (!file) {
      setCastStatus("インポートするZIPファイルを選択してください");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("conflict", el.voiceImportOverwrite.checked ? "overwrite" : "rename");
    el.btnConfirmVoiceImport.disabled = true;
    setCastStatus("キャラクターをインポート中...");
    try {
      const imported = await apiFetch("/api/voices/import", {
        method: "POST",
        body: fd,
      });
      el.voiceImportDialog.close();
      await refreshVoices();
      state.selectedVoiceId = imported.id;
      renderCastView();
      if (state.project) {
        state.project = await apiFetch(`/api/projects/${state.project.id}`);
        renderBlocks();
      }
      setCastStatus(`「${imported.name}」をインポートしました`);
    } catch (err) {
      setCastStatus(`インポートエラー: ${err.message}`);
    } finally {
      el.btnConfirmVoiceImport.disabled = false;
    }
  });

  el.btnExportVoice.addEventListener("click", () => {
    const v = currentVoice();
    if (!v) return;
    const link = document.createElement("a");
    link.href = `/api/voices/${encodeURIComponent(v.id)}/export`;
    link.download = `${v.name}.omnicast-voice.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setCastStatus(`「${v.name}」をエクスポートしました`);
  });

  el.btnNewVoice.addEventListener("click", async () => {
    const name = window.prompt("新しいキャラクター名（台本で @名前: の形で使えます）", "Mika");
    if (!name || !name.trim()) return;
    try {
      const created = await apiFetch("/api/voices", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), lang: "Japanese" }),
      });
      await refreshVoices();
      state.selectedVoiceId = created.id;
      renderCastView();
      setCastStatus(`「${created.name}」を作成しました`);
    } catch (err) {
      setCastStatus(`作成エラー: ${err.message}`);
    }
  });

  el.btnDeleteVoice.addEventListener("click", async () => {
    const v = currentVoice();
    if (!v) return;
    const msg = v.is_builtin
      ? `「${v.name}」のカスタマイズを削除し、初期プリセットに戻しますか？`
      : `キャラクター「${v.name}」を削除しますか？`;
    if (!window.confirm(msg)) return;
    try {
      await apiFetch(`/api/voices/${encodeURIComponent(v.id)}`, { method: "DELETE" });
      await refreshVoices();
      renderCastView();
      setCastStatus(v.is_builtin ? "初期プリセットに戻しました" : "削除しました");
    } catch (err) {
      setCastStatus(`削除エラー: ${err.message}`);
    }
  });

  el.btnSaveVoice.addEventListener("click", () => {
    const v = currentVoice();
    if (!v) return;
    const body = {
      role: el.vRole.value,
      lang: el.vLang.value,
      default_speed: parseFloat(el.vSpeed.value) || 1.0,
      default_instruct: el.vInstruct.value,
      ref_text: el.vRefText.value,
    };
    if (!v.is_builtin) {
      body.name = el.vName.value.trim() || v.name;
    }
    updateVoice(v.id, body);
  });

  el.btnSaveDesignAttrs.addEventListener("click", () => {
    const v = currentVoice();
    if (!v) return;
    updateVoice(v.id, {
      gender: el.vGender.value,
      age: el.vAge.value,
      pitch: el.vPitch.value,
      style: el.vStyle.value,
      english_accent: el.vAccent.value,
      chinese_dialect: el.vDialect.value,
    });
  });

  el.btnDesignSampleJa.addEventListener("click", () => {
    el.designPreviewText.value = DESIGN_SAMPLE_JA;
  });
  el.btnDesignSampleEn.addEventListener("click", () => {
    el.designPreviewText.value = DESIGN_SAMPLE_EN;
  });
  el.btnClearDesignPreviews.addEventListener("click", async () => {
    if (state.designPreviews.length === 0) return;
    if (!window.confirm(`表示中の試作音声（${state.designPreviews.length}件）をすべて削除しますか？`)) {
      return;
    }
    el.btnClearDesignPreviews.disabled = true;
    try {
      const items = [...state.designPreviews];
      const results = await Promise.allSettled(
        items.map(async (item) => {
          await deleteDraftPreviewFile(item.preview_file);
          return item.preview_file;
        })
      );
      const deleted = new Set(
        results.filter((r) => r.status === "fulfilled").map((r) => r.value)
      );
      state.designPreviews = state.designPreviews.filter((p) => !deleted.has(p.preview_file));
      renderDesignPreviews();
      const firstRejected = results.find((r) => r.status === "rejected");
      if (firstRejected) {
        setCastStatus(`一括削除エラー: ${firstRejected.reason.message}`);
      } else {
        setCastStatus("試作音声をすべて削除しました");
      }
    } finally {
      el.btnClearDesignPreviews.disabled = false;
    }
  });
  el.btnCloneSampleJa.addEventListener("click", () => {
    el.cloneTestText.value = CLONE_TEST_JA;
  });
  el.btnCloneSampleEn.addEventListener("click", () => {
    el.cloneTestText.value = CLONE_TEST_EN;
  });

  el.btnDesignPreview.addEventListener("click", async () => {
    const text = el.designPreviewText.value.trim();
    if (!text) return;
    el.btnDesignPreview.disabled = true;
    setCastStatus("試作音声を生成中...");
    try {
      const res = await apiFetch("/api/voices/design-preview", {
        method: "POST",
        body: JSON.stringify({
          text,
          lang: el.vLang.value || "Auto",
          speed: parseFloat(el.vSpeed.value) || 1.0,
          gender: el.vGender.value,
          age: el.vAge.value,
          pitch: el.vPitch.value,
          style: el.vStyle.value,
          english_accent: el.vAccent.value,
          chinese_dialect: el.vDialect.value,
        }),
      });
      state.designPreviews.unshift(res);
      renderDesignPreviews();
      setCastStatus("試作音声を生成しました");
    } catch (err) {
      setCastStatus(`試作エラー: ${err.message}`);
    } finally {
      el.btnDesignPreview.disabled = false;
    }
  });

  el.btnUploadRef.addEventListener("click", async () => {
    const v = currentVoice();
    const file = el.vUploadFile.files?.[0];
    if (!v || !file) {
      setCastStatus("アップロードする音声ファイルを選択してください");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    el.btnUploadRef.disabled = true;
    setCastStatus("音声を変換・登録中...");
    try {
      await apiFetch(`/api/voices/${encodeURIComponent(v.id)}/ref-audio`, {
        method: "POST",
        body: fd,
      });
      el.vUploadFile.value = "";
      await refreshVoices();
      renderCastView();
      setCastStatus(`「${v.name}」のベース音声をアップロード設定しました`);
    } catch (err) {
      setCastStatus(`アップロードエラー: ${err.message}`);
    } finally {
      el.btnUploadRef.disabled = false;
    }
  });

  el.btnCloneTest.addEventListener("click", async () => {
    const v = currentVoice();
    const text = el.cloneTestText.value.trim();
    if (!v || !text) return;
    el.btnCloneTest.disabled = true;
    setCastStatus("テスト発話を生成中...");
    try {
      const res = await apiFetch(`/api/voices/${encodeURIComponent(v.id)}/clone-preview`, {
        method: "POST",
        body: JSON.stringify({
          text,
          instruct: el.cloneTestInstruct.value,
        }),
      });
      el.cloneTestResult.innerHTML = "";
      const badge = document.createElement("span");
      badge.className = "pill pill-ready";
      badge.textContent = `${res.mode_used} (${res.duration.toFixed(1)}s)`;
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.autoplay = true;
      audio.src = res.audio_url;
      el.cloneTestResult.append(badge, audio);
      el.cloneTestResult.classList.remove("hidden");
      setCastStatus("テスト発話を生成しました");
    } catch (err) {
      setCastStatus(`テスト発話エラー: ${err.message}`);
    } finally {
      el.btnCloneTest.disabled = false;
    }
  });
}

async function init() {
  wireEvents();
  state.designOptions = await apiFetch("/api/voices/options");
  populateSelectOptions(el.vGender, state.designOptions.gender);
  populateSelectOptions(el.vAge, state.designOptions.age);
  populateSelectOptions(el.vPitch, state.designOptions.pitch);
  populateSelectOptions(el.vStyle, state.designOptions.style);
  populateSelectOptions(el.vAccent, state.designOptions.english_accent);
  populateSelectOptions(el.vDialect, state.designOptions.chinese_dialect);

  await refreshVoices();
  await refreshHealth();
  await refreshProjects();
}

init().catch((err) => {
  setStatus(`初期化エラー: ${err.message}`);
});
