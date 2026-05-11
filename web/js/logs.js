window.WeiboLogs = {
  createController({ ui, controls, escapeHtml, showToast, getCurrentJob, stageLabel }) {
    let lastLogJobId = "";
    let logClearCursor = 0;
    let visibleLogEntries = [];

    function render(job) {
      const entries = normalizeLogEntries(job);
      const jobId = job?.id || "";
      if (jobId && jobId !== lastLogJobId) {
        lastLogJobId = jobId;
        logClearCursor = 0;
      }
      const afterClear = entries.slice(logClearCursor);
      const keyword = (controls.logSearch.value || "").trim().toLowerCase();
      const levelFilter = controls.logLevelFilter.value || "all";
      visibleLogEntries = afterClear.filter((item) => {
        const levelOk = levelFilter === "all" || item.level === levelFilter;
        const keywordOk =
          !keyword ||
          `${item.time} ${stageName(item.stage)} ${item.level} ${item.message}`.toLowerCase().includes(keyword);
        return levelOk && keywordOk;
      });
      const nearBottom = isNearBottom();
      if (!visibleLogEntries.length) {
        ui.backendLogBox.innerHTML = '<div class="empty-state">暂无匹配日志</div>';
        ui.logCount.textContent = "0 条";
        if (nearBottom) scrollToBottom();
        return;
      }
      ui.backendLogBox.innerHTML = visibleLogEntries
        .map(
          (item) => `
        <div class="backend-log-line ${escapeHtml(item.level)}">
          <span class="backend-log-time">[${escapeHtml(item.time)}]</span>
          <span class="backend-log-message">[${escapeHtml(stageName(item.stage))}] [${escapeHtml(logLevelLabel(item.level))}] ${escapeHtml(item.message)}</span>
        </div>`,
        )
        .join("");
      ui.logCount.textContent = `${visibleLogEntries.length} 条`;
      if (nearBottom) scrollToBottom();
    }

    function normalizeLogEntries(job) {
      if (!job) return [];
      const events = Array.isArray(job.events) ? job.events : [];
      if (events.length) {
        return events
          .filter((event) => ["log", "warning", "error"].includes(event.type || "log"))
          .map((event) => ({
            time: shortTime(event.created_at),
            stage: event.stage || "idle",
            level: normalizeLogLevel(event.level || event.type),
            message: sanitizeLogMessage(event.message || ""),
          }))
          .filter((item) => item.message);
      }
      return (job.logs || [])
        .map((item) => {
          const message = typeof item === "string" ? item : item?.message || "";
          return {
            time: shortTime(item?.created_at || item?.time || ""),
            stage: item?.stage || job.stage || "idle",
            level: item?.level ? normalizeLogLevel(item.level) : logLevel(message),
            message: sanitizeLogMessage(message),
          };
        })
        .filter((item) => item.message);
    }

    function isNearBottom() {
      const el = ui.backendLogBox;
      return el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    }

    function scrollToBottom() {
      ui.backendLogBox.scrollTop = ui.backendLogBox.scrollHeight;
    }

    function logLevel(message) {
      const text = String(message || "").toLowerCase();
      if (/失败|错误|异常|error|failed/.test(text)) return "error";
      if (/警告|warning|可能|未成功/.test(text)) return "warning";
      if (/完成|成功|已保存|已生成|success/.test(text)) return "success";
      return "normal";
    }

    function normalizeLogLevel(level) {
      const value = String(level || "info").toLowerCase();
      if (["error", "warning", "success", "normal"].includes(value)) return value;
      if (value === "warn") return "warning";
      if (value === "debug" || value === "info") return "normal";
      return "normal";
    }

    function logLevelLabel(level) {
      return {
        normal: "普通",
        success: "成功",
        warning: "警告",
        error: "错误",
      }[level] || "普通";
    }

    function stageName(stage) {
      if (!stage) return "任务";
      return (stageLabel ? stageLabel(stage) : "") || stage || "任务";
    }

    function shortTime(value) {
      const raw = String(value || "");
      if (!raw) return "";
      return raw.split(" ").pop() || raw;
    }

    function sanitizeLogMessage(message) {
      return String(message || "")
        .replace(/(Cookie\s*[:=]\s*)[^;\n]+(?:;[^;\n]+)*/gi, "$1[已隐藏]")
        .replace(/(SUB|SUBP|SCF|SSOLoginState|ALF|WBPSESS|XSRF-TOKEN)=[^;\s]+/g, "$1=[已隐藏]");
    }

    async function copyVisible() {
      if (!visibleLogEntries.length) {
        showToast("当前没有可复制的日志。", "info");
        return;
      }
      const text = visibleLogEntries
        .map((item) => `[${item.time}] [${stageName(item.stage)}] [${logLevelLabel(item.level)}] ${item.message}`)
        .join("\n");
      try {
        await navigator.clipboard.writeText(text);
        showToast("日志已复制。");
      } catch (err) {
        showToast(`复制日志失败：${err.message}`, "error");
      }
    }

    function downloadVisible() {
      if (!visibleLogEntries.length) {
        showToast("当前没有可下载的日志。", "info");
        return;
      }
      const text = visibleLogEntries
        .map((item) => `[${item.time}] [${stageName(item.stage)}] [${logLevelLabel(item.level)}] ${item.message}`)
        .join("\n");
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `weibo_super_stats_log_${formatDateForFilename(new Date())}.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
    }

    function clearView() {
      const entries = normalizeLogEntries(getCurrentJob ? getCurrentJob() : null);
      logClearCursor = entries.length;
      visibleLogEntries = [];
      ui.backendLogBox.innerHTML = "";
      ui.logCount.textContent = "0 条";
      showToast("前端日志显示已清空。", "info");
    }

    function formatDateForFilename(date) {
      const pad = (value) => String(value).padStart(2, "0");
      return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
    }

    return {
      render,
      scrollToBottom,
      sanitize: sanitizeLogMessage,
      stageName,
      copyVisible,
      downloadVisible,
      clearView,
    };
  },
};
