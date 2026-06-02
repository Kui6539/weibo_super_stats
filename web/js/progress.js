window.WeiboProgress = {
  createController({ ui, fields, getSelectedCount }) {
    const AUTO_COLLAPSE_DELAY = 2000;
    const STAGE_LABELS = {
      init: "初始化任务",
      crawl: "抓取帖子",
      hydrate: "正文补全",
      score: "评论分析与评分",
      thumbnails: "下载预选帖缩略图",
      selection: "人工筛选",
      images: "图片下载",
      export: "导出文件",
      completed: "完成",
    };
    let progressCollapsed = false;
    let collapseTimer = null;
    let heightAnimationTimer = null;
    let renderedJobId = "";
    let userToggled = false;
    let lastRenderedJob = null;
    let deferNextReveal = false;
    let deferredRevealJobId = "";

    initToggle();

    function statusText(status) {
      return (
        {
          running: "抓取中",
          awaiting_selection: "等待筛选",
          exporting: "导出中",
          completed: "已完成",
          failed: "失败",
          cancelled: "已取消",
        }[status] || "未开始"
      );
    }

    function updateStatus(job) {
      const status = job?.status || "";
      ui.statusPill.className = `status-pill ${status}`;
      ui.statusPill.textContent = statusText(status);
      ui.jobMeta.textContent = job
        ? `${job.stage_label || statusText(status)} / ${job.progress?.message || job.updated_at || ""}`
        : "等待启动";
    }

    function render(job) {
      syncCollapseState(job);
      const allSteps = buildSteps(job);
      const steps = progressCollapsed ? compactSteps(allSteps) : allSteps;
      renderStepsWithHeightTransition(steps);
    }

    function renderStepsWithHeightTransition(steps) {
      const box = ui.logBox;
      const beforeHeight = box.getBoundingClientRect().height;
      const shouldAnimate = beforeHeight > 0;
      if (shouldAnimate) {
        prepareHeightAnimation(beforeHeight);
      }
      renderStepNodes(steps);
      updateCollapsedUi();
      if (!shouldAnimate) {
        return;
      }
      const afterHeight = measureStackContentHeight();
      if (Math.abs(afterHeight - beforeHeight) < 2) {
        finishHeightAnimation();
        return;
      }
      requestAnimationFrame(() => {
        box.style.height = `${afterHeight}px`;
      });
      window.clearTimeout(heightAnimationTimer);
      heightAnimationTimer = window.setTimeout(finishHeightAnimation, 380);
    }

    function renderStepNodes(steps) {
      const existing = new Map(
        Array.from(ui.logBox.querySelectorAll("[data-step-id]")).map((node) => [node.dataset.stepId, node]),
      );
      const visibleIds = new Set(steps.map((step) => step.id));

      ui.logBox.querySelectorAll("[data-step-id]").forEach((node) => {
        if (!visibleIds.has(node.dataset.stepId)) {
          node.remove();
        }
      });

      let prevNode = null;
      steps.forEach((step) => {
        let node = existing.get(step.id);
        if (node) {
          updateItem(node, step, false);
        } else {
          node = createItem(step);
          updateItem(node, step, true);
        }
        const expectedNext = prevNode ? prevNode.nextSibling : ui.logBox.firstChild;
        if (node !== expectedNext) {
          ui.logBox.insertBefore(node, expectedNext);
        }
        prevNode = node;
      });
    }

    function prepareHeightAnimation(height) {
      window.clearTimeout(heightAnimationTimer);
      const box = ui.logBox;
      box.classList.add("height-animating");
      box.style.height = `${height}px`;
      box.style.overflow = "hidden";
      void box.offsetHeight;
    }

    function finishHeightAnimation() {
      window.clearTimeout(heightAnimationTimer);
      heightAnimationTimer = null;
      const box = ui.logBox;
      box.classList.remove("height-animating");
      box.style.height = "";
      box.style.overflow = "";
    }

    function measureStackContentHeight() {
      const box = ui.logBox;
      const lockedHeight = box.style.height;
      const lockedOverflow = box.style.overflow;
      box.style.height = "";
      box.style.overflow = "";
      const height = box.getBoundingClientRect().height;
      box.style.height = lockedHeight;
      box.style.overflow = lockedOverflow;
      void box.offsetHeight;
      return height;
    }

    function initToggle() {
      if (!ui.progressToggle) return;
      ui.progressToggle.addEventListener("click", (event) => {
        event.stopPropagation();
        userToggled = true;
        setCollapsed(!progressCollapsed, { updateUi: false });
        if (lastRenderedJob) render(lastRenderedJob);
      });
      ui.logBox?.addEventListener("click", () => {
        if (!progressCollapsed || !lastRenderedJob) return;
        userToggled = true;
        setCollapsed(false, { updateUi: false });
        render(lastRenderedJob);
      });
    }

    function syncCollapseState(job) {
      lastRenderedJob = job || null;
      const jobId = String(job?.id || "");
      if (!job) {
        renderedJobId = "";
        userToggled = false;
        deferredRevealJobId = "";
        setCollapsed(false, { schedule: false, updateUi: false });
        clearCollapseTimer();
        return;
      }
      if (jobId && jobId !== renderedJobId) {
        renderedJobId = jobId;
        userToggled = false;
        if (deferNextReveal && isActiveJob(job)) {
          deferNextReveal = false;
          deferredRevealJobId = jobId;
          setCollapsed(true, { schedule: false, updateUi: false });
          clearCollapseTimer();
          return;
        }
        deferredRevealJobId = "";
        setCollapsed(false, { schedule: false, updateUi: false });
        scheduleAutoCollapse(job);
        return;
      }
      if (!isActiveJob(job)) {
        deferredRevealJobId = "";
        clearCollapseTimer();
        return;
      }
      if (deferredRevealJobId === jobId) {
        if (userToggled) {
          deferredRevealJobId = "";
        } else {
          clearCollapseTimer();
          return;
        }
      }
      if (!progressCollapsed && !userToggled && !collapseTimer) {
        scheduleAutoCollapse(job);
      }
    }

    function scheduleAutoCollapse(job) {
      clearCollapseTimer();
      if (!isActiveJob(job)) return;
      collapseTimer = window.setTimeout(() => {
        collapseTimer = null;
        if (!userToggled) {
          setCollapsed(true, { schedule: false, updateUi: false });
          render(job);
        }
      }, AUTO_COLLAPSE_DELAY);
    }

    function clearCollapseTimer() {
      if (collapseTimer) {
        clearTimeout(collapseTimer);
        collapseTimer = null;
      }
    }

    function setCollapsed(collapsed, options = {}) {
      progressCollapsed = Boolean(collapsed);
      if (options.schedule !== false) {
        clearCollapseTimer();
      }
      if (options.updateUi !== false) {
        updateCollapsedUi();
      }
    }

    function deferNextActiveJobReveal() {
      deferNextReveal = true;
      deferredRevealJobId = "";
      userToggled = false;
      clearCollapseTimer();
    }

    function revealCurrentJob() {
      if (!lastRenderedJob) return;
      deferNextReveal = false;
      deferredRevealJobId = "";
      userToggled = false;
      setCollapsed(false, { schedule: false, updateUi: false });
      render(lastRenderedJob);
    }

    function cancelDeferredReveal() {
      deferNextReveal = false;
      deferredRevealJobId = "";
    }

    function updateCollapsedUi() {
      ui.logBox.classList.toggle("compact", progressCollapsed);
      ui.monitorPanel?.classList.toggle("progress-compact", progressCollapsed);
      if (ui.progressToggle) {
        const hasJob = Boolean(lastRenderedJob);
        ui.progressToggle.classList.toggle("hidden", !hasJob);
        ui.progressToggle.disabled = !hasJob;
        ui.progressToggle.textContent = progressCollapsed ? "展开" : "收起";
        ui.progressToggle.setAttribute("aria-expanded", progressCollapsed ? "false" : "true");
      }
    }

    function compactSteps(steps) {
      if (!steps.length) return steps;
      const current = steps.find((step) => ["active", "waiting", "failed", "cancelled"].includes(step.state));
      if (current) return [current];
      return [steps[steps.length - 1]];
    }

    function isActiveJob(job) {
      return ["running", "awaiting_selection", "exporting"].includes(job?.status);
    }

    function buildSteps(job) {
      if (Array.isArray(job?.subtasks) && job.subtasks.length) {
        const currentStage = job.stage || "";
        const progressMessage = job.progress?.message || job.stage_label || "";
        return job.subtasks.map((item, index) => {
          const state = normalizeSubtaskStatus(item.status);
          const isCurrent =
            item.id === currentStage || state === "active" || state === "failed" || state === "cancelled";
          return progressStep(
            item.id || `stage-${index}`,
            item.label || STAGE_LABELS[item.id] || item.id || "任务阶段",
            isCurrent ? progressMessage : subtaskDetailByState(state),
            Number(item.percent || 0),
            state,
            isCurrent && job.progress?.total ? `${job.progress.current || 0}/${job.progress.total}` : `阶段 ${index + 1}/${job.subtasks.length}`,
          );
        });
      }

      const logs = job?.logs || [];
      const messages = logs.map((item) => item.message || "");
      const status = job?.status || "";
      const failed = status === "failed";
      const cancelled = status === "cancelled";
      const completed = status === "completed";
      const selectionReady = status === "awaiting_selection";
      const exporting = status === "exporting";
      const hasStarted = Boolean(job);
      const maxPages = Math.max(1, Number(fields.maxPages.value || 80));
      const latestPage = lastNumber(messages, /抓取第\s+(\d+)\s+页/);
      const latestCrawlDetail =
        lastMatchingMessage(messages, /已连续5页无时间窗口命中帖子/) ||
        lastMatchingMessage(messages, /本页没有帖子数据，停止翻页/) ||
        lastMatchingMessage(messages, /第\s+\d+\s+页读取/) ||
        lastMatchingMessage(messages, /连续无命中页/) ||
        "";
      const textProgress = maxProgress(messages, /正文校正(?:进度)?\s+(\d+)\/(\d+)/);
      const scoreProgress = maxProgress(messages, /评分进度\s+(\d+)\/(\d+)/);
      const thumbnailProgress = maxProgress(messages, /预选帖缩略图\s+(\d+)\/(\d+)/);
      const downloadProgress = maxProgress(messages, /下载图片(?:进度|失败)\s+(\d+)\/(\d+)/);
      const exportSavedCount = [
        "Excel 已保存",
        "CSV 已保存",
        "DOCX 已保存",
        "总 DOCX 已保存",
        "MD 已保存",
        "汇总已保存",
        "微博正文已保存",
        "长图预览已保存",
      ].filter((marker) => messages.some((message) => message.includes(marker))).length;
      const hasCandidates = messages.some((message) => message.includes("等待人工筛选"));
      const hasSelectionDone = messages.some((message) => message.includes("人工筛选完成"));
      const hasThumbnailStart = messages.some((message) =>
        ["开始下载预选帖缩略图", "准备处理预选帖缩略图"].some((marker) => message.includes(marker)),
      );
      const hasThumbnailDone = messages.some((message) =>
        ["预选帖缩略图缓存完成", "预选帖没有图片"].some((marker) => message.includes(marker)),
      );
      const hasImageStart = messages.some((message) => message.includes("正在下载帖子/评论图片"));
      const hasExportFiles = exportSavedCount > 0 || completed;
      const imageDownloadDone =
        Boolean(downloadProgress) && downloadProgress.current >= downloadProgress.total;
      const crawlFinished =
        completed ||
        exporting ||
        selectionReady ||
        hasCandidates ||
        messages.some((message) =>
          [
            "已连续5页无时间窗口命中帖子",
            "已连续5页没有时间窗口内的新增帖子",
            "本页没有帖子数据，停止翻页",
            "补全帖子正文",
            "开始计算评分",
            "自动校准时间权重",
          ].some((marker) => message.includes(marker)),
        );
      const steps = [
        progressStep(
          "init",
          "初始化任务",
          hasStarted ? "配置已读取，任务线程已启动" : "填写参数后开始任务",
          hasStarted ? 100 : 0,
          hasStarted ? "done" : "pending",
          "阶段 1/7",
        ),
      ];

      if (hasStarted) {
        const crawlPercent = crawlFinished ? 100 : clamp((latestPage / maxPages) * 86 + 8, 8, 96);
        steps.push(
          progressStep(
            "crawl",
            "抓取帖子数据",
            latestCrawlDetail || (latestPage ? `正在读取第 ${latestPage} 页，最多 ${maxPages} 页` : "连接超话页面并读取帖子"),
            crawlPercent,
            crawlFinished ? "done" : "active",
            latestPage ? `第 ${latestPage}/${maxPages} 页` : "阶段 2/7",
          ),
        );
      }

      if (latestPage || hasCandidates || selectionReady || exporting || completed) {
        const candidateProgress = candidateStageProgress({
          hasCandidates,
          hasThumbnailStart,
          hasThumbnailDone,
          selectionReady,
          exporting,
          completed,
          textProgress,
          scoreProgress,
          messages,
        });
        steps.push(
          progressStep(
            "candidate",
            "评论分析与评分",
            candidateProgress.detail,
            hasThumbnailStart || hasCandidates || selectionReady || exporting || completed ? 100 : candidateProgress.progress,
            hasThumbnailStart || hasCandidates || selectionReady || exporting || completed ? "done" : "active",
            candidateProgress.meta,
          ),
        );
      }

      if (hasThumbnailStart || hasCandidates || selectionReady || exporting || completed || cancelled) {
        const thumbnailDone = hasThumbnailDone || hasCandidates || selectionReady || exporting || completed;
        steps.push(
          progressStep(
            "thumbnails",
            "下载预选帖缩略图",
            thumbnailProgress
              ? `已处理 ${thumbnailProgress.current}/${thumbnailProgress.total} 张缩略图`
              : thumbnailDone
                ? "预选帖缩略图缓存完成"
                : "正在准备预选帖缩略图缓存",
            thumbnailDone ? 100 : thumbnailProgress ? (thumbnailProgress.current / thumbnailProgress.total) * 100 : 12,
            thumbnailDone ? "done" : "active",
            thumbnailProgress ? `${thumbnailProgress.current}/${thumbnailProgress.total} 张` : "阶段 4/7",
          ),
        );
      }

      if (hasCandidates || selectionReady || exporting || completed || cancelled) {
        steps.push(
          progressStep(
            "selection",
            "人工筛选",
            selectionReady
              ? `请选择 ${job?.required_pick_count || 0} 条入选帖子`
              : hasSelectionDone || exporting || completed
                ? "入选帖子已确认"
                : "等待人工确认",
            hasSelectionDone || exporting || completed ? 100 : selectionReady ? 62 : 0,
            hasSelectionDone || exporting || completed ? "done" : selectionReady ? "waiting" : "pending",
            selectionReady ? `${getSelectedCount(job)}/${job?.required_pick_count || 0} 已选` : "阶段 5/7",
          ),
        );
      }

      if (hasSelectionDone || hasImageStart || downloadProgress || exporting || completed) {
        const percent = completed || hasExportFiles || imageDownloadDone ? 100 : downloadProgress ? (downloadProgress.current / downloadProgress.total) * 100 : 18;
        steps.push(
          progressStep(
            "images",
            "下载图片资源",
            downloadProgress
              ? `已处理 ${downloadProgress.current}/${downloadProgress.total} 个帖子`
              : hasImageStart
                ? "正在下载帖子图片与热评图片"
                : "等待图片下载",
            percent,
            completed || hasExportFiles || imageDownloadDone ? "done" : "active",
            downloadProgress ? `${downloadProgress.current}/${downloadProgress.total} 帖` : "阶段 6/7",
          ),
        );
      }

      if (imageDownloadDone || hasExportFiles || completed) {
        steps.push(
          progressStep(
            "export",
            "生成导出文件",
            completed
              ? "XLSX、CSV、DOCX、Markdown、微博正文、汇总与长图文件已生成"
              : exportSavedCount
                ? `已生成 ${exportSavedCount}/8 类文件`
                : "图片下载完成，正在生成导出文件",
            completed ? 100 : clamp((exportSavedCount / 8) * 100, imageDownloadDone || hasExportFiles ? 20 : 0, 96),
            completed ? "done" : imageDownloadDone || hasExportFiles ? "active" : "pending",
            completed ? "8/8 文件" : `${exportSavedCount}/8 文件`,
          ),
        );
      }

      if (failed) {
        markLastMutableStep(steps, "failed", job?.error || lastMessage(messages) || "任务失败");
      } else if (cancelled) {
        markLastMutableStep(steps, "cancelled", "任务已取消");
      }

      return steps;
    }

    function candidateStageProgress({ hasCandidates, hasThumbnailStart, hasThumbnailDone, selectionReady, exporting, completed, textProgress, scoreProgress, messages }) {
      if (hasThumbnailStart || hasThumbnailDone || hasCandidates || selectionReady || exporting || completed) {
        return { progress: 100, detail: "评分完成，预选帖列表已生成", meta: "阶段 3/7" };
      }
      if (scoreProgress) {
        return {
          progress: clamp(62 + (scoreProgress.current / scoreProgress.total) * 28, 62, 96),
          detail: `正在计算热度评分：${scoreProgress.current}/${scoreProgress.total}`,
          meta: `${scoreProgress.current}/${scoreProgress.total} 评分`,
        };
      }
      if (messages.some((message) => message.includes("开始计算评分"))) {
        return { progress: 62, detail: "正在估算评论结构并计算时间权重", meta: "评分中" };
      }
      if (textProgress) {
        return {
          progress: clamp(28 + (textProgress.current / textProgress.total) * 26, 28, 58),
          detail: `正在补全正文：${textProgress.current}/${textProgress.total}`,
          meta: `${textProgress.current}/${textProgress.total} 正文`,
        };
      }
      if (messages.some((message) => message.includes("补全帖子正文"))) {
        return { progress: 28, detail: "正在补全长文与被截断正文", meta: "正文校正" };
      }
      return { progress: 18, detail: "清洗帖子内容并准备评分", meta: "阶段 3/7" };
    }

    function progressStep(id, title, detail, progress, state, meta = "") {
      return {
        id,
        title,
        detail,
        progress: Math.round(clamp(progress, 0, 100)),
        state,
        meta,
      };
    }

    function createItem() {
      const node = document.createElement("div");
      node.className = "progress-item";
      node.innerHTML = `
    <div class="progress-icon" aria-hidden="true"></div>
    <div class="progress-main">
      <div class="progress-head">
        <div class="progress-copy">
          <span class="progress-title"></span>
          <span class="progress-meta"></span>
        </div>
        <div class="progress-stats">
          <span class="progress-state"></span>
          <span class="progress-percent"></span>
        </div>
      </div>
      <div class="progress-detail"></div>
      <div class="progress-track"><div class="progress-fill"></div></div>
    </div>`;
      return node;
    }

    function updateItem(node, step, isNew = false) {
      node.className = `progress-item ${step.state}`;
      node.dataset.stepId = step.id;
      node.setAttribute("aria-label", `${step.title}，${stateLabel(step.state)}，${step.progress}%`);
      node.querySelector(".progress-title").textContent = step.title;
      node.querySelector(".progress-meta").textContent = step.meta || "";
      node.querySelector(".progress-detail").textContent = step.detail || "";
      node.querySelector(".progress-state").textContent = stateLabel(step.state);
      node.querySelector(".progress-percent").textContent = step.state === "waiting" ? "待确认" : `${step.progress}%`;
      const fill = node.querySelector(".progress-fill");
      if (isNew) {
        fill.style.width = "0%";
        requestAnimationFrame(() => {
          fill.style.width = `${step.progress}%`;
        });
      } else {
        fill.style.width = `${step.progress}%`;
      }
    }

    function stateLabel(state) {
      return (
        {
          active: "进行中",
          waiting: "待确认",
          done: "已完成",
          failed: "失败",
          cancelled: "已取消",
          pending: "排队中",
        }[state] || "排队中"
      );
    }

    function normalizeSubtaskStatus(status) {
      if (["pending", "active", "done", "failed", "cancelled", "waiting"].includes(status)) {
        return status;
      }
      return "pending";
    }

    function subtaskDetailByState(state) {
      return (
        {
          pending: "等待前置阶段完成",
          active: "正在处理",
          done: "阶段已完成",
          failed: "阶段失败",
          cancelled: "任务已取消",
          waiting: "等待人工确认",
        }[state] || ""
      );
    }

    function markLastMutableStep(steps, state, detail) {
      const step = [...steps].reverse().find((item) => item.state !== "done") || steps[steps.length - 1];
      if (!step) return;
      step.state = state;
      step.detail = detail;
      step.progress = state === "failed" ? Math.max(step.progress, 6) : step.progress;
    }

    function lastNumber(messages, regex) {
      let value = 0;
      for (const message of messages) {
        const match = regex.exec(message);
        if (match) value = Number(match[1] || 0);
      }
      return value;
    }

    function maxProgress(messages, regex) {
      let value = null;
      for (const message of messages) {
        const match = regex.exec(message);
        if (match) {
          const next = {
            current: Number(match[1] || 0),
            total: Math.max(1, Number(match[2] || 1)),
          };
          if (!value || next.current / next.total >= value.current / value.total) {
            value = next;
          }
        }
      }
      return value;
    }

    function lastMatchingMessage(messages, regex) {
      let value = "";
      for (const message of messages) {
        if (regex.test(message)) value = message;
      }
      return value;
    }

    function lastMessage(messages) {
      return messages.length ? messages[messages.length - 1] : "";
    }

    function clamp(value, min, max) {
      return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
    }

    return {
      statusText,
      stageName: (stage) => STAGE_LABELS[stage] || stage,
      updateStatus,
      render,
      deferNextActiveJobReveal,
      revealCurrentJob,
      cancelDeferredReveal,
    };
  },
};
