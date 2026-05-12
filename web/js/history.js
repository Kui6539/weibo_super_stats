window.WeiboHistory = {
  createController({ ui, controls, api, setBusy, escapeHtml, escapeAttr, copyText, showToast, appendClientLog, renderJob }) {
    let items = [];
    let dropdownOpen = false;
    let currentDetailItem = null;

    async function load() {
      if (!ui.historyList) return;
      try {
        const response = await api("/api/history/scan", {
          method: "POST",
          body: JSON.stringify({ output_dir: "output" }),
        });
        const data = response.data || response;
        items = data.items || data.history?.items || [];
        render();
      } catch (err) {
        appendClientLog(err.message);
      }
    }

    async function scan() {
      setBusy(controls.historyScan, true, "扫描中");
      try {
        const response = await api("/api/history/scan", {
          method: "POST",
          body: JSON.stringify({ output_dir: "output" }),
        });
        const data = response.data || response;
        items = data.items || data.history?.items || [];
        render();
        showToast(`扫描完成：${data.scanned || 0} 个任务`);
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.historyScan, false);
      }
    }

    function render() {
      if (!ui.historyList) return;
      const rows = filteredItems();
      if (ui.historySummary) {
        ui.historySummary.textContent = `共 ${items.length} 条，当前显示 ${rows.length} 条`;
      }
      if (ui.historyTopbarCount) {
        ui.historyTopbarCount.textContent = String(items.length);
      }
      ui.historyList.innerHTML = rows.length
        ? rows.map(renderItem).join("")
        : `<div class="empty-state">暂无历史任务。可以点击"扫描 output"。</div>`;
    }

    function toggleDropdown(force) {
      const shouldOpen = typeof force === "boolean" ? force : !dropdownOpen;
      setDropdownOpen(shouldOpen);
    }

    function openDropdown() {
      setDropdownOpen(true);
    }

    function closeDropdown() {
      setDropdownOpen(false);
    }

    function setDropdownOpen(open) {
      dropdownOpen = open;
      ui.historyDropdown?.classList.toggle("open", dropdownOpen);
      ui.historyDropdown?.setAttribute("aria-hidden", dropdownOpen ? "false" : "true");
      if (ui.historyBackdrop) {
        const topbar = ui.historyTopbar?.closest(".topbar");
        if (topbar) {
          ui.historyBackdrop.style.top = topbar.getBoundingClientRect().bottom + "px";
        }
        ui.historyBackdrop.classList.toggle("visible", dropdownOpen);
      }
      document.body.style.overflow = dropdownOpen ? "hidden" : "";
      const trigger = controls.historyToggle || controls.historySearch;
      trigger?.setAttribute("aria-expanded", dropdownOpen ? "true" : "false");
    }

    function handleDocumentClick(event) {
      if (!dropdownOpen) return;
      if (ui.historyTopbar?.contains(event.target)) return;
      if (ui.historyDetailOverlay?.contains(event.target)) return;
      if (ui.historyPreviewOverlay?.contains(event.target)) return;
      closeDropdown();
    }

    function filteredItems() {
      const query = (controls.historySearch?.value || "").trim().toLowerCase();
      const filter = controls.historyFilter?.value || "all";
      return items.filter((item) => {
        const haystack = [
          item.run_id,
          item.super_topic_name,
          item.super_topic_id,
          item.super_topic,
          item.report_dir,
          item.status,
        ]
          .join(" ")
          .toLowerCase();
        if (query && !haystack.includes(query)) return false;
        if (filter === "reexport") return Boolean(item.can_reexport);
        if (filter === "warning") return Number(item.warnings_count || 0) > 0;
        if (filter === "failed") return ["failed", "cancelled", "partial"].includes(item.status);
        if (filter === "completed") return item.status === "completed" || item.status === "reexported";
        return true;
      });
    }

    function renderItem(item) {
      const files = item.files || {};
      const title = item.super_topic_name || item.super_topic_id || item.super_topic || "未知超话";
      const badges = ["markdown", "docx", "excel", "csv", "summary", "images"]
        .map((key) => `<span class="mini-badge ${files[key] ? "ok" : ""}">${fileLabel(key)}</span>`)
        .join("");
      return `
        <article class="history-card" data-run-id="${escapeAttr(item.run_id)}">
          <div class="history-card-main">
            <div>
              <h3>${escapeHtml(title)}</h3>
              <p class="muted">${escapeHtml(item.window_start || "")} - ${escapeHtml(item.window_end || "")}</p>
              <p class="history-path">${escapeHtml(item.report_dir || "")}</p>
            </div>
            <div class="history-status">
              <span class="mini-badge">${escapeHtml(item.status || "unknown")}</span>
              <span class="mini-badge ${item.can_reexport ? "ok" : ""}">${item.can_reexport ? "可重新生成" : "缓存不完整"}</span>
            </div>
          </div>
          <div class="history-stats">
            <span>入选 ${Number(item.selected_count || 0)}</span>
            <span>总帖 ${Number(item.total_posts || 0)}</span>
            <span>警告 ${Number(item.warnings_count || 0)}</span>
            <span>失败图 ${Number(item.failed_images_count || 0)}</span>
          </div>
          <div class="history-files">${badges}</div>
          <div class="history-card-actions">
            <button type="button" class="secondary small-button" data-history-open>打开目录</button>
            <button type="button" class="secondary small-button" data-history-cache>检查缓存</button>
            <button type="button" class="secondary small-button" data-history-reexport ${item.can_reexport ? "" : "disabled"}>重新生成</button>
            <button type="button" class="secondary small-button" data-history-copy="${escapeAttr(item.report_dir || "")}">复制路径</button>
            <button type="button" class="secondary small-button" data-history-detail>查看详情</button>
            <button type="button" class="secondary small-button danger-button" data-history-remove>删除</button>
          </div>
        </article>`;
    }

    async function handleClick(event) {
      const card = event.target.closest("[data-run-id]");
      if (!card) return;
      const runId = card.dataset.runId;
      const item = items.find((row) => row.run_id === runId);
      if (event.target.closest("[data-history-open]")) return openDir(runId);
      if (event.target.closest("[data-history-cache]")) return checkCache(runId);
      if (event.target.closest("[data-history-reexport]")) return reexport(runId);
      const copy = event.target.closest("[data-history-copy]");
      if (copy) return copyText(copy.dataset.historyCopy || "", "路径已复制");
      if (event.target.closest("[data-history-detail]")) return showDetail(item);
      if (event.target.closest("[data-history-remove]")) return remove(runId);
    }

    async function openDir(runId) {
      try {
        await api("/api/history/open-dir", { method: "POST", body: JSON.stringify({ run_id: runId }) });
      } catch (err) {
        appendClientLog(err.message);
      }
    }

    async function checkCache(runId) {
      try {
        const response = await api("/api/history/cache-status", { method: "POST", body: JSON.stringify({ run_id: runId }) });
        const data = response.data || response;
        showToast(
          data.can_reexport ? "缓存完整，可重新生成" : `缓存不完整：${(data.missing || []).join(", ")}`,
          data.can_reexport ? "success" : "warning",
        );
      } catch (err) {
        appendClientLog(err.message);
      }
    }

    async function reexport(runId) {
      if (!confirm("确定要从该历史任务的 cache 重新生成报告吗？")) return;
      closeDropdown();
      const item = items.find((row) => row.run_id === runId);
      const topicLabel = item?.super_topic_name || item?.super_topic_id || runId;
      renderJob({
        status: "exporting",
        stage: "export",
        stage_label: "重新生成报告",
        progress: { message: `正在为「${topicLabel}」重新生成导出文件…` },
        subtasks: [
          { id: "export", label: "生成导出文件", status: "active", percent: 50 },
        ],
      });
      try {
        const response = await api("/api/history/reexport", {
          method: "POST",
          body: JSON.stringify({ run_id: runId, export_types: selectedExportTypes() }),
        });
        const data = response.data || response;
        renderJob({
          status: "completed",
          stage: "export",
          stage_label: "重新生成完成",
          progress: { message: data.message || "重新生成完成" },
          subtasks: [
            { id: "export", label: "生成导出文件", status: "done", percent: 100 },
          ],
          result: data.result || null,
        });
        showToast(data.message || "重新生成完成");
        await load();
      } catch (err) {
        renderJob({
          status: "failed",
          stage: "export",
          stage_label: "重新生成失败",
          error: err.message,
          progress: { message: err.message },
          subtasks: [
            { id: "export", label: "生成导出文件", status: "failed", percent: 100 },
          ],
        });
        appendClientLog(err.message);
      }
    }

    async function remove(runId) {
      if (!confirm("确定要删除该任务的 output 目录吗？该操作不可撤销。")) return;
      try {
        await api("/api/history/remove", { method: "POST", body: JSON.stringify({ run_id: runId, delete_files: true, confirm: true }) });
        showToast("已删除");
        await load();
      } catch (err) {
        appendClientLog(err.message);
      }
    }

    function showDetail(item) {
      if (!item || !ui.historyDetailOverlay) return;
      currentDetailItem = item;
      ui.historyDetailMeta.textContent = item.run_id || "";
      ui.historyDetailContent.innerHTML = `
        <div class="detail-grid">
          ${detailRow("创建时间", item.created_at)}
          ${detailRow("更新时间", item.updated_at)}
          ${detailRow("超话", item.super_topic_name || item.super_topic_id || item.super_topic)}
          ${detailRow("时间范围", `${item.window_start || ""} - ${item.window_end || ""}`)}
          ${detailRow("输出目录", item.report_dir)}
          ${detailRow("状态", item.status)}
          ${detailRow("可重新生成", item.can_reexport ? "是" : "否")}
          ${detailRow("重新生成次数", item.reexport_count || 0)}
          ${detailRow("上次重新生成", item.last_reexport_at || "无")}
          ${detailRow("警告数量", item.warnings_count || 0)}
          ${detailRow("失败图片", item.failed_images_count || 0)}
        </div>`;
      ui.historyDetailOverlay.classList.add("visible");
      ui.historyDetailOverlay.setAttribute("aria-hidden", "false");
    }

    function closeDetail() {
      ui.historyDetailOverlay?.classList.remove("visible");
      ui.historyDetailOverlay?.setAttribute("aria-hidden", "true");
      currentDetailItem = null;
    }

    async function showPreview() {
      if (!currentDetailItem) return;
      if (!ui.historyPreviewOverlay || !ui.historyPreviewContent) return;
      ui.historyPreviewContent.innerHTML = `<div class="empty-state loading">正在加载 Markdown 预览...</div>`;
      if (ui.historyPreviewPath) ui.historyPreviewPath.textContent = "";
      ui.historyPreviewOverlay.classList.add("visible");
      ui.historyPreviewOverlay.setAttribute("aria-hidden", "false");
      try {
        const response = await api("/api/history/preview", {
          method: "POST",
          body: JSON.stringify({ run_id: currentDetailItem.run_id }),
        });
        const data = response.data || response;
        const markdown = data.markdown || "";
        if (ui.historyPreviewPath) ui.historyPreviewPath.textContent = data.path || "";
        if (!markdown.trim()) {
          ui.historyPreviewContent.innerHTML = `<div class="empty-state">暂无可预览内容</div>`;
          return;
        }
        if (typeof window.markdownit !== "function") {
          ui.historyPreviewContent.innerHTML = `<div class="empty-state error">Markdown 渲染器未加载</div>`;
          return;
        }
        const md = window.markdownit({ html: false, linkify: true, breaks: true });
        ui.historyPreviewContent.innerHTML = md.render(markdown);
        ui.historyPreviewContent.querySelectorAll("img").forEach((img) => {
          const src = img.getAttribute("src");
          if (src && !src.startsWith("http") && !src.startsWith("//") && !src.startsWith("/api/")) {
            img.src = `/api/history/asset?run_id=${encodeURIComponent(currentDetailItem.run_id)}&path=${encodeURIComponent(src)}`;
          }
        });
      } catch (err) {
        ui.historyPreviewContent.innerHTML = `<div class="empty-state error">预览失败：${escapeHtml(err.message || "未知错误")}</div>`;
      }
    }

    function closePreview() {
      ui.historyPreviewOverlay?.classList.remove("visible");
      ui.historyPreviewOverlay?.setAttribute("aria-hidden", "true");
    }

    function detailRow(label, value) {
      return `<div class="detail-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "")}</strong></div>`;
    }

    function selectedExportTypes() {
      return Array.from(document.querySelectorAll("input[name='reexportType']:checked")).map((item) => item.value);
    }

    function fileLabel(key) {
      return { markdown: "MD", docx: "DOCX", excel: "XLSX", csv: "CSV", summary: "summary", images: "images" }[key] || key;
    }

    return { load, scan, render, handleClick, closeDetail, showPreview, closePreview, toggleDropdown, openDropdown, closeDropdown, handleDocumentClick };
  },
};
