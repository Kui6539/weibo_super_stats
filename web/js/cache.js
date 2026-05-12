window.WeiboCache = {
  createController({
    ui,
    controls,
    api,
    setBusy,
    escapeHtml,
    escapeAttr,
    copyText,
    showToast,
    appendClientLog,
    previewController,
  }) {
    let autoPreviewResultKey = "";
    let lastCacheStatusKey = "";
    let lastCacheCanReexport = false;
    let currentRunDir = "";

    function renderResult(job) {
      const result = job?.result;
      if (!result) {
        ui.resultPanel.classList.add("hidden");
        ui.monitorPanel.classList.remove("collapsed");
        controls.preview.classList.add("hidden");
        controls.preview.disabled = true;
        controls.openResultDir.classList.add("hidden");
        controls.openResultDir.disabled = true;
        if (ui.cacheStatusBox) ui.cacheStatusBox.textContent = "尚未检查缓存";
        if (controls.reexport) controls.reexport.disabled = true;
        lastCacheStatusKey = "";
        lastCacheCanReexport = false;
        previewController.hide();
        autoPreviewResultKey = "";
        return;
      }
      ui.resultPanel.classList.remove("hidden");
      ui.monitorPanel.classList.add("collapsed");
      controls.preview.classList.remove("hidden");
      controls.preview.disabled = false;
      controls.openResultDir.classList.remove("hidden");
      controls.openResultDir.disabled = false;
      renderResultList(result);
      if (result.run_dir) currentRunDir = result.run_dir;
      if (ui.reexportRunDir && result.run_dir && ui.reexportRunDir.value !== result.run_dir) {
        ui.reexportRunDir.value = result.run_dir;
      }
      if (result.run_dir && result.run_dir !== lastCacheStatusKey) {
        checkCacheStatus({ silent: true });
      }

      if (result.md && result.md !== autoPreviewResultKey) {
        autoPreviewResultKey = result.md;
        previewController.load({ auto: true, mdPath: result.md });
      }
    }

    function resetPreviewCache() {
      autoPreviewResultKey = "";
      currentRunDir = "";
    }

    function renderResultList(result) {
      const manifest = result.manifest || {};
      const files = manifest.files || {};
      const warnings = result.warnings || manifest.warnings || [];
      const failedImageCount = Number(result.failed_image_count || manifest.failed_image_count || 0);
      const rows = [
        resultInfoRow("导出目录", result.run_dir || manifest.run_dir, true),
        resultFileRow("Markdown 文件", normalizeFileItem(files.markdown, "Markdown", result.md, "preview_markdown")),
        ...arrayFileRows("DOCX 文件", files.docx || result.docx),
        resultFileRow("总 DOCX", normalizeFileItem(files.docx_sum, "总 DOCX", result.docx_sum)),
        resultFileRow("XLSX 文件", normalizeFileItem(files.xlsx || files.excel, "XLSX", result.xlsx)),
        resultFileRow("CSV 文件", normalizeFileItem(files.csv, "CSV", result.csv)),
        resultFileRow("summary txt 文件", normalizeFileItem(files.summary, "summary txt", result.summary)),
        resultFileRow("images 图片目录", normalizeFileItem(files.images || files.images_dir, "images 图片目录", result.image_dir, "open_result_dir")),
        failedImageCount ? resultInfoRow("失败图片数量", `${failedImageCount} 张`, false) : "",
        ...warnings.map((warning) => resultInfoRow("警告", warning, false, "warning")),
      ].filter(Boolean);
      ui.resultList.innerHTML = rows.join("");
    }

    function arrayFileRows(label, value) {
      if (!value) return [];
      const rows = Array.isArray(value) ? value : [value];
      return rows.map((item, index) => {
        const rowLabel = rows.length > 1 ? `${label} ${index + 1}` : label;
        return resultFileRow(rowLabel, normalizeFileItem(item, rowLabel));
      });
    }

    function normalizeFileItem(item, label, fallbackPath = "", action = "") {
      if (!item && fallbackPath) return pathToFileItem(label, fallbackPath, action);
      if (!item) return null;
      if (typeof item === "string") return pathToFileItem(label, item, action);
      if (item.path || item.relative_path || item.name) return { ...item, action: item.action || action };
      return pathToFileItem(label, String(item), action);
    }

    function pathToFileItem(label, path, action = "") {
      if (!path) return null;
      const name = String(path).split(/[\\/]/).filter(Boolean).pop() || String(path);
      return { label, name, path: String(path), relative_path: String(path), exists: true, action };
    }

    function resultFileRow(label, item) {
      if (!item) return "";
      const path = item.path || "";
      const exists = item.exists !== false;
      const action = item.action || "";
      const previewButton =
        action === "preview_markdown"
          ? `<button type="button" class="secondary small-button" data-preview-md="1">预览 Markdown</button>`
          : "";
      const openButton =
        action === "open_result_dir"
          ? `<button type="button" class="secondary small-button" data-open-result="1">打开导出目录</button>`
          : "";
      return `
    <div class="result-row file-row ${exists ? "exists" : "missing"}">
      <div class="result-label">${escapeHtml(label)}</div>
      <div class="result-value">
        <div class="result-file-head">
          <strong>${escapeHtml(item.name || "未生成")}</strong>
          <span class="mini-badge">${exists ? "存在" : "不存在"}</span>
        </div>
        <div class="result-path">${escapeHtml(item.relative_path || path || "")}</div>
        <div class="result-actions">
          ${previewButton}
          ${openButton}
          ${path ? `<button type="button" class="secondary small-button" data-copy-path="${escapeAttr(path)}">复制路径</button>` : ""}
        </div>
      </div>
    </div>`;
    }

    function resultInfoRow(label, value, copyable = false, state = "") {
      return `
    <div class="result-row ${state}">
      <div class="result-label">${escapeHtml(label)}</div>
      <div class="result-value">
        <div class="result-path">${escapeHtml(value || "")}</div>
        ${copyable && value ? `<div class="result-actions"><button type="button" class="secondary small-button" data-copy-path="${escapeAttr(value)}">复制路径</button></div>` : ""}
      </div>
    </div>`;
    }

    function handleResultClick(event) {
      const copyButton = event.target.closest("[data-copy-path]");
      if (copyButton) {
        copyText(copyButton.dataset.copyPath || "", "路径已复制。");
        return;
      }
      if (event.target.closest("[data-preview-md]")) {
        previewController.load({ mdPath: autoPreviewResultKey });
        return;
      }
      if (event.target.closest("[data-open-result]")) {
        openResultDir();
      }
    }

    async function openResultDir() {
      setBusy(controls.openResultDir, true, "正在打开");
      try {
        const data = await api("/api/open-result-dir", { method: "POST", body: JSON.stringify({ run_dir: currentRunDir }) });
        showToast(`已打开：${data.path || "导出目录"}`);
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.openResultDir, false);
      }
    }

    async function checkCacheStatus(options = {}) {
      const runDir = (ui.reexportRunDir?.value || "").trim();
      if (!runDir) {
        if (!options.silent) showToast("请先填写运行目录。", "warning");
        return null;
      }
      if (!options.silent) setBusy(controls.checkCache, true, "正在检查");
      try {
        const response = await api("/api/cache-status", {
          method: "POST",
          body: JSON.stringify({ run_dir: runDir }),
        });
        const data = response.data || response;
        lastCacheStatusKey = runDir;
        lastCacheCanReexport = Boolean(data.can_reexport);
        renderCacheStatus(data);
        controls.reexport.disabled = !lastCacheCanReexport;
        if (!options.silent) {
          showToast(lastCacheCanReexport ? "缓存完整，可以重新生成报告。" : "缓存不完整，无法重新生成。", lastCacheCanReexport ? "success" : "warning");
        }
        return data;
      } catch (err) {
        lastCacheCanReexport = false;
        controls.reexport.disabled = true;
        renderCacheStatus({ has_cache: false, can_reexport: false, missing: [err.message], files: {} });
        if (!options.silent) appendClientLog(err.message);
        return null;
      } finally {
        if (!options.silent) setBusy(controls.checkCache, false);
      }
    }

    async function reexportReport() {
      const runDir = (ui.reexportRunDir?.value || "").trim();
      if (!runDir) {
        showToast("请先填写运行目录。", "warning");
        return;
      }
      setBusy(controls.reexport, true, "正在生成");
      try {
        const response = await api("/api/reexport", {
          method: "POST",
          body: JSON.stringify({
            run_dir: runDir,
            selected_post_ids: null,
            export_types: selectedReexportTypes(),
          }),
        });
        const data = response.data || response;
        showToast(data.message || "重新生成完成。", "success");
        if (data.result) {
          renderResultList(data.result);
          if (data.result.run_dir) ui.reexportRunDir.value = data.result.run_dir;
        }
        await checkCacheStatus({ silent: true });
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.reexport, false);
        controls.reexport.disabled = !lastCacheCanReexport;
      }
    }

    function selectedReexportTypes() {
      return Array.from(document.querySelectorAll("input[name='reexportType']:checked")).map((item) => item.value);
    }

    function renderCacheStatus(status) {
      if (!ui.cacheStatusBox) return;
      const files = status.files || {};
      const rows = [
        cacheStatusLine("cache/ 文件夹", Boolean(status.has_cache)),
        cacheStatusLine("原始帖子缓存", Boolean(files.posts_raw)),
        cacheStatusLine("正文补全缓存", Boolean(files.posts_hydrated)),
        cacheStatusLine("评分缓存", Boolean(files.posts_scored)),
        cacheStatusLine("候选缓存", Boolean(files.candidates)),
        cacheStatusLine("人工选择缓存", Boolean(files.selected_posts)),
        cacheStatusLine(`评论缓存 ${Number(status.comments_count || 0)} 个`, Number(status.comments_count || 0) > 0),
        cacheStatusLine("图片清单", Boolean(files.images_manifest)),
        cacheStatusLine("可重新生成报告", Boolean(status.can_reexport)),
      ];
      const missing = (status.missing || []).map((item) => `<div class="cache-status-line missing"><span>缺少</span><strong>${escapeHtml(item)}</strong></div>`);
      ui.cacheStatusBox.innerHTML = [...rows, ...missing].join("");
    }

    function cacheStatusLine(label, ok) {
      return `<div class="cache-status-line ${ok ? "ok" : "missing"}"><span>${ok ? "✓" : "✗"} ${escapeHtml(label)}</span><strong>${ok ? "是" : "否"}</strong></div>`;
    }

    function resetCacheStatus() {
      lastCacheStatusKey = "";
      lastCacheCanReexport = false;
      controls.reexport.disabled = true;
      ui.cacheStatusBox.textContent = "运行目录已修改，请重新检查缓存";
    }

    return {
      renderResult,
      handleResultClick,
      openResultDir,
      checkCacheStatus,
      reexportReport,
      resetCacheStatus,
      resetPreviewCache,
    };
  },
};
