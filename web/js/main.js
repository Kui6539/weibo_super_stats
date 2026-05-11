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

const setBusy = (...args) => window.WeiboUtils.setBusy(...args);
const escapeHtml = (value) => window.WeiboUtils.escapeHtml(value);
const escapeAttr = (value) => window.WeiboUtils.escapeAttr(value);
const clamp = (...args) => window.WeiboUtils.clamp(...args);

let configController = null;
let taskController = null;

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

const themeController = window.WeiboTheme.createController({
  controls,
  onChange: () => saveConfigNow(),
});

const formController = window.WeiboForm.createController({
  fields,
  controls,
  ui,
  getTheme: themeController.current,
});

const candidatesController = window.WeiboCandidates.createController({
  ui,
  controls,
  escapeHtml,
  escapeAttr,
  getCurrentJob: () => taskController?.getCurrentJob(),
});

const progressController = window.WeiboProgress.createController({
  ui,
  fields,
  getSelectedCount: (job) => candidatesController.currentSelectedCount(job),
});

const logsController = window.WeiboLogs.createController({
  ui,
  controls,
  escapeHtml,
  showToast,
  getCurrentJob: () => taskController?.getCurrentJob(),
  stageLabel: progressController.stageName,
});

const toastController = window.WeiboToast.createController({ sanitizeLogMessage });

const clipboardController = window.WeiboUtils.createClipboard({
  showToast,
  appendClientLog,
});

const previewController = window.WeiboPreview.createController({
  ui,
  controls,
  api,
  setBusy,
  escapeHtml,
  escapeAttr,
  appendClientLog,
  showToast,
  copyText,
});

const cacheController = window.WeiboCache.createController({
  ui,
  controls,
  api,
  setBusy,
  escapeHtml,
  escapeAttr,
  copyText,
  showToast,
  appendClientLog,
  previewController,
});

const helpController = window.WeiboHelp.createController({
  ui,
  api,
  previewController,
  appendClientLog,
  clamp,
});

const particlesController = window.WeiboParticles.createController({
  ui,
  clamp,
});

const cookieController = window.WeiboCookie.createController({
  fields,
  controls,
  ui,
  api,
  setBusy,
  showToast,
  appendClientLog,
  saveConfigNow,
  scheduleConfigSave,
  resetPreflightInline,
});

configController = window.WeiboConfig.createController({
  api,
  formController,
  themeController,
  cookieController,
  setSaveState,
});

const preflightController = window.WeiboPreflight.createController({
  ui,
  controls,
  readForm,
  escapeHtml,
  escapeAttr,
});

taskController = window.WeiboTask.createController({
  controls,
  api,
  setBusy,
  readForm,
  saveConfigNow,
  renderPreflightInline,
  showPreflightModal,
  showToast,
  appendClientLog,
  progressController,
  logsController,
  candidatesController,
  cacheController,
  previewController,
});

function readForm() {
  return formController.readForm();
}

function scheduleConfigSave() {
  configController?.scheduleSave();
}

async function saveConfigNow() {
  return configController?.saveNow();
}

function sanitizeLogMessage(message) {
  return logsController.sanitize(message);
}

function appendClientLog(message) {
  toastController.appendClientLog(message);
}

function showToast(message, state = "success") {
  toastController.show(message, state);
}

function renderPreflightInline(preflight, options = {}) {
  preflightController.renderInline(preflight, options);
}

function resetPreflightInline() {
  preflightController.resetInline();
}

function showPreflightModal(preflight, canProceed, payload) {
  preflightController.showModal(preflight, canProceed, payload);
}

async function copyText(text, successMessage) {
  return clipboardController.copy(text, successMessage);
}

window.WeiboEvents.bind({
  fields,
  controls,
  ui,
  taskController,
  formController,
  cookieController,
  candidatesController,
  cacheController,
  previewController,
  logsController,
  preflightController,
  helpController,
  configController,
});

themeController.init();
particlesController.init();

configController
  .initDefaults()
  .then(async () => {
    preflightController.restoreCache();
    await taskController.refreshStatus();
    await helpController.load();
  })
  .catch((err) => {
    appendClientLog(err.message);
  });
