window.WeiboTopicPreview = {
  createController({ fields, ui, api, readForm }) {
    let timer = null;
    let sequence = 0;
    let lastAutoIssue = "";
    let issueTouched = false;
    let lastTopicName = "";
    let lastSuperTopic = "";
    let lastTitle = "";

    function sanitizeIssue() {
      const clean = String(fields.issue.value || "").replace(/\D+/g, "");
      if (fields.issue.value !== clean) {
        fields.issue.value = clean;
      }
      issueTouched = true;
      renderTitleHint();
    }

    function resetIssueAutoState() {
      lastAutoIssue = fields.issue.value || "";
      issueTouched = false;
    }

    function scheduleRefresh(delay = 520) {
      clearTimeout(timer);
      const superTopic = fields.superTopic.value.trim();
      if (superTopic !== lastSuperTopic) {
        lastSuperTopic = superTopic;
        lastTopicName = "";
        lastTitle = "";
      }
      renderShell();
      timer = window.setTimeout(refresh, delay);
    }

    async function refresh() {
      clearTimeout(timer);
      timer = null;
      const superTopic = fields.superTopic.value.trim();
      if (!superTopic) {
        lastTopicName = "";
        lastSuperTopic = "";
        lastTitle = "";
        ui.topicMeta.classList.add("hidden");
        return;
      }
      lastSuperTopic = superTopic;
      ui.topicMeta.classList.remove("hidden");
      ui.topicPreviewMessage.textContent = "正在识别标题...";
      const current = ++sequence;
      try {
        const response = await api("/api/topic-preview", {
          method: "POST",
          body: JSON.stringify(readForm()),
        });
        if (current !== sequence) return;
        const data = response.data || response;
        lastTopicName = data.topic_name || "";
        lastTitle = data.title_with_issue || data.title || "";
        ui.topicNameText.textContent = lastTopicName || (data.super_topic_id ? `ID ${data.super_topic_id}` : "等待识别");
        ui.topicPreviewMessage.textContent = lastTitle || data.message || "等待识别";
        if (data.issue && (!issueTouched || !fields.issue.value || fields.issue.value === lastAutoIssue)) {
          fields.issue.value = data.issue;
          lastAutoIssue = data.issue;
          issueTouched = false;
        }
      } catch (err) {
        if (current !== sequence) return;
        ui.topicNameText.textContent = "识别失败";
        ui.topicPreviewMessage.textContent = err.message || "无法识别超话名称";
      }
      renderTitleHint();
    }

    function renderShell() {
      const superTopic = fields.superTopic.value.trim();
      ui.topicMeta.classList.toggle("hidden", !superTopic);
      if (!superTopic) return;
      if (!lastTopicName) {
        ui.topicNameText.textContent = "等待识别";
        ui.topicPreviewMessage.textContent = "等待识别";
      }
    }

    function renderTitleHint() {
      const issue = fields.issue.value.trim();
      if (issue && lastTopicName) {
        lastTitle = `${lastTopicName}超话周报 第${issue}期`;
      }
      if (lastTitle) {
        ui.topicPreviewMessage.textContent = lastTitle;
      }
    }

    return {
      refresh,
      scheduleRefresh,
      sanitizeIssue,
      resetIssueAutoState,
    };
  },
};
