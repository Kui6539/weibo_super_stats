window.WeiboConfig = {
  createController({ api, formController, themeController, cookieController, setSaveState }) {
    let configReady = false;
    let configSaveTimer = null;

    function scheduleSave() {
      if (!configReady) return;
      clearTimeout(configSaveTimer);
      setSaveState("配置待保存", "pending");
      configSaveTimer = setTimeout(saveNow, 420);
    }

    async function saveNow() {
      if (!configReady) return;
      clearTimeout(configSaveTimer);
      try {
        await api("/api/config", {
          method: "POST",
          body: JSON.stringify(formController.configPayload()),
        });
        setSaveState("配置已保存", "saved");
      } catch (err) {
        setSaveState(`配置保存失败：${err.message}`, "error");
      }
    }

    async function initDefaults() {
      const data = await api("/api/defaults");
      const defaults = data.defaults || {};
      formController.applyDefaults(defaults);
      themeController.apply(defaults.theme === "light" ? "light" : "dark");
      cookieController.updateSummary();
      configReady = true;
      setSaveState("配置自动保存", "ready");
    }

    return {
      initDefaults,
      scheduleSave,
      saveNow,
      isReady: () => configReady,
    };
  },
};
