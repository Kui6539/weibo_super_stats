window.WeiboLogs = {
  createController({ ui, controls, escapeHtml, showToast, getCurrentJob, stageLabel, clamp, onPositionChange }) {
    const MORPH_FRAME_COUNT = 60;

    let lastLogJobId = "";
    let logClearCursor = 0;
    let visibleLogEntries = [];
    let dragState = null;
    let suppressBubbleClick = false;
    let lastRenderedCount = 0;
    let floatingAnimation = null;
    let bubblePopTimer = null;
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
      scrollToBottom();
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
      const scaleX = clamp(bubbleRect.width / panelRect.width, 0.12, 0.42);
      const scaleY = clamp(bubbleRect.height / panelRect.height, 0.08, 0.34);
      if (typeof ui.logPanel.animate !== "function") {
        finishHidePanel(true);
        return;
      }
      floatingAnimation = ui.logPanel.animate(
        buildMorphFrames({
          dx,
          dy,
          mode: "close",
          fromScaleX: 1,
          fromScaleY: 1,
          toScaleX: scaleX,
          toScaleY: scaleY,
          fromOpacity: 1,
          toOpacity: 0,
          fromRadius: 8,
          toRadius: 999,
          fromBlur: 0,
          toBlur: 2,
        }),
        {
          duration: 260,
          easing: "linear",
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
      const scaleX = clamp(bubbleRect.width / panelRect.width, 0.12, 0.42);
      const scaleY = clamp(bubbleRect.height / panelRect.height, 0.08, 0.34);
      if (typeof ui.logPanel.animate !== "function") {
        finishOpenPanel();
        return;
      }
      floatingAnimation = ui.logPanel.animate(
        buildMorphFrames({
          dx,
          dy,
          mode: "open",
          fromScaleX: scaleX,
          fromScaleY: scaleY,
          toScaleX: 1,
          toScaleY: 1,
          fromOpacity: 0,
          toOpacity: 1,
          fromRadius: 999,
          toRadius: 8,
          fromBlur: 2,
          toBlur: 0,
        }),
        {
          duration: 280,
          easing: "linear",
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
      controls.logBubble.classList.add("hidden");
      controls.logBubble.classList.remove("log-bubble-pending", "log-bubble-pop");
    }

    function buildMorphFrames({
      dx,
      dy,
      mode,
      fromScaleX,
      fromScaleY,
      toScaleX,
      toScaleY,
      fromOpacity,
      toOpacity,
      fromRadius,
      toRadius,
      fromBlur,
      toBlur,
    }) {
      return Array.from({ length: MORPH_FRAME_COUNT }, (_, index) => {
        const raw = index / (MORPH_FRAME_COUNT - 1);
        const t = iosMorph(raw, mode);
        const settledT = clamp(t, 0, 1);
        const translateRatio = isClosing(fromOpacity, toOpacity) ? settledT : 1 - settledT;
        const scaleX = lerp(fromScaleX, toScaleX, t);
        const scaleY = lerp(fromScaleY, toScaleY, t);
        const radiusT = clamp(t, 0, 1);
        return {
          offset: raw,
          opacity: lerp(fromOpacity, toOpacity, fadeCurve(raw)).toFixed(3),
          transform: `translate3d(${(dx * translateRatio).toFixed(2)}px, ${(dy * translateRatio).toFixed(2)}px, 0) scale(${scaleX.toFixed(4)}, ${scaleY.toFixed(4)})`,
          borderRadius: `${lerp(fromRadius, toRadius, radiusT).toFixed(2)}px`,
          filter: `blur(${lerp(fromBlur, toBlur, radiusT).toFixed(3)}px)`,
        };
      });
    }

    function iosMorph(value, mode) {
      const t = clamp(value, 0, 1);
      const base = 1 - (1 - t) ** 5;
      const overshoot = mode === "open" ? 0.055 : 0.032;
      const spring = Math.sin(Math.PI * t) * overshoot * (1 - t) ** 0.72;
      const settle = Math.sin(Math.PI * Math.min(1, t * 2.4)) * 0.01 * (1 - t);
      return base + spring - settle;
    }

    function fadeCurve(value) {
      return value < 0.18 ? value * 0.45 : 0.081 + (value - 0.18) / 0.82;
    }

    function isClosing(fromOpacity, toOpacity) {
      return fromOpacity > toOpacity;
    }

    function lerp(from, to, ratio) {
      return from + (to - from) * ratio;
    }

    function finishHidePanel(popBubble) {
      ui.logPanel.classList.add("hidden");
      ui.logPanel.classList.remove("log-window-closing", "log-window-opening");
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
      controls.logBubble?.classList.remove("log-bubble-pending", "log-bubble-pop");
    }

    function clearBubblePopTimer() {
      if (!bubblePopTimer) return;
      window.clearTimeout(bubblePopTimer);
      bubblePopTimer = null;
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
