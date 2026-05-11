window.WeiboHelp = {
  createController({ ui, api, previewController, appendClientLog, clamp }) {
    let dragState = null;

    async function load() {
      try {
        const data = await api("/api/help-doc");
        ui.helpContent.innerHTML = previewController.renderMarkdown(data.markdown || "");
        previewController.bindImages(ui.helpContent);
        ui.helpPath.textContent = data.path || "";
        show();
      } catch (err) {
        appendClientLog(err.message);
      }
    }

    function show() {
      ui.helpDialog.style.left = "";
      ui.helpDialog.style.top = "";
      ui.helpDialog.style.transform = "";
      ui.helpOverlay.classList.add("visible");
      ui.helpOverlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("help-modal-open");
      ui.helpClose.focus();
    }

    function close() {
      ui.helpOverlay.classList.remove("visible");
      ui.helpOverlay.setAttribute("aria-hidden", "true");
      document.body.classList.remove("help-modal-open");
    }

    function startDrag(event) {
      if (event.button !== 0 || event.target.closest("button, a, input, textarea")) return;
      const rect = ui.helpDialog.getBoundingClientRect();
      dragState = {
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
      };
      ui.helpDialog.classList.add("dragging");
      ui.helpDialog.style.left = `${rect.left}px`;
      ui.helpDialog.style.top = `${rect.top}px`;
      ui.helpDialog.style.transform = "none";
      window.addEventListener("pointermove", dragDialog);
      window.addEventListener("pointerup", stopDrag, { once: true });
      event.preventDefault();
    }

    function dragDialog(event) {
      if (!dragState) return;
      const rect = ui.helpDialog.getBoundingClientRect();
      const margin = 12;
      const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin);
      const maxTop = Math.max(margin, window.innerHeight - rect.height - margin);
      const left = clamp(event.clientX - dragState.offsetX, margin, maxLeft);
      const top = clamp(event.clientY - dragState.offsetY, margin, maxTop);
      ui.helpDialog.style.left = `${left}px`;
      ui.helpDialog.style.top = `${top}px`;
    }

    function stopDrag() {
      dragState = null;
      ui.helpDialog.classList.remove("dragging");
      window.removeEventListener("pointermove", dragDialog);
    }

    function handleOverlayClick(event) {
      if (event.target === ui.helpOverlay) close();
    }

    function handleEscape(event) {
      if (event.key === "Escape" && ui.helpOverlay.classList.contains("visible")) {
        close();
      }
    }

    return {
      load,
      show,
      close,
      startDrag,
      handleOverlayClick,
      handleEscape,
    };
  },
};
