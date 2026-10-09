// SPDX-License-Identifier: AGPL-3.0-or-later
// Settings and UI strings rendered by Django into the page (strings are translated server side).

export interface PlayerEnv {
  version: string;
  api: string;
  ws: string;
  strings: Record<string, string>;
  mode: "screen" | "obs";
}

export function readEnv(doc: Document = document): PlayerEnv {
  const el = doc.getElementById("player-env");
  const raw = el?.textContent ? JSON.parse(el.textContent) : {};
  const params = new URLSearchParams(doc.location?.search ?? "");
  return {
    version: raw.version ?? "dev",
    api: raw.api ?? "/player/api/",
    ws: raw.ws ?? "",
    strings: raw.strings ?? {},
    mode: params.get("mode") === "obs" ? "obs" : "screen",
  };
}

export function t(env: PlayerEnv, key: string, vars: Record<string, string | number> = {}): string {
  let text = env.strings[key] ?? key;
  for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, String(v));
  return text;
}

export function wsUrl(env: PlayerEnv, loc: Location = location): string {
  if (env.ws) return env.ws.replace(/\/$/, "") + "/ws/screen/";
  return `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}/ws/screen/`;
}
