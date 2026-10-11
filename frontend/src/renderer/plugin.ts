// SPDX-License-Identifier: AGPL-3.0-or-later
// Widgets of third-party plugins (ADR-0045). A layout element {"type": "plugin", "props": {"widget": key,
// "settings": {…}}} shows the widget a plugin registered with WidgetSpec(element="evac-x-…", script=…). The
// renderer loads the plugin's script (a JavaScript module from the plugin's static files) once, creates the custom
// element inside the box and keeps it fed:
//   element.settings = the element's settings        element.vars = template variables (event, screen, …)
//   element.data = {source key: payload, …}           (refreshed every ttl seconds; the last payload is kept
//                                                       while the server is unreachable)
// A plugin element only needs to render; it never talks to the server itself.
import type { PluginHost, PluginWidgetInfo } from "./types";
import { EvacWidget, WIDGETS } from "./widgets";

const loading = new Map<string, Promise<unknown>>();

export function loadScript(url: string): Promise<unknown> {
  let p = loading.get(url);
  if (!p) {
    p = import(/* @vite-ignore */ url);
    loading.set(url, p);
    p.catch(() => loading.delete(url));  // try again next time
  }
  return p;
}

/** A PluginHost that reads data sources from ``base + key + "/"`` with optional headers (player, editor). With
 * ``persist`` the last payload of every source is also kept in localStorage, so a player that restarts offline
 * still shows what it had. */
export function fetchHost(widgets: () => Record<string, PluginWidgetInfo>, base: string,
                          headers: () => Record<string, string> = () => ({}), persist = false): PluginHost {
  const last = new Map<string, unknown>();
  const storeKey = (key: string) => `evac.plugin-source.${key}`;
  return {
    get widgets() { return widgets(); },
    async source(key: string): Promise<unknown> {
      try {
        const res = await fetch(`${base}${encodeURIComponent(key)}/`, { headers: headers(), cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { data: unknown };
        last.set(key, body.data);
        if (persist) {
          try { localStorage.setItem(storeKey(key), JSON.stringify(body.data)); } catch { /* quota */ }
        }
        return body.data;
      } catch (err) {
        if (last.has(key)) return last.get(key);
        if (persist) {
          try {
            const raw = localStorage.getItem(storeKey(key));
            if (raw !== null) return JSON.parse(raw) as unknown;
          } catch { /* blocked or broken */ }
        }
        throw err;
      }
    },
  };
}

/** A PluginHost with fixed data (preview pages, tests). */
export function staticHost(widgets: Record<string, PluginWidgetInfo>, data: Record<string, unknown>): PluginHost {
  return {
    widgets,
    source: (key: string) => (key in data ? Promise.resolve(data[key]) : Promise.reject(new Error(`no data for ${key}`))),
  };
}

type PluginElement = HTMLElement & { settings?: unknown; vars?: unknown; data?: Record<string, unknown> };

export class PluginWidget extends EvacWidget {
  private inner: PluginElement | null = null;

  draw(): void {
    const key = String(this.props.widget ?? "");
    const info = key ? this.ctx.plugins?.widgets[key] : undefined;
    if (!info) return this.placeholder(key ? `Plugin widget “${key}” is not installed` : "Plugin widget");
    const settings = (this.props.settings as Record<string, unknown> | undefined) ?? {};
    loadScript(info.script).then(() => {
      if (!this.isConnected && !this.ctx.editing) return;
      if (!customElements.get(info.element)) throw new Error(`${info.script} did not define <${info.element}>`);
      const inner = document.createElement(info.element) as PluginElement;
      inner.className = "evac-plugin-element";
      inner.settings = settings;
      inner.vars = this.ctx.vars;
      inner.data = {};
      this.replaceChildren(inner);
      this.inner = inner;
      this.refresh(info);
      if (info.sources.length) this.every(Math.max(10, info.ttl) * 1000, () => this.refresh(info));
    }).catch((err) => this.safely(() => { throw err; }));
  }

  private refresh(info: PluginWidgetInfo): void {
    const host = this.ctx.plugins;
    if (!host) return;
    for (const key of info.sources) {
      host.source(key).then((payload) => {
        if (!this.inner) return;
        this.inner.data = { ...(this.inner.data ?? {}), [key]: payload };
      }).catch((err) => this.ctx.onError?.(this.el.id, err));
    }
  }
}

WIDGETS.plugin = PluginWidget;
