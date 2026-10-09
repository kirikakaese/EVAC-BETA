// SPDX-License-Identifier: AGPL-3.0-or-later
// Template expressions in layout texts:
//   {{ event.name }}  {{ screen.zone|default:"Foyer" }}  {{ now|time:"HH:mm" }}  {{ title|upper|truncate:20 }}
//   {% if screen.zone %}Zone {{ screen.zone }}{% else %}No zone{% endif %}   (also: not x, x == "y", x != "y")
// Output is plain text (inserted with textContent), so templates can never inject markup.

type Vars = Record<string, unknown>;

export interface TemplateOptions { now?: () => number; timezone?: string }

function lookup(vars: Vars, path: string, opts: TemplateOptions): unknown {
  const p = path.trim();
  if (p === "now") return new Date(opts.now ? opts.now() : Date.now());
  if (/^".*"$|^'.*'$/.test(p)) return p.slice(1, -1);
  if (/^-?\d+(\.\d+)?$/.test(p)) return Number(p);
  let cur: unknown = vars;
  for (const part of p.split(".")) {
    if (cur === null || cur === undefined || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function splitArgs(s: string): string[] {
  const out: string[] = [];
  let cur = "", quote = "";
  for (const ch of s) {
    if (quote) {
      if (ch === quote) quote = "";
      cur += ch;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
      cur += ch;
    } else if (ch === "|") {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out.map((x) => x.trim());
}

function unquote(s: string | undefined): string {
  if (!s) return "";
  const t = s.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}

function formatDate(d: Date, fmt: string, tz?: string): string {
  const base: Intl.DateTimeFormatOptions = tz ? { timeZone: tz } : {};
  switch (fmt) {
    case "short": return new Intl.DateTimeFormat("en-GB", { ...base, day: "numeric", month: "short" }).format(d);
    case "weekday": return new Intl.DateTimeFormat("en-GB", { ...base, weekday: "long" }).format(d);
    case "iso": return d.toISOString().slice(0, 10);
    case "HH:mm": return new Intl.DateTimeFormat("en-GB", { ...base, hour: "2-digit", minute: "2-digit" }).format(d);
    case "HH:mm:ss":
      return new Intl.DateTimeFormat("en-GB", { ...base, hour: "2-digit", minute: "2-digit", second: "2-digit" })
        .format(d);
    case "h:mm a":
      return new Intl.DateTimeFormat("en-US", { ...base, hour: "numeric", minute: "2-digit" }).format(d);
    default:
      return new Intl.DateTimeFormat("en-GB", { ...base, weekday: "long", day: "numeric", month: "long",
                                                year: "numeric" }).format(d);
  }
}

function toText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (Array.isArray(v)) return v.map(toText).join(", ");
  if (v instanceof Date) return v.toISOString();
  if (typeof v === "object") return (v as { name?: string }).name ?? "";
  return String(v);
}

function applyFilter(value: unknown, filter: string, opts: TemplateOptions): unknown {
  const [name, ...rest] = filter.split(":");
  const arg = unquote(rest.join(":"));
  const asDate = () => (value instanceof Date ? value : new Date(String(value)));
  switch (name.trim()) {
    case "upper": return toText(value).toUpperCase();
    case "lower": return toText(value).toLowerCase();
    case "title": return toText(value).replace(/\b\p{L}/gu, (c) => c.toUpperCase());
    case "truncate": {
      const n = Number(arg) || 30;
      const s = toText(value);
      return s.length > n ? `${s.slice(0, Math.max(0, n - 1))}…` : s;
    }
    case "default": return toText(value) === "" ? arg : value;
    case "date": return isNaN(asDate().getTime()) ? "" : formatDate(asDate(), arg || "long", opts.timezone);
    case "time": return isNaN(asDate().getTime()) ? "" : formatDate(asDate(), arg || "HH:mm", opts.timezone);
    case "join": return Array.isArray(value) ? value.map(toText).join(arg || ", ") : toText(value);
    default: return value;
  }
}

export function evaluate(expr: string, vars: Vars, opts: TemplateOptions = {}): unknown {
  const [head, ...filters] = splitArgs(expr);
  let value = lookup(vars, head, opts);
  for (const f of filters) value = applyFilter(value, f, opts);
  return value;
}

function truthy(v: unknown): boolean {
  if (Array.isArray(v)) return v.length > 0;
  return !(v === undefined || v === null || v === false || v === "" || v === 0);
}

export function condition(expr: string, vars: Vars, opts: TemplateOptions = {}): boolean {
  const e = expr.trim();
  if (!e) return true;
  if (e.startsWith("not ")) return !condition(e.slice(4), vars, opts);
  const m = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(e);
  if (m) {
    const a = toText(evaluate(m[1], vars, opts)), b = toText(evaluate(m[3], vars, opts));
    return m[2] === "==" ? a === b : a !== b;
  }
  return truthy(evaluate(e.replace(/^\{\{|\}\}$/g, ""), vars, opts));
}

const TOKEN = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;

export function render(template: string, vars: Vars, opts: TemplateOptions = {}): string {
  if (!template || (!template.includes("{{") && !template.includes("{%"))) return template ?? "";
  const parts = template.split(TOKEN);
  let pos = 0;
  const run = (stopAt: string[]): [string, string] => {
    let out = "";
    while (pos < parts.length) {
      const part = parts[pos++];
      const tag = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(part);
      if (tag) {
        const word = tag[1].startsWith("if") ? "if" : tag[1];
        if (stopAt.includes(word)) return [out, word];
        if (word === "if") {
          const ok = condition(tag[2], vars, opts);
          const [yes, end] = run(["else", "endif"]);
          let no = "";
          if (end === "else") no = run(["endif"])[0];
          out += ok ? yes : no;
        }
      } else if (part.startsWith("{{") && part.endsWith("}}")) {
        out += toText(evaluate(part.slice(2, -2), vars, opts));
      } else {
        out += part;
      }
    }
    return [out, ""];
  };
  return run([])[0];
}
