export const ACCENT_COLORS = {
  blue: { light: "#2563eb", dark: "#5983dd" },
  purple: { light: "#7c3aed", dark: "#7c3aed" },
  green: { light: "#059669", dark: "#059669" },
  orange: { light: "#ea580c", dark: "#ea580c" },
  red: { light: "#dc2626", dark: "#dc2626" },
};

export function applyAccentColor(accentName) {
  if (typeof window === "undefined") return;

  const root = window.document.documentElement;
  const selectedColor = ACCENT_COLORS[accentName] || ACCENT_COLORS.blue;
  const isDark = root.classList.contains("dark");
  const activeColor = isDark ? selectedColor.dark : selectedColor.light;

  root.style.setProperty("--accent-color-light", selectedColor.light);
  root.style.setProperty("--accent-color-dark-mode", selectedColor.dark);
  root.style.setProperty("--accent-color", activeColor);
}
