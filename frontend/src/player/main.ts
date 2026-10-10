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
import { nextOverlayChange, OverlayLayer, SPEECH_DELAY_MS } from "./overlays";
import { prefetchSpeech, Speaker } from "./speech";
import { MemoryStore } from "../renderer/data";
import { cachedWidgetData, clearWidgetData, refreshWidgetData } from "./widgetdata";
import { cachedSchedule, clearSchedule, refreshSchedule } from "./scheduledata";
import { ProgramStore } from "../renderer/program";
import { nextChange, slideAt, type Program, type Slide } from "../program/engine";
import { pageNonce } from "../renderer/code";
import type { LayoutData } from "../renderer/types";
import { applyTheme, fetchTheme } from "./theme";
import { readEnv, t, wsUrl, type PlayerEnv } from "./env";
import { installErrorHandlers, log, logLines, onErrorStorm, recordError, report } from "./report";
import { bootCheck, installLifecycle, markAlive, memoryPressure, safeReload } from "./resilience";
import { canCapture, captureScreenshot, clearCaches, upload } from "./remote";
import { applyRoot, applyState, displayState, localHHMM, type DisplaySettings } from "./screen-settings";
import { getConfig, getToken, setConfig, setToken } from "./storage";
import { EvacController, probeAudio, type EvacBundle, type EvacPayload } from "./evac";
import type { Signed } from "./ed25519";

const PAIR_POLL_MS = 3000;

/** Where the start-up got to (``<html data-boot>``): visible in remote screenshots' DOM and in tests. */
function stage(name: string): void {
  document.documentElement.dataset.boot = name;
}
/** re-evaluate at least this often (item validity, clock corrections) */
const MAX_WAIT_MS = 60_000;
/** fetch the program again this often to extend its horizon (it covers several days) */
const PROGRAM_REFRESH_MS = 3_600_000;
/** custom widget rows: refetched this often besides "data.changed" pushes */
const WIDGET_DATA_REFRESH_MS = 300_000;
/** housekeeping: display state, daily reload, memory, stalled timers */
const TICK_MS = 15_000;
/** evacuation state is fetched this often besides pushes (cheap; catches missed messages) */
const EVAC_REFRESH_MS = 60_000;
/** without a connection to the server, fallback origins are asked this often for the signed alarm state */
const FALLBACK_POLL_MS = 3_000;

export class Player {
  readonly clock = new Clock();
  private display: Display;
  private speaker = new Speaker();
  private widgetData = new MemoryStore(cachedWidgetData());
  /** the event's sessions for "program" elements (ADR-0038) */
  private schedule = new ProgramStore(cachedSchedule());
  private dataRefresher: ReturnType<typeof setInterval> | null = null;
  private overlays = new OverlayLayer(this.speaker);
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
  private housekeeping: ReturnType<typeof setInterval> | null = null;
  private displayState = "on";
  private recovered = "";
  private lastTick = Date.now();
  private reloadAtNextSlide = "";
  private lastDailyReload = "";
  private evac: EvacController | null = null;
  private evacAck = "";
  private evacAudio = "";
  private evacTimer: ReturnType<typeof setInterval> | null = null;
  private fallbackTimer: ReturnType<typeof setInterval> | null = null;

  constructor(private env: PlayerEnv, private root: HTMLElement) {
    this.display = new Display(root, this.clock);
    if (env.mode === "obs") document.documentElement.classList.add("obs");
  }

  async boot(): Promise<void> {
    stage("boot");
    this.recovered = bootCheck();
    log("info", `player ${this.env.version} started (${navigator.userAgent})`);
    if (this.recovered) log("warn", this.recovered);
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
    // an alarm that was showing before a restart or power cut shows again at once, even without the server
    this.evac = this.evac ?? this.makeEvac(token);
    if (cached) applyRoot(this.evac.layer, cached.display ?? {});
    this.evac.render(true);
    // offline first: show the last known state at once; the network refreshes it in the background (a hanging
    // network must never keep a screen blank)
    stage(cached ? "play: cached config" : "play: no cached config");
    if (cached) {
      this.config = cached;
      this.bundle = cachedBundle();
      this.program = cachedProgram();
      this.applySettings();
      if (this.bundle) {
        void applyTheme({ ...this.bundle.theme, fonts_css: this.bundle.fonts_css }, token)
          .catch((e) => recordError(String(e)));
      }
      this.show();
      stage("play: shown from cache");
    }
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
    this.applySettings();
    this.bundle = this.bundle ?? cachedBundle();
    this.program = this.program ?? cachedProgram();
    await this.loadContent(token);
    await this.loadProgram(token);
    this.show();
    void this.loadEvac(token);
    void probeAudio().then((a) => { this.evacAudio = a; });
    this.evacTimer = setInterval(() => void this.loadEvac(token), EVAC_REFRESH_MS);
    this.fallbackTimer = setInterval(() => void this.pollFallback(), FALLBACK_POLL_MS);
    stage("play: online");
    this.refresher = setInterval(() => void this.loadProgram(token).then(() => this.show()), PROGRAM_REFRESH_MS);
    void this.loadWidgetData(token);
    void this.loadSchedule(token);
    this.dataRefresher = setInterval(() => {
      void this.loadWidgetData(token);
      void this.loadSchedule(token);
    }, WIDGET_DATA_REFRESH_MS);
    this.housekeeping = setInterval(() => this.tick(), TICK_MS);
    this.conn = new Connection({
      api: this.env.api, ws: wsUrl(this.env), token, clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10, since: this.config?.seq ?? 0,
      report: () => report({ version: this.env.version, slide: this.slide, lastSync: this.lastSync,
                             online: this.transport !== "offline", displayState: this.displayState,
                             capture: canCapture(), recovered: this.recovered, evacAck: this.evacAck,
                             evacBundle: this.evac?.bundle?.version, evacAudio: this.evacAudio }),
      onMessage: (m) => void this.handle(m, token),
      onTransport: (tr) => {
        if (tr !== this.transport) {
          log("info", `connection: ${tr}`);
          // back online: catch up on the evacuation state at once
          if (this.transport === "offline" || this.transport === "connecting") void this.loadEvac(token);
        }
        this.transport = tr;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (at) => { this.lastSync = at; },
    });
    this.conn.start();
  }

  private async handle(msg: Message, token: string): Promise<void> {
    log("info", `message: ${msg.type}`);
    switch (msg.type) {
      case "config.changed":
        try {
          this.config = await fetchConfig(this.env.api, token);
          setConfig(this.config);
          this.lastSync = Date.now();
          this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds);
          this.applySettings();
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
      case "data.changed":
        await this.loadWidgetData(token);
        break;
      case "schedule.changed":
        await this.loadSchedule(token);
        break;
      case "evac.state":
        this.evac?.offer(msg.data as unknown as EvacPayload, this.transport);
        break;
      case "evac.bundle":
        void this.loadEvac(token);
        break;
      case "evac.selftest": {
        if (!this.evac) break;
        await this.loadEvac(token);
        const result = await this.evac.selfTest({ visible: !!msg.data.visible, seconds: Number(msg.data.seconds) || 5 });
        this.evacAudio = result.audio;
        log("info", `evacuation self-test: ${result.ok ? "ok" : "problems"}`);
        await fetch(`${this.env.api}evacuation/selftest/`, {
          method: "POST", headers: { Authorization: `Screen ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify(result),
        }).catch((e) => recordError(`self-test report: ${String(e)}`));
        break;
      }
      case "reload":
        safeReload("requested by staff", { force: true });
        break;
      case "clear_cache":
        await clearCaches();
        safeReload("cache cleared by staff", { force: true });
        break;
      case "test_pattern": {
        const name = this.config?.screen.name ?? "";
        const res = `${Math.round(innerWidth * devicePixelRatio)}×${Math.round(innerHeight * devicePixelRatio)}`;
        this.display.testPattern(name, [`${res} · DPR ${devicePixelRatio}`, `${this.env.version} · ${this.transport}`],
                                 Number(msg.data.seconds) || 30);
        break;
      }
      case "screenshot":
        try {
          await upload(this.env.api, token, "screenshot", await captureScreenshot());
        } catch (err) {
          recordError(`screenshot: ${String(err)}`);
          await upload(this.env.api, token, "screenshot", { error: String(err).slice(0, 280) }).catch(() => undefined);
        }
        break;
      case "logs":
        await upload(this.env.api, token, "logs", { lines: logLines() }).catch((e) => recordError(String(e)));
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
    const speech = [...(this.program?.entries ?? []), ...(this.program?.overlays ?? [])]
      .map((x) => x.speech).filter((u): u is string => !!u);
    if (speech.length) void prefetchSpeech(speech);
  }

  /** The program: "program" elements redraw themselves when the store changes. */
  private async loadSchedule(token: string): Promise<void> {
    try {
      await refreshSchedule(this.env.api, token, this.schedule);
    } catch (err) {
      if (err instanceof Unauthorized) this.unpair();
    }
  }

  /** Custom widget rows: "data" elements redraw themselves when the store changes. */
  private async loadWidgetData(token: string): Promise<void> {
    try {
      await refreshWidgetData(this.env.api, token, this.widgetData);
    } catch (err) {
      if (err instanceof Unauthorized) this.unpair();
    }
  }

  // ---------------------------------------------------------------- evacuation (ADR-0033/0034)
  private makeEvac(token: string): EvacController {
    return new EvacController({
      now: () => this.clock.now(),
      speaker: this.speaker,
      audio: () => ({ enabled: this.config?.display?.audio !== false, volume: this.config?.display?.volume ?? 100 }),
      strings: this.env.strings,
      context: () => ({ vars: this.config ? this.vars() : {}, now: () => this.clock.now(),
                        timezone: this.config?.event.timezone, assets: this.bundle?.assets ?? {},
                        fonts: this.bundle?.fonts ?? {}, nonce: pageNonce(), data: this.widgetData,
                        program: this.schedule,
                        onError: (id, err) => recordError(`evac ${id}: ${String(err)}`) }),
      onRendered: (p, info) => {
        this.evacAck = `${p.seq}:${p.v}`.slice(0, 40);
        log("info", `evacuation: ${p.state}${p.drill ? " (drill)" : ""} #${p.seq} via ${p.via ?? "cache"}`);
        void fetch(`${this.env.api}evacuation/ack/`, {
          method: "POST", headers: { Authorization: `Screen ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ seq: p.seq, v: p.v, state: p.state, drill: p.drill, rendered_at: info.rendered_at,
                                 issued: p.issued ?? null, via: p.via ?? "cache", fallback: info.fallback }),
        }).catch(() => undefined);
      },
      onChange: () => {
        this.updateDisplayState();
        this.shown = "";
        this.show();
      },
    });
  }

  private async loadEvac(token: string): Promise<void> {
    try {
      const res = await fetch(`${this.env.api}evacuation/state/`, { headers: { Authorization: `Screen ${token}` } });
      if (res.status === 401) return this.unpair();
      if (!res.ok) return;
      const body = await res.json() as { enabled: boolean; payload?: EvacPayload | null; bundle?: EvacBundle };
      if (!body.enabled) return;
      this.evac?.setBundle(body.bundle ?? null);
      this.evac?.offer(body.payload, "fetch");
      // the spoken messages of every stage are fetched now, so they play without the server
      const speech = Object.values(body.bundle?.stages ?? {}).map((s) => s.speech).filter((u) => !!u);
      if (speech.length) void prefetchSpeech(speech);
    } catch {
      // offline: the fallback origins and the cached state take over
    }
  }

  /** Without a connection, ask the fallback origins (secondary node, bridge) for the signed alarm state. */
  private async pollFallback(): Promise<void> {
    const b = this.evac?.bundle;
    // no live connection (offline, or still reconnecting after the server went away): ask the fallback origins
    if (["websocket", "sse", "poll"].includes(this.transport) || !b?.fallback_origins.length) return;
    for (const origin of b.fallback_origins) {
      try {
        const res = await fetch(`${origin}/evac/${b.event}/state`, { cache: "no-store" });
        if (!res.ok) continue;
        const body = await res.json() as { sig?: Signed };
        if (body.sig && this.evac?.offerFallback(body.sig)) return;
      } catch {
        // try the next origin
      }
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
      const next = [nextChange(this.program, now, slide), nextOverlayChange(this.program.overlays, now)]
        .filter((n): n is number => n !== null);
      const wait = Math.max(5, Math.min(MAX_WAIT_MS, (next.length ? Math.min(...next) : now + MAX_WAIT_MS) - now));
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
    const audio = { enabled: cfg.display?.audio !== false, volume: cfg.display?.volume ?? 100 };
    // a full-screen announcement or an evacuation hides the overlays and keeps quiet
    const evacuating = !!this.evac?.active;
    const takeover = evacuating || (!!slide && (slide.entry.startsWith("announcement:")
                                                || slide.entry.startsWith("evacuation")));
    this.overlays.update(this.program?.overlays, now, { hidden: takeover, audio });
    // a full-screen announcement speaks once per appearance (after its alert tone, if any)
    const entry = slide ? this.program?.entries.find((e) => e.id === slide?.entry) : undefined;
    if (entry?.speech && audio.enabled && !evacuating) {
      this.speaker.say(`${entry.id}@${slide?.start ?? 0}`, entry.speech, { volume: audio.volume,
                                                                         delayMs: SPEECH_DELAY_MS });
    }
    if (key === this.shown) return;
    if (this.reloadAtNextSlide && this.shown && safeReload(this.reloadAtNextSlide)) return;
    this.reloadAtNextSlide = "";
    this.shown = key;
    log("info", `showing ${this.slide}`);
    try {
      if (!data || !this.bundle) throw new Error("nothing to show");
      this.display.layout(data, {
        vars: this.vars(), now: () => this.clock.now(), timezone: cfg.event.timezone, assets: this.bundle.assets,
        fonts: this.bundle.fonts, reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches, audio,
        nonce: pageNonce(), data: this.widgetData, program: this.schedule,
        onError: (id, err) => recordError(`${id}: ${String(err)}`),
        onLog: (id, message) => log("info", `${id}: ${message}`),
      }, variables);
    } catch (err) {
      if (data) recordError(`render failed, showing the idle slide: ${String(err)}`);
      this.slide = "idle";
      this.display.idle(cfg);
    }
    this.overlays.attach(this.root);
  }

  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  private applySettings(): void {
    const s: DisplaySettings = this.config?.display ?? {};
    applyRoot(this.root, s);
    // the evacuation layer lives outside #player (above the dim overlay) but turns and fits like it
    if (this.evac) applyRoot(this.evac.layer, s);
    this.updateDisplayState();
  }

  private updateDisplayState(): void {
    const s: DisplaySettings = this.config?.display ?? {};
    // an evacuation always wakes the screen (brief §5.2)
    const state = this.evac?.active ? "on"
      : displayState(s, localHHMM(this.clock.now(), this.config?.event.timezone));
    if (state !== this.displayState) log("info", `display ${state}`);
    this.displayState = state;
    applyState(state, s);
  }

  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  private tick(): void {
    const now = Date.now();
    const stalled = now - this.lastTick > TICK_MS * 3;
    this.lastTick = now;
    markAlive(now);
    this.updateDisplayState();
    if (stalled) {
      log("warn", "timers were stalled; resynchronising");
      this.shown = "";
      this.show();
    }
    const daily = this.config?.display?.daily_reload;
    const hhmm = localHHMM(this.clock.now(), this.config?.event.timezone);
    if (daily && hhmm === daily && this.lastDailyReload !== hhmm && performance.now() > 3_600_000) {
      this.lastDailyReload = hhmm;
      this.reloadAtNextSlide = "daily reload";
    }
    if (memoryPressure() && !this.reloadAtNextSlide) this.reloadAtNextSlide = "memory pressure";
  }

  private unpair(): void {
    if (this.housekeeping) clearInterval(this.housekeeping);
    this.housekeeping = null;
    if (this.timer) clearTimeout(this.timer);
    if (this.refresher) clearInterval(this.refresher);
    if (this.dataRefresher) clearInterval(this.dataRefresher);
    if (this.evacTimer) clearInterval(this.evacTimer);
    if (this.fallbackTimer) clearInterval(this.fallbackTimer);
    this.timer = this.refresher = this.dataRefresher = this.evacTimer = this.fallbackTimer = null;
    clearWidgetData();
    this.widgetData.set({});
    clearSchedule();
    this.schedule.set(null);
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
  installLifecycle();
  onErrorStorm(() => safeReload("50 errors within a minute"));
  registerServiceWorker();
  const env = readEnv();
  void new Player(env, document.getElementById("player") as HTMLElement).boot();
}
