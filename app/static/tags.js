// Tag editor: colored chips, an inline "+ tag" field with suggestions, keyboard friendly.
// <div data-tag-editor data-tags='["a","b"]' data-url="/papers/1/tags">   saves at once
// <div data-tag-editor data-tags='[...]' data-name="tags">                 fills a form field
(() => {
  const norm = (s) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().trim()
    .replace(/[\s_]+/g, "-").replace(/[^a-z0-9-]/g, "").replace(/-+/g, "-").replace(/^-|-$/g, "");
  const index = () => window.TAGS || [];
  const color = (name) => (index().find((t) => t.name === name) || {}).color || "slate";
  const chipCls = (c) => `bg-${c}-100 text-${c}-800 dark:bg-${c}-900/40 dark:text-${c}-200`;
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  function editor(root) {
    let tags = JSON.parse(root.dataset.tags || "[]");
    const url = root.dataset.url;
    let field = null;
    if (root.dataset.name) {
      field = h("input"); field.type = "hidden"; field.name = root.dataset.name;
      root.after(field);
    }
    const wrap = h("div", "flex flex-wrap items-center gap-1");
    root.append(wrap);
    let input = null, menu = null, active = 0, options = [], moving = false, browsing = false;

    async function commit(next) {
      const before = tags;
      tags = next;
      render();
      if (field) { field.value = tags.join(" "); field.dispatchEvent(new Event("change", { bubbles: true })); return; }
      const body = new FormData();
      body.append("tags", tags.join(" "));
      try {
        const r = await fetch(url, { method: "POST", body });
        if (!r.ok) throw new Error(r.status);
        window.TAGS = (await r.json()).index;
        render();
      } catch {
        tags = before; render();
        wrap.classList.add("animate-pulse"); setTimeout(() => wrap.classList.remove("animate-pulse"), 800);
      }
    }
    const add = (raw) => {
      const names = raw.split(/[,;]+/).map(norm).filter((n) => n && !tags.includes(n));
      if (names.length) commit([...tags, ...names]);
    };
    const remove = (name) => commit(tags.filter((t) => t !== name));

    function suggestions(q) {
      const n = norm(q);
      const pool = index().filter((t) => !tags.includes(t.name) && t.name.includes(n));
      pool.sort((a, b) => (b.name.startsWith(n) - a.name.startsWith(n)) || (b.n - a.n) || a.name.localeCompare(b.name));
      const out = pool.slice(0, 8).map((t) => ({ name: t.name, label: t.name }));
      if (n && !tags.includes(n) && !index().some((t) => t.name === n)) out.push({ name: n, label: `Create "${n}"` });
      return out;
    }
    function drawMenu() {
      options = suggestions(input.value);
      active = Math.min(active, Math.max(options.length - 1, 0));
      menu.replaceChildren(...options.map((o, i) => {
        const li = h("li", `flex cursor-pointer items-center gap-2 px-3 py-1.5 ${i === active ? "bg-slate-100 dark:bg-slate-700" : ""}`);
        li.append(h("span", `h-2 w-2 rounded-full bg-${color(o.name) === "slate" ? "slate" : color(o.name)}-400`), h("span", "", o.label));
        li.onmousedown = (e) => { e.preventDefault(); input.value = ""; add(o.name); };
        return li;
      }));
      menu.classList.toggle("hidden", !options.length);
    }
    function open() {
      const box = h("span", "relative inline-block");
      input = h("input", "w-32 rounded-full border border-slate-300 bg-white px-2 py-0.5 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900");
      input.placeholder = "tag";
      menu = h("ul", "absolute left-0 top-full z-30 mt-1 hidden max-h-64 min-w-[12rem] overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-800");
      box.append(input, menu);
      wrap.lastChild.replaceWith(box);
      input.oninput = () => { active = 0; browsing = false; drawMenu(); };
      input.onfocus = drawMenu;
      input.onkeydown = (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          if (options.length && browsing) active = (active + (e.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
          browsing = true;
          drawMenu();
        } else if (e.key === "Enter" || e.key === "Tab" || e.key === ",") {
          const pick = (input.value.trim() || browsing) && options[active] ? options[active].name : input.value;
          if (!pick.trim()) { if (e.key === "Enter") e.preventDefault(); return; }
          e.preventDefault(); e.stopPropagation(); input.value = ""; browsing = false; add(pick);
        } else if (e.key === "Escape") {
          input.value = ""; input.blur();
        } else if (e.key === "Backspace" && !input.value && tags.length) {
          remove(tags[tags.length - 1]);
        }
      };
      input.onblur = () => {
        if (moving) return;
        const v = input.value; input = null;
        if (v.trim()) add(v); else render();
      };
      input.focus();
    }
    function render() {
      const focused = input && document.activeElement === input;
      moving = true;
      wrap.replaceChildren(...tags.map((name) => {
        const chip = h("span", `inline-flex items-center gap-1 rounded-full py-0.5 pl-2 pr-1 text-xs ${chipCls(color(name))}`);
        const label = url ? h("a", "", name) : h("span", "", name);
        if (url) label.href = `/?tag=${encodeURIComponent(name)}`;
        const x = h("button", "rounded-full px-1 opacity-50 hover:opacity-100", "×");
        x.type = "button"; x.title = "Remove"; x.onclick = () => remove(name);
        chip.append(label, x);
        return chip;
      }), input ? input.parentElement : (() => {
        const b = h("button", "rounded-full border border-dashed border-slate-300 px-2 py-0.5 text-xs text-slate-500 hover:border-slate-400 hover:text-slate-700 dark:border-slate-600 dark:hover:text-slate-200", "+ tag");
        b.type = "button"; b.onclick = open;
        return b;
      })());
      if (field) field.value = tags.join(" ");
      if (focused) { input.focus(); drawMenu(); }
      moving = false;
    }
    render();
  }

  const init = (scope) => scope.querySelectorAll("[data-tag-editor]:not([data-ready])").forEach((el) => {
    el.dataset.ready = "1"; editor(el);
  });
  document.addEventListener("DOMContentLoaded", () => init(document));
  document.addEventListener("htmx:load", (e) => init(e.target));
})();
