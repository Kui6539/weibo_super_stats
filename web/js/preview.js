window.WeiboPreview = {
  createController({
    ui,
    controls,
    api,
    setBusy,
    escapeHtml,
    escapeAttr,
    appendClientLog,
    showToast,
    copyText,
  }) {
    let renderedPreviewKey = "";
    let currentMarkdown = "";

    async function load(options = {}) {
      const isAuto = Boolean(options.auto);
      const force = Boolean(options.force);
      if (!isAuto) {
        setBusy(controls.preview, true, "正在载入");
      }
      setLoading("正在加载 Markdown 预览...");
      try {
        const data = await api("/api/report-preview");
        const markdown = data.markdown || "";
        const key = `${data.path || ""}:${markdown.length}:${force ? Date.now() : ""}`;
        currentMarkdown = markdown;
        if (!markdown.trim()) {
          ui.previewContent.innerHTML = `<div class="empty-state">暂无可预览内容</div>`;
          renderedPreviewKey = key;
        } else {
          ui.previewContent.innerHTML = renderMarkdown(markdown);
          bindImages(ui.previewContent);
          renderedPreviewKey = key;
        }
        ui.previewPath.textContent = data.path || "";
        show();
        if (!isAuto || window.innerWidth <= 980) {
          ui.previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } catch (err) {
        currentMarkdown = "";
        ui.previewContent.innerHTML = `<div class="empty-state error">预览失败：${escapeHtml(err.message)}。建议确认 Markdown 文件是否已经生成。</div>`;
        show();
        appendClientLog(err.message);
      } finally {
        if (!isAuto) {
          setBusy(controls.preview, false);
        }
      }
    }

    function reset() {
      renderedPreviewKey = "";
      currentMarkdown = "";
      hide();
    }

    function setLoading(message) {
      ui.previewContent.innerHTML = `<div class="empty-state loading">${escapeHtml(message)}</div>`;
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
      controls.preview.textContent = "预览 Markdown";
    }

    async function copy() {
      if (!currentMarkdown) {
        try {
          const data = await api("/api/report-preview");
          currentMarkdown = data.markdown || "";
        } catch (err) {
          appendClientLog(err.message);
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
      const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
      const html = [];
      let listMode = null;

      function closeList() {
        if (listMode) {
          html.push(`</${listMode}>`);
          listMode = null;
        }
      }

      for (const rawLine of lines) {
        const line = rawLine.trimEnd();
        const trimmed = line.trim();

        if (!trimmed) {
          closeList();
          continue;
        }

        const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
        if (heading) {
          closeList();
          const level = heading[1].length;
          html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
          continue;
        }

        const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(trimmed);
        if (image) {
          closeList();
          const src = reportAssetUrl(image[2]);
          html.push(`<img src="${escapeAttr(src)}" alt="${escapeAttr(image[1])}" loading="lazy" />`);
          continue;
        }

        const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
        if (unordered) {
          if (listMode !== "ul") {
            closeList();
            html.push("<ul>");
            listMode = "ul";
          }
          html.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
          continue;
        }

        const ordered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
        if (ordered) {
          if (listMode !== "ol") {
            closeList();
            html.push("<ol>");
            listMode = "ol";
          }
          html.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
          continue;
        }

        closeList();
        html.push(`<p>${inlineMarkdown(trimmed)}</p>`);
      }
      closeList();
      return html.join("");
    }

    function inlineMarkdown(text) {
      let html = escapeHtml(text);
      html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
      html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
        const href = /^https?:\/\//i.test(url) ? url : reportAssetUrl(url);
        return `<a href="${escapeAttr(href)}" target="_blank" rel="noreferrer">${label}</a>`;
      });
      return html;
    }

    function reportAssetUrl(raw) {
      const text = String(raw || "").trim();
      if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(text)) return text;
      return `/api/report-asset?path=${encodeURIComponent(text)}`;
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
