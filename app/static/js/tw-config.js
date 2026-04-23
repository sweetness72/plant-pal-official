/* Shared Tailwind Play CDN config for every Plant Pal page.
 *
 * Every template loads the Tailwind Play CDN and then loads THIS file,
 * which assigns window.tailwind.config. The CDN picks the config up and
 * all `bg-primary`, `text-on-surface`, `rounded-lg`, etc. utilities resolve
 * to the same values on every page.
 *
 * Colors here MUST match the CSS variables in app/static/css/main.css
 * (search for the "Canonical Plant Pal palette" block). When you change a
 * color, change it in both places — Tailwind utilities and pp-* components
 * should always render the same hue.
 */
(function () {
  window.tailwind = window.tailwind || {};
  window.tailwind.config = {
    darkMode: "class",
    theme: {
      extend: {
        colors: {
          /* Page background + surfaces */
          background:                 "#fdf8ee",
          surface:                    "#fdf8ee",
          "surface-bright":           "#fef9f1",
          "surface-container-lowest": "#ffffff",
          "surface-container-low":    "#f8f3eb",
          "surface-container":        "#f2ede5",
          "surface-container-high":   "#ece8e0",
          "surface-container-highest":"#e4dfd2",
          "surface-dim":              "#e4dfd2",
          "surface-variant":          "#ece8e0",
          "surface-tint":             "#2d6b4a",

          /* Ink */
          "on-background":            "#2b2a22",
          "on-surface":               "#2b2a22",
          "on-surface-variant":       "#6a6658",

          /* Primary — plant green, matches --pp-primary */
          primary:                    "#2d6b4a",
          "primary-dim":              "#1f5036",
          "primary-container":        "#d9ecdc",
          "primary-fixed":            "#d9ecdc",
          "primary-fixed-dim":        "#b8d6bd",
          "on-primary":               "#ffffff",
          "on-primary-container":     "#0f3a23",
          "inverse-primary":          "#b8d6bd",

          /* Secondary — warm terracotta (the cozy accent) */
          secondary:                  "#b8734a",
          "secondary-dim":            "#8f542f",
          "secondary-container":      "#f6e4d4",
          "on-secondary":             "#ffffff",
          "on-secondary-container":   "#5a331a",

          /* Tertiary — muted sage/olive */
          tertiary:                   "#7d8b6f",
          "tertiary-container":       "#e8efe0",
          "on-tertiary":              "#ffffff",
          "on-tertiary-container":    "#3e4a2e",

          /* Semantic */
          error:                      "#a8442f",
          "error-dim":                "#7a2d1e",
          "error-container":          "#f4d5cd",
          "on-error":                 "#ffffff",
          "on-error-container":       "#5a1f11",

          /* Outlines */
          outline:                    "#9a9280",
          "outline-variant":          "#e6dfd0",
        },
        borderRadius: {
          DEFAULT: "0.25rem",
          md:      "0.875rem",
          lg:      "1.375rem",
          xl:      "1.75rem",
          full:    "9999px",
        },
        fontFamily: {
          headline: ["Newsreader", "Georgia", "serif"],
          body:     ["Plus Jakarta Sans", "system-ui", "sans-serif"],
          label:    ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        },
        boxShadow: {
          soft:   "0 1px 2px rgba(43,42,34,0.06)",
          lifted: "0 6px 16px -6px rgba(43,42,34,0.12)",
          hover:  "0 18px 36px -12px rgba(43,42,34,0.16)",
        },
      },
    },
  };
})();
