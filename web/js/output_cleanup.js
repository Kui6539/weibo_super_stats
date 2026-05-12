window.WeiboOutputCleanup = {
  createController({ ui, controls, api, setBusy, escapeHtml, showToast, appendClientLog }) {
    let lastPreview = null;
    let lastRules = null;

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
        renderPreview(lastPreview);
        controls.cleanupRun.disabled = !(lastPreview.delete_count > 0);
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.cleanupPreview, false);
      }
    }

    async function run() {
      if (!lastPreview || !(lastPreview.delete_count > 0)) return;
      if (!confirm(`确认删除 ${lastPreview.delete_count} 个 output 运行目录吗？该操作不可撤销。`)) return;
      setBusy(controls.cleanupRun, true, "清理中");
      try {
        const response = await api("/api/output/cleanup", {
          method: "POST",
          body: JSON.stringify({ ...(lastRules || rules()), confirm: true }),
        });
        const data = response.data || response;
        showToast(data.message || "清理完成");
        renderPreview(data);
        await loadSummary();
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.cleanupRun, false);
        controls.cleanupRun.disabled = true;
      }
    }

    function renderPreview(data) {
      if (!ui.cleanupPreviewBox) return;
      const items = data.items || [];
      ui.cleanupPreviewBox.innerHTML = `
        <div class="cleanup-total">将删除 ${Number(data.delete_count || 0)} 个目录，约 ${Number(data.total_size_mb || 0)} MB</div>
        ${items.length ? items.map(renderItem).join("") : "<div>没有符合规则的目录。</div>"}`;
    }

    function renderItem(item) {
      const cacheTag = item.can_reexport ? "" : `<em class="incomplete">缓存不完整</em>`;
      return `<div class="cleanup-row"><span>${escapeHtml(item.run_id || "")}</span><strong>${escapeHtml(item.size_mb || 0)} MB</strong><em>${escapeHtml(item.status || "")}</em>${cacheTag}</div>`;
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
      if (controls.cleanupRun) controls.cleanupRun.disabled = true;
      if (ui.cleanupPreviewBox) {
        ui.cleanupPreviewBox.textContent = "清理规则已修改，请重新生成预览";
      }
    }

    return { loadSummary, preview, run, resetPreview };
  },
};
