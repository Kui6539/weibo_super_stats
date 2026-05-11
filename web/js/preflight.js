window.WeiboPreflight = {
  createController({ ui, controls, readForm, escapeHtml, escapeAttr }) {
    const PREFLIGHT_SESSION_KEY = "weibo_preflight_session_v2";
    const LEGACY_PREFLIGHT_STORAGE_KEY = "weibo_preflight_cache_v1";

    let preflightPendingPayload = null;
    let preflightCollapseTimer = null;
    let lastPreflight = null;

    function renderInline(preflight, options = {}) {
      const checks = preflight.checks || [];
      const { collapsed = false, restore = false } = options;
      clearTimeout(preflightCollapseTimer);
      if (!checks.length) {
        resetInline();
        return;
      }
      const wasHidden = ui.preflightPanel.classList.contains("hidden");
      ui.preflightPanel.classList.remove("hidden");
      lastPreflight = preflight;
      ui.preflightSummary.textContent = summaryText(checks);
      renderCheckList(ui.preflightList, checks);
      setCollapsed(collapsed);
      if (!restore && wasHidden && !collapsed) {
        playEnterAnimation();
      }
      if (!restore) {
        preflightCollapseTimer = window.setTimeout(() => {
          setCollapsed(true);
        }, 2000);
      }
    }

    function resetInline() {
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
      clearCache();
    }

    function setCollapsed(collapsed) {
      const isCollapsed = Boolean(collapsed);
      ui.preflightPanel.classList.toggle("collapsed", isCollapsed);
      ui.preflightPanel.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
      if (controls.preflightToggle) {
        controls.preflightToggle.textContent = isCollapsed ? "展开" : "收起";
        controls.preflightToggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
      }
      persistCache(isCollapsed);
    }

    function playEnterAnimation() {
      ui.preflightPanel.classList.remove("preflight-entering");
      void ui.preflightPanel.offsetWidth;
      ui.preflightPanel.classList.add("preflight-entering");
      window.setTimeout(() => {
        ui.preflightPanel.classList.remove("preflight-entering");
      }, 420);
    }

    function formKey(payload = readForm()) {
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

    function persistCache(collapsed) {
      if (!lastPreflight?.checks?.length) return;
      try {
        sessionStorage.setItem(
          PREFLIGHT_SESSION_KEY,
          JSON.stringify({
            preflight: lastPreflight,
            collapsed: Boolean(collapsed),
            form_key: formKey(),
            saved_at: Date.now(),
          }),
        );
      } catch (err) {
        // Ignore storage failures.
      }
    }

    function clearCache() {
      try {
        sessionStorage.removeItem(PREFLIGHT_SESSION_KEY);
        localStorage.removeItem(LEGACY_PREFLIGHT_STORAGE_KEY);
      } catch (err) {
        // Ignore storage failures.
      }
    }

    function clearLegacyCache() {
      try {
        localStorage.removeItem(LEGACY_PREFLIGHT_STORAGE_KEY);
      } catch (err) {
        // Ignore storage failures.
      }
    }

    function restoreCache() {
      clearLegacyCache();
      let cached = null;
      try {
        cached = JSON.parse(sessionStorage.getItem(PREFLIGHT_SESSION_KEY) || "null");
      } catch (err) {
        clearCache();
        return false;
      }
      if (!cached?.preflight?.checks?.length) return false;
      renderInline(cached.preflight, {
        collapsed: Boolean(cached.collapsed),
        restore: true,
      });
      return true;
    }

    function showModal(preflight, canProceed, payload) {
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

    function closeModal() {
      ui.preflightOverlay.classList.remove("visible");
      ui.preflightOverlay.setAttribute("aria-hidden", "true");
      preflightPendingPayload = null;
    }

    function pendingPayload() {
      return preflightPendingPayload;
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

    function summaryText(checks) {
      const errors = checks.filter((item) => item.status === "error").length;
      const warnings = checks.filter((item) => item.status === "warning").length;
      if (errors) return `${errors} 个错误，${warnings} 个警告`;
      if (warnings) return `${warnings} 个警告，可继续`;
      return "全部通过";
    }

    function checkStatusLabel(status) {
      return { ok: "通过", warning: "警告", error: "错误" }[status] || "检查";
    }

    return {
      renderInline,
      resetInline,
      setCollapsed,
      restoreCache,
      clearLegacyCache,
      showModal,
      closeModal,
      pendingPayload,
    };
  },
};
