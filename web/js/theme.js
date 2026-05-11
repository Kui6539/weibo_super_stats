window.WeiboTheme = {
  createController({ controls, onChange }) {
    function current() {
      return document.body.classList.contains("light-theme") ? "light" : "dark";
    }

    function apply(theme) {
      const nextTheme = theme === "light" ? "light" : "dark";
      document.body.classList.toggle("light-theme", nextTheme === "light");
      controls.themeToggle.classList.toggle("is-light", nextTheme === "light");
      controls.themeToggle.setAttribute(
        "aria-label",
        nextTheme === "light" ? "切换为暗色主题" : "切换为亮色主题",
      );
      controls.themeToggle.title = controls.themeToggle.getAttribute("aria-label") || "";
    }

    function init() {
      apply("dark");
      controls.themeToggle.addEventListener("click", () => {
        const nextTheme = current() === "light" ? "dark" : "light";
        apply(nextTheme);
        if (onChange) onChange(nextTheme);
      });
    }

    return {
      current,
      apply,
      init,
    };
  },
};
