window.WeiboForm = {
  createController({ fields, controls, ui, getTheme }) {
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
        theme: getTheme(),
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
        theme: getTheme(),
        advanced_mode: controls.advancedMode.checked,
      };
    }

    function setAdvancedMode(enabled) {
      const nextEnabled = Boolean(enabled);
      controls.advancedMode.checked = nextEnabled;
      ui.advancedFields.classList.toggle("expanded", nextEnabled);
      ui.advancedFields.setAttribute("aria-hidden", nextEnabled ? "false" : "true");
    }

    function applyDefaults(defaults) {
      fields.superTopic.value = defaults.super_topic || "";
      fields.cookie.value = defaults.cookie || "";
      fields.windowStart.value = defaults.window_start || "";
      fields.windowEnd.value = defaults.window_end || "";
      fields.maxPages.value = defaults.max_pages || 80;
      fields.topicCommentFactor.value = defaults.topic_comment_factor || 1;
      fields.pauseSeconds.value = defaults.pause_seconds || 1;
      fields.outputDir.value = defaults.output_dir || "";
      setAdvancedMode(defaults.advanced_mode === true || defaults.advanced_mode === "true");
    }

    return {
      readForm,
      configPayload,
      setAdvancedMode,
      applyDefaults,
    };
  },
};
