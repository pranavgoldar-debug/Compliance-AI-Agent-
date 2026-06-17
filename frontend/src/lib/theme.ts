// Theme is fixed to LIGHT — dark mode was removed. initTheme() also clears any
// previously-stored dark preference so nobody is left stuck in dark after the
// toggle was taken out.
const KEY = "aspora-theme";

export function initTheme() {
  document.documentElement.classList.remove("dark");
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* localStorage unavailable — nothing to clear */
  }
}
