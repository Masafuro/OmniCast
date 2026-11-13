const SAMPLE_SCRIPT = `# OmniCast サンプル台本
@Alice: こんにちは、OmniCast へようこそ！今日は台本からポッドキャストを作るデモをお送りします。
@Bob: よろしくお願いします。気になるセリフだけ後からリテイクしたり、間の秒数を調整できるのが便利ですね。
@Alice: そうなんです。まずは一括 Generate を押して、全体を聴きながら調整してみてください！`;

const STATUS_LABEL = {
  unbuilt: "未生成",
  dirty: "要再生成",
  ready: "準備完了",
  locked: "ロック中",
};

const state = {
  characters: [],
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
  btnCreateBlank: document.getElementById("btn-create-blank"),
  blocksContainer: document.getElementById("blocks-container"),
  bottomAddWrap: document.getElementById("bottom-add-wrap"),
  btnAddBlockEnd: document.getElementById("btn-add-block-end"),
  importDialog: document.getElementById("import-dialog"),
  btnCloseImport: document.getElementById("btn-close-import"),
  importTextarea: document.getElementById("import-textarea"),
  importWarnings: document.getElementById("import-warnings"),
  btnFillSample: document.getElementById("btn-fill-sample"),
  btnConfirmImport: document.getElementById("btn-confirm-import"),
};

function setStatus(msg) {
  el.statusMessage.textContent = msg || "";
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
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

  el.settingsBar.classList.toggle("hidden", !hasProj);
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

  // Header
  const header = document.createElement("div");
  header.className = "block-header";

  const idxSpan = document.createElement("span");
  idxSpan.className = "block-index";
  idxSpan.textContent = `#${String(idx + 1).padStart(2, "0")}`;

  const voiceSelect = document.createElement("select");
  for (const ch of state.characters) {
    const opt = document.createElement("option");
    opt.value = ch.id;
    opt.textContent = `${ch.name}`;
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

  // Textarea
  const textarea = document.createElement("textarea");
  textarea.className = "block-textarea";
  textarea.value = block.text;
  textarea.rows = Math.max(2, Math.min(6, block.text.split("\n").length));
  textarea.addEventListener("change", () => {
    if (textarea.value !== block.text) {
      patchBlock(block.id, { text: textarea.value });
    }
  });

  // Details (optional overrides)
  const details = document.createElement("details");
  details.className = "block-details";
  if (block.tts_text || block.speed || block.lang || (block.style && block.style !== "Auto")) {
    details.open = true;
  }
  const summary = document.createElement("summary");
  summary.textContent = "読み・話速・言語の個別調整";
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
  speedInput.placeholder = "1.0";
  speedInput.value = block.speed ?? "";
  speedInput.addEventListener("change", () => {
    const val = speedInput.value.trim();
    patchBlock(block.id, { speed: val ? parseFloat(val) : null });
  });

  const langSelect = document.createElement("select");
  for (const optVal of ["", "Auto", "Japanese", "English", "Chinese", "Korean"]) {
    const o = document.createElement("option");
    o.value = optVal;
    o.textContent = optVal ? optVal : "プロジェクト既定";
    langSelect.appendChild(o);
  }
  langSelect.value = block.lang || "";
  langSelect.addEventListener("change", () =>
    patchBlock(block.id, { lang: langSelect.value || null })
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
    wrapField("スタイル", styleSelect)
  );
  details.append(summary, grid);

  // Controls
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

async function createProject(title, initialScript = null) {
  const proj = await apiFetch("/api/projects", {
    method: "POST",
    body: JSON.stringify({ title }),
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

function wireEvents() {
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
    createProject("Sample Episode", SAMPLE_SCRIPT)
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
}

async function init() {
  wireEvents();
  state.characters = await apiFetch("/api/characters");
  await refreshHealth();
  await refreshProjects();
}

init().catch((err) => {
  setStatus(`初期化エラー: ${err.message}`);
});
