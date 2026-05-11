window.WeiboToast = {
  createController({ sanitizeLogMessage }) {
    let toastStack = null;

    function appendClientLog(message) {
      const text = sanitize(String(message || "").trim());
      if (!text) return;
      show(text, /失败|错误|拒绝|异常|failed|error/i.test(text) ? "error" : "info");
    }

    function show(message, state = "success") {
      const text = sanitize(String(message || "").trim());
      if (!text) return;
      if (!toastStack) {
        toastStack = document.createElement("div");
        toastStack.className = "toast-stack";
        toastStack.setAttribute("aria-live", "polite");
        toastStack.setAttribute("aria-atomic", "true");
        document.body.appendChild(toastStack);
      }

      const toast = document.createElement("div");
      toast.className = `toast ${state}`;
      toast.textContent = text;
      toastStack.appendChild(toast);

      window.setTimeout(() => {
        toast.classList.add("leaving");
        window.setTimeout(() => toast.remove(), 260);
      }, 3000);
    }

    function sanitize(value) {
      return sanitizeLogMessage ? sanitizeLogMessage(value) : value;
    }

    return { appendClientLog, show };
  },
};
