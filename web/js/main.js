const $ = window.WeiboUtils?.$ || ((id) => document.getElementById(id));

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
  advancedMode: $("advancedModeToggle"),
  start: $("startBtn"),
  cancelJob: $("cancelJobBtn"),
  edgeDebug: $("edgeDebugBtn"),
  autoCookie: $("autoCookieBtn"),
  clipboard: $("clipboardBtn"),
  extractCookie: $("extractCookieBtn"),
  checkCookie: $("checkCookieBtn"),
  clearCookie: $("clearCookieBtn"),
  cookieExpand: $("cookieExpandBtn"),
  cookieCollapse: $("cookieCollapseBtn"),
  select: $("selectBtn"),
  cancelSelect: $("cancelSelectBtn"),
  candidateFilter: $("candidateFilter"),
  candidateSort: $("candidateSort"),
  preview: $("previewBtn"),
  refreshPreview: $("refreshPreviewBtn"),
  copyMarkdown: $("copyMarkdownBtn"),
  openResultDir: $("openResultDirBtn"),
  logSearch: $("logSearch"),
  logLevelFilter: $("logLevelFilter"),
  copyLog: $("copyLogBtn"),
  downloadLog: $("downloadLogBtn"),
  clearLogView: $("clearLogViewBtn"),
  logBottom: $("logBottomBtn"),
  checkCache: $("checkCacheBtn"),
  reexport: $("reexportBtn"),
  preflightToggle: $("preflightToggleBtn"),
  preflightClose: $("preflightCloseBtn"),
  preflightCancel: $("preflightCancelBtn"),
  preflightProceed: $("preflightProceedBtn"),
};

const ui = {
  particleLayer: $("particleLayer"),
  layout: $("layout"),
  statusPill: $("statusPill"),
  saveState: $("saveState"),
  jobMeta: $("jobMeta"),
  monitorPanel: $("monitorPanel"),
  logBox: $("logBox"),
  logPanel: $("logPanel"),
  backendLogBox: $("backendLogBox"),
  logCount: $("logCount"),
  candidatePanel: $("candidatePanel"),
  candidateList: $("candidateList"),
  pickCount: $("pickCount"),
  resultPanel: $("resultPanel"),
  resultList: $("resultList"),
  cacheStatusBox: $("cacheStatusBox"),
  reexportRunDir: $("reexportRunDir"),
  previewPanel: $("previewPanel"),
  previewContent: $("previewContent"),
  previewPath: $("previewPath"),
  cookieSummary: $("cookieSummary"),
  cookieStateBadge: $("cookieStateBadge"),
  cookieEditor: $("cookieEditor"),
  advancedFields: $("advancedFields"),
  preflightPanel: $("preflightPanel"),
  preflightSummary: $("preflightSummary"),
  preflightList: $("preflightList"),
  preflightOverlay: $("preflightOverlay"),
  preflightModalSummary: $("preflightModalSummary"),
  preflightModalList: $("preflightModalList"),
  helpOverlay: $("helpOverlay"),
  helpDialog: $("helpDialog"),
  helpDragHandle: $("helpDragHandle"),
  helpContent: $("helpContent"),
  helpPath: $("helpPath"),
  helpClose: $("helpCloseBtn"),
};

const PREFLIGHT_SESSION_KEY = "weibo_preflight_session_v2";
const LEGACY_PREFLIGHT_STORAGE_KEY = "weibo_preflight_cache_v1";

let pollTimer = null;
let pollFailures = 0;
let renderedPreviewKey = "";
let autoPreviewResultKey = "";
let currentMarkdown = "";
let configReady = false;
let configSaveTimer = null;
let currentRenderedJob = null;
let toastStack = null;
let helpDragState = null;
let particleFrame = 0;
let particlePointer = null;
let cookieValidationState = "unverified";
let lastLogJobId = "";
let logClearCursor = 0;
let visibleLogEntries = [];
let candidateJobId = "";
let candidateSelections = new Set();
let candidateExpanded = new Set();
let preflightPendingPayload = null;
let preflightCollapseTimer = null;
let lastPreflight = null;
let lastCacheStatusKey = "";
let lastCacheCanReexport = false;

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
  if (window.WeiboApi?.request) {
    return window.WeiboApi.request(path, options);
  }
  const init = {
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  return fetch(path, init).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(formatApiError(data, response.status));
    }
    return data;
  });
}

function formatApiError(data, status) {
  if (window.WeiboApi?.formatError) {
    return window.WeiboApi.formatError(data, status);
  }
  if (data && typeof data.error === "object" && data.error) {
    const message = data.error.message || `请求失败：${status}`;
    const suggestion = data.error.suggestion ? `建议：${data.error.suggestion}` : "";
    return [message, suggestion].filter(Boolean).join("。");
  }
  return String(data?.error || `请求失败：${status}`);
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
    advanced_mode: controls.advancedMode.checked,
  };
}

function configPayload() {
  return {
    super_topic: fields.superTopic.value.trim(),
    cookie: fields.cookie.value.trim(),
    max_pages: fields.maxPages.value,
    topic_comment_factor: fields.topicCommentFactor.value,
    pause_seconds: fields.pauseSeconds.value,
    output_dir: fields.outputDir.value.trim(),
    theme: currentTheme(),
    advanced_mode: controls.advancedMode.checked,
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

const STAGE_LABELS = {
  init: "初始化任务",
  crawl: "抓取帖子",
  hydrate: "正文补全",
  score: "评论分析与评分",
  selection: "人工筛选",
  images: "图片下载",
  export: "导出文件",
  completed: "完成",
};

function updateStatus(job) {
  const status = job?.status || "";
  ui.statusPill.className = `status-pill ${status}`;
  ui.statusPill.textContent = statusText(status);
  ui.jobMeta.textContent = job
    ? `${job.stage_label || statusText(status)} / ${job.progress?.message || job.updated_at || ""}`
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
  if (Array.isArray(job?.subtasks) && job.subtasks.length) {
    const currentStage = job.stage || "";
    const progressMessage = job.progress?.message || job.stage_label || "";
    return job.subtasks.map((item, index) => {
      const state = normalizeSubtaskStatus(item.status);
      const isCurrent =
        item.id === currentStage || state === "active" || state === "failed" || state === "cancelled";
      return progressStep(
        item.id || `stage-${index}`,
        item.label || STAGE_LABELS[item.id] || item.id || "任务阶段",
        isCurrent ? progressMessage : subtaskDetailByState(state),
        Number(item.percent || 0),
        state,
        isCurrent && job.progress?.total ? `${job.progress.current || 0}/${job.progress.total}` : `阶段 ${index + 1}/${job.subtasks.length}`,
      );
    });
  }

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

function createProgressItem() {
  const node = document.createElement("div");
  node.className = "progress-item";
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

function normalizeSubtaskStatus(status) {
  if (["pending", "active", "done", "failed", "cancelled", "waiting"].includes(status)) {
    return status;
  }
  return "pending";
}

function subtaskDetailByState(state) {
  return (
    {
      pending: "等待前置阶段完成",
      active: "正在处理",
      done: "阶段已完成",
      failed: "阶段失败",
      cancelled: "任务已取消",
      waiting: "等待人工确认",
    }[state] || ""
  );
}

function currentSelectedCount(job) {
  if (job?.status === "awaiting_selection") {
    return candidateSelections.size;
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

function renderBackendLogs(job) {
  if (!ui.backendLogBox) return;
  if ((job?.id || "") !== lastLogJobId) {
    lastLogJobId = job?.id || "";
    logClearCursor = 0;
  }
  const eventLogs = Array.isArray(job?.events)
    ? job.events
        .filter((item) => ["log", "warning", "error"].includes(item.type))
        .map((item, index) => ({
          index,
          time: shortTime(item.created_at || ""),
          stage: item.stage || "",
          level: normalizeLogLevel(item.level || item.type),
          message: sanitizeLogMessage(item.message || ""),
        }))
    : [];
  const allLogs = eventLogs.length
    ? eventLogs
    : (job?.logs || []).map((item, index) => ({
        index,
        time: item.time || "",
        stage: "",
        level: logLevel(item.message || ""),
        message: sanitizeLogMessage(item.message || ""),
      }));
  const rows = allLogs.slice(logClearCursor);
  const levelFilter = controls.logLevelFilter.value || "all";
  const search = controls.logSearch.value.trim().toLowerCase();
  const nearBottom = isLogNearBottom();
  visibleLogEntries = rows
    .filter((item) => levelFilter === "all" || item.level === levelFilter)
    .filter((item) => !search || `${item.time} ${item.stage} ${item.level} ${item.message}`.toLowerCase().includes(search));

  ui.logCount.textContent = `${visibleLogEntries.length}/${rows.length} 条日志`;
  if (!visibleLogEntries.length) {
    ui.backendLogBox.innerHTML = `<div class="empty-state">暂无匹配日志</div>`;
    return;
  }
  ui.backendLogBox.innerHTML = visibleLogEntries
    .map(
      (item) => `
        <div class="backend-log-line ${item.level}">
          <span class="backend-log-time">[${escapeHtml(item.time)}]</span>
          <span class="backend-log-message">[${escapeHtml(stageName(item.stage))}] [${escapeHtml(logLevelLabel(item.level))}] ${escapeHtml(item.message)}</span>
        </div>`,
    )
    .join("");
  if (nearBottom) {
    scrollLogToBottom();
  }
}

function isLogNearBottom() {
  const node = ui.backendLogBox;
  if (!node) return true;
  return node.scrollHeight - node.scrollTop - node.clientHeight < 42;
}

function scrollLogToBottom() {
  if (!ui.backendLogBox) return;
  ui.backendLogBox.scrollTop = ui.backendLogBox.scrollHeight;
}

function logLevel(message) {
  if (/失败|错误|异常|访客验证|未成功|不可写|invalid|error|failed/i.test(message)) return "error";
  if (/警告|可能|跳过|无命中|等待|建议|warning/i.test(message)) return "warning";
  if (/成功|完成|已保存|已生成|可用|completed|saved/i.test(message)) return "success";
  return "normal";
}

function normalizeLogLevel(level) {
  if (level === "success") return "success";
  if (level === "warning") return "warning";
  if (level === "error") return "error";
  if (level === "debug" || level === "info") return "normal";
  return "normal";
}

function logLevelLabel(level) {
  return (
    {
      normal: "普通",
      success: "成功",
      warning: "警告",
      error: "错误",
    }[level] || "普通"
  );
}

function stageName(stage) {
  if (!stage) return "任务";
  return STAGE_LABELS[stage] || stage;
}

function shortTime(value) {
  const text = String(value || "");
  const match = /(\d{2}:\d{2}:\d{2})/.exec(text);
  return match ? match[1] : text;
}

function sanitizeLogMessage(message) {
  return String(message || "").replace(
    /\b(ALF|SCF|SUB|SUBP|WBPSESS|XSRF-TOKEN|SSOLoginState|MLOGIN|_T_WM|M_WEIBOCN_PARAMS)=([^;\s]+)/g,
    "$1=***",
  );
}

async function copyVisibleLogs() {
  const text = visibleLogEntries
    .map((item) => `[${item.time}] [${stageName(item.stage)}] [${logLevelLabel(item.level)}] ${item.message}`)
    .join("\n");
  if (!text) {
    showToast("当前没有可复制的日志。", "info");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast("日志已复制。");
  } catch (err) {
    appendClientLog(`复制日志失败：${err.message}`);
  }
}

function downloadVisibleLogs() {
  const text = visibleLogEntries
    .map((item) => `[${item.time}] [${stageName(item.stage)}] [${logLevelLabel(item.level)}] ${item.message}`)
    .join("\n");
  if (!text) {
    showToast("当前没有可下载的日志。", "info");
    return;
  }
  const stamp = formatDateForFilename(new Date());
  const blob = new Blob([text + "\n"], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `weibo_super_stats_log_${stamp}.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

function clearLogView() {
  const logs = currentRenderedJob?.logs || [];
  logClearCursor = logs.length;
  renderBackendLogs(currentRenderedJob);
  showToast("前端日志显示已清空。", "info");
}

function formatDateForFilename(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

function renderCandidates(job) {
  if (job?.status !== "awaiting_selection") {
    ui.layout.classList.remove("has-candidate");
    ui.candidatePanel.setAttribute("aria-hidden", "true");
    return;
  }

  ui.layout.classList.add("has-candidate");
  ui.candidatePanel.setAttribute("aria-hidden", "false");
  const required = requiredPickCount(job);
  const candidates = job.candidates || [];

  if (candidateJobId !== job.id) {
    candidateJobId = job.id;
    candidateSelections = new Set(candidates.slice(0, required).map((item) => Number(item.index)));
    candidateExpanded = new Set();
  }

  const visible = filterAndSortCandidates(candidates);
  ui.candidateList.innerHTML = visible.length
    ? visible.map((item) => candidateCardHtml(item)).join("")
    : `<div class="empty-state">没有匹配的候选帖子</div>`;
  updatePickCount(job);
}

function requiredPickCount(job) {
  return Number(job?.required_pick_count || 15);
}

function filterAndSortCandidates(candidates) {
  const filter = controls.candidateFilter.value || "all";
  const sort = controls.candidateSort.value || "score";
  const threshold = highCommentThreshold(candidates);
  return [...candidates]
    .filter((item) => {
      const index = Number(item.index);
      if (filter === "selected") return candidateSelections.has(index);
      if (filter === "unselected") return !candidateSelections.has(index);
      if (filter === "images") return Number(item.image_count || 0) > 0;
      if (filter === "high_comments") return Number(item.comments || 0) >= threshold;
      return true;
    })
    .sort((a, b) => compareCandidate(a, b, sort));
}

function highCommentThreshold(candidates) {
  const maxComments = Math.max(0, ...candidates.map((item) => Number(item.comments || 0)));
  return Math.max(10, Math.ceil(maxComments * 0.6));
}

function compareCandidate(a, b, sort) {
  if (sort === "publish_time") {
    const aTime = Date.parse(a.publish_time || "") || 0;
    const bTime = Date.parse(b.publish_time || "") || 0;
    return bTime - aTime;
  }
  return Number(b[sort] || 0) - Number(a[sort] || 0);
}

function candidateCardHtml(item) {
  const index = Number(item.index);
  const checked = candidateSelections.has(index);
  const expanded = candidateExpanded.has(index);
  const content = expanded ? item.content_full || item.content || "" : item.content_excerpt || item.content || "";
  const imageCount = Number(item.image_count || 0);
  const previewPaths = Array.isArray(item.image_preview_paths) ? item.image_preview_paths : [];
  const previews = previewPaths
    .map(candidatePreviewUrl)
    .filter(Boolean)
    .map((src) => `<img src="${escapeAttr(src)}" alt="候选图片预览" loading="lazy" />`)
    .join("");
  const postButton = item.post_url
    ? `<a class="candidate-link" href="${escapeAttr(item.post_url)}" target="_blank" rel="noreferrer">原帖链接</a>`
    : `<span class="candidate-link disabled">无原帖链接</span>`;

  return `
    <article class="candidate ${checked ? "selected" : ""}" data-index="${index}">
      <div class="candidate-check">
        <input type="checkbox" value="${index}" ${checked ? "checked" : ""} aria-label="选择第 ${escapeAttr(item.rank)} 条" />
        <span class="mini-badge">${checked ? "已选" : "未选"}</span>
      </div>
      <div class="candidate-body">
        <div class="candidate-title">
          <strong>#${escapeHtml(item.rank)} ${escapeHtml(item.user_name || "未知作者")}</strong>
          <span class="muted">${escapeHtml(item.publish_time || "")}</span>
          <span class="score">综合分 ${escapeHtml(item.score)}</span>
        </div>
        <div class="candidate-metrics">
          <span>赞 ${escapeHtml(item.likes)}</span>
          <span>评 ${escapeHtml(item.comments)}</span>
          <span>转 ${escapeHtml(item.reposts)}</span>
          ${imageCount ? `<span>图片 ${imageCount} 张</span>` : ""}
        </div>
        <div class="candidate-content ${expanded ? "expanded" : ""}">${escapeHtml(content)}</div>
        ${previews ? `<div class="candidate-previews">${previews}</div>` : ""}
        <div class="candidate-card-actions">
          ${postButton}
          <button type="button" class="secondary small-button" data-toggle-full="${index}">
            ${expanded ? "收起全文" : "展开全文"}
          </button>
        </div>
      </div>
    </article>`;
}

function candidatePreviewUrl(path) {
  const text = String(path || "").trim();
  if (!text) return "";
  if (/^https?:\/\//i.test(text) || text.startsWith("/")) return text;
  return "";
}

function updatePickCount(job = currentRenderedJob) {
  if (!job || job.status !== "awaiting_selection") return;
  const checked = candidateSelections.size;
  const required = requiredPickCount(job);
  const diff = required - checked;
  let hint = "数量正确，可以确认";
  let valid = true;
  if (diff > 0) {
    hint = `还需选择 ${diff} 条`;
    valid = false;
  } else if (diff < 0) {
    hint = `已多选 ${Math.abs(diff)} 条`;
    valid = false;
  }
  ui.pickCount.textContent = `已选 ${checked} / ${required}；${hint}`;
  controls.select.disabled = !valid || Boolean(controls.select.dataset.busyText);
}

function selectedIndexes() {
  return [...candidateSelections].sort((a, b) => a - b);
}

function handleCandidateClick(event) {
  const toggle = event.target.closest("[data-toggle-full]");
  if (toggle) {
    const index = Number(toggle.dataset.toggleFull);
    if (candidateExpanded.has(index)) {
      candidateExpanded.delete(index);
    } else {
      candidateExpanded.add(index);
    }
    renderCandidates(currentRenderedJob);
  }
}

function handleCandidateChange(event) {
  const checkbox = event.target.closest("input[type=checkbox]");
  if (!checkbox) return;
  const index = Number(checkbox.value);
  if (checkbox.checked) {
    candidateSelections.add(index);
  } else {
    candidateSelections.delete(index);
  }
  renderCandidates(currentRenderedJob);
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
    if (ui.cacheStatusBox) ui.cacheStatusBox.textContent = "尚未检查缓存";
    if (controls.reexport) controls.reexport.disabled = true;
    lastCacheStatusKey = "";
    lastCacheCanReexport = false;
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
  renderResultList(result);
  if (ui.reexportRunDir && result.run_dir && ui.reexportRunDir.value !== result.run_dir) {
    ui.reexportRunDir.value = result.run_dir;
  }
  if (result.run_dir && result.run_dir !== lastCacheStatusKey) {
    checkCacheStatus({ silent: true });
  }

  if (result.md && result.md !== autoPreviewResultKey) {
    autoPreviewResultKey = result.md;
    loadMarkdownPreview({ auto: true });
  }
}

function renderResultList(result) {
  const manifest = result.manifest || {};
  const files = manifest.files || {};
  const warnings = result.warnings || manifest.warnings || [];
  const failedImageCount = Number(result.failed_image_count || manifest.failed_image_count || 0);
  const rows = [
    resultInfoRow("导出目录", result.run_dir || manifest.run_dir, true),
    resultFileRow("Markdown 文件", normalizeFileItem(files.markdown, "Markdown", result.md, "preview_markdown")),
    ...arrayFileRows("DOCX 文件", files.docx || result.docx),
    resultFileRow("总 DOCX", normalizeFileItem(files.docx_sum, "总 DOCX", result.docx_sum)),
    resultFileRow("XLSX 文件", normalizeFileItem(files.xlsx || files.excel, "XLSX", result.xlsx)),
    resultFileRow("CSV 文件", normalizeFileItem(files.csv, "CSV", result.csv)),
    resultFileRow("summary txt 文件", normalizeFileItem(files.summary, "summary txt", result.summary)),
    resultFileRow("images 图片目录", normalizeFileItem(files.images || files.images_dir, "images 图片目录", result.image_dir, "open_result_dir")),
    failedImageCount ? resultInfoRow("失败图片数量", `${failedImageCount} 张`, false) : "",
    ...warnings.map((warning) => resultInfoRow("警告", warning, false, "warning")),
  ].filter(Boolean);
  ui.resultList.innerHTML = rows.join("");
}

function arrayFileRows(label, value) {
  if (!value) return [];
  const rows = Array.isArray(value) ? value : [value];
  return rows.map((item, index) => {
    const rowLabel = rows.length > 1 ? `${label} ${index + 1}` : label;
    return resultFileRow(rowLabel, normalizeFileItem(item, rowLabel));
  });
}

function normalizeFileItem(item, label, fallbackPath = "", action = "") {
  if (!item && fallbackPath) return pathToFileItem(label, fallbackPath, action);
  if (!item) return null;
  if (typeof item === "string") return pathToFileItem(label, item, action);
  if (item.path || item.relative_path || item.name) return { ...item, action: item.action || action };
  return pathToFileItem(label, String(item), action);
}

function pathToFileItem(label, path, action = "") {
  if (!path) return null;
  const name = String(path).split(/[\\/]/).filter(Boolean).pop() || String(path);
  return { label, name, path: String(path), relative_path: String(path), exists: true, action };
}

function resultFileRow(label, item) {
  if (!item) return "";
  const path = item.path || "";
  const exists = item.exists !== false;
  const action = item.action || "";
  const previewButton =
    action === "preview_markdown"
      ? `<button type="button" class="secondary small-button" data-preview-md="1">预览 Markdown</button>`
      : "";
  const openButton =
    action === "open_result_dir"
      ? `<button type="button" class="secondary small-button" data-open-result="1">打开导出目录</button>`
      : "";
  return `
    <div class="result-row file-row ${exists ? "exists" : "missing"}">
      <div class="result-label">${escapeHtml(label)}</div>
      <div class="result-value">
        <div class="result-file-head">
          <strong>${escapeHtml(item.name || "未生成")}</strong>
          <span class="mini-badge">${exists ? "存在" : "不存在"}</span>
        </div>
        <div class="result-path">${escapeHtml(item.relative_path || path || "")}</div>
        <div class="result-actions">
          ${previewButton}
          ${openButton}
          ${path ? `<button type="button" class="secondary small-button" data-copy-path="${escapeAttr(path)}">复制路径</button>` : ""}
        </div>
      </div>
    </div>`;
}

function resultInfoRow(label, value, copyable = false, state = "") {
  return `
    <div class="result-row ${state}">
      <div class="result-label">${escapeHtml(label)}</div>
      <div class="result-value">
        <div class="result-path">${escapeHtml(value || "")}</div>
        ${copyable && value ? `<div class="result-actions"><button type="button" class="secondary small-button" data-copy-path="${escapeAttr(value)}">复制路径</button></div>` : ""}
      </div>
    </div>`;
}

function handleResultClick(event) {
  const copyButton = event.target.closest("[data-copy-path]");
  if (copyButton) {
    copyText(copyButton.dataset.copyPath || "", "路径已复制。");
    return;
  }
  if (event.target.closest("[data-preview-md]")) {
    loadMarkdownPreview();
    return;
  }
  if (event.target.closest("[data-open-result]")) {
    openResultDir();
  }
}

function renderJob(job) {
  currentRenderedJob = job;
  updateStatus(job);
  renderProgress(job);
  renderBackendLogs(job);
  renderCandidates(job);
  renderResult(job);

  const active = ["running", "awaiting_selection", "exporting"].includes(job?.status);
  controls.start.disabled = active;
  controls.cancelJob.classList.toggle("hidden", !active);
  controls.cancelJob.disabled = !active || Boolean(controls.cancelJob.dataset.busyText);
  if (!active && pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    pollFailures = 0;
    const job = data.data?.job ?? data.job;
    renderJob(job);
    scheduleNextPoll(job);
  } catch (err) {
    pollFailures += 1;
    appendClientLog(`状态刷新失败：${err.message}`);
    scheduleNextPoll(currentRenderedJob);
  }
}

function startPolling() {
  scheduleNextPoll(currentRenderedJob, 0);
}

function scheduleNextPoll(job, overrideDelay = null) {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  if (!["running", "awaiting_selection", "exporting"].includes(job?.status)) {
    return;
  }
  const delay = overrideDelay ?? nextPollDelay(job);
  pollTimer = window.setTimeout(refreshStatus, delay);
}

function nextPollDelay(job) {
  if (pollFailures === 1) return 2000;
  if (pollFailures === 2) return 5000;
  if (pollFailures >= 3) return 10000;
  if (document.hidden) return 5000;
  if (job?.status === "awaiting_selection") return 2500;
  return 1000;
}

function appendClientLog(message) {
  const text = sanitizeLogMessage(String(message || "").trim());
  if (!text) return;
  showToast(text, /失败|错误|拒绝|异常|failed|error/i.test(text) ? "error" : "info");
}

function showToast(message, state = "success") {
  const text = sanitizeLogMessage(String(message || "").trim());
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
  }, 3000);
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
  setAdvancedMode(defaults.advanced_mode === true || defaults.advanced_mode === "true");
  applyTheme(defaults.theme === "light" ? "light" : "dark");
  updateCookieSummary();
  configReady = true;
  setSaveState("配置自动保存", "ready");
}

async function startJob() {
  setBusy(controls.start, true, "正在检查");
  try {
    await saveConfigNow();
    const payload = readForm();
    const response = await api("/api/preflight", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const preflight = response.data || response;
    renderPreflightInline(preflight);
    const hasError = preflight.checks?.some((item) => item.status === "error");
    const hasWarning = preflight.checks?.some((item) => item.status === "warning");
    if (hasError || hasWarning) {
      showPreflightModal(preflight, !hasError, payload);
      return;
    }
    showToast("预检查通过，开始任务。");
    setBusy(controls.start, false);
    await startJobAfterPreflight(payload);
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    if (!["running", "awaiting_selection", "exporting"].includes(currentRenderedJob?.status)) {
      setBusy(controls.start, false);
    } else {
      controls.start.disabled = true;
    }
  }
}

async function startJobAfterPreflight(payload = readForm()) {
  setBusy(controls.start, true, "正在启动");
  try {
    const data = await api("/api/start", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const job = data.data?.job ?? data.job;
    candidateJobId = "";
    renderedPreviewKey = "";
    autoPreviewResultKey = "";
    currentMarkdown = "";
    hidePreview();
    renderJob(job);
    startPolling();
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.start, false);
    if (["running", "awaiting_selection", "exporting"].includes(currentRenderedJob?.status)) {
      controls.start.disabled = true;
    }
    refreshStatus();
  }
}

function renderPreflightInline(preflight, options = {}) {
  const checks = preflight.checks || [];
  const { collapsed = false, restore = false } = options;
  clearTimeout(preflightCollapseTimer);
  if (!checks.length) {
    resetPreflightInline();
    return;
  }
  ui.preflightPanel.classList.remove("hidden");
  lastPreflight = preflight;
  ui.preflightSummary.textContent = preflightSummaryText(checks);
  renderCheckList(ui.preflightList, checks);
  setPreflightCollapsed(collapsed);
  if (!restore) {
    preflightCollapseTimer = window.setTimeout(() => {
      setPreflightCollapsed(true);
    }, 2000);
  }
}

function resetPreflightInline() {
  clearTimeout(preflightCollapseTimer);
  preflightCollapseTimer = null;
  lastPreflight = null;
  ui.preflightPanel.classList.add("hidden");
  ui.preflightPanel.classList.remove("collapsed");
  ui.preflightPanel.setAttribute("aria-expanded", "false");
  ui.preflightSummary.textContent = "";
  ui.preflightList.innerHTML = "";
  if (controls.preflightToggle) {
    controls.preflightToggle.textContent = "展开";
    controls.preflightToggle.setAttribute("aria-expanded", "false");
  }
  clearPreflightCache();
}

function setPreflightCollapsed(collapsed) {
  const isCollapsed = Boolean(collapsed);
  ui.preflightPanel.classList.toggle("collapsed", isCollapsed);
  ui.preflightPanel.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
  if (controls.preflightToggle) {
    controls.preflightToggle.textContent = isCollapsed ? "展开" : "收起";
    controls.preflightToggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
  }
  persistPreflightCache(isCollapsed);
}

function preflightFormKey(payload = readForm()) {
  return JSON.stringify({
    super_topic: payload.super_topic || "",
    cookie_present: Boolean(payload.cookie),
    cookie_length: String(payload.cookie || "").length,
    window_start: payload.window_start || "",
    window_end: payload.window_end || "",
    max_pages: payload.max_pages || "",
    topic_comment_factor: payload.topic_comment_factor || "",
    pause_seconds: payload.pause_seconds || "",
    output_dir: payload.output_dir || "",
  });
}

function persistPreflightCache(collapsed) {
  if (!lastPreflight?.checks?.length) return;
  try {
    sessionStorage.setItem(
      PREFLIGHT_SESSION_KEY,
      JSON.stringify({
        preflight: lastPreflight,
        collapsed: Boolean(collapsed),
        form_key: preflightFormKey(),
        saved_at: Date.now(),
      }),
    );
  } catch (err) {
    // Ignore storage failures.
  }
}

function clearPreflightCache() {
  try {
    sessionStorage.removeItem(PREFLIGHT_SESSION_KEY);
    localStorage.removeItem(LEGACY_PREFLIGHT_STORAGE_KEY);
  } catch (err) {
    // Ignore storage failures.
  }
}

function clearLegacyPreflightCache() {
  try {
    localStorage.removeItem(LEGACY_PREFLIGHT_STORAGE_KEY);
  } catch (err) {
    // Ignore storage failures.
  }
}

function restorePreflightCache() {
  clearLegacyPreflightCache();
  let cached = null;
  try {
    cached = JSON.parse(sessionStorage.getItem(PREFLIGHT_SESSION_KEY) || "null");
  } catch (err) {
    clearPreflightCache();
    return false;
  }
  if (!cached?.preflight?.checks?.length) return false;
  renderPreflightInline(cached.preflight, {
    collapsed: Boolean(cached.collapsed),
    restore: true,
  });
  return true;
}

function showPreflightModal(preflight, canProceed, payload) {
  preflightPendingPayload = payload;
  const checks = preflight.checks || [];
  ui.preflightModalSummary.textContent = canProceed
    ? "存在警告项，可以继续，但建议先确认。"
    : "存在错误项，暂不能开始任务。";
  renderCheckList(ui.preflightModalList, checks);
  controls.preflightProceed.disabled = !canProceed;
  controls.preflightProceed.textContent = canProceed ? "仍然开始" : "无法开始";
  ui.preflightOverlay.classList.add("visible");
  ui.preflightOverlay.setAttribute("aria-hidden", "false");
}

function closePreflightModal() {
  ui.preflightOverlay.classList.remove("visible");
  ui.preflightOverlay.setAttribute("aria-hidden", "true");
  preflightPendingPayload = null;
}

function renderCheckList(target, checks) {
  target.innerHTML = checks
    .map(
      (item) => `
        <div class="check-item ${escapeAttr(item.status)}">
          <span class="check-status">${checkStatusLabel(item.status)}</span>
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <p>${escapeHtml(item.message)}</p>
          </div>
        </div>`,
    )
    .join("");
}

function preflightSummaryText(checks) {
  const errors = checks.filter((item) => item.status === "error").length;
  const warnings = checks.filter((item) => item.status === "warning").length;
  if (errors) return `${errors} 个错误，${warnings} 个警告`;
  if (warnings) return `${warnings} 个警告，可继续`;
  return "全部通过";
}

function checkStatusLabel(status) {
  return { ok: "通过", warning: "警告", error: "错误" }[status] || "检查";
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
    setCookieValidationState("unverified");
    updateCookieSummary();
    resetPreflightInline();
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
    setCookieValidationState("unverified");
    updateCookieSummary();
    resetPreflightInline();
    scheduleConfigSave();
    showToast("剪贴板内容已填入 Cookie 文本框。", "info");
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
    setCookieValidationState("unverified");
    updateCookieSummary();
    resetPreflightInline();
    await saveConfigNow();
    showToast("已从粘贴内容中识别 Cookie。", "info");
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.extractCookie, false);
  }
}

async function checkCookie() {
  setBusy(controls.checkCookie, true, "正在测试");
  try {
    const data = await api("/api/check-cookie", {
      method: "POST",
      body: JSON.stringify({
        cookie: fields.cookie.value.trim(),
        super_topic: fields.superTopic.value.trim(),
      }),
    });
    const result = data.data || data;
    setCookieValidationState(cookieStateFromLoginState(result.login_state));
    updateCookieSummary();
    const toastState = result.login_state === "valid" ? "success" : result.login_state === "unknown" ? "info" : "error";
    showToast(`${result.message || "Cookie 检测完成"}。${result.suggestion ? `建议：${result.suggestion}` : ""}`, toastState);
  } catch (err) {
    setCookieValidationState("failed");
    updateCookieSummary();
    appendClientLog(err.message);
  } finally {
    setBusy(controls.checkCookie, false);
  }
}

async function clearCookie() {
  setBusy(controls.clearCookie, true, "正在清空");
  try {
    fields.cookie.value = "";
    setCookieValidationState("unverified");
    updateCookieSummary();
    resetPreflightInline();
    await api("/api/clear-config", {
      method: "POST",
      body: JSON.stringify({ scope: "cookie" }),
    });
    showToast("Cookie 已清空。", "info");
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.clearCookie, false);
  }
}

function expandCookieEditor() {
  ui.cookieEditor.classList.remove("hidden");
  controls.cookieExpand.classList.add("hidden");
  controls.cookieCollapse.classList.remove("hidden");
  fields.cookie.focus();
}

function collapseCookieEditor() {
  ui.cookieEditor.classList.add("hidden");
  controls.cookieExpand.classList.remove("hidden");
  controls.cookieCollapse.classList.add("hidden");
}

function setCookieValidationState(state) {
  cookieValidationState = state || "unverified";
}

function updateCookieSummary() {
  const length = fields.cookie.value.trim().length;
  ui.cookieSummary.textContent = length ? `已填写 Cookie，长度 ${length} 字符` : "未填写 Cookie";
  ui.cookieStateBadge.textContent = cookieStatusLabel(cookieValidationState);
  ui.cookieStateBadge.className = `mini-badge cookie-state ${cookieValidationState}`;
}

function cookieStatusLabel(state) {
  return (
    {
      unverified: "未验证",
      valid: "验证成功",
      failed: "验证失败",
      stale: "可能失效",
    }[state] || "未验证"
  );
}

function cookieStateFromLoginState(state) {
  if (state === "valid") return "valid";
  if (state === "unknown") return "stale";
  return "failed";
}

async function submitSelection() {
  if (controls.select.disabled) return;
  setBusy(controls.select, true, "正在提交");
  try {
    const data = await api("/api/select", {
      method: "POST",
      body: JSON.stringify({ indexes: selectedIndexes() }),
    });
    renderJob(data.data?.job ?? data.job);
    startPolling();
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.select, false);
    updatePickCount();
  }
}

async function cancelSelection() {
  setBusy(controls.cancelSelect, true, "正在取消");
  try {
    const data = await api("/api/cancel-selection", {
      method: "POST",
      body: "{}",
    });
    renderJob(data.data?.job ?? data.job);
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.cancelSelect, false);
  }
}

async function cancelJob() {
  const confirmed = window.confirm("确定要取消当前任务吗？已抓取的数据和已生成的临时文件可能会保留。");
  if (!confirmed) return;
  setBusy(controls.cancelJob, true, "正在取消");
  showToast("正在取消，请等待当前请求结束……", "warning");
  try {
    const data = await api("/api/cancel-job", { method: "POST", body: "{}" });
    const job = data.data?.job ?? data.job;
    renderJob(job);
    startPolling();
    if (job?.status === "cancelled") {
      showToast("任务已取消。", "info");
    }
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.cancelJob, false);
    if (["running", "awaiting_selection", "exporting"].includes(currentRenderedJob?.status)) {
      controls.cancelJob.disabled = false;
    }
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

async function checkCacheStatus(options = {}) {
  const runDir = (ui.reexportRunDir?.value || "").trim();
  if (!runDir) {
    if (!options.silent) showToast("请先填写运行目录。", "warning");
    return null;
  }
  if (!options.silent) setBusy(controls.checkCache, true, "正在检查");
  try {
    const response = await api("/api/cache-status", {
      method: "POST",
      body: JSON.stringify({ run_dir: runDir }),
    });
    const data = response.data || response;
    lastCacheStatusKey = runDir;
    lastCacheCanReexport = Boolean(data.can_reexport);
    renderCacheStatus(data);
    controls.reexport.disabled = !lastCacheCanReexport;
    if (!options.silent) {
      showToast(lastCacheCanReexport ? "缓存完整，可以重新生成报告。" : "缓存不完整，无法重新生成。", lastCacheCanReexport ? "success" : "warning");
    }
    return data;
  } catch (err) {
    lastCacheCanReexport = false;
    controls.reexport.disabled = true;
    renderCacheStatus({ has_cache: false, can_reexport: false, missing: [err.message], files: {} });
    if (!options.silent) appendClientLog(err.message);
    return null;
  } finally {
    if (!options.silent) setBusy(controls.checkCache, false);
  }
}

async function reexportReport() {
  const runDir = (ui.reexportRunDir?.value || "").trim();
  if (!runDir) {
    showToast("请先填写运行目录。", "warning");
    return;
  }
  setBusy(controls.reexport, true, "正在生成");
  try {
    const response = await api("/api/reexport", {
      method: "POST",
      body: JSON.stringify({
        run_dir: runDir,
        selected_post_ids: null,
        export_types: selectedReexportTypes(),
      }),
    });
    const data = response.data || response;
    showToast(data.message || "重新生成完成。", "success");
    if (data.result) {
      renderResultList(data.result);
      if (data.result.run_dir) ui.reexportRunDir.value = data.result.run_dir;
    }
    await checkCacheStatus({ silent: true });
  } catch (err) {
    appendClientLog(err.message);
  } finally {
    setBusy(controls.reexport, false);
    controls.reexport.disabled = !lastCacheCanReexport;
  }
}

function selectedReexportTypes() {
  return Array.from(document.querySelectorAll("input[name='reexportType']:checked")).map((item) => item.value);
}

function renderCacheStatus(status) {
  if (!ui.cacheStatusBox) return;
  const files = status.files || {};
  const rows = [
    cacheStatusLine("cache/ 文件夹", Boolean(status.has_cache)),
    cacheStatusLine("原始帖子缓存", Boolean(files.posts_raw)),
    cacheStatusLine("正文补全缓存", Boolean(files.posts_hydrated)),
    cacheStatusLine("评分缓存", Boolean(files.posts_scored)),
    cacheStatusLine("候选缓存", Boolean(files.candidates)),
    cacheStatusLine("人工选择缓存", Boolean(files.selected_posts)),
    cacheStatusLine(`评论缓存 ${Number(status.comments_count || 0)} 个`, Number(status.comments_count || 0) > 0),
    cacheStatusLine("图片清单", Boolean(files.images_manifest)),
    cacheStatusLine("可重新生成报告", Boolean(status.can_reexport)),
  ];
  const missing = (status.missing || []).map((item) => `<div class="cache-status-line missing"><span>缺少</span><strong>${escapeHtml(item)}</strong></div>`);
  ui.cacheStatusBox.innerHTML = [...rows, ...missing].join("");
}

function cacheStatusLine(label, ok) {
  return `<div class="cache-status-line ${ok ? "ok" : "missing"}"><span>${ok ? "✓" : "✗"} ${escapeHtml(label)}</span><strong>${ok ? "是" : "否"}</strong></div>`;
}

async function loadMarkdownPreview(options = {}) {
  const isAuto = Boolean(options.auto);
  const force = Boolean(options.force);
  if (!isAuto) {
    setBusy(controls.preview, true, "正在载入");
  }
  setPreviewLoading("正在加载 Markdown 预览...");
  try {
    const data = await api("/api/report-preview");
    const markdown = data.markdown || "";
    const key = `${data.path || ""}:${markdown.length}:${force ? Date.now() : ""}`;
    currentMarkdown = markdown;
    if (!markdown.trim()) {
      ui.previewContent.innerHTML = `<div class="empty-state">暂无可预览内容</div>`;
      renderedPreviewKey = key;
    } else {
      ui.previewContent.innerHTML = renderMarkdown(markdown);
      bindMarkdownImages(ui.previewContent);
      renderedPreviewKey = key;
    }
    ui.previewPath.textContent = data.path || "";
    showPreview();
    if (!isAuto || window.innerWidth <= 980) {
      ui.previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    currentMarkdown = "";
    ui.previewContent.innerHTML = `<div class="empty-state error">预览失败：${escapeHtml(err.message)}。建议确认 Markdown 文件是否已经生成。</div>`;
    showPreview();
    appendClientLog(err.message);
  } finally {
    if (!isAuto) {
      setBusy(controls.preview, false);
    }
  }
}

function setPreviewLoading(message) {
  ui.previewContent.innerHTML = `<div class="empty-state loading">${escapeHtml(message)}</div>`;
}

function bindMarkdownImages(container) {
  container.querySelectorAll("img").forEach((image) => {
    image.addEventListener(
      "error",
      () => {
        image.classList.add("image-error");
        const placeholder = document.createElement("div");
        placeholder.className = "image-error-placeholder";
        placeholder.textContent = "图片加载失败";
        image.replaceWith(placeholder);
      },
      { once: true },
    );
  });
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

async function copyMarkdown() {
  if (!currentMarkdown) {
    try {
      const data = await api("/api/report-preview");
      currentMarkdown = data.markdown || "";
    } catch (err) {
      appendClientLog(err.message);
      return;
    }
  }
  if (!currentMarkdown.trim()) {
    showToast("暂无可复制的 Markdown。", "info");
    return;
  }
  copyText(currentMarkdown, "Markdown 已复制。");
}

async function copyText(text, successMessage) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage || "已复制。");
  } catch (err) {
    appendClientLog(`复制失败：${err.message}`);
  }
}

async function loadHelpDoc() {
  try {
    const data = await api("/api/help-doc");
    ui.helpContent.innerHTML = renderMarkdown(data.markdown || "");
    bindMarkdownImages(ui.helpContent);
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
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
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

function setAdvancedMode(enabled) {
  controls.advancedMode.checked = Boolean(enabled);
  ui.advancedFields.classList.toggle("expanded", Boolean(enabled));
  ui.advancedFields.setAttribute("aria-hidden", enabled ? "false" : "true");
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
controls.cancelJob.addEventListener("click", cancelJob);
controls.advancedMode.addEventListener("change", () => {
  setAdvancedMode(controls.advancedMode.checked);
  scheduleConfigSave();
});
controls.cookieExpand.addEventListener("click", expandCookieEditor);
controls.cookieCollapse.addEventListener("click", collapseCookieEditor);
controls.edgeDebug.addEventListener("click", launchEdgeDebug);
controls.autoCookie.addEventListener("click", autoCookie);
controls.clipboard.addEventListener("click", readClipboard);
controls.extractCookie.addEventListener("click", extractCookie);
controls.checkCookie.addEventListener("click", checkCookie);
controls.clearCookie.addEventListener("click", clearCookie);
controls.select.addEventListener("click", submitSelection);
controls.cancelSelect.addEventListener("click", cancelSelection);
controls.candidateFilter.addEventListener("change", () => renderCandidates(currentRenderedJob));
controls.candidateSort.addEventListener("change", () => renderCandidates(currentRenderedJob));
ui.candidateList.addEventListener("change", handleCandidateChange);
ui.candidateList.addEventListener("click", handleCandidateClick);
controls.openResultDir.addEventListener("click", openResultDir);
controls.checkCache.addEventListener("click", () => checkCacheStatus());
controls.reexport.addEventListener("click", reexportReport);
ui.reexportRunDir.addEventListener("input", () => {
  lastCacheStatusKey = "";
  lastCacheCanReexport = false;
  controls.reexport.disabled = true;
  ui.cacheStatusBox.textContent = "运行目录已修改，请重新检查缓存";
});
ui.resultList.addEventListener("click", handleResultClick);
controls.preview.addEventListener("click", () => {
  if (ui.previewPanel.getAttribute("aria-hidden") === "true") {
    loadMarkdownPreview();
  } else {
    hidePreview();
  }
});
controls.refreshPreview.addEventListener("click", () => loadMarkdownPreview({ force: true }));
controls.copyMarkdown.addEventListener("click", copyMarkdown);
controls.logSearch.addEventListener("input", () => renderBackendLogs(currentRenderedJob));
controls.logLevelFilter.addEventListener("change", () => renderBackendLogs(currentRenderedJob));
controls.copyLog.addEventListener("click", copyVisibleLogs);
controls.downloadLog.addEventListener("click", downloadVisibleLogs);
controls.clearLogView.addEventListener("click", clearLogView);
controls.logBottom.addEventListener("click", scrollLogToBottom);
controls.preflightClose.addEventListener("click", closePreflightModal);
controls.preflightCancel.addEventListener("click", closePreflightModal);
controls.preflightProceed.addEventListener("click", () => {
  if (!preflightPendingPayload || controls.preflightProceed.disabled) return;
  const payload = preflightPendingPayload;
  closePreflightModal();
  startJobAfterPreflight(payload);
});
ui.preflightPanel.addEventListener("click", () => {
  if (!ui.preflightPanel.classList.contains("collapsed")) return;
  clearTimeout(preflightCollapseTimer);
  setPreflightCollapsed(false);
});
controls.preflightToggle?.addEventListener("click", (event) => {
  event.stopPropagation();
  clearTimeout(preflightCollapseTimer);
  setPreflightCollapsed(!ui.preflightPanel.classList.contains("collapsed"));
});
ui.preflightOverlay.addEventListener("click", (event) => {
  if (event.target === ui.preflightOverlay) {
    closePreflightModal();
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
  if (event.key === "Escape" && ui.preflightOverlay.classList.contains("visible")) {
    closePreflightModal();
  }
});
document.addEventListener("visibilitychange", () => {
  if (["running", "awaiting_selection", "exporting"].includes(currentRenderedJob?.status)) {
    scheduleNextPoll(currentRenderedJob);
  }
});

[
  fields.superTopic,
  fields.cookie,
  fields.windowStart,
  fields.windowEnd,
  fields.maxPages,
  fields.topicCommentFactor,
  fields.pauseSeconds,
  fields.outputDir,
].forEach((field) => {
  field.addEventListener("input", () => {
    if (field === fields.cookie) {
      setCookieValidationState("unverified");
      updateCookieSummary();
    }
    resetPreflightInline();
    scheduleConfigSave();
  });
});

initThemeToggle();
initParticleLayer();

initDefaults()
  .then(async () => {
    restorePreflightCache();
    await refreshStatus();
    await loadHelpDoc();
  })
  .catch((err) => {
    appendClientLog(err.message);
  });
