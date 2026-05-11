window.WeiboCookie = {
  createController({
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
  }) {
    let cookieValidationState = "unverified";
    let selectedBrowser = "edge";

    async function launchEdgeDebug() {
      setBusy(controls.edgeDebug, true, "正在打开");
      try {
        const data = await api("/api/cookie/edge-debug", {
          method: "POST",
          body: JSON.stringify({ browser: selectedBrowser }),
        });
        showToast(`调试 ${data.browser_label || browserLabel()} 已启动：${data.endpoint}`);
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.edgeDebug, false);
      }
    }

    async function autoCookie() {
      setBusy(controls.autoCookie, true, "正在读取");
      try {
        const data = await api("/api/cookie/auto", {
          method: "POST",
          body: JSON.stringify({ browser: selectedBrowser }),
        });
        fields.cookie.value = data.cookie || "";
        setValidationState("unverified");
        updateSummary();
        resetPreflightInline();
        await saveConfigNow();
        const label = data.browser_label || browserLabel();
        showToast(data.debug_browser_closed ? `Cookie 自动读取成功，调试 ${label} 已关闭。` : "Cookie 自动读取成功。");
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
        setValidationState("unverified");
        updateSummary();
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
        setValidationState("unverified");
        updateSummary();
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
        setValidationState(stateFromLoginState(result.login_state));
        updateSummary();
        const toastState = result.login_state === "valid" ? "success" : result.login_state === "unknown" ? "info" : "error";
        showToast(`${result.message || "Cookie 检测完成"}。${result.suggestion ? `建议：${result.suggestion}` : ""}`, toastState);
      } catch (err) {
        setValidationState("failed");
        updateSummary();
        appendClientLog(err.message);
      } finally {
        setBusy(controls.checkCookie, false);
      }
    }

    async function clearCookie() {
      setBusy(controls.clearCookie, true, "正在清空");
      try {
        fields.cookie.value = "";
        setValidationState("unverified");
        updateSummary();
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

    function expandEditor() {
      ui.cookieEditor.classList.remove("hidden");
      controls.cookieExpand.classList.add("hidden");
      controls.cookieCollapse.classList.remove("hidden");
      fields.cookie.focus();
    }

    function collapseEditor() {
      ui.cookieEditor.classList.add("hidden");
      controls.cookieExpand.classList.remove("hidden");
      controls.cookieCollapse.classList.add("hidden");
    }

    function setValidationState(state) {
      cookieValidationState = state || "unverified";
    }

    function setBrowser(browser, options = {}) {
      selectedBrowser = normalizeBrowser(browser);
      updateBrowserButtons();
      if (!options.silent) {
        scheduleConfigSave();
      }
    }

    function getBrowser() {
      return selectedBrowser;
    }

    function updateBrowserButtons() {
      const isEdge = selectedBrowser === "edge";
      const switchEl = controls.cookieBrowserEdge?.closest(".cookie-browser-switch");
      switchEl?.classList.toggle("is-chrome", !isEdge);
      controls.cookieBrowserEdge?.classList.toggle("active", isEdge);
      controls.cookieBrowserChrome?.classList.toggle("active", !isEdge);
      controls.cookieBrowserEdge?.setAttribute("aria-pressed", String(isEdge));
      controls.cookieBrowserChrome?.setAttribute("aria-pressed", String(!isEdge));
    }

    function normalizeBrowser(browser) {
      return String(browser || "").toLowerCase() === "chrome" ? "chrome" : "edge";
    }

    function browserLabel() {
      return selectedBrowser === "chrome" ? "Chrome" : "Edge";
    }

    function updateSummary() {
      const length = fields.cookie.value.trim().length;
      ui.cookieSummary.textContent = length ? `已填写 Cookie，长度 ${length} 字符` : "未填写 Cookie";
      ui.cookieStateBadge.textContent = statusLabel(cookieValidationState);
      ui.cookieStateBadge.className = `mini-badge cookie-state ${cookieValidationState}`;
    }

    function statusLabel(state) {
      return (
        {
          unverified: "未验证",
          valid: "验证成功",
          failed: "验证失败",
          stale: "可能失效",
        }[state] || "未验证"
      );
    }

    function stateFromLoginState(state) {
      if (state === "valid") return "valid";
      if (state === "unknown") return "stale";
      return "failed";
    }

    return {
      launchEdgeDebug,
      autoCookie,
      readClipboard,
      extractCookie,
      checkCookie,
      clearCookie,
      expandEditor,
      collapseEditor,
      getBrowser,
      setBrowser,
      setValidationState,
      updateSummary,
    };
  },
};
