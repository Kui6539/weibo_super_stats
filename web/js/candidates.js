window.WeiboCandidates = {
  createController({ ui, controls, escapeHtml, escapeAttr, getCurrentJob }) {
    let candidateJobId = "";
    let candidateSelections = new Set();
    let candidateExpanded = new Set();

    function render(job) {
      if (job?.status !== "awaiting_selection") {
        ui.layout.classList.remove("has-candidate");
        ui.candidatePanel.setAttribute("aria-hidden", "true");
        return;
      }

      ui.layout.classList.add("has-candidate");
      ui.candidatePanel.setAttribute("aria-hidden", "false");
      const required = requiredPickCount(job);
      const candidates = job.candidates || [];

      if (candidateJobId !== job.id) {
        candidateJobId = job.id;
        candidateSelections = new Set(candidates.slice(0, required).map((item) => Number(item.index)));
        candidateExpanded = new Set();
      }

      const visible = filterAndSort(candidates);
      ui.candidateList.innerHTML = visible.length
        ? visible.map((item) => cardHtml(item)).join("")
        : `<div class="empty-state">没有匹配的候选帖子</div>`;
      updatePickCount(job);
    }

    function reset() {
      candidateJobId = "";
      candidateSelections = new Set();
      candidateExpanded = new Set();
    }

    function requiredPickCount(job) {
      return Number(job?.required_pick_count || 15);
    }

    function filterAndSort(candidates) {
      const filter = controls.candidateFilter.value || "all";
      const sort = controls.candidateSort.value || "score";
      const threshold = highCommentThreshold(candidates);
      return [...candidates]
        .filter((item) => {
          const index = Number(item.index);
          if (filter === "selected") return candidateSelections.has(index);
          if (filter === "unselected") return !candidateSelections.has(index);
          if (filter === "images") return Number(item.image_count || 0) > 0;
          if (filter === "high_comments") return Number(item.comments || 0) >= threshold;
          return true;
        })
        .sort((a, b) => compare(a, b, sort));
    }

    function highCommentThreshold(candidates) {
      const maxComments = Math.max(0, ...candidates.map((item) => Number(item.comments || 0)));
      return Math.max(10, Math.ceil(maxComments * 0.6));
    }

    function compare(a, b, sort) {
      if (sort === "publish_time") {
        const aTime = Date.parse(a.publish_time || "") || 0;
        const bTime = Date.parse(b.publish_time || "") || 0;
        return bTime - aTime;
      }
      return Number(b[sort] || 0) - Number(a[sort] || 0);
    }

    function cardHtml(item) {
      const index = Number(item.index);
      const checked = candidateSelections.has(index);
      const expanded = candidateExpanded.has(index);
      const content = expanded ? item.content_full || item.content || "" : item.content_excerpt || item.content || "";
      const imageCount = Number(item.image_count || 0);
      const previewPaths = Array.isArray(item.image_preview_paths) ? item.image_preview_paths : [];
      const previews = previewPaths
        .map(candidatePreviewUrl)
        .filter(Boolean)
        .map((src) => `<img src="${escapeAttr(src)}" alt="候选图片预览" loading="lazy" />`)
        .join("");
      const postButton = item.post_url
        ? `<a class="candidate-link" href="${escapeAttr(item.post_url)}" target="_blank" rel="noreferrer">原帖链接</a>`
        : `<span class="candidate-link disabled">无原帖链接</span>`;

      return `
    <article class="candidate ${checked ? "selected" : ""}" data-index="${index}">
      <div class="candidate-check">
        <input type="checkbox" value="${index}" ${checked ? "checked" : ""} aria-label="选择第 ${escapeAttr(item.rank)} 条" />
        <span class="mini-badge">${checked ? "已选" : "未选"}</span>
      </div>
      <div class="candidate-body">
        <div class="candidate-title">
          <strong>#${escapeHtml(item.rank)} ${escapeHtml(item.user_name || "未知作者")}</strong>
          <span class="muted">${escapeHtml(item.publish_time || "")}</span>
          <span class="score">综合分 ${escapeHtml(item.score)}</span>
        </div>
        <div class="candidate-metrics">
          <span>赞 ${escapeHtml(item.likes)}</span>
          <span>评 ${escapeHtml(item.comments)}</span>
          <span>转 ${escapeHtml(item.reposts)}</span>
          ${imageCount ? `<span>图片 ${imageCount} 张</span>` : ""}
        </div>
        <div class="candidate-content ${expanded ? "expanded" : ""}">${escapeHtml(content)}</div>
        ${previews ? `<div class="candidate-previews">${previews}</div>` : ""}
        <div class="candidate-card-actions">
          ${postButton}
          <button type="button" class="secondary small-button" data-toggle-full="${index}">
            ${expanded ? "收起全文" : "展开全文"}
          </button>
        </div>
      </div>
    </article>`;
    }

    function candidatePreviewUrl(path) {
      const text = String(path || "").trim();
      if (!text) return "";
      if (/^https?:\/\//i.test(text) || text.startsWith("/")) return text;
      return "";
    }

    function updatePickCount(job = getCurrentJob?.()) {
      if (!job || job.status !== "awaiting_selection") return;
      const checked = candidateSelections.size;
      const required = requiredPickCount(job);
      const diff = required - checked;
      let hint = "数量正确，可以确认";
      let valid = true;
      if (diff > 0) {
        hint = `还需选择 ${diff} 条`;
        valid = false;
      } else if (diff < 0) {
        hint = `已多选 ${Math.abs(diff)} 条`;
        valid = false;
      }
      ui.pickCount.textContent = `已选 ${checked} / ${required}；${hint}`;
      controls.select.disabled = !valid || Boolean(controls.select.dataset.busyText);
    }

    function selectedIndexes() {
      return [...candidateSelections].sort((a, b) => a - b);
    }

    function handleClick(event) {
      const toggle = event.target.closest("[data-toggle-full]");
      if (toggle) {
        const index = Number(toggle.dataset.toggleFull);
        if (candidateExpanded.has(index)) {
          candidateExpanded.delete(index);
        } else {
          candidateExpanded.add(index);
        }
        render(getCurrentJob?.());
      }
    }

    function handleChange(event) {
      const checkbox = event.target.closest("input[type=checkbox]");
      if (!checkbox) return;
      const index = Number(checkbox.value);
      if (checkbox.checked) {
        candidateSelections.add(index);
      } else {
        candidateSelections.delete(index);
      }
      render(getCurrentJob?.());
    }

    function currentSelectedCount(job) {
      if (!job || job.status !== "awaiting_selection") return 0;
      return candidateSelections.size;
    }

    return {
      render,
      reset,
      selectedIndexes,
      handleClick,
      handleChange,
      currentSelectedCount,
    };
  },
};
