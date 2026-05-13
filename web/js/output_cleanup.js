window.WeiboOutputCleanup = {
  createController({ ui, controls, api, setBusy, escapeHtml, showToast, appendClientLog }) {
    let lastPreview = null;
    let lastRules = null;
    let selectedRunIds = new Set();

    async function loadSummary() {
      if (!ui.cleanupSummary) return;
      setBusy(controls.cleanupSummary, true, "扫描中");
      try {
        const response = await api("/api/output/summary", {
          method: "POST",
          body: JSON.stringify({ output_dir: "output" }),
        });
        const data = response.data || response;
        ui.cleanupSummary.textContent = `共 ${data.run_count || 0} 个任务，约 ${data.total_size_mb || 0} MB，可重新生成 ${data.can_reexport_count || 0} 个`;
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.cleanupSummary, false);
      }
    }

    async function preview() {
      setBusy(controls.cleanupPreview, true, "预览中");
      try {
        const nextRules = rules();
        const response = await api("/api/output/cleanup-preview", {
          method: "POST",
          body: JSON.stringify(nextRules),
        });
        lastPreview = response.data || response;
        lastRules = nextRules;
        selectedRunIds = new Set((lastPreview.all_items || lastPreview.items || []).filter((item) => item.selected).map((item) => item.run_id));
        renderPreview(lastPreview);
        updateSelectedSummary();
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.cleanupPreview, false);
      }
    }

    async function run() {
      const count = selectedRunIds.size;
      if (!lastPreview || count <= 0) return;
      if (!confirm(`确认删除 ${count} 个 output 运行目录吗？该操作不可撤销。`)) return;
      setBusy(controls.cleanupRun, true, "清理中");
      try {
        const response = await api("/api/output/cleanup", {
          method: "POST",
          body: JSON.stringify({ ...(lastRules || rules()), confirm: true, selected_run_ids: [...selectedRunIds] }),
        });
        const data = response.data || response;
        showToast(data.message || "清理完成");
        selectedRunIds = new Set((data.all_items || data.items || []).filter((item) => item.selected).map((item) => item.run_id));
        renderPreview(data);
        updateSelectedSummary();
        await loadSummary();
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.cleanupRun, false);
      }
    }

    function renderPreview(data) {
      if (!ui.cleanupPreviewBox) return;
      const items = data.all_items || data.items || [];
      ui.cleanupPreviewBox.innerHTML = `
        <div class="cleanup-total" data-cleanup-total="1">已勾选 ${Number(data.delete_count || 0)} / ${items.length} 个目录，约 ${Number(data.total_size_mb || 0)} MB</div>
        ${items.length ? items.map(renderItem).join("") : "<div>没有符合规则的目录。</div>"}`;
      ui.cleanupPreviewBox.querySelectorAll("[data-cleanup-run-id]").forEach((input) => {
        input.addEventListener("change", () => {
          const runId = input.getAttribute("data-cleanup-run-id") || "";
          if (input.checked) {
            selectedRunIds.add(runId);
          } else {
            selectedRunIds.delete(runId);
          }
          updateSelectedSummary();
        });
      });
    }

    function renderItem(item) {
      const runId = String(item.run_id || "");
      const checked = item.selected ? "checked" : "";
      const cacheTag = item.can_reexport ? `<em>缓存完整</em>` : `<em class="incomplete">缓存不完整</em>`;
      const outputTag = item.output_files_complete ? `<em>文件完整</em>` : `<em class="incomplete">文件不完整</em>`;
      const missing = Array.isArray(item.missing_output_files) && item.missing_output_files.length
        ? `<small>缺失：${escapeHtml(item.missing_output_files.slice(0, 4).join("，"))}${item.missing_output_files.length > 4 ? "…" : ""}</small>`
        : "";
      return `
        <label class="cleanup-row ${item.selected_by_default ? "" : "manual-only"}">
          <input type="checkbox" data-cleanup-run-id="${escapeHtml(runId)}" ${checked} />
          <span>
            <strong>${escapeHtml(runId)}</strong>
            <small>${escapeHtml(item.cleanup_reason || "")}</small>
            ${missing}
          </span>
          <b>${escapeHtml(item.size_mb || 0)} MB</b>
          <em>${escapeHtml(item.status || "")}</em>
          ${cacheTag}
          ${outputTag}
        </label>`;
    }

    function updateSelectedSummary() {
      if (!lastPreview) {
        if (controls.cleanupRun) controls.cleanupRun.disabled = true;
        return;
      }
      const allItems = lastPreview.all_items || lastPreview.items || [];
      const selectedItems = allItems.filter((item) => selectedRunIds.has(item.run_id));
      const totalSize = selectedItems.reduce((sum, item) => sum + Number(item.size || 0), 0);
      if (controls.cleanupRun) controls.cleanupRun.disabled = selectedItems.length <= 0;
      const total = ui.cleanupPreviewBox?.querySelector("[data-cleanup-total]");
      if (total) {
        total.textContent = `已勾选 ${selectedItems.length} / ${allItems.length} 个目录，约 ${(totalSize / 1024 / 1024).toFixed(2)} MB`;
      }
    }

    function rules() {
      const olderText = controls.cleanupOlderThan?.value || "";
      return {
        output_dir: "output",
        older_than_days: olderText === "" ? null : Number(olderText),
        keep_recent: controls.cleanupKeepRecent?.value === "" ? 5 : Number(controls.cleanupKeepRecent?.value || 0),
        incomplete_only: Boolean(controls.cleanupIncompleteOnly?.checked),
        include_warnings: Boolean(controls.cleanupIncludeWarnings?.checked),
        include_failed: Boolean(controls.cleanupIncludeFailed?.checked),
      };
    }

    function resetPreview() {
      lastPreview = null;
      lastRules = null;
      selectedRunIds = new Set();
      if (controls.cleanupRun) controls.cleanupRun.disabled = true;
      if (ui.cleanupPreviewBox) {
        ui.cleanupPreviewBox.textContent = "清理规则已修改，请重新生成预览";
      }
    }

    return { loadSummary, preview, run, resetPreview };
  },
};
