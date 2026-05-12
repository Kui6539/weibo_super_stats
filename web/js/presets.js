window.WeiboPresets = {
  createController({ fields, controls, api, setBusy, showToast, formController, scheduleConfigSave }) {
    let data = { presets: {}, active_preset: "default" };

    async function load() {
      if (!controls.presetSelect) return;
      const response = await api("/api/presets");
      data = response.data || response;
      render();
    }

    function render() {
      const select = controls.presetSelect;
      if (!select) return;
      const presets = data.presets || {};
      select.innerHTML = Object.entries(presets)
        .map(([id, preset]) => `<option value="${escapeAttr(id)}">${escapeHtml(preset.name || id)}</option>`)
        .join("");
      select.value = data.active_preset || "default";
    }

    async function activate() {
      const presetId = controls.presetSelect?.value || "";
      if (!presetId) return;
      const response = await api("/api/presets/activate", {
        method: "POST",
        body: JSON.stringify({ preset_id: presetId }),
      });
      data = response.data || response;
      applyPreset(data.active_config || {});
      render();
      showToast("已切换预设");
    }

    async function saveCurrent() {
      const presetId = controls.presetSelect?.value || data.active_preset || "default";
      setBusy(controls.presetSave, true, "保存中");
      try {
        const payload = formController.configPayload();
        const response = await api("/api/presets/save", {
          method: "POST",
          body: JSON.stringify({
            preset_id: presetId,
            preset: {
              name: (data.presets?.[presetId]?.name || "默认预设"),
              ...payload,
            },
          }),
        });
        data = response.data || response;
        render();
        scheduleConfigSave?.();
        showToast("预设已保存");
      } finally {
        setBusy(controls.presetSave, false);
      }
    }

    async function createNew() {
      const name = prompt("请输入新预设名称", "新预设");
      if (!name) return;
      const uniqueName = deduplicateName(name);
      const presetId = slugify(uniqueName) + "_" + Date.now().toString(36);
      const response = await api("/api/presets/save", {
        method: "POST",
        body: JSON.stringify({
          preset_id: presetId,
          preset: {
            name: uniqueName,
            ...formController.configPayload(),
          },
        }),
      });
      data = response.data || response;
      render();
      showToast("新预设已创建");
    }

    async function duplicate() {
      const sourceId = controls.presetSelect?.value || data.active_preset || "default";
      const name = prompt("请输入副本名称", `${data.presets?.[sourceId]?.name || sourceId} 副本`);
      if (!name) return;
      const response = await api("/api/presets/duplicate", {
        method: "POST",
        body: JSON.stringify({ source_id: sourceId, new_id: slugify(name), name }),
      });
      data = response.data || response;
      render();
      applyPreset(data.active_config || {});
      showToast("预设已复制");
    }

    async function rename() {
      const presetId = controls.presetSelect?.value || data.active_preset || "default";
      const current = data.presets?.[presetId] || {};
      const name = prompt("请输入新的预设名称", current.name || presetId);
      if (!name) return;
      const response = await api("/api/presets/save", {
        method: "POST",
        body: JSON.stringify({ preset_id: presetId, preset: { ...current, name } }),
      });
      data = response.data || response;
      render();
      showToast("预设已重命名");
    }

    async function remove() {
      const presetId = controls.presetSelect?.value || data.active_preset || "default";
      if (!confirm("确定要删除该预设吗？Cookie 不会被删除。")) return;
      const response = await api("/api/presets/delete", {
        method: "POST",
        body: JSON.stringify({ preset_id: presetId }),
      });
      data = response.data || response;
      render();
      applyPreset(data.active_config || {});
      showToast("预设已删除");
    }

    function applyPreset(config) {
      if (config.super_topic !== undefined) fields.superTopic.value = config.super_topic || "";
      if (config.max_pages !== undefined) fields.maxPages.value = config.max_pages || 80;
      if (config.topic_comment_factor !== undefined) fields.topicCommentFactor.value = config.topic_comment_factor || 1;
      if (config.pause_seconds !== undefined) fields.pauseSeconds.value = config.pause_seconds || 1;
      if (config.likes_weight !== undefined) fields.likesWeight.value = config.likes_weight ?? 0.3;
      if (config.comment_weight !== undefined) fields.commentWeight.value = config.comment_weight ?? 0.5;
      if (config.author_reply_weight !== undefined) fields.authorReplyWeight.value = config.author_reply_weight ?? 0.2;
      if (config.repost_weight !== undefined) fields.repostWeight.value = config.repost_weight ?? 0.1;
      if (config.output_dir !== undefined) fields.outputDir.value = config.output_dir || "";
      scheduleConfigSave?.();
    }

    function escapeHtml(value) {
      return window.WeiboUtils.escapeHtml(value);
    }

    function escapeAttr(value) {
      return window.WeiboUtils.escapeAttr(value);
    }

    function slugify(value) {
      return String(value || "preset")
        .trim()
        .toLowerCase()
        .replace(/[^\w\u4e00-\u9fff-]+/g, "_")
        .replace(/^_+|_+$/g, "") || "preset";
    }

    function deduplicateName(name) {
      const existing = Object.values(data.presets || {}).map((p) => p.name || "");
      if (!existing.includes(name)) return name;
      let i = 2;
      while (existing.includes(`${name} ${i}`)) i++;
      return `${name} ${i}`;
    }

    return { load, activate, saveCurrent, createNew, duplicate, rename, remove };
  },
};
