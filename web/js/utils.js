window.WeiboUtils = {
  $(id) {
    return document.getElementById(id);
  },

  clamp(value, min, max) {
    return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
  },

  escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },

  escapeAttr(value) {
    return this.escapeHtml(value);
  },

  setBusy(button, busy, text) {
    if (!button) return;
    if (busy) {
      const busyText = text || "处理中";
      button.dataset.originalText = button.textContent;
      button.dataset.busyText = busyText;
      button.textContent = busyText;
      button.disabled = true;
      return;
    }
    if (
      button.dataset.busyText &&
      button.textContent === button.dataset.busyText &&
      button.dataset.originalText
    ) {
      button.textContent = button.dataset.originalText;
    }
    delete button.dataset.originalText;
    delete button.dataset.busyText;
    button.disabled = false;
  },

  createClipboard({ showToast, appendClientLog }) {
    return {
      async copy(text, successMessage) {
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          showToast(successMessage || "已复制。");
        } catch (err) {
          appendClientLog(`复制失败：${err.message}`);
        }
      },
    };
  },
};
