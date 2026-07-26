window.WeiboForm = {
  createController({ fields, controls, ui, getTheme }) {
    // The server never sends the saved cookie back, so an empty textarea means
    // "keep whatever is stored", not "clear it". Omitting the key entirely lets
    // the server fall back to the stored value; sending "" would wipe it.
    let hasStoredCookie = false;

    function withCookie(payload) {
      const typed = fields.cookie.value.trim();
      if (typed) return { ...payload, cookie: typed };
      if (hasStoredCookie) return payload;
      return { ...payload, cookie: "" };
    }

    function readForm() {
      return withCookie({
        super_topic: fields.superTopic.value.trim(),
        issue: fields.issue.value.trim(),
        window_start: fields.windowStart.value,
        window_end: fields.windowEnd.value,
        max_pages: fields.maxPages.value,
        topic_comment_factor: fields.topicCommentFactor.value,
        pause_seconds: fields.pauseSeconds.value,
        likes_weight: fields.likesWeight.value,
        comment_weight: fields.commentWeight.value,
        author_reply_weight: fields.authorReplyWeight.value,
        repost_weight: fields.repostWeight.value,
        output_dir: fields.outputDir.value.trim(),
        theme: getTheme(),
        advanced_mode: controls.advancedMode.checked,
      });
    }

    function configPayload() {
      return withCookie({
        super_topic: fields.superTopic.value.trim(),
        issue: fields.issue.value.trim(),
        max_pages: fields.maxPages.value,
        topic_comment_factor: fields.topicCommentFactor.value,
        pause_seconds: fields.pauseSeconds.value,
        likes_weight: fields.likesWeight.value,
        comment_weight: fields.commentWeight.value,
        author_reply_weight: fields.authorReplyWeight.value,
        repost_weight: fields.repostWeight.value,
        output_dir: fields.outputDir.value.trim(),
        theme: getTheme(),
        advanced_mode: controls.advancedMode.checked,
      });
    }

    function setStoredCookieState(hasCookie, cookieLength) {
      hasStoredCookie = Boolean(hasCookie);
      fields.cookie.placeholder = hasStoredCookie
        ? `已保存 Cookie（${cookieLength || 0} 个字符），留空表示继续使用；粘贴新的可覆盖`
        : "粘贴微博 Cookie，或使用上方按钮自动获取";
    }

    function setAdvancedMode(enabled) {
      const nextEnabled = Boolean(enabled);
      controls.advancedMode.checked = nextEnabled;
      ui.advancedFields.classList.toggle("expanded", nextEnabled);
      ui.advancedFields.setAttribute("aria-hidden", nextEnabled ? "false" : "true");
    }

    function applyDefaults(defaults) {
      fields.superTopic.value = defaults.super_topic || "";
      fields.issue.value = defaults.issue || "";
      fields.cookie.value = "";
      setStoredCookieState(defaults.has_cookie, defaults.cookie_length);
      fields.windowStart.value = defaults.window_start || "";
      fields.windowEnd.value = defaults.window_end || "";
      fields.maxPages.value = defaults.max_pages || 80;
      fields.topicCommentFactor.value = defaults.topic_comment_factor || 1;
      fields.pauseSeconds.value = defaults.pause_seconds || 1;
      fields.likesWeight.value = defaults.likes_weight ?? 0.3;
      fields.commentWeight.value = defaults.comment_weight ?? 0.5;
      fields.authorReplyWeight.value = defaults.author_reply_weight ?? 0.2;
      fields.repostWeight.value = defaults.repost_weight ?? 0.1;
      fields.outputDir.value = defaults.output_dir || "";
      setAdvancedMode(defaults.advanced_mode === true || defaults.advanced_mode === "true");
    }

    return {
      readForm,
      configPayload,
      setAdvancedMode,
      applyDefaults,
      setStoredCookieState,
      hasStoredCookie: () => hasStoredCookie,
    };
  },
};
