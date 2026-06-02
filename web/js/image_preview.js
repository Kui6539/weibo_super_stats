window.WeiboImagePreview = {
  createController({
    ui,
    controls,
    api,
    setBusy,
    escapeHtml,
    escapeAttr,
    appendClientLog,
    showToast,
  }) {
    let pages = [];
    let currentIndex = 0;
    let currentMdPath = "";
    let currentPreviewHtmlPath = "";
    let onBeforeShow = null;

    function setOnBeforeShow(callback) {
      onBeforeShow = typeof callback === "function" ? callback : null;
    }

    function setPages(options = {}) {
      const list = Array.isArray(options.pages) ? options.pages.slice() : [];
      const incomingMd = options.mdPath !== undefined ? String(options.mdPath || "") : currentMdPath;
      const previewPath = options.previewHtml !== undefined ? String(options.previewHtml || "") : currentPreviewHtmlPath;
      const sameList =
        list.length === pages.length &&
        list.every((item, idx) => normalizePagePath(item) === normalizePagePath(pages[idx]));
      const sameMd = incomingMd === currentMdPath;
      pages = list;
      currentMdPath = incomingMd;
      currentPreviewHtmlPath = previewPath;
      if (!sameList || !sameMd) {
        currentIndex = 0;
      }
      updateAvailability();
      if (isVisible()) {
        renderViewport();
        renderThumbs();
      }
    }

    function reset() {
      pages = [];
      currentIndex = 0;
      currentMdPath = "";
      currentPreviewHtmlPath = "";
      hide();
      updateAvailability();
    }

    function hasPages() {
      return pages.length > 0;
    }

    function isVisible() {
      return ui.imagePreviewPanel?.getAttribute("aria-hidden") === "false";
    }

    function show() {
      if (!ui.imagePreviewPanel) return;
      if (typeof onBeforeShow === "function") {
        onBeforeShow();
      }
      ui.layout.classList.add("has-image-preview");
      ui.imagePreviewPanel.setAttribute("aria-hidden", "false");
      renderViewport();
      renderThumbs();
      if (window.innerWidth <= 980) {
        ui.imagePreviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

    function hide() {
      if (!ui.imagePreviewPanel) return;
      ui.layout.classList.remove("has-image-preview");
      ui.imagePreviewPanel.setAttribute("aria-hidden", "true");
    }

    function toggle() {
      if (!hasPages()) {
        showToast("当前没有可预览的长图。", "warning");
        return;
      }
      if (isVisible()) {
        hide();
      } else {
        show();
      }
    }

    function next() {
      if (!hasPages()) return;
      currentIndex = (currentIndex + 1) % pages.length;
      renderViewport();
      renderThumbs();
    }

    function prev() {
      if (!hasPages()) return;
      currentIndex = (currentIndex - 1 + pages.length) % pages.length;
      renderViewport();
      renderThumbs();
    }

    function goto(index) {
      if (!hasPages()) return;
      const target = Number(index);
      if (!Number.isFinite(target)) return;
      const next = Math.max(0, Math.min(pages.length - 1, target));
      if (next === currentIndex) return;
      currentIndex = next;
      renderViewport();
      renderThumbs();
    }

    function refresh() {
      if (!hasPages()) {
        showToast("当前没有可预览的长图。", "warning");
        return;
      }
      renderViewport({ bust: true });
    }

    function openInNewWindow() {
      const target = pages.length
        ? buildAssetUrl(pages[currentIndex])
        : currentPreviewHtmlPath
          ? buildAssetUrl(currentPreviewHtmlPath)
          : "";
      if (!target) {
        showToast("当前没有可打开的长图。", "warning");
        return;
      }
      window.open(target, "_blank", "noopener");
    }

    function renderViewport(options = {}) {
      if (!ui.imagePreviewViewport) return;
      if (!hasPages()) {
        ui.imagePreviewViewport.innerHTML = `<div class="empty-state">暂无可预览的长图</div>`;
        if (ui.imagePreviewPath) ui.imagePreviewPath.textContent = "";
        if (ui.imagePreviewCounter) ui.imagePreviewCounter.textContent = "0 / 0";
        updateAvailability();
        return;
      }
      const path = pages[currentIndex];
      const url = buildAssetUrl(path, { bust: Boolean(options.bust) });
      ui.imagePreviewViewport.innerHTML = `<img src="${escapeAttr(url)}" alt="长图第 ${currentIndex + 1} 页" />`;
      const img = ui.imagePreviewViewport.querySelector("img");
      if (img) {
        img.addEventListener(
          "error",
          () => {
            ui.imagePreviewViewport.innerHTML = `<div class="empty-state error">长图加载失败：${escapeHtml(String(path))}</div>`;
          },
          { once: true },
        );
      }
      if (ui.imagePreviewPath) ui.imagePreviewPath.textContent = relativizeAssetPath(path) || normalizePagePath(path);
      if (ui.imagePreviewCounter) ui.imagePreviewCounter.textContent = `${currentIndex + 1} / ${pages.length}`;
      updateAvailability();
    }

    function renderThumbs() {
      if (!ui.imagePreviewThumbs) return;
      if (!hasPages()) {
        ui.imagePreviewThumbs.innerHTML = "";
        return;
      }
      ui.imagePreviewThumbs.innerHTML = pages
        .map(
          (_, index) =>
            `<button type="button" data-image-page-index="${index}" class="${index === currentIndex ? "active" : ""}">第 ${index + 1} 张</button>`,
        )
        .join("");
    }

    function updateAvailability() {
      const disableArrows = pages.length <= 1;
      if (controls.imagePreviewPrev) controls.imagePreviewPrev.disabled = disableArrows;
      if (controls.imagePreviewNext) controls.imagePreviewNext.disabled = disableArrows;
    }

    function buildAssetUrl(rawPath, options = {}) {
      const text = relativizeAssetPath(normalizePagePath(rawPath));
      if (!text) return "";
      if (/^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|\/\/)/.test(text) && !/^[a-zA-Z]:[\\/]/.test(text)) {
        return text;
      }
      const params = new URLSearchParams();
      params.set("path", text);
      if (currentMdPath) params.set("md_path", currentMdPath);
      if (options.bust) params.set("_t", String(Date.now()));
      return `/api/report-asset?${params.toString()}`;
    }

    function normalizePagePath(value) {
      if (!value) return "";
      if (typeof value === "string") return value.trim();
      if (typeof value === "object") {
        return String(value.path || value.relative_path || value.name || "").trim();
      }
      return String(value).trim();
    }

    function relativizeAssetPath(rawPath) {
      const text = normalizeSlashes(rawPath);
      if (!text) return "";
      if (!/^[a-zA-Z]:\//.test(text) && !text.startsWith("/")) {
        return text;
      }
      const baseDir = normalizeSlashes(dirname(currentMdPath));
      if (!baseDir) {
        return text;
      }
      const lowerText = text.toLowerCase();
      const lowerBase = baseDir.toLowerCase();
      if (lowerText === lowerBase) {
        return "";
      }
      if (lowerText.startsWith(lowerBase + "/")) {
        return text.slice(baseDir.length + 1);
      }
      return text;
    }

    function dirname(path) {
      const text = normalizeSlashes(path);
      if (!text) return "";
      const index = text.lastIndexOf("/");
      return index >= 0 ? text.slice(0, index) : "";
    }

    function normalizeSlashes(path) {
      return String(path || "").trim().replace(/\\+/g, "/");
    }

    function handleThumbClick(event) {
      const button = event.target.closest("[data-image-page-index]");
      if (!button) return;
      goto(button.dataset.imagePageIndex);
    }

    return {
      setPages,
      reset,
      show,
      hide,
      toggle,
      next,
      prev,
      goto,
      refresh,
      openInNewWindow,
      hasPages,
      isVisible,
      handleThumbClick,
      setOnBeforeShow,
    };
  },
};
