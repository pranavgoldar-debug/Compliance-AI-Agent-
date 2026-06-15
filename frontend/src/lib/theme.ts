// Light/dark theme — toggled from the Topbar, persisted in localStorage.
// Default is LIGHT (no stored choice → light). Applying = toggling the `.dark`
// class on <html>, which flips the CSS variables defined in index.css.
import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "aspora-theme";

export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "light";
  return window.localStorage.getItem(KEY) === "dark" ? "dark" : "light";
}

function apply(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
}

// Apply the stored theme as early as possible (called from main.tsx before
// React renders, so there's no light-mode flash for dark-mode users).
export function initTheme() {
  apply(getStoredTheme());
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);

  useEffect(() => {
    apply(theme);
    window.localStorage.setItem(KEY, theme);
  }, [theme]);

  return {
    theme,
    setTheme: setThemeState,
    toggle: () => setThemeState((t) => (t === "dark" ? "light" : "dark")),
  };
}
