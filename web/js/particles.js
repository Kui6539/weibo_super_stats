window.WeiboParticles = {
  createController({ ui, clamp }) {
    let particleFrame = 0;
    let particlePointer = null;

    function init() {
      if (!ui.particleLayer || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return;
      }
      const fragment = document.createDocumentFragment();
      const particleCount = Math.min(130, Math.max(72, Math.floor(window.innerWidth / 11)));
      for (let index = 0; index < particleCount; index += 1) {
        const particle = document.createElement("span");
        particle.className = "particle";
        particle.style.setProperty("--x", String(Math.random() * 100));
        particle.style.setProperty("--size", `${(Math.random() * 1.8 + 1.1).toFixed(2)}px`);
        particle.style.setProperty("--opacity", (Math.random() * 0.34 + 0.18).toFixed(2));
        particle.style.setProperty("--duration", `${(Math.random() * 18 + 22).toFixed(2)}s`);
        particle.style.setProperty("--delay", `${(-Math.random() * 30).toFixed(2)}s`);
        particle.style.setProperty("--tilt", `${(Math.random() * 46 - 23).toFixed(2)}deg`);
        fragment.appendChild(particle);
      }
      ui.particleLayer.replaceChildren(fragment);
      window.addEventListener("pointermove", scheduleRepel, { passive: true });
      document.addEventListener("mouseleave", resetRepel);
      window.addEventListener("blur", resetRepel);
    }

    function scheduleRepel(event) {
      particlePointer = { x: event.clientX, y: event.clientY };
      if (particleFrame) return;
      particleFrame = window.requestAnimationFrame(updateRepel);
    }

    function updateRepel() {
      particleFrame = 0;
      if (!particlePointer || !ui.particleLayer) return;
      const radius = 150;
      const maxOffset = 66;
      for (const particle of ui.particleLayer.children) {
        const rect = particle.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const dx = centerX - particlePointer.x;
        const dy = centerY - particlePointer.y;
        const distance = Math.hypot(dx, dy);
        if (!distance || distance > radius) {
          particle.style.setProperty("--repel-x", "0px");
          particle.style.setProperty("--repel-y", "0px");
          continue;
        }
        const force = ((radius - distance) / radius) ** 2 * maxOffset;
        particle.style.setProperty("--repel-x", `${((dx / distance) * force).toFixed(2)}px`);
        particle.style.setProperty("--repel-y", `${((dy / distance) * force).toFixed(2)}px`);
      }
    }

    function resetRepel() {
      particlePointer = null;
      if (!ui.particleLayer) return;
      for (const particle of ui.particleLayer.children) {
        particle.style.setProperty("--repel-x", "0px");
        particle.style.setProperty("--repel-y", "0px");
      }
    }

    return { init };
  },
};
