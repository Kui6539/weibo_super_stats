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

      // No subtasks means no server-side job: history reexport renders a
      // synthetic snapshot and a freshly loaded page has nothing yet. This was
      // ~185 lines that re-derived the whole stage list by running regexes
      // over Chinese log text -- a second copy of the parser the backend has
      // now replaced with structured events, and one that drifted silently
      // whenever a message was reworded.
      const status = job?.status || "";
      if (!job) {
        return [progressStep("idle", "任务进度", "填写参数后开始任务", 0, "pending", "未开始")];
      }
      const state =
        status === "completed"
          ? "done"
          : status === "failed"
            ? "failed"
            : status === "cancelled"
              ? "cancelled"
              : "active";
      const detail = job.progress?.message || job.stage_label || "任务进行中";
      const counter = job.progress?.total ? `${job.progress.current || 0}/${job.progress.total}` : "";
      return [
        progressStep(
          job.stage || "task",
          job.stage_label || "任务进度",
          detail,
          Number(job.progress?.percent || 0),
          state,
          counter,
        ),
      ];
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
