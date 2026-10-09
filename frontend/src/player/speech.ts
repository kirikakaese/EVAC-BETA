// SPDX-License-Identifier: AGPL-3.0-or-later
// Spoken announcements (ADR-0022): files rendered on the server by Piper, played once per appearance, one after
// the other. The service worker caches them (they are named by a hash), so they also play offline.

export interface SayOptions { volume?: number; delayMs?: number }

type AudioFactory = (url: string) => HTMLAudioElement;

export class Speaker {
  private spoken = new Set<string>();
  private queue: { url: string; volume: number }[] = [];
  private playing = false;

  constructor(private make: AudioFactory = (url) => new Audio(url)) {}

  /** Speak ``url`` once for ``key`` (an announcement occurrence); later calls with the same key do nothing. */
  say(key: string, url: string, opts: SayOptions = {}): boolean {
    if (!url || this.spoken.has(key)) return false;
    this.spoken.add(key);
    if (this.spoken.size > 500) this.spoken = new Set([...this.spoken].slice(-100));
    const item = { url, volume: Math.max(0, Math.min(1, (opts.volume ?? 100) / 100)) };
    setTimeout(() => { this.queue.push(item); this.next(); }, opts.delayMs ?? 0);
    return true;
  }

  get busy(): boolean { return this.playing; }

  private next(): void {
    if (this.playing) return;
    const item = this.queue.shift();
    if (!item) return;
    this.playing = true;
    const audio = this.make(item.url);
    audio.volume = item.volume;
    const done = (): void => { this.playing = false; this.next(); };
    audio.addEventListener("ended", done, { once: true });
    audio.addEventListener("error", done, { once: true });
    const started = audio.play();
    if (started && typeof started.catch === "function") started.catch(done);  // autoplay blocked: skip
  }
}

/** Fetch every spoken file of the program once, so the service worker has it for offline playback. */
export async function prefetchSpeech(urls: string[]): Promise<number> {
  let ok = 0;
  await Promise.all([...new Set(urls)].map(async (u) => {
    try {
      const res = await fetch(u, { credentials: "omit" });
      if (res.ok) ok += 1;
      await res.body?.cancel();
    } catch {
      /* offline: the next program refresh retries */
    }
  }));
  return ok;
}
