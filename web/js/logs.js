window.WeiboLogs = {
  createController({ ui, controls, escapeHtml, showToast, getCurrentJob, stageLabel, clamp, onPositionChange }) {
    const FLOATING_OPEN_DURATION = 190;
    const FLOATING_CLOSE_DURATION = 150;
    const FLOATING_OPEN_EASING = "cubic-bezier(0.16, 1, 0.3, 1)";
    const FLOATING_CLOSE_EASING = "cubic-bezier(0.4, 0, 0.2, 1)";

    let lastLogJobId = "";
    let logClearCursor = 0;
    let logClearAnchor = "";
    let visibleLogEntries = [];

    function entryKey(entry) {
      return `${entry?.time || ""}|${entry?.stage || ""}|${entry?.level || ""}|${entry?.message || ""}`;
    }

    function resolveClearCursor(entries) {
      if (!logClearAnchor) return Math.min(logClearCursor, entries.length);
      for (let i = entries.length - 1; i >= 0; i -= 1) {
        if (entryKey(entries[i]) === logClearAnchor) {
          logClearCursor = i + 1;
          return logClearCursor;
        }
      }
      // The anchor has scrolled out of the window; everything still shown is
      // newer than the clear, so show all of it rather than nothing.
      logClearAnchor = "";
      logClearCursor = 0;
      return 0;
    }
    let dragState = null;
    let suppressBubbleClick = false;
    let lastRenderedCount = 0;
    let floatingAnimation = null;
    let bubblePopTimer = null;
    let contentRevealTimer = null;
    let openAnchor = null;
    let panelMovedAfterOpen = false;
    let lastPosition = null;

    function initFloating() {
      hidePanel({ animate: false });
      setInitialPosition(controls.logBubble, 18, 86);
      setInitialPosition(ui.logPanel, 18, 96);
    }

    function render(job) {
      const entries = normalizeLogEntries(job);
      const jobId = job?.id || "";
      if (jobId && jobId !== lastLogJobId) {
        lastLogJobId = jobId;
        logClearCursor = 0;
        logClearAnchor = "";
      }
      const afterClear = entries.slice(resolveClearCursor(entries));
      const keyword = (controls.logSearch.value || "").trim().toLowerCase();
      const levelFilter = controls.logLevelFilter.value || "all";
      visibleLogEntries = afterClear.filter((item) => {
        const levelOk = levelFilter === "all" || item.level === levelFilter;
        const keywordOk =
          !keyword ||
          `${item.time} ${stageName(item.stage)} ${item.level} ${item.message}`.toLowerCase().includes(keyword);
        return levelOk && keywordOk;
      });

      updateBubble(afterClear);
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

    function openPanel() {
      if (!ui.logPanel || !controls.logBubble) return;
      cancelFloatingAnimation();
      const bubbleRect = controls.logBubble.getBoundingClientRect();
      openAnchor = { left: bubbleRect.left, top: bubbleRect.top };
      panelMovedAfterOpen = false;
      ui.logPanel.classList.remove("hidden");
      ui.logPanel.classList.remove("log-window-closing", "log-window-opening");
      ui.logPanel.setAttribute("aria-hidden", "false");
      placeAt(ui.logPanel, bubbleRect.left, bubbleRect.top);
      const panelRect = ui.logPanel.getBoundingClientRect();
      controls.logBubble.classList.remove("hidden", "log-bubble-pop");
      controls.logBubble.classList.add("log-bubble-pending");
      controls.logBubble.setAttribute("aria-expanded", "true");
      ui.logPanel.classList.add("log-window-opening");
      animateBubbleIntoPanel(bubbleRect, panelRect);
      notifyPositionChange();
    }

    function hidePanel(options = {}) {
      if (!ui.logPanel || !controls.logBubble) return;
      cancelFloatingAnimation();
      const { animate = true } = options;
      const panelRect = ui.logPanel.getBoundingClientRect();
      controls.logBubble.classList.remove("hidden");
      const target = panelMovedAfterOpen || !openAnchor ? { left: panelRect.left, top: panelRect.top } : openAnchor;
      placeAt(controls.logBubble, target.left, target.top);
      const bubbleRect = controls.logBubble.getBoundingClientRect();
      ui.logPanel.setAttribute("aria-hidden", "true");
      controls.logBubble.setAttribute("aria-expanded", "false");
      if (!animate || ui.logPanel.classList.contains("hidden") || !panelRect.width || !panelRect.height) {
        finishHidePanel(false);
        return;
      }
      controls.logBubble.classList.add("log-bubble-pending");
      ui.logPanel.classList.add("log-window-closing");
      animatePanelIntoBubble(panelRect, bubbleRect);
      notifyPositionChange({
        mode: "bubble",
        left: Math.round(bubbleRect.left),
        top: Math.round(bubbleRect.top),
      });
    }

    function handleBubbleClick() {
      if (suppressBubbleClick) {
        suppressBubbleClick = false;
        return;
      }
      openPanel();
    }

    function startBubbleDrag(event) {
      startDrag(event, controls.logBubble, "bubble");
    }

    function startPanelDrag(event) {
      if (event.target.closest("button, input, select, textarea, a")) return;
      startDrag(event, ui.logPanel, "panel");
    }

    function startDrag(event, element, type) {
      if (!element || event.button !== 0) return;
      const rect = element.getBoundingClientRect();
      dragState = {
        element,
        type,
        startX: event.clientX,
        startY: event.clientY,
        left: rect.left,
        top: rect.top,
        moved: false,
      };
      element.classList.add("dragging");
      element.style.right = "auto";
      element.style.bottom = "auto";
      element.style.left = `${rect.left}px`;
      element.style.top = `${rect.top}px`;
      window.addEventListener("pointermove", dragMove);
      window.addEventListener("pointerup", dragEnd, { once: true });
      event.preventDefault();
    }

    function dragMove(event) {
      if (!dragState) return;
      const dx = event.clientX - dragState.startX;
      const dy = event.clientY - dragState.startY;
      if (Math.abs(dx) + Math.abs(dy) > 4) {
        dragState.moved = true;
      }
      const rect = dragState.element.getBoundingClientRect();
      const margin = 8;
      const minTop = minimumTop();
      const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin);
      const maxTop = Math.max(minTop, window.innerHeight - rect.height - margin);
      dragState.element.style.left = `${clamp(dragState.left + dx, margin, maxLeft)}px`;
      dragState.element.style.top = `${clamp(dragState.top + dy, minTop, maxTop)}px`;
    }

    function dragEnd() {
      if (!dragState) return;
      dragState.element.classList.remove("dragging");
      if (dragState.type === "bubble" && dragState.moved) {
        suppressBubbleClick = true;
        window.setTimeout(() => {
          suppressBubbleClick = false;
        }, 0);
      }
      if (dragState.type === "panel" && dragState.moved) {
        panelMovedAfterOpen = true;
      }
      if (dragState.moved) {
        notifyPositionChange();
      }
      dragState = null;
      window.removeEventListener("pointermove", dragMove);
    }

    function getPosition() {
      if (lastPosition) {
        return { ...lastPosition };
      }
      return computePosition();
    }

    function computePosition() {
      const panelVisible = ui.logPanel && !ui.logPanel.classList.contains("hidden");
      const target = panelVisible ? ui.logPanel : controls.logBubble;
      const rect = target?.getBoundingClientRect();
      return {
        mode: panelVisible ? "panel" : "bubble",
        left: Math.round(rect?.left || 18),
        top: Math.round(rect?.top || 86),
      };
    }

    function applyPosition(position) {
      if (!position || typeof position !== "object") return;
      const left = Number(position.left);
      const top = Number(position.top);
      if (!Number.isFinite(left) || !Number.isFinite(top)) return;
      controls.logBubble.classList.remove("hidden");
      controls.logBubble.setAttribute("aria-expanded", "false");
      ui.logPanel.classList.add("hidden");
      ui.logPanel.setAttribute("aria-hidden", "true");
      placeAt(controls.logBubble, left, top);
      const rect = controls.logBubble.getBoundingClientRect();
      const actual = { left: Math.round(rect.left), top: Math.round(rect.top) };
      openAnchor = actual;
      panelMovedAfterOpen = false;
      lastPosition = { mode: "bubble", ...actual };
    }

    function updateBubble(entries) {
      if (!controls.logBubble) return;
      const count = entries.length;
      const hasError = entries.some((item) => item.level === "error");
      const hasWarning = entries.some((item) => item.level === "warning");
      if (ui.logBubbleCount) {
        ui.logBubbleCount.textContent = String(count);
      }
      controls.logBubble.classList.toggle("has-logs", count > 0);
      controls.logBubble.classList.toggle("has-warning", hasWarning && !hasError);
      controls.logBubble.classList.toggle("has-error", hasError);
      if (count > lastRenderedCount && ui.logPanel?.classList.contains("hidden")) {
        controls.logBubble.classList.add("attention");
        window.setTimeout(() => controls.logBubble?.classList.remove("attention"), 900);
      }
      lastRenderedCount = count;
    }

    function setInitialPosition(element, left, top) {
      if (!element) return;
      placeAt(element, left, top);
    }

    function notifyPositionChange(position = null) {
      lastPosition = position || computePosition();
      if (typeof onPositionChange === "function") {
        onPositionChange({ ...lastPosition });
      }
    }

    function placeAt(element, left, top) {
      if (!element) return;
      const rect = element.getBoundingClientRect();
      const margin = 8;
      const minTop = minimumTop();
      const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin);
      const maxTop = Math.max(minTop, window.innerHeight - rect.height - margin);
      element.style.right = "auto";
      element.style.bottom = "auto";
      element.style.left = `${clamp(left, margin, maxLeft)}px`;
      element.style.top = `${clamp(top, minTop, maxTop)}px`;
    }

    function animatePanelIntoBubble(panelRect, bubbleRect) {
      const dx = bubbleRect.left - panelRect.left;
      const dy = bubbleRect.top - panelRect.top;
      if (prefersReducedMotion() || typeof ui.logPanel.animate !== "function") {
        finishHidePanel(true);
        return;
      }
      const endScale = panelScaleFromBubble(panelRect, bubbleRect);
      floatingAnimation = ui.logPanel.animate(
        [
          { opacity: 1, transform: "translate3d(0, 0, 0) scale(1)" },
          {
            opacity: 0.76,
            transform: `translate3d(${(dx * 0.12).toFixed(2)}px, ${(dy * 0.12).toFixed(2)}px, 0) scale(0.92)`,
          },
          {
            opacity: 0,
            transform: `translate3d(${dx.toFixed(2)}px, ${dy.toFixed(2)}px, 0) scale(${endScale.toFixed(4)})`,
          },
        ],
        {
          duration: FLOATING_CLOSE_DURATION,
          easing: FLOATING_CLOSE_EASING,
          fill: "forwards",
        },
      );
      const animation = floatingAnimation;
      animation.onfinish = () => {
        if (floatingAnimation !== animation) return;
        floatingAnimation = null;
        animation.cancel();
        finishHidePanel(true);
      };
    }

    function animateBubbleIntoPanel(bubbleRect, panelRect) {
      const dx = bubbleRect.left - panelRect.left;
      const dy = bubbleRect.top - panelRect.top;
      if (prefersReducedMotion() || typeof ui.logPanel.animate !== "function") {
        finishOpenPanel();
        return;
      }
      const startScale = panelScaleFromBubble(panelRect, bubbleRect);
      floatingAnimation = ui.logPanel.animate(
        [
          {
            opacity: 0.16,
            transform: `translate3d(${dx.toFixed(2)}px, ${dy.toFixed(2)}px, 0) scale(${startScale.toFixed(4)})`,
          },
          {
            opacity: 0.76,
            transform: `translate3d(${(dx * 0.12).toFixed(2)}px, ${(dy * 0.12).toFixed(2)}px, 0) scale(0.92)`,
          },
          { opacity: 1, transform: "translate3d(0, 0, 0) scale(1)" },
        ],
        {
          duration: FLOATING_OPEN_DURATION,
          easing: FLOATING_OPEN_EASING,
          fill: "forwards",
        },
      );
      const animation = floatingAnimation;
      animation.onfinish = () => {
        if (floatingAnimation !== animation) return;
        floatingAnimation = null;
        animation.cancel();
        finishOpenPanel();
      };
    }

    function finishOpenPanel() {
      ui.logPanel.classList.remove("log-window-opening", "log-window-closing");
      ui.logPanel.classList.add("log-window-content-in");
      controls.logBubble.classList.add("hidden");
      controls.logBubble.classList.remove("log-bubble-pending", "log-bubble-pop");
      scrollToBottom();
      clearContentRevealTimer();
      contentRevealTimer = window.setTimeout(() => {
        ui.logPanel?.classList.remove("log-window-content-in");
        contentRevealTimer = null;
      }, 150);
    }

    function finishHidePanel(popBubble) {
      ui.logPanel.classList.add("hidden");
      ui.logPanel.classList.remove("log-window-closing", "log-window-opening", "log-window-content-in");
      controls.logBubble.classList.remove("log-bubble-pending");
      if (popBubble) {
        controls.logBubble.classList.add("log-bubble-pop");
        clearBubblePopTimer();
        bubblePopTimer = window.setTimeout(() => {
          controls.logBubble?.classList.remove("log-bubble-pop");
          bubblePopTimer = null;
        }, 220);
      }
    }

    function minimumTop() {
      const topbar = document.querySelector(".topbar");
      if (!topbar) return 8;
      const rect = topbar.getBoundingClientRect();
      return Math.max(8, Math.ceil(rect.bottom + 8));
    }

    function cancelFloatingAnimation() {
      if (floatingAnimation) {
        floatingAnimation.cancel();
        floatingAnimation = null;
      }
      clearBubblePopTimer();
      ui.logPanel?.classList.remove("log-window-closing", "log-window-opening");
      ui.logPanel?.classList.remove("log-window-content-in");
      controls.logBubble?.classList.remove("log-bubble-pending", "log-bubble-pop");
      clearContentRevealTimer();
    }

    function clearBubblePopTimer() {
      if (!bubblePopTimer) return;
      window.clearTimeout(bubblePopTimer);
      bubblePopTimer = null;
    }

    function clearContentRevealTimer() {
      if (!contentRevealTimer) return;
      window.clearTimeout(contentRevealTimer);
      contentRevealTimer = null;
    }

    function prefersReducedMotion() {
      return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    }

    function panelScaleFromBubble(panelRect, bubbleRect) {
      if (!panelRect.width || !panelRect.height || !bubbleRect.width || !bubbleRect.height) {
        return 0.22;
      }
      const widthScale = bubbleRect.width / panelRect.width;
      const heightScale = bubbleRect.height / panelRect.height;
      return clamp(Math.sqrt(widthScale * heightScale) * 1.08, 0.18, 0.34);
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
      // The snapshot is a sliding window of the most recent SNAPSHOT_LIMIT
      // entries, so a plain index stops meaning anything once the window
      // moves. Remember the entry we cleared up to and re-derive the index
      // from it on every render.
      logClearAnchor = entries.length ? entryKey(entries[entries.length - 1]) : "";
      visibleLogEntries = [];
      ui.backendLogBox.innerHTML = "";
      ui.logCount.textContent = "0 条";
      if (ui.logBubbleCount) ui.logBubbleCount.textContent = "0";
      showToast("前端日志显示已清空。", "info");
    }

    function formatDateForFilename(date) {
      const pad = (value) => String(value).padStart(2, "0");
      return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
    }

    return {
      initFloating,
      render,
      scrollToBottom,
      sanitize: sanitizeLogMessage,
      stageName,
      copyVisible,
      downloadVisible,
      clearView,
      openPanel,
      hidePanel,
      handleBubbleClick,
      startBubbleDrag,
      startPanelDrag,
      getPosition,
      applyPosition,
    };
  },
};
