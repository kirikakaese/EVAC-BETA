// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC screen player: pairs itself, connects, reports health and shows content. Keeps running offline with
// the last known configuration (service worker caches the app itself).
import "./player.css";

import { fetchConfig, pairingStatus, startPairing, Unauthorized, type PairStart, type ScreenConfig } from "./api";
import { Clock } from "./clock";
import { Connection, type Message, type Transport } from "./connection";
import { Display } from "./display";
import { cachedBundle, clearBundle, defaultLayout, fetchBundle, prefetch, type Bundle } from "./content";
import { cachedProgram, clearProgram, fetchProgram } from "./program";
import { nextChange, slideAt, type Program, type Slide } from "../program/engine";
import type { LayoutData } from "../renderer/types";
import { applyTheme, fetchTheme } from "./theme";
import { readEnv, t, wsUrl, type PlayerEnv } from "./env";
import { installErrorHandlers, recordError, report } from "./report";
import { getConfig, getToken, setConfig, setToken } from "./storage";

const PAIR_POLL_MS = 3000;
/** re-evaluate at least this often (item validity, clock corrections) */
const MAX_WAIT_MS = 60_000;
/** fetch the program again this often to extend its horizon (it covers several days) */
const PROGRAM_REFRESH_MS = 3_600_000;

export class Player {
  readonly clock = new Clock();
  private display: Display;
  private conn: Connection | null = null;
  private config: ScreenConfig | null = null;
  private transport: Transport = "connecting";
  private lastSync: number | null = null;
  private slide = "idle";
  private bundle: Bundle | null = null;
  private program: Program | null = null;
  private shown = "";
  private timer: ReturnType<typeof setTimeout> | null = null;
  private refresher: ReturnType<typeof setInterval> | null = null;

  constructor(private env: PlayerEnv, root: HTMLElement) {
    this.display = new Display(root, this.clock);
    if (env.mode === "obs") document.documentElement.classList.add("obs");
  }

  async boot(): Promise<void> {
    const token = getToken();
    if (!token) return this.pair();
    return this.play(token);
  }

  // ---------------------------------------------------------------- pairing
  private async pair(): Promise<void> {
    const strings = {
      title: t(this.env, "pair_title"), step1: t(this.env, "pair_step1"), step2: t(this.env, "pair_step2"),
      waiting: t(this.env, "pair_waiting"),
    };
    let start: PairStart;
    try {
      start = await startPairing(this.env.api, report({ version: this.env.version, slide: "pairing", lastSync: null,
                                                        online: true }));
    } catch (err) {
      recordError(String(err));
      this.display.message(t(this.env, "no_server"), t(this.env, "retrying"));
      setTimeout(() => void this.pair(), 10000);
      return;
    }
    this.display.pairing(start.code, start.pair_url, strings);
    const poll = async (): Promise<void> => {
      try {
        const st = await pairingStatus(this.env.api, start);
        if (st.status === "paired") {
          setToken(st.token);
          return this.play(st.token);
        }
        if (st.status !== "pending") return this.pair();
      } catch (err) {
        recordError(String(err));
      }
      setTimeout(() => void poll(), PAIR_POLL_MS);
    };
    setTimeout(() => void poll(), PAIR_POLL_MS);
  }

  // ---------------------------------------------------------------- playing
  private async play(token: string): Promise<void> {
    const cached = getConfig<ScreenConfig>();
    try {
      const sent = Date.now();
      this.config = await fetchConfig(this.env.api, token);
      this.clock.add(sent, Date.now(), this.config.server_time);
      this.lastSync = Date.now();
      setConfig(this.config);
    } catch (err) {
      if (err instanceof Unauthorized) return this.unpair();
      recordError(String(err));
      this.config = cached;
    }
    this.bundle = cachedBundle();
    this.program = cachedProgram();
    await this.loadContent(token);
    await this.loadProgram(token);
    this.show();
    this.refresher = setInterval(() => void this.loadProgram(token).then(() => this.show()), PROGRAM_REFRESH_MS);
    this.conn = new Connection({
      api: this.env.api, ws: wsUrl(this.env), token, clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10, since: this.config?.seq ?? 0,
      report: () => report({ version: this.env.version, slide: this.slide, lastSync: this.lastSync,
                             online: this.transport !== "offline" }),
      onMessage: (m) => void this.handle(m, token),
      onTransport: (tr) => { this.transport = tr; },
      onUnauthorized: () => this.unpair(),
      onSync: (at) => { this.lastSync = at; },
    });
    this.conn.start();
  }

  private async handle(msg: Message, token: string): Promise<void> {
    switch (msg.type) {
      case "config.changed":
        try {
          this.config = await fetchConfig(this.env.api, token);
          setConfig(this.config);
          this.lastSync = Date.now();
          this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds);
          const before = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(token);
          await this.loadProgram(token);
          if (`${this.bundle?.version}/${this.program?.version}` !== before || this.slide === "idle") {
            this.shown = "";
            this.show();
          }
        } catch (err) {
          if (err instanceof Unauthorized) this.unpair();
        }
        break;
      case "identify": {
        const name = this.config?.screen.name ?? "";
        const where = [this.config?.screen.venue, this.config?.screen.zone, this.config?.screen.room]
          .filter(Boolean).join(" · ");
        this.display.identify(name, `${where}${where ? " · " : ""}${this.transport}`,
                              Number(msg.data.seconds) || 10);
        break;
      }
      case "program.changed": {
        const before = this.program?.version;
        await this.loadProgram(token);
        if (this.program?.version !== before) {
          this.shown = "";
          this.show();
        }
        break;
      }
      case "reload":
        location.reload();
        break;
      default:
        break;
    }
  }

  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  private async loadContent(token: string): Promise<void> {
    try {
      this.bundle = (await fetchBundle(this.env.api, token)) ?? this.bundle;
    } catch (err) {
      if (err instanceof Unauthorized) return this.unpair();
    }
    const theme = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css }
      : await fetchTheme(this.env.api, token);
    if (theme) await applyTheme(theme, token).catch((e) => recordError(String(e)));
    if (this.bundle) void prefetch(this.bundle);
  }

  private async loadProgram(token: string): Promise<void> {
    try {
      this.program = await fetchProgram(this.env.api, token);
    } catch (err) {
      if (err instanceof Unauthorized) this.unpair();
    }
  }

  private vars(): Record<string, unknown> {
    const cfg = this.config as ScreenConfig;
    const s = cfg.screen;
    return { event: cfg.event, screen: { name: s.name, zone: s.zone ?? "", room: s.room ?? "", venue: s.venue ?? "",
                                         tags: s.tags, groups: s.groups.map((g) => g.name) } };
  }

  /** Show what the program says for now (or the default layout without one) and wake up at the next change. */
  private show(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const cfg = this.config;
    if (!cfg) {
      this.slide = "error";
      this.display.message(t(this.env, "no_server"), t(this.env, "retrying"));
      return;
    }
    const now = this.clock.now();
    let data: LayoutData | null = null;
    let variables: Record<string, string> | undefined;
    let key = "idle";
    let slide: Slide | null = null;
    if (this.program && this.bundle) {
      slide = slideAt(this.program, this.vars(), now);
      if (slide?.message) {
        data = (this.program.messages?.[slide.message] as LayoutData | undefined) ?? null;
        key = `${slide.entry}|message`;
        this.slide = `${slide.entry} message`;
      } else if (slide?.layout) {
        const layout = this.bundle.layouts.find((l) => l.id === slide?.layout);
        if (layout) {
          data = layout.data;
          variables = layout.variables;
          key = `${slide.entry}|${layout.id}|${layout.version}|${slide.count > 1 ? slide.start : ""}`;
          this.slide = `${layout.key} v${layout.version} (${slide.entry} ${slide.index + 1}/${slide.count})`;
        }
      }
      const next = nextChange(this.program, now, slide);
      const wait = Math.max(5, Math.min(MAX_WAIT_MS, (next ?? now + MAX_WAIT_MS) - now));
      this.timer = setTimeout(() => this.show(), wait);
    } else {
      const layout = defaultLayout(this.bundle);
      if (layout) {
        data = layout.data;
        variables = layout.variables;
        key = `default|${layout.id}|${layout.version}`;
        this.slide = `${layout.key} v${layout.version}`;
      }
    }
    if (key === this.shown) return;
    this.shown = key;
    if (data && this.bundle) {
      this.display.layout(data, {
        vars: this.vars(), now: () => this.clock.now(), timezone: cfg.event.timezone, assets: this.bundle.assets,
        fonts: this.bundle.fonts, reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
        onError: (id, err) => recordError(`${id}: ${String(err)}`),
      }, variables);
    } else {
      this.slide = "idle";
      this.display.idle(cfg);
    }
  }

  private unpair(): void {
    if (this.timer) clearTimeout(this.timer);
    if (this.refresher) clearInterval(this.refresher);
    this.timer = this.refresher = null;
    clearProgram();
    this.program = null;
    this.shown = "";
    this.conn?.stop();
    this.conn = null;
    setToken(null);
    clearBundle();
    void this.pair();
  }
}

function registerServiceWorker(): void {
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((e) => recordError(String(e)));
  }
}

if (typeof document !== "undefined" && document.getElementById("player")) {
  installErrorHandlers();
  registerServiceWorker();
  const env = readEnv();
  void new Player(env, document.getElementById("player") as HTMLElement).boot();
}
