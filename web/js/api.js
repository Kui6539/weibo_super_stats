window.WeiboApi = {
  async request(path, options = {}) {
    const init = {
      headers: { "Content-Type": "application/json" },
      ...options,
    };
    const response = await fetch(path, init);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(window.WeiboApi.formatError(data, response.status));
    }
    return data;
  },

  formatError(data, status) {
    if (data && typeof data.error === "object" && data.error) {
      const message = data.error.message || `请求失败：${status}`;
      const suggestion = data.error.suggestion ? `建议：${data.error.suggestion}` : "";
      return [message, suggestion].filter(Boolean).join("。");
    }
    return String(data?.error || `请求失败：${status}`);
  },
};
