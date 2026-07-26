// A tiny pub/sub bus for messages that cross controller boundaries.
//
// Controllers mostly talk through callbacks injected by main.js, which is fine
// while the direction is one-way. It stops working when a controller needs to
// announce something to whoever cares -- wiring that as a callback means main.js
// has to thread the dependency through, and the two controllers become ordered.
//
// That case previously used window.dispatchEvent with a CustomEvent, which works
// but puts app messages on the same channel as DOM events and leaves the topic
// names undiscoverable. This keeps them in one place and out of window's
// namespace. state.js was an empty placeholder that the docs already credited
// with this job.
window.WeiboState = (() => {
  const listeners = new Map();

  function on(topic, handler) {
    if (typeof handler !== "function") return () => {};
    if (!listeners.has(topic)) listeners.set(topic, new Set());
    listeners.get(topic).add(handler);
    return () => off(topic, handler);
  }

  function off(topic, handler) {
    listeners.get(topic)?.delete(handler);
  }

  function emit(topic, detail) {
    // Copy first: a handler may unsubscribe itself while we iterate.
    for (const handler of Array.from(listeners.get(topic) || [])) {
      try {
        handler(detail);
      } catch (err) {
        // One bad subscriber must not stop the others from being told.
        console.error(`[WeiboState] listener for "${topic}" failed:`, err);
      }
    }
  }

  return {
    on,
    off,
    emit,
    // Topic names live here so a typo is an undefined property rather than a
    // silent no-op on a misspelled string.
    TOPICS: {
      PREVIEW_MODE_CHANGE: "preview-mode-change",
    },
  };
})();
