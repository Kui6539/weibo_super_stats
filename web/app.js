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
  start: $("startBtn"),
  edgeDebug: $("edgeDebugBtn"),
  autoCookie: $("autoCookieBtn"),
  clipboard: $("clipboardBtn"),
  extractCookie: $("extractCookieBtn"),
  select: $("selectBtn"),
  cancelSelect: $("cancelSelectBtn"),
  preview: $("previewBtn"),
};

const ui = {
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
};

let pollTimer = null;
let lastRenderedCandidateJob = null;
let renderedPreviewKey = "";
let autoPreviewResultKey = "";
let configReady = false;
let configSaveTimer = null;

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
  };
}

function configPayload() {
  return {
    super_topic: fields.superTopic.value.trim(),
    cookie: fields.cookie.value.trim(),
    output_dir: fields.outputDir.value.trim(),
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

function renderLogs(job) {
  const logs = job?.logs || [];
  if (!logs.length) {
    ui.logBox.innerHTML = '<div class="log-line"><span class="log-time">--:--:--</span><span>等待任务日志</span></div>';
    return;
  }
  ui.logBox.innerHTML = logs
    .map(
      (item) =>
        `<div class="log-line"><span class="log-time">${escapeHtml(item.time || "")}</span><span>${escapeHtml(
          item.message || "",
        )}</span></div>`,
    )
    .join("");
  ui.logBox.scrollTop = ui.logBox.scrollHeight;
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
    hidePreview();
    autoPreviewResultKey = "";
    return;
  }
  ui.resultPanel.classList.remove("hidden");
  ui.monitorPanel.classList.add("collapsed");
  controls.preview.classList.remove("hidden");
  controls.preview.disabled = false;
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
  updateStatus(job);
  renderLogs(job);
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
  const row = document.createElement("div");
  row.className = "log-line";
  row.innerHTML = `<span class="log-time">页面</span><span>${escapeHtml(message)}</span>`;
  ui.logBox.appendChild(row);
  ui.logBox.scrollTop = ui.logBox.scrollHeight;
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
    alert(err.message);
  } finally {
    setBusy(controls.start, false);
    refreshStatus();
  }
}

async function launchEdgeDebug() {
  setBusy(controls.edgeDebug, true, "正在打开");
  try {
    const data = await api("/api/cookie/edge-debug", { method: "POST", body: "{}" });
    appendClientLog(`调试 Edge 已启动：${data.endpoint}`);
  } catch (err) {
    appendClientLog(err.message);
    alert(err.message);
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
    appendClientLog("Cookie 自动读取成功。");
  } catch (err) {
    appendClientLog(err.message);
    alert(err.message);
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
    alert("浏览器拒绝读取剪贴板，请手动粘贴。");
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
    alert(err.message);
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
    alert(err.message);
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
    alert(err.message);
  } finally {
    setBusy(controls.cancelSelect, false);
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
    if (!isAuto) {
      alert(err.message);
    }
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

controls.start.addEventListener("click", startJob);
controls.edgeDebug.addEventListener("click", launchEdgeDebug);
controls.autoCookie.addEventListener("click", autoCookie);
controls.clipboard.addEventListener("click", readClipboard);
controls.extractCookie.addEventListener("click", extractCookie);
controls.select.addEventListener("click", submitSelection);
controls.cancelSelect.addEventListener("click", cancelSelection);
controls.preview.addEventListener("click", () => {
  if (ui.previewPanel.getAttribute("aria-hidden") === "true") {
    loadMarkdownPreview();
  } else {
    hidePreview();
  }
});

[fields.superTopic, fields.cookie, fields.outputDir].forEach((field) => {
  field.addEventListener("input", scheduleConfigSave);
});

initDefaults()
  .then(refreshStatus)
  .catch((err) => {
    appendClientLog(err.message);
  });
