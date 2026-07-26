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
        const dot = document.createElement("span");
        dot.className = "particle-dot";
        particle.appendChild(dot);
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
      const particles = Array.from(ui.particleLayer.children);

      // Read every position first, then write every offset. Alternating a
      // getBoundingClientRect with a style write makes the browser re-layout
      // once per particle -- 130 forced layouts per pointer frame.
      const offsets = particles.map((particle) => {
        const rect = particle.getBoundingClientRect();
        const dx = rect.left + rect.width / 2 - particlePointer.x;
        const dy = rect.top + rect.height / 2 - particlePointer.y;
        const distance = Math.hypot(dx, dy);
        if (!distance || distance > radius) return null;
        const force = ((radius - distance) / radius) ** 2 * maxOffset;
        return {
          x: `${((dx / distance) * force).toFixed(2)}px`,
          y: `${((dy / distance) * force).toFixed(2)}px`,
        };
      });

      particles.forEach((particle, index) => {
        const dot = particle.firstElementChild;
        if (!dot) return;
        const offset = offsets[index];
        dot.style.setProperty("--repel-x", offset ? offset.x : "0px");
        dot.style.setProperty("--repel-y", offset ? offset.y : "0px");
      });
    }

    function resetRepel() {
      particlePointer = null;
      if (!ui.particleLayer) return;
      for (const particle of ui.particleLayer.children) {
        const dot = particle.firstElementChild;
        if (!dot) continue;
        dot.style.setProperty("--repel-x", "0px");
        dot.style.setProperty("--repel-y", "0px");
      }
    }

    return { init };
  },
};
