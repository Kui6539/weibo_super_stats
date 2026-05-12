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
    presetController,
    historyController,
    outputCleanupController,
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

    controls.presetSelect?.addEventListener("change", () => presetController.activate());
    controls.presetNew?.addEventListener("click", () => presetController.createNew());
    controls.presetSave?.addEventListener("click", () => presetController.saveCurrent());
    controls.presetDuplicate?.addEventListener("click", () => presetController.duplicate());
    controls.presetRename?.addEventListener("click", () => presetController.rename());
    controls.presetDelete?.addEventListener("click", () => presetController.remove());

    controls.cookieExpand.addEventListener("click", () => cookieController.expandEditor());
    controls.cookieCollapse.addEventListener("click", () => cookieController.collapseEditor());
    controls.cookieBrowserEdge?.addEventListener("click", () => cookieController.setBrowser("edge"));
    controls.cookieBrowserChrome?.addEventListener("click", () => cookieController.setBrowser("chrome"));
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

    controls.historySearch?.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleCleanupDropdown(false);
      historyController.openDropdown();
    });
    controls.historySearch?.addEventListener("focus", () => {
      toggleCleanupDropdown(false);
      historyController.openDropdown();
    });
    controls.historyRefresh?.addEventListener("click", () => historyController.load());
    controls.historyScan?.addEventListener("click", () => historyController.scan());
    controls.historySearch?.addEventListener("input", () => {
      historyController.openDropdown();
      historyController.render();
    });
    controls.historyFilter?.addEventListener("change", () => historyController.render());
    ui.historyList?.addEventListener("click", (event) => historyController.handleClick(event));
    controls.historyDetailClose?.addEventListener("click", () => historyController.closeDetail());
    controls.historyDetailPreview?.addEventListener("click", () => historyController.showPreview());
    controls.historyPreviewClose?.addEventListener("click", () => historyController.closePreview());
    ui.historyDetailOverlay?.addEventListener("click", (event) => {
      if (event.target === ui.historyDetailOverlay) historyController.closeDetail();
    });
    ui.historyPreviewOverlay?.addEventListener("click", (event) => {
      if (event.target === ui.historyPreviewOverlay) historyController.closePreview();
    });

    function toggleCleanupDropdown(force) {
      const dropdown = ui.cleanupDropdown;
      if (!dropdown) return;
      const shouldOpen = typeof force === "boolean" ? force : !dropdown.classList.contains("open");
      dropdown.classList.toggle("open", shouldOpen);
      dropdown.setAttribute("aria-hidden", shouldOpen ? "false" : "true");
      controls.cleanupToggle?.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
      if (ui.historyBackdrop) {
        const topbar = ui.historyTopbar?.closest(".topbar");
        if (topbar) {
          ui.historyBackdrop.style.top = topbar.getBoundingClientRect().bottom + "px";
        }
        ui.historyBackdrop.classList.toggle("visible", shouldOpen);
      }
      document.body.style.overflow = shouldOpen ? "hidden" : "";
    }
    controls.cleanupToggle?.addEventListener("click", (event) => {
      event.stopPropagation();
      historyController.closeDropdown();
      toggleCleanupDropdown();
    });

    controls.cleanupSummary?.addEventListener("click", () => outputCleanupController.loadSummary());
    controls.cleanupPreview?.addEventListener("click", () => outputCleanupController.preview());
    controls.cleanupRun?.addEventListener("click", () => outputCleanupController.run());
    [
      controls.cleanupKeepRecent,
      controls.cleanupOlderThan,
      controls.cleanupIncompleteOnly,
      controls.cleanupIncludeWarnings,
      controls.cleanupIncludeFailed,
    ].forEach((control) => {
      control?.addEventListener("input", () => outputCleanupController.resetPreview());
      control?.addEventListener("change", () => outputCleanupController.resetPreview());
    });

    controls.preview.addEventListener("click", () => {
      if (ui.previewPanel.getAttribute("aria-hidden") === "true") {
        previewController.load();
      } else {
        previewController.hide();
      }
    });
    document.addEventListener("click", (event) => {
      historyController.handleDocumentClick(event);
      if (ui.cleanupDropdown?.classList.contains("open")) {
        if (!controls.cleanupToggle?.contains(event.target) && !ui.cleanupDropdown?.contains(event.target)) {
          toggleCleanupDropdown(false);
        }
      }
    });
    ui.historyBackdrop?.addEventListener("click", () => {
      historyController.closeDropdown();
      toggleCleanupDropdown(false);
    });
    controls.refreshPreview.addEventListener("click", () => previewController.load({ force: true }));
    controls.copyMarkdown.addEventListener("click", previewController.copy);

    controls.logSearch.addEventListener("input", () => logsController.render(taskController.getCurrentJob()));
    controls.logLevelFilter.addEventListener("change", () => logsController.render(taskController.getCurrentJob()));
    controls.copyLog.addEventListener("click", () => logsController.copyVisible());
    controls.downloadLog.addEventListener("click", () => logsController.downloadVisible());
    controls.clearLogView.addEventListener("click", () => logsController.clearView());
    controls.logBottom.addEventListener("click", () => logsController.scrollToBottom());
    controls.logBubble.addEventListener("click", () => logsController.handleBubbleClick());
    controls.logBubble.addEventListener("pointerdown", (event) => logsController.startBubbleDrag(event));
    controls.logPanelHide.addEventListener("click", () => logsController.hidePanel());
    ui.logDragHandle.addEventListener("pointerdown", (event) => logsController.startPanelDrag(event));

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
      if (event.key === "Escape" && ui.historyPreviewOverlay?.classList.contains("visible")) {
        historyController.closePreview();
        return;
      }
      if (event.key === "Escape" && ui.preflightOverlay.classList.contains("visible")) {
        preflightController.closeModal();
      }
      if (event.key === "Escape") {
        historyController.closeDropdown();
        toggleCleanupDropdown(false);
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
      fields.likesWeight,
      fields.commentWeight,
      fields.authorReplyWeight,
      fields.repostWeight,
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

    logsController.initFloating();
  },
};
