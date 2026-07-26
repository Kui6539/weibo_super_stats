window.WeiboTask = {
  createController({
    controls,
    api,
    setBusy,
    readForm,
    saveConfigNow,
    renderPreflightInline,
    showPreflightModal,
    showToast,
    appendClientLog,
    progressController,
    logsController,
    candidatesController,
    cacheController,
    previewController,
    historyController,
    outputCleanupController,
  }) {
    let pollTimer = null;
    let pollFailures = 0;
    let currentRenderedJob = null;
    let lastRenderKey = null;
    let cancelledToastJobId = null;

    let lastJobActive = false;

    // Identifies a snapshot's rendered state. Polling returns the same
    // snapshot most of the time, and re-rendering it rebuilt up to 300 log
    // rows and 20 candidate cards every second -- destroying the user's text
    // selection and keyboard focus along the way.
    function renderKey(job) {
      if (!job) return "none";
      return [
        job.id,
        job.status,
        job.stage,
        job.updated_at,
        job.events?.length ?? 0,
        job.logs?.length ?? 0,
        job.progress?.percent ?? "",
        job.cancel_requested ? 1 : 0,
      ].join("|");
    }

    function renderJob(job, options = {}) {
      const previousJob = currentRenderedJob;
      const key = renderKey(job);
      const unchanged = key === lastRenderKey && !options.force;
      currentRenderedJob = job;
      lastRenderKey = key;
      if (!unchanged) {
        progressController.updateStatus(job);
        progressController.render(job);
        logsController.render(job);
        candidatesController.render(job);
        cacheController.renderResult(job);
      }
      if (job?.status !== "cancelled") {
        cancelledToastJobId = null;
      }

      const active = ["running", "awaiting_selection", "exporting"].includes(job?.status);
      controls.start.disabled = active;
      controls.cancelJob.classList.toggle("hidden", !active);
      controls.cancelJob.disabled =
        !active ||
        job?.status === "exporting" ||
        Boolean(job?.cancel_requested) ||
        Boolean(controls.cancelJob.dataset.busyText);
      if (!active && pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }
      if (job?.status === "cancelled" && previousJob?.id === job.id && previousJob?.status !== "cancelled") {
        notifyCancelled(job);
      }
      if (lastJobActive && !active) {
        historyController?.load();
        outputCleanupController?.loadSummary();
      }
      lastJobActive = active;
    }

    async function refreshStatus() {
      try {
        const data = await api("/api/status");
        pollFailures = 0;
        const job = data.data?.job ?? data.job;
        renderJob(job);
        scheduleNextPoll(job);
      } catch (err) {
        pollFailures += 1;
        appendClientLog(`状态刷新失败：${err.message}`);
        scheduleNextPoll(currentRenderedJob);
      }
    }

    function notifyCancelled(job) {
      if (!job?.id || cancelledToastJobId === job.id) return;
      cancelledToastJobId = job.id;
      const cleanup = job.cancel_cleanup || {};
      const deletedCount = Array.isArray(cleanup.deleted_dirs) ? cleanup.deleted_dirs.length : 0;
      showToast(deletedCount ? `任务已取消，已清理 ${deletedCount} 个目录。` : "任务已取消。", "info");
    }

    function startPolling() {
      scheduleNextPoll(currentRenderedJob, 0);
    }

    function scheduleNextPoll(job, overrideDelay = null) {
      if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }
      if (!isActive(job)) {
        return;
      }
      const delay = overrideDelay ?? nextPollDelay(job);
      pollTimer = window.setTimeout(refreshStatus, delay);
    }

    function nextPollDelay(job) {
      if (pollFailures === 1) return 2000;
      if (pollFailures === 2) return 5000;
      if (pollFailures >= 3) return 10000;
      if (document.hidden) return 5000;
      if (job?.status === "awaiting_selection") return 2500;
      return 1000;
    }

    async function startJob() {
      setBusy(controls.start, true, "正在检查");
      try {
        await saveConfigNow();
        const payload = readForm();
        const response = await api("/api/preflight", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        const preflight = response.data || response;
        const preflightCollapse = renderPreflightInline(preflight);
        const hasError = preflight.checks?.some((item) => item.status === "error");
        const hasWarning = preflight.checks?.some((item) => item.status === "warning");
        if (hasError || hasWarning) {
          showPreflightModal(preflight, !hasError, payload);
          return;
        }
        showToast("预检查通过，开始任务。");
        setBusy(controls.start, false);
        await startJobAfterPreflight(payload, { revealAfter: preflightCollapse });
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        if (!isActive(currentRenderedJob)) {
          setBusy(controls.start, false);
        } else {
          controls.start.disabled = true;
        }
      }
    }

    async function startJobAfterPreflight(payload = readForm(), options = {}) {
      const revealAfter = options.revealAfter;
      const shouldSequenceProgress = Boolean(revealAfter?.then);
      if (shouldSequenceProgress) {
        progressController.deferNextActiveJobReveal();
      }
      setBusy(controls.start, true, "正在启动");
      try {
        const data = await api("/api/start", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        const job = data.data?.job ?? data.job;
        candidatesController.reset();
        cacheController.resetPreviewCache();
        previewController.reset();
        renderJob(job);
        if (shouldSequenceProgress) {
          revealAfter.then(
            () => progressController.revealCurrentJob(),
            () => progressController.revealCurrentJob(),
          );
        }
        startPolling();
      } catch (err) {
        if (shouldSequenceProgress) {
          progressController.cancelDeferredReveal();
        }
        appendClientLog(err.message);
      } finally {
        setBusy(controls.start, false);
        if (isActive(currentRenderedJob)) {
          controls.start.disabled = true;
        }
        refreshStatus();
      }
    }

    async function submitSelection() {
      if (controls.select.disabled) return;
      setBusy(controls.select, true, "正在提交");
      try {
        const data = await api("/api/select", {
          method: "POST",
          body: JSON.stringify({ indexes: candidatesController.selectedIndexes() }),
        });
        renderJob(data.data?.job ?? data.job);
        startPolling();
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.select, false);
        candidatesController.render(currentRenderedJob);
      }
    }

    async function cancelSelection() {
      setBusy(controls.cancelSelect, true, "正在取消");
      try {
        const data = await api("/api/cancel-selection", {
          method: "POST",
          body: "{}",
        });
        renderJob(data.data?.job ?? data.job);
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.cancelSelect, false);
      }
    }

    async function cancelJob() {
      const confirmed = window.confirm("确定要取消当前任务吗？未完成的任务目录和对应缓存会自动删除，已完成的历史任务不会受影响。");
      if (!confirmed) return;
      setBusy(controls.cancelJob, true, "正在取消");
      showToast("正在取消，请等待当前请求结束……", "warning");
      try {
        const data = await api("/api/cancel-job", { method: "POST", body: "{}" });
        const job = data.data?.job ?? data.job;
        renderJob(job);
        startPolling();
        if (job?.status === "cancelled") {
          notifyCancelled(job);
        } else {
          window.setTimeout(refreshStatus, 800);
        }
      } catch (err) {
        appendClientLog(err.message);
      } finally {
        setBusy(controls.cancelJob, false);
        if (isActive(currentRenderedJob) && !currentRenderedJob?.cancel_requested && currentRenderedJob?.status !== "exporting") {
          controls.cancelJob.disabled = false;
        }
      }
    }

    function handleVisibilityChange() {
      if (isActive(currentRenderedJob)) {
        scheduleNextPoll(currentRenderedJob);
      }
    }

    function isActive(job) {
      // History reexport renders a synthetic job to reuse this panel. It has
      // no server-side counterpart, so polling on its behalf would fetch
      // job=null and wipe the progress the user is watching.
      if (job?.local) return false;
      return ["running", "awaiting_selection", "exporting"].includes(job?.status);
    }

    function getCurrentJob() {
      return currentRenderedJob;
    }

    return {
      renderJob,
      refreshStatus,
      startPolling,
      startJob,
      startJobAfterPreflight,
      submitSelection,
      cancelSelection,
      cancelJob,
      handleVisibilityChange,
      getCurrentJob,
    };
  },
};
