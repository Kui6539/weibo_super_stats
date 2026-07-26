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

  // Focus handling for elements marked role="dialog" aria-modal="true".
  //
  // Without it the attribute is a promise the page does not keep: Tab still
  // walks the controls behind the overlay, and a screen reader is never told
  // the dialog opened. help.js moved focus on open; the preflight, history
  // detail and history preview dialogs did not.
  //
  // Returns a function that restores focus to whatever had it before.
  trapFocus(dialog) {
    if (!dialog) return () => {};
    const previous = document.activeElement;
    const selector =
      'a[href], button:not([disabled]), textarea, input:not([type="hidden"]):not([disabled]), select, [tabindex]:not([tabindex="-1"])';

    const focusable = () =>
      Array.from(dialog.querySelectorAll(selector)).filter(
        (node) => node.offsetParent !== null || node === document.activeElement,
      );

    const onKeydown = (event) => {
      if (event.key !== "Tab") return;
      const nodes = focusable();
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      // Wrap at both ends so focus cannot escape to the page behind.
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    dialog.addEventListener("keydown", onKeydown);
    (focusable()[0] || dialog).focus();

    return () => {
      dialog.removeEventListener("keydown", onKeydown);
      if (previous && typeof previous.focus === "function") previous.focus();
    };
  },
};
