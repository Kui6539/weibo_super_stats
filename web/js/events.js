window.WeiboEvents = {
  bind({
    fields,
    controls,
    ui,
    taskController,
    formController,
    cookieController,
    candidatesController,
    cacheController,
    previewController,
    logsController,
    preflightController,
    helpController,
    configController,
  }) {
    controls.help.addEventListener("click", () => helpController.load());
    controls.start.addEventListener("click", () => taskController.startJob());
    controls.cancelJob.addEventListener("click", () => taskController.cancelJob());
    controls.advancedMode.addEventListener("change", () => {
      formController.setAdvancedMode(controls.advancedMode.checked);
      configController.scheduleSave();
    });

    controls.cookieExpand.addEventListener("click", () => cookieController.expandEditor());
    controls.cookieCollapse.addEventListener("click", () => cookieController.collapseEditor());
    controls.edgeDebug.addEventListener("click", () => cookieController.launchEdgeDebug());
    controls.autoCookie.addEventListener("click", () => cookieController.autoCookie());
    controls.clipboard.addEventListener("click", () => cookieController.readClipboard());
    controls.extractCookie.addEventListener("click", () => cookieController.extractCookie());
    controls.checkCookie.addEventListener("click", () => cookieController.checkCookie());
    controls.clearCookie.addEventListener("click", () => cookieController.clearCookie());

    controls.select.addEventListener("click", () => taskController.submitSelection());
    controls.cancelSelect.addEventListener("click", () => taskController.cancelSelection());
    controls.candidateFilter.addEventListener("change", () =>
      candidatesController.render(taskController.getCurrentJob()),
    );
    controls.candidateSort.addEventListener("change", () =>
      candidatesController.render(taskController.getCurrentJob()),
    );
    ui.candidateList.addEventListener("change", (event) => candidatesController.handleChange(event));
    ui.candidateList.addEventListener("click", (event) => candidatesController.handleClick(event));

    controls.openResultDir.addEventListener("click", () => cacheController.openResultDir());
    controls.checkCache.addEventListener("click", () => cacheController.checkCacheStatus());
    controls.reexport.addEventListener("click", () => cacheController.reexportReport());
    ui.reexportRunDir.addEventListener("input", () => cacheController.resetCacheStatus());
    ui.resultList.addEventListener("click", (event) => cacheController.handleResultClick(event));

    controls.preview.addEventListener("click", () => {
      if (ui.previewPanel.getAttribute("aria-hidden") === "true") {
        previewController.load();
      } else {
        previewController.hide();
      }
    });
    controls.refreshPreview.addEventListener("click", () => previewController.load({ force: true }));
    controls.copyMarkdown.addEventListener("click", previewController.copy);

    controls.logSearch.addEventListener("input", () => logsController.render(taskController.getCurrentJob()));
    controls.logLevelFilter.addEventListener("change", () => logsController.render(taskController.getCurrentJob()));
    controls.copyLog.addEventListener("click", () => logsController.copyVisible());
    controls.downloadLog.addEventListener("click", () => logsController.downloadVisible());
    controls.clearLogView.addEventListener("click", () => logsController.clearView());
    controls.logBottom.addEventListener("click", () => logsController.scrollToBottom());

    controls.preflightClose.addEventListener("click", () => preflightController.closeModal());
    controls.preflightCancel.addEventListener("click", () => preflightController.closeModal());
    controls.preflightProceed.addEventListener("click", () => {
      const payload = preflightController.pendingPayload();
      if (!payload || controls.preflightProceed.disabled) return;
      preflightController.closeModal();
      taskController.startJobAfterPreflight(payload);
    });
    ui.preflightPanel.addEventListener("click", () => {
      if (!ui.preflightPanel.classList.contains("collapsed")) return;
      preflightController.setCollapsed(false);
    });
    controls.preflightToggle?.addEventListener("click", (event) => {
      event.stopPropagation();
      preflightController.setCollapsed(!ui.preflightPanel.classList.contains("collapsed"));
    });
    ui.preflightOverlay.addEventListener("click", (event) => {
      if (event.target === ui.preflightOverlay) {
        preflightController.closeModal();
      }
    });

    ui.helpClose.addEventListener("click", () => helpController.close());
    ui.helpOverlay.addEventListener("click", (event) => helpController.handleOverlayClick(event));
    ui.helpDragHandle.addEventListener("pointerdown", (event) => helpController.startDrag(event));

    window.addEventListener("keydown", (event) => {
      helpController.handleEscape(event);
      if (event.key === "Escape" && ui.preflightOverlay.classList.contains("visible")) {
        preflightController.closeModal();
      }
    });
    document.addEventListener("visibilitychange", () => taskController.handleVisibilityChange());

    [
      fields.superTopic,
      fields.cookie,
      fields.windowStart,
      fields.windowEnd,
      fields.maxPages,
      fields.topicCommentFactor,
      fields.pauseSeconds,
      fields.outputDir,
    ].forEach((field) => {
      field.addEventListener("input", () => {
        if (field === fields.cookie) {
          cookieController.setValidationState("unverified");
          cookieController.updateSummary();
        }
        preflightController.resetInline();
        configController.scheduleSave();
      });
    });
  },
};
