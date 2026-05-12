window.WeiboPreview = {
  createController({
    ui,
    controls,
    api,
    setBusy,
    escapeHtml,
    appendClientLog,
    showToast,
    copyText,
  }) {
    let currentMarkdown = "";
    let markdownRenderer = null;
    let currentMdPath = "";

    async function load(options = {}) {
      const isAuto = Boolean(options.auto);
      if (options.mdPath !== undefined) currentMdPath = options.mdPath || "";
      if (!isAuto) {
        setBusy(controls.preview, true, "正在加载");
      }
      setLoading("正在加载 Markdown 预览...");
      try {
        const previewUrl = currentMdPath
          ? `/api/report-preview?md_path=${encodeURIComponent(currentMdPath)}`
          : "/api/report-preview";
        const data = await api(previewUrl);
        currentMarkdown = String(data.markdown || "");
        ui.previewPath.textContent = data.path || "";
        renderIntoPreview(currentMarkdown);
        show();
        if (window.innerWidth <= 980) {
          ui.previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } catch (err) {
        const message = getErrorMessage(err);
        currentMarkdown = "";
        ui.previewContent.innerHTML = `<div class="empty-state error">预览失败：${escapeHtml(
          message,
        )}。建议确认 Markdown 文件是否已经生成。</div>`;
        show();
        appendClientLog(`Markdown 预览失败：${message}`);
      } finally {
        if (!isAuto) {
          setBusy(controls.preview, false);
        }
      }
    }

    function reset() {
      currentMarkdown = "";
      currentMdPath = "";
      hide();
    }

    function setLoading(message) {
      ui.previewContent.innerHTML = `<div class="empty-state loading">${escapeHtml(message)}</div>`;
    }

    function renderIntoPreview(markdown) {
      if (!markdown.trim()) {
        ui.previewContent.innerHTML = `<div class="empty-state">暂无可预览内容</div>`;
        return;
      }
      ui.previewContent.innerHTML = renderMarkdown(markdown);
      bindImages(ui.previewContent);
    }

    function bindImages(container) {
      container.querySelectorAll("img").forEach((image) => {
        image.addEventListener(
          "error",
          () => {
            image.classList.add("image-error");
            const placeholder = document.createElement("div");
            placeholder.className = "image-error-placeholder";
            placeholder.textContent = "图片加载失败";
            image.replaceWith(placeholder);
          },
          { once: true },
        );
      });
    }

    function show() {
      ui.layout.classList.add("has-preview");
      ui.previewPanel.setAttribute("aria-hidden", "false");
      controls.preview.textContent = "关闭预览";
    }

    function hide() {
      ui.layout.classList.remove("has-preview");
      ui.previewPanel.setAttribute("aria-hidden", "true");
      controls.preview.textContent = "周报编辑预览";
    }

    async function copy() {
      if (!currentMarkdown) {
        try {
          const data = await api("/api/report-preview");
          currentMarkdown = String(data.markdown || "");
        } catch (err) {
          appendClientLog(`复制 Markdown 失败：${getErrorMessage(err)}`);
          return;
        }
      }
      if (!currentMarkdown.trim()) {
        showToast("暂无可复制的 Markdown。", "info");
        return;
      }
      copyText(currentMarkdown, "Markdown 已复制。");
    }

    function renderMarkdown(markdown) {
      return getMarkdownRenderer().render(String(markdown || ""));
    }

    function getMarkdownRenderer() {
      if (markdownRenderer) {
        return markdownRenderer;
      }
      if (typeof window.markdownit !== "function") {
        throw new Error("Markdown-it 未加载，请确认 /vendor/markdown-it.min.js 可访问。");
      }

      const renderer = window.markdownit({
        html: false,
        linkify: true,
        typographer: false,
        breaks: true,
      });
      const defaultImageRenderer =
        renderer.renderer.rules.image ||
        function defaultImage(tokens, idx, options, env, self) {
          return self.renderToken(tokens, idx, options);
        };
      const defaultLinkRenderer =
        renderer.renderer.rules.link_open ||
        function defaultLink(tokens, idx, options, env, self) {
          return self.renderToken(tokens, idx, options);
        };

      renderer.renderer.rules.image = function imageRule(tokens, idx, options, env, self) {
        const token = tokens[idx];
        const src = token.attrGet("src");
        if (src) {
          token.attrSet("src", normalizeReportAssetUrl(src));
        }
        token.attrSet("loading", "lazy");
        token.attrSet("decoding", "async");
        return defaultImageRenderer(tokens, idx, options, env, self);
      };

      renderer.renderer.rules.link_open = function linkOpenRule(tokens, idx, options, env, self) {
        const token = tokens[idx];
        const href = token.attrGet("href");
        if (href) {
          const normalizedHref = normalizeReportAssetUrl(href);
          token.attrSet("href", normalizedHref);
          if (!normalizedHref.startsWith("#")) {
            token.attrSet("target", "_blank");
            token.attrSet("rel", "noreferrer");
          }
        }
        return defaultLinkRenderer(tokens, idx, options, env, self);
      };

      markdownRenderer = renderer;
      return markdownRenderer;
    }

    function normalizeReportAssetUrl(raw) {
      const text = String(raw || "").trim();
      if (!text || text.startsWith("#")) {
        return text;
      }
      if (/^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|\/\/)/.test(text) && !/^[a-zA-Z]:[\\/]/.test(text)) {
        return text;
      }
      const base = `/api/report-asset?path=${encodeURIComponent(text)}`;
      return currentMdPath ? `${base}&md_path=${encodeURIComponent(currentMdPath)}` : base;
    }

    function getErrorMessage(err) {
      return err && err.message ? err.message : String(err || "未知错误");
    }

    return {
      load,
      reset,
      show,
      hide,
      copy,
      renderMarkdown,
      bindImages,
    };
  },
};
