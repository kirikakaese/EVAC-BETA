// SPDX-License-Identifier: AGPL-3.0-or-later
// Server connection of a paired screen: WebSocket first, then SSE (read with fetch so the token travels in a
// header), then long-poll. Heartbeats go over the WebSocket when it is up, otherwise over HTTP. Messages carry
// a sequence number; after a reconnect the player resumes from the last one it saw.

import { request, Unauthorized } from "./api";
import { Clock } from "./clock";

export type Transport = "connecting" | "websocket" | "sse" | "poll" | "offline";

export interface Message { seq: number; type: string; data: Record<string, unknown>; ts: number }

export interface ConnectionOptions {
  api: string;
  ws: string;
  token: string;
  clock: Clock;
  heartbeatSeconds: number;
  since: number;
  report: () => Record<string, unknown>;
  onMessage: (msg: Message) => void;
  onTransport: (t: Transport) => void;
  onUnauthorized: () => void;
  onSync: (at: number) => void;
}

const MAX_BACKOFF = 30000;
const WS_RETRY_FROM_FALLBACK = 300000;

export class Connection {
  private ws: WebSocket | null = null;
  private seq: number;
  private transport: Transport = "connecting";
  private wsFailures = 0;
  private backoff = 1000;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private pendingBeat: number | null = null;
  private stopped = false;
  private fallbackSince = 0;
  private abort: AbortController | null = null;

  constructor(private o: ConnectionOptions) {
    this.seq = o.since;
  }

  start(): void {
    this.stopped = false;
    this.heartbeatTimer = setInterval(() => this.beat(), Math.max(2, this.o.heartbeatSeconds) * 1000);
    if (typeof WebSocket === "undefined") this.fallback();
    else this.openWebSocket();
  }

  stop(): void {
    this.stopped = true;
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.abort?.abort();
    this.ws?.close();
  }

  setHeartbeat(seconds: number): void {
    if (seconds === this.o.heartbeatSeconds || !this.heartbeatTimer) return;
    this.o.heartbeatSeconds = seconds;
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = setInterval(() => this.beat(), Math.max(2, seconds) * 1000);
  }

  private setTransport(t: Transport): void {
    if (t !== this.transport) {
      this.transport = t;
      this.o.onTransport(t);
    }
  }

  private deliver(msg: Message): void {
    if (typeof msg.seq === "number") {
      if (msg.seq <= this.seq) return;
      this.seq = msg.seq;
    }
    if (msg.type === "revoked") {
      this.stop();
      this.o.onUnauthorized();
      return;
    }
    this.o.onMessage(msg);
  }

  private retry(fn: () => void): void {
    if (this.stopped) return;
    const delay = this.backoff + Math.random() * 500;
    this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF);
    setTimeout(() => !this.stopped && fn(), delay);
  }

  // ---------------------------------------------------------------- WebSocket
  private openWebSocket(): void {
    let opened = false;
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.o.ws);
    } catch {
      this.fallback();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      opened = true;
      ws.send(JSON.stringify({ type: "auth", token: this.o.token, since: this.seq }));
    };
    ws.onmessage = (ev) => {
      let msg: Message & { type: string; server_time?: number; seq: number };
      try {
        msg = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (msg.type === "hello") {
        this.wsFailures = 0;
        this.backoff = 1000;
        this.setTransport("websocket");
        this.beat();
      } else if (msg.type === "heartbeat.ack") {
        this.ack(msg.server_time ?? NaN);
      } else if (msg.type !== "pong") {
        this.deliver(msg);
      }
    };
    ws.onclose = (ev) => {
      this.ws = null;
      if (this.stopped) return;
      if (ev.code === 4401) {
        this.stop();
        this.o.onUnauthorized();
        return;
      }
      if (!opened) this.wsFailures += 1;
      if (this.wsFailures >= 2) this.fallback();
      else {
        this.setTransport("connecting");
        this.retry(() => this.openWebSocket());
      }
    };
  }

  // ---------------------------------------------------------------- SSE and long-poll fallbacks
  private fallback(): void {
    this.fallbackSince = Date.now();
    void this.sse();
  }

  private maybeBackToWebSocket(): boolean {
    if (typeof WebSocket !== "undefined" && Date.now() - this.fallbackSince > WS_RETRY_FROM_FALLBACK) {
      this.wsFailures = 0;
      this.openWebSocket();
      return true;
    }
    return false;
  }

  private async sse(): Promise<void> {
    if (this.stopped || this.maybeBackToWebSocket()) return;
    this.abort = new AbortController();
    try {
      const res = await fetch(`${this.o.api}stream/?since=${this.seq}`, {
        headers: { Authorization: `Screen ${this.o.token}`, Accept: "text/event-stream" },
        signal: this.abort.signal, cache: "no-store", credentials: "omit",
      });
      if (res.status === 401) throw new Unauthorized("token rejected");
      if (!res.ok || !res.body) throw new Error(`SSE HTTP ${res.status}`);
      this.setTransport("sse");
      this.backoff = 1000;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const data = block.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
          if (data) {
            try {
              this.deliver(JSON.parse(data));
            } catch {
              /* ignore malformed event */
            }
          }
        }
      }
      void this.sse();
    } catch (err) {
      if (err instanceof Unauthorized) {
        this.stop();
        this.o.onUnauthorized();
      } else if (!this.stopped) {
        void this.poll();
      }
    }
  }

  private async poll(): Promise<void> {
    if (this.stopped || this.maybeBackToWebSocket()) return;
    try {
      const res = await request<{ messages: Message[] }>(this.o.api, `poll/?since=${this.seq}&wait=10`,
                                                           { token: this.o.token, timeout: 20000 });
      this.setTransport("poll");
      this.backoff = 1000;
      res.messages.forEach((m) => this.deliver(m));
      void this.poll();
    } catch (err) {
      if (err instanceof Unauthorized) {
        this.stop();
        this.o.onUnauthorized();
        return;
      }
      this.setTransport("offline");
      this.retry(() => void this.sse());
    }
  }

  // ---------------------------------------------------------------- heartbeat + time sync
  private ack(serverTime: number): void {
    if (this.pendingBeat !== null) {
      const now = Date.now();
      this.o.clock.add(this.pendingBeat, now, serverTime);
      this.pendingBeat = null;
      this.o.onSync(now);
    }
  }

  beat(): void {
    if (this.stopped) return;
    const data = this.o.report();
    this.pendingBeat = Date.now();
    if (this.ws && this.ws.readyState === WebSocket.OPEN && this.transport === "websocket") {
      this.ws.send(JSON.stringify({ type: "heartbeat", data }));
      return;
    }
    request<{ server_time: number }>(this.o.api, "heartbeat/", { method: "POST", token: this.o.token,
                                                                 body: JSON.stringify({ data }) })
      .then((r) => this.ack(r.server_time))
      .catch((err) => {
        if (err instanceof Unauthorized) {
          this.stop();
          this.o.onUnauthorized();
        } else if (this.transport !== "websocket") {
          this.setTransport("offline");
        }
      });
  }
}
