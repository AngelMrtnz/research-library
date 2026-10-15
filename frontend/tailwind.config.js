// Rebuild app/static/app.css after changing templates:
//   npx tailwindcss@3.4.16 -c frontend/tailwind.config.js -i frontend/input.css -o app/static/app.css --minify
const colors = ["blue", "emerald", "amber", "rose", "violet", "cyan", "lime", "orange",
                "fuchsia", "teal", "sky", "pink"];
module.exports = {
  darkMode: "media",
  content: ["./app/templates/**/*.html"],
  // Tag colors are chosen at runtime, so their classes must always be built.
  safelist: colors.flatMap((c) => [
    `bg-${c}-100`, `text-${c}-800`, `ring-${c}-300`, `ring-${c}-600`, `bg-${c}-400`,
    `dark:bg-${c}-900/40`, `dark:text-${c}-200`,
  ]),
};
