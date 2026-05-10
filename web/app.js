const $ = (id) => document.getElementById(id);

const fields = {
  superTopic: $("superTopic"),
  cookie: $("cookie"),
  windowStart: $("windowStart"),
  windowEnd: $("windowEnd"),
  maxPages: $("maxPages"),
  topicCommentFactor: $("topicCommentFactor"),
  pauseSeconds: $("pauseSeconds"),
  outputDir: $("outputDir"),
};

const controls = {
  themeToggle: $("themeToggleBtn"),
  help: $("helpBtn"),
  start: $("startBtn"),
  edgeDebug: $("edgeDebugBtn"),
  autoCookie: $("autoCookieBtn"),
  clipboard: $("clipboardBtn"),
  extractCookie: $("extractCookieBtn"),
  select: $("selectBtn"),
  cancelSelect: $("cancelSelectBtn"),
  preview: $("previewBtn"),
  openResultDir: $("openResultDirBtn"),
};

const ui = {
  particleLayer: $("particleLayer"),
  layout: $("layout"),
  statusPill: $("statusPill"),
  saveState: $("saveState"),
  jobMeta: $("jobMeta"),
  monitorPanel: $("monitorPanel"),
  logBox: $("logBox"),
  candidatePanel: $("candidatePanel"),
  candidateList: $("candidateList"),
  pickCount: $("pickCount"),
  resultPanel: $("resultPanel"),
  resultList: $("resultList"),
  previewPanel: $("previewPanel"),
  previewContent: $("previewContent"),
  previewPath: $("previewPath"),
  helpOverlay: $("helpOverlay"),
  helpDialog: $("helpDialog"),
  helpDragHandle: $("helpDragHandle"),
  helpContent: $("helpContent"),
  helpPath: $("helpPath"),
  helpClose: $("helpCloseBtn"),
};

let pollTimer = null;
let lastRenderedCandidateJob = null;
let renderedPreviewKey = "";
let autoPreviewResultKey = "";
let configReady = false;
let configSaveTimer = null;
let currentRenderedJob = null;
let toastStack = null;
let helpDragState = null;
let particleFrame = 0;
let particlePointer = null;

function setBusy(button, busy, text) {
  if (!button) return;
  if (busy) {
    const busyText = text || "处理中";
    button.dataset.originalText = button.textContent;
    button.dataset.busyText = busyText;
    button.textContent = busyText;
    button.disabled = true;
    return;
  }
  if (
    button.dataset.busyText &&
    button.textContent === button.dataset.busyText &&
    button.dataset.originalText
  ) {
    button.textContent = button.dataset.originalText;
  }
  delete button.dataset.originalText;
  delete button.dataset.busyText;
  button.disabled = false;
}

function setSaveState(text, state = "") {
  ui.saveState.textContent = text;
  ui.saveState.dataset.state = state;
}

function api(path, options = {}) {
  const init = {
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  return fetch(path, init).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `请求失败：${response.status}`);
    }
    return data;
  });
}

function readForm() {
  return {
    super_topic: fields.superTopic.value.trim(),
    cookie: fields.cookie.value.trim(),
    window_start: fields.windowStart.value,
    window_end: fields.windowEnd.value,
    max_pages: fields.maxPages.value,
    topic_comment_factor: fields.topicCommentFactor.value,
    pause_seconds: fields.pauseSeconds.value,
    output_dir: fields.outputDir.value.trim(),
    theme: currentTheme(),
  };
}

function configPayload() {
  return {
    super_topic: fields.superTopic.value.trim(),
    cookie: fields.cookie.value.trim(),
    output_dir: fields.outputDir.value.trim(),
    theme: currentTheme(),
  };
}

function scheduleConfigSave() {
  if (!configReady) return;
  clearTimeout(configSaveTimer);
  setSaveState("配置待保存", "pending");
  configSaveTimer = setTimeout(saveConfigNow, 420);
}

async function saveConfigNow() {
  if (!configReady) return;
  clearTimeout(configSaveTimer);
  try {
    await api("/api/config", {
      method: "POST",
      body: JSON.stringify(configPayload()),
    });
    setSaveState("配置已保存", "saved");
  } catch (err) {
    setSaveState(`配置保存失败：${err.message}`, "error");
  }
}

function statusText(status) {
  return (
    {
      running: "抓取中",
      awaiting_selection: "等待筛选",
      exporting: "导出中",
      completed: "已完成",
      failed: "失败",
      cancelled: "已取消",
    }[status] || "未开始"
  );
}

function updateStatus(job) {
  const status = job?.status || "";
  ui.statusPill.className = `status-pill ${status}`;
  ui.statusPill.textContent = statusText(status);
  ui.jobMeta.textContent = job
    ? `${job.started_at || ""} / ${job.updated_at || ""}`
    : "等待启动";
}

function renderProgress(job) {
  const steps = buildProgressSteps(job);
  const existing = new Map(
    Array.from(ui.logBox.querySelectorAll("[data-step-id]")).map((node) => [node.dataset.stepId, node]),
  );
  const visibleIds = new Set(steps.map((step) => step.id));

  ui.logBox.querySelectorAll("[data-step-id]").forEach((node) => {
    if (!visibleIds.has(node.dataset.stepId)) {
      node.remove();
    }
  });

  steps.forEach((step) => {
    const node = existing.get(step.id);
    if (node) {
      updateProgressItem(node, step, false);
    } else {
      const created = createProgressItem(step);
      ui.logBox.appendChild(created);
      updateProgressItem(created, step, true);
    }
  });
}

function buildProgressSteps(job) {
  const logs = job?.logs || [];
  const messages = logs.map((item) => item.message || "");
  const status = job?.status || "";
  const failed = status === "failed";
  const cancelled = status === "cancelled";
  const completed = status === "completed";
  const selectionReady = status === "awaiting_selection";
  const exporting = status === "exporting";
  const hasStarted = Boolean(job);
  const maxPages = Math.max(1, Number(fields.maxPages.value || 80));
  const latestPage = lastNumber(messages, /抓取第\s+(\d+)\s+页/);
  const latestCrawlDetail =
    lastMatchingMessage(messages, /已连续5页无时间窗口命中帖子/) ||
    lastMatchingMessage(messages, /本页没有帖子数据，停止翻页/) ||
    lastMatchingMessage(messages, /第\s+\d+\s+页读取/) ||
    lastMatchingMessage(messages, /连续无命中页/) ||
    "";
  const textProgress = maxProgress(messages, /正文校正(?:进度)?\s+(\d+)\/(\d+)/);
  const scoreProgress = maxProgress(messages, /评分进度\s+(\d+)\/(\d+)/);
  const downloadProgress = maxProgress(messages, /下载图片(?:进度|失败)\s+(\d+)\/(\d+)/);
  const exportSavedCount = [
    "Excel 已保存",
    "CSV 已保存",
    "DOCX 已保存",
    "总 DOCX 已保存",
    "MD 已保存",
    "汇总已保存",
  ].filter((marker) => messages.some((message) => message.includes(marker))).length;
  const hasCandidates = messages.some((message) => message.includes("等待人工筛选"));
  const hasSelectionDone = messages.some((message) => message.includes("人工筛选完成"));
  const hasImageStart = messages.some((message) => message.includes("正在下载帖子/评论图片"));
  const hasExportFiles = exportSavedCount > 0 || completed;
  const imageDownloadDone =
    Boolean(downloadProgress) && downloadProgress.current >= downloadProgress.total;
  const crawlFinished =
    completed ||
    exporting ||
    selectionReady ||
    hasCandidates ||
    messages.some((message) =>
      [
        "已连续5页无时间窗口命中帖子",
        "本页没有帖子数据，停止翻页",
        "补全帖子正文",
        "开始计算评分",
        "自动校准时间权重",
      ].some((marker) => message.includes(marker)),
    );
  const steps = [
    progressStep(
      "init",
      "初始化任务",
      hasStarted ? "配置已读取，任务线程已启动" : "填写参数后开始任务",
      hasStarted ? 100 : 0,
      hasStarted ? "done" : "pending",
      "阶段 1/6",
    ),
  ];

  if (hasStarted) {
    const crawlPercent = crawlFinished ? 100 : clamp((latestPage / maxPages) * 86 + 8, 8, 96);
    steps.push(
      progressStep(
        "crawl",
        "抓取帖子数据",
        latestCrawlDetail || (latestPage ? `正在读取第 ${latestPage} 页，最多 ${maxPages} 页` : "连接超话页面并读取帖子"),
        crawlPercent,
        crawlFinished ? "done" : "active",
        latestPage ? `第 ${latestPage}/${maxPages} 页` : "阶段 2/6",
      ),
    );
  }

  if (latestPage || hasCandidates || selectionReady || exporting || completed) {
    const candidateProgress = candidateStageProgress({
      hasCandidates,
      selectionReady,
      exporting,
      completed,
      textProgress,
      scoreProgress,
      messages,
    });
    steps.push(
      progressStep(
        "candidate",
        "计算评分与候选",
        hasCandidates ? `候选 ${job?.candidates?.length || 0} 条，等待确认` : candidateProgress.detail,
        hasCandidates || selectionReady || exporting || completed ? 100 : candidateProgress.progress,
        hasCandidates || selectionReady || exporting || completed ? "done" : "active",
        candidateProgress.meta,
      ),
    );
  }

  if (hasCandidates || selectionReady || exporting || completed || cancelled) {
    steps.push(
      progressStep(
        "selection",
        "人工筛选",
        selectionReady
          ? `请选择 ${job?.required_pick_count || 0} 条入选帖子`
          : hasSelectionDone || exporting || completed
            ? "入选帖子已确认"
            : "等待人工确认",
        hasSelectionDone || exporting || completed ? 100 : selectionReady ? 62 : 0,
        hasSelectionDone || exporting || completed ? "done" : selectionReady ? "waiting" : "pending",
        selectionReady ? `${currentSelectedCount(job)}/${job?.required_pick_count || 0} 已选` : "阶段 4/6",
      ),
    );
  }

  if (hasSelectionDone || hasImageStart || downloadProgress || exporting || completed) {
    const percent = completed || hasExportFiles || imageDownloadDone ? 100 : downloadProgress ? (downloadProgress.current / downloadProgress.total) * 100 : 18;
    steps.push(
      progressStep(
        "images",
        "下载图片资源",
        downloadProgress
          ? `已处理 ${downloadProgress.current}/${downloadProgress.total} 个帖子`
          : hasImageStart
            ? "正在下载帖子图片与热评图片"
            : "等待图片下载",
        percent,
        completed || hasExportFiles || imageDownloadDone ? "done" : "active",
        downloadProgress ? `${downloadProgress.current}/${downloadProgress.total} 帖` : "阶段 5/6",
      ),
    );
  }

  if (imageDownloadDone || hasExportFiles || completed) {
    steps.push(
      progressStep(
        "export",
        "生成导出文件",
        completed
          ? "XLSX、CSV、DOCX、Markdown 与汇总文件已生成"
          : exportSavedCount
            ? `已生成 ${exportSavedCount}/6 类文件`
            : "图片下载完成，正在生成导出文件",
        completed ? 100 : clamp((exportSavedCount / 6) * 100, imageDownloadDone || hasExportFiles ? 20 : 0, 96),
        completed ? "done" : imageDownloadDone || hasExportFiles ? "active" : "pending",
        completed ? "6/6 文件" : `${exportSavedCount}/6 文件`,
      ),
    );
  }

  if (failed) {
    markLastMutableStep(steps, "failed", job?.error || lastMessage(messages) || "任务失败");
  } else if (cancelled) {
    markLastMutableStep(steps, "cancelled", "任务已取消");
  }

  return steps;
}

function candidateStageProgress({ hasCandidates, selectionReady, exporting, completed, textProgress, scoreProgress, messages }) {
  if (hasCandidates || selectionReady || exporting || completed) {
    return { progress: 100, detail: "候选列表已生成", meta: "阶段 3/6" };
  }
  if (scoreProgress) {
    return {
      progress: clamp(62 + (scoreProgress.current / scoreProgress.total) * 28, 62, 96),
      detail: `正在计算热度评分：${scoreProgress.current}/${scoreProgress.total}`,
      meta: `${scoreProgress.current}/${scoreProgress.total} 评分`,
    };
  }
  if (messages.some((message) => message.includes("开始计算评分"))) {
    return { progress: 62, detail: "正在估算评论结构并计算时间权重", meta: "评分中" };
  }
  if (textProgress) {
    return {
      progress: clamp(28 + (textProgress.current / textProgress.total) * 26, 28, 58),
      detail: `正在补全正文：${textProgress.current}/${textProgress.total}`,
      meta: `${textProgress.current}/${textProgress.total} 正文`,
    };
  }
  if (messages.some((message) => message.includes("补全帖子正文"))) {
    return { progress: 28, detail: "正在补全长文与被截断正文", meta: "正文校正" };
  }
  return { progress: 18, detail: "清洗帖子内容并准备评分", meta: "阶段 3/6" };
}

function progressStep(id, title, detail, progress, state, meta = "") {
  return {
    id,
    title,
    detail,
    progress: Math.round(clamp(progress, 0, 100)),
    state,
    meta,
  };
}

function createProgressItem(step) {
  const node = document.createElement("div");
  node.className = "progress-item";
  node.dataset.stepId = step.id;
  node.innerHTML = `
    <div class="progress-icon" aria-hidden="true"></div>
    <div class="progress-main">
      <div class="progress-head">
        <div class="progress-copy">
          <span class="progress-title"></span>
          <span class="progress-meta"></span>
        </div>
        <div class="progress-stats">
          <span class="progress-state"></span>
          <span class="progress-percent"></span>
        </div>
      </div>
      <div class="progress-detail"></div>
      <div class="progress-track"><div class="progress-fill"></div></div>
    </div>`;
  return node;
}

function updateProgressItem(node, step, isNew = false) {
  node.className = `progress-item ${step.state}`;
  node.dataset.stepId = step.id;
  node.setAttribute("aria-label", `${step.title}，${stateLabel(step.state)}，${step.progress}%`);
  node.querySelector(".progress-title").textContent = step.title;
  node.querySelector(".progress-meta").textContent = step.meta || "";
  node.querySelector(".progress-detail").textContent = step.detail || "";
  node.querySelector(".progress-state").textContent = stateLabel(step.state);
  node.querySelector(".progress-percent").textContent = step.state === "waiting" ? "待确认" : `${step.progress}%`;
  const fill = node.querySelector(".progress-fill");
  if (isNew) {
    fill.style.width = "0%";
    requestAnimationFrame(() => {
      fill.style.width = `${step.progress}%`;
    });
  } else {
    fill.style.width = `${step.progress}%`;
  }
}

function stateLabel(state) {
  return (
    {
      active: "进行中",
      waiting: "待确认",
      done: "已完成",
      failed: "失败",
      cancelled: "已取消",
      pending: "排队中",
    }[state] || "排队中"
  );
}

function currentSelectedCount(job) {
  if (ui.candidateList.children.length) {
    return selectedIndexes().length;
  }
  return Number(job?.required_pick_count || 0);
}

function markLastMutableStep(steps, state, detail) {
  const step = [...steps].reverse().find((item) => item.state !== "done") || steps[steps.length - 1];
  if (!step) return;
  step.state = state;
  step.detail = detail;
  step.progress = state === "failed" ? Math.max(step.progress, 6) : step.progress;
}

function lastNumber(messages, regex) {
  let value = 0;
  for (const message of messages) {
    const match = regex.exec(message);
    if (match) value = Number(match[1] || 0);
  }
  return value;
}

function maxProgress(messages, regex) {
  let value = null;
  for (const message of messages) {
    const match = regex.exec(message);
    if (match) {
      const next = {
        current: Number(match[1] || 0),
        total: Math.max(1, Number(match[2] || 1)),
      };
      if (!value || next.current / next.total >= value.current / value.total) {
        value = next;
      }
    }
  }
  return value;
}

function lastMatchingMessage(messages, regex) {
  let value = "";
  for (const message of messages) {
    if (regex.test(message)) value = message;
  }
  return value;
}

function lastMessage(messages) {
  return messages.length ? messages[messages.length - 1] : "";
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
}

function renderCandidates(job) {
  if (job?.status !== "awaiting_selection") {
    ui.layout.classList.remove("has-candidate");
    ui.candidatePanel.setAttribute("aria-hidden", "true");
    return;
  }

  ui.layout.classList.add("has-candidate");
  ui.candidatePanel.setAttribute("aria-hidden", "false");
  const required = Number(job.required_pick_count || 0);
  const candidates = job.candidates || [];
  ui.pickCount.textContent = `需选择 ${required} 条，候选 ${candidates.length} 条`;

  if (lastRenderedCandidateJob === job.id) {
    updatePickCount();
    return;
  }

  lastRenderedCandidateJob = job.id;
  ui.candidateList.innerHTML = candidates
    .map((item, idx) => {
      const checked = idx < required ? "checked" : "";
      const url = item.post_url
        ? `<a href="${escapeAttr(item.post_url)}" target="_blank" rel="noreferrer">原帖</a>`
        : "";
      return `
        <label class="candidate">
          <input type="checkbox" value="${Number(item.index)}" ${checked} />
          <div>
            <div class="candidate-title">
              <strong>#${escapeHtml(item.rank)} ${escapeHtml(item.user_name)}</strong>
              <span class="muted">${escapeHtml(item.publish_time)}</span>
              <span class="score">${escapeHtml(item.score)}</span>
              ${url}
            </div>
            <div class="candidate-content">${escapeHtml(item.content)}</div>
            <div class="candidate-metrics">
              <span>赞 ${escapeHtml(item.likes)}</span>
              <span>评 ${escapeHtml(item.comments)}</span>
              <span>转 ${escapeHtml(item.reposts)}</span>
            </div>
          </div>
        </label>`;
    })
    .join("");
  ui.candidateList.querySelectorAll("input[type=checkbox]").forEach((checkbox) => {
    checkbox.addEventListener("change", updatePickCount);
  });
  updatePickCount();
}

function updatePickCount() {
  const checked = selectedIndexes().length;
  const requiredText = ui.pickCount.textContent.replace(/；已选.*$/, "");
  ui.pickCount.textContent = `${requiredText}；已选 ${checked} 条`;
}

function selectedIndexes() {
  return Array.from(ui.candidateList.querySelectorAll("input[type=checkbox]:checked")).map((input) =>
    Number(input.value),
  );
}

function renderResult(job) {
  const result = job?.result;
  if (!result) {
    ui.resultPanel.classList.add("hidden");
    ui.monitorPanel.classList.remove("collapsed");
    controls.preview.classList.add("hidden");
    controls.preview.disabled = true;
    controls.openResultDir.classList.add("hidden");
    controls.openResultDir.disabled = true;
    hidePreview();
    autoPreviewResultKey = "";
    return;
  }
  ui.resultPanel.classList.remove("hidden");
  ui.monitorPanel.classList.add("collapsed");
  controls.preview.classList.remove("hidden");
  controls.preview.disabled = false;
  controls.openResultDir.classList.remove("hidden");
  controls.openResultDir.disabled = false;
  const rows = [
    ["总帖数", result.total_posts],
    ["导出目录", result.run_dir],
    ["图片目录", result.image_dir],
    ["XLSX", result.xlsx],
    ["CSV", result.csv],
    ["DOCX", Array.isArray(result.docx) ? result.docx.join("\n") : result.docx],
    ["总 DOCX", result.docx_sum],
    ["Markdown", result.md],
    ["摘要", result.summary],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  ui.resultList.innerHTML = rows
    .map(([label, value]) => {
      const text = String(value);
      const html = text
        .split("\n")
        .map((line) => `<div>${escapeHtml(line)}</div>`)
        .join("");
      return `<div class="result-row"><div class="result-label">${escapeHtml(label)}</div><div class="result-value">${html}</div></div>`;
    })
    .join("");

  if (result.md && result.md !== autoPreviewResultKey) {
    autoPreviewResultKey = result.md;
    loadMarkdownPreview({ auto: true });
  }
}

function renderJob(job) {
  currentRenderedJob = job;
  updateStatus(job);
  renderProgress(job);
  renderCandidates(job);
  renderResult(job);

  const active = ["running", "awaiting_selection", "exporting"].includes(job?.status);
  controls.start.disabled = active;
  if (!active && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    renderJob(data.job);
    if (["running", "awaiting_selection", "exporting"].includes(data.job?.status) && !pollTimer) {
      startPolling();
    }
  } catch (err) {
    appendClientLog(`状态刷新失败：${err.message}`);
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(refreshStatus, 1200);
}

function appendClientLog(message) {
  const text = String(message || "").trim();
  if (!text) return;
  showToast(text, /失败|错误|拒绝|异常|failed|error/i.test(text) ? "error" : "info");
}

function showToast(message, state = "success") {
  const text = String(message || "").trim();
  if (!text) return;
  if (!toastStack) {
    toastStack = document.createElement("div");
    toastStack.className = "toast-stack";
    toastStack.setAttribute("aria-live", "polite");
    toastStack.setAttribute("aria-atomic", "true");
    document.body.appendChild(toastStack);
  }

  const toast = document.createElement("div");
  toast.className = `toast ${state}`;
  toast.textContent = text;
  toastStack.appendChild(toast);

  window.setTimeout(() => {
    toast.classList.add("leaving");
    window.setTimeout(() => toast.remove(), 260);
  }, 2600);
}

async function initDefaults() {
  const data = await api("/api/defaults");
  const defaults = data.defaults || {};
  fields.superTopic.value = defaults.super_topic || "";
  fields.cookie.value = defaults.cookie || "";
  fields.windowStart.value = defaults.window_start || "";
  fields.windowEnd.value = defaults.window_end || "";
  fields.maxPages.value = defaults.max_pages || 80;
  fields.topicCommentFactor.value = defaults.topic_comment_factor || 1;
  fields.pauseSeconds.value = defaults.pause_seconds || 1;
  fields.outputDir.value = defaults.output_dir || "";
  applyTheme(defaults.theme === "light" ? "light" : "dark");
  configReady = true;
  setSaveState("配置自动保存", "ready");
}

async function startJob() {
  setBusy(controls.start, true, "正在启动");
  try {
    await saveConfigNow();
    const data = await api("/api/start", {
      method: "POST",
      body: JSON.stringify(readForm()),
    });
    lastRenderedCandidateJob = null;
    renderedPreviewKey = "";
    autoPreviewResultKey = "";
    hidePreview();
    renderJob(data.job);
    startPolling();
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.start, false);
    refreshStatus();
  }
}

async function launchEdgeDebug() {
  setBusy(controls.edgeDebug, true, "正在打开");
  try {
    const data = await api("/api/cookie/edge-debug", { method: "POST", body: "{}" });
    showToast(`调试 Edge 已启动：${data.endpoint}`);
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.edgeDebug, false);
  }
}

async function autoCookie() {
  setBusy(controls.autoCookie, true, "正在读取");
  try {
    const data = await api("/api/cookie/auto", { method: "POST", body: "{}" });
    fields.cookie.value = data.cookie || "";
    await saveConfigNow();
    showToast(data.debug_edge_closed ? "Cookie 自动读取成功，调试 Edge 已关闭。" : "Cookie 自动读取成功。");
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.autoCookie, false);
  }
}

async function readClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    fields.cookie.value = text || "";
    scheduleConfigSave();
    appendClientLog("剪贴板内容已填入 Cookie 文本框。");
  } catch (err) {
    appendClientLog(`读取剪贴板失败：${err.message}`);
  }
}

async function extractCookie() {
  setBusy(controls.extractCookie, true, "正在识别");
  try {
    const data = await api("/api/cookie/extract", {
      method: "POST",
      body: JSON.stringify({ text: fields.cookie.value }),
    });
    fields.cookie.value = data.cookie || "";
    await saveConfigNow();
    appendClientLog("已从粘贴内容中识别 Cookie。");
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.extractCookie, false);
  }
}

async function submitSelection() {
  setBusy(controls.select, true, "正在提交");
  try {
    const data = await api("/api/select", {
      method: "POST",
      body: JSON.stringify({ indexes: selectedIndexes() }),
    });
    renderJob(data.job);
    startPolling();
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.select, false);
  }
}

async function cancelSelection() {
  setBusy(controls.cancelSelect, true, "正在取消");
  try {
    const data = await api("/api/cancel-selection", {
      method: "POST",
      body: "{}",
    });
    renderJob(data.job);
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.cancelSelect, false);
  }
}

async function openResultDir() {
  setBusy(controls.openResultDir, true, "正在打开");
  try {
    const data = await api("/api/open-result-dir", { method: "POST", body: "{}" });
    showToast(`已打开：${data.path || "导出目录"}`);
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.openResultDir, false);
  }
}

async function loadMarkdownPreview(options = {}) {
  const isAuto = Boolean(options.auto);
  if (!isAuto) {
    setBusy(controls.preview, true, "正在载入");
  }
  try {
    const data = await api("/api/report-preview");
    const key = `${data.path || ""}:${data.markdown?.length || 0}`;
    if (key !== renderedPreviewKey) {
      ui.previewContent.innerHTML = renderMarkdown(data.markdown || "");
      renderedPreviewKey = key;
    }
    ui.previewPath.textContent = data.path || "";
    showPreview();
    if (!isAuto || window.innerWidth <= 980) {
      ui.previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    if (!isAuto) {
      setBusy(controls.preview, false);
    }
  }
}

function showPreview() {
  ui.layout.classList.add("has-preview");
  ui.previewPanel.setAttribute("aria-hidden", "false");
  controls.preview.textContent = "关闭预览";
}

function hidePreview() {
  ui.layout.classList.remove("has-preview");
  ui.previewPanel.setAttribute("aria-hidden", "true");
  controls.preview.textContent = "预览 Markdown";
}

async function loadHelpDoc() {
  try {
    const data = await api("/api/help-doc");
    ui.helpContent.innerHTML = renderMarkdown(data.markdown || "");
    ui.helpPath.textContent = data.path || "";
    showHelpDialog();
  } catch (err) {
    appendClientLog(err.message);
  }
}

function showHelpDialog() {
  ui.helpDialog.style.left = "";
  ui.helpDialog.style.top = "";
  ui.helpDialog.style.transform = "";
  ui.helpOverlay.classList.add("visible");
  ui.helpOverlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("help-modal-open");
  ui.helpClose.focus();
}

function closeHelpDialog() {
  ui.helpOverlay.classList.remove("visible");
  ui.helpOverlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("help-modal-open");
}

function startHelpDrag(event) {
  if (event.button !== 0 || event.target.closest("button, a, input, textarea")) return;
  const rect = ui.helpDialog.getBoundingClientRect();
  helpDragState = {
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
  };
  ui.helpDialog.classList.add("dragging");
  ui.helpDialog.style.left = `${rect.left}px`;
  ui.helpDialog.style.top = `${rect.top}px`;
  ui.helpDialog.style.transform = "none";
  window.addEventListener("pointermove", dragHelpDialog);
  window.addEventListener("pointerup", stopHelpDrag, { once: true });
  event.preventDefault();
}

function dragHelpDialog(event) {
  if (!helpDragState) return;
  const rect = ui.helpDialog.getBoundingClientRect();
  const margin = 12;
  const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin);
  const maxTop = Math.max(margin, window.innerHeight - rect.height - margin);
  const left = clamp(event.clientX - helpDragState.offsetX, margin, maxLeft);
  const top = clamp(event.clientY - helpDragState.offsetY, margin, maxTop);
  ui.helpDialog.style.left = `${left}px`;
  ui.helpDialog.style.top = `${top}px`;
}

function stopHelpDrag() {
  helpDragState = null;
  ui.helpDialog.classList.remove("dragging");
  window.removeEventListener("pointermove", dragHelpDialog);
}

function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let listMode = null;

  function closeList() {
    if (listMode) {
      html.push(`</${listMode}>`);
      listMode = null;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (!trimmed) {
      closeList();
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(trimmed);
    if (image) {
      closeList();
      const src = reportAssetUrl(image[2]);
      html.push(`<img src="${escapeAttr(src)}" alt="${escapeAttr(image[1])}" loading="lazy" />`);
      continue;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      if (listMode !== "ul") {
        closeList();
        html.push("<ul>");
        listMode = "ul";
      }
      html.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
    if (ordered) {
      if (listMode !== "ol") {
        closeList();
        html.push("<ol>");
        listMode = "ol";
      }
      html.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }
  closeList();
  return html.join("");
}

function inlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
    const href = /^https?:\/\//i.test(url) ? url : reportAssetUrl(url);
    return `<a href="${escapeAttr(href)}" target="_blank" rel="noreferrer">${label}</a>`;
  });
  return html;
}

function reportAssetUrl(raw) {
  const text = String(raw || "").trim();
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(text)) return text;
  return `/api/report-asset?path=${encodeURIComponent(text)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function currentTheme() {
  return document.body.classList.contains("light-theme") ? "light" : "dark";
}

function applyTheme(theme) {
  const nextTheme = theme === "light" ? "light" : "dark";
  document.body.classList.toggle("light-theme", nextTheme === "light");
  controls.themeToggle.classList.toggle("is-light", nextTheme === "light");
  controls.themeToggle.setAttribute(
    "aria-label",
    nextTheme === "light" ? "切换为暗色主题" : "切换为亮色主题",
  );
  controls.themeToggle.title = controls.themeToggle.getAttribute("aria-label") || "";
}

function initThemeToggle() {
  applyTheme("dark");
  controls.themeToggle.addEventListener("click", () => {
    const nextTheme = currentTheme() === "light" ? "dark" : "light";
    applyTheme(nextTheme);
    saveConfigNow();
  });
}

function initParticleLayer() {
  if (!ui.particleLayer || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }
  const fragment = document.createDocumentFragment();
  const particleCount = Math.min(130, Math.max(72, Math.floor(window.innerWidth / 11)));
  for (let index = 0; index < particleCount; index += 1) {
    const particle = document.createElement("span");
    particle.className = "particle";
    particle.style.setProperty("--x", String(Math.random() * 100));
    particle.style.setProperty("--size", `${(Math.random() * 1.8 + 1.1).toFixed(2)}px`);
    particle.style.setProperty("--opacity", (Math.random() * 0.34 + 0.18).toFixed(2));
    particle.style.setProperty("--duration", `${(Math.random() * 18 + 22).toFixed(2)}s`);
    particle.style.setProperty("--delay", `${(-Math.random() * 30).toFixed(2)}s`);
    particle.style.setProperty("--tilt", `${(Math.random() * 46 - 23).toFixed(2)}deg`);
    fragment.appendChild(particle);
  }
  ui.particleLayer.replaceChildren(fragment);
  window.addEventListener("pointermove", scheduleParticleRepel, { passive: true });
  document.addEventListener("mouseleave", resetParticleRepel);
  window.addEventListener("blur", resetParticleRepel);
}

function scheduleParticleRepel(event) {
  particlePointer = { x: event.clientX, y: event.clientY };
  if (particleFrame) return;
  particleFrame = window.requestAnimationFrame(updateParticleRepel);
}

function updateParticleRepel() {
  particleFrame = 0;
  if (!particlePointer || !ui.particleLayer) return;
  const radius = 150;
  const maxOffset = 66;
  for (const particle of ui.particleLayer.children) {
    const rect = particle.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const dx = centerX - particlePointer.x;
    const dy = centerY - particlePointer.y;
    const distance = Math.hypot(dx, dy);
    if (!distance || distance > radius) {
      particle.style.setProperty("--repel-x", "0px");
      particle.style.setProperty("--repel-y", "0px");
      continue;
    }
    const force = ((radius - distance) / radius) ** 2 * maxOffset;
    particle.style.setProperty("--repel-x", `${((dx / distance) * force).toFixed(2)}px`);
    particle.style.setProperty("--repel-y", `${((dy / distance) * force).toFixed(2)}px`);
  }
}

function resetParticleRepel() {
  particlePointer = null;
  if (!ui.particleLayer) return;
  for (const particle of ui.particleLayer.children) {
    particle.style.setProperty("--repel-x", "0px");
    particle.style.setProperty("--repel-y", "0px");
  }
}

controls.help.addEventListener("click", loadHelpDoc);
controls.start.addEventListener("click", startJob);
controls.edgeDebug.addEventListener("click", launchEdgeDebug);
controls.autoCookie.addEventListener("click", autoCookie);
controls.clipboard.addEventListener("click", readClipboard);
controls.extractCookie.addEventListener("click", extractCookie);
controls.select.addEventListener("click", submitSelection);
controls.cancelSelect.addEventListener("click", cancelSelection);
controls.openResultDir.addEventListener("click", openResultDir);
controls.preview.addEventListener("click", () => {
  if (ui.previewPanel.getAttribute("aria-hidden") === "true") {
    loadMarkdownPreview();
  } else {
    hidePreview();
  }
});
ui.helpClose.addEventListener("click", closeHelpDialog);
ui.helpOverlay.addEventListener("click", (event) => {
  if (event.target === ui.helpOverlay) {
    closeHelpDialog();
  }
});
ui.helpDragHandle.addEventListener("pointerdown", startHelpDrag);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && ui.helpOverlay.classList.contains("visible")) {
    closeHelpDialog();
  }
});

[fields.superTopic, fields.cookie, fields.outputDir].forEach((field) => {
  field.addEventListener("input", scheduleConfigSave);
});

initThemeToggle();
initParticleLayer();

initDefaults()
  .then(async () => {
    await refreshStatus();
    await loadHelpDoc();
  })
  .catch((err) => {
    appendClientLog(err.message);
  });
