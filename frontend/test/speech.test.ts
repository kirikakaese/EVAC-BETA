// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverlayLayer, SPEECH_DELAY_MS, type Overlay } from "../src/player/overlays";
import { prefetchSpeech, Speaker } from "../src/player/speech";

class FakeAudio extends EventTarget {
  volume = 1;
  static played: string[] = [];
  static fail = false;
  constructor(public src: string) { super(); }
  play(): Promise<void> {
    if (FakeAudio.fail) return Promise.reject(new Error("NotAllowedError"));
    FakeAudio.played.push(this.src);
    return Promise.resolve();
  }
  end(): void { this.dispatchEvent(new Event("ended")); }
}

describe("spoken announcements", () => {
  afterEach(() => { vi.useRealTimers(); FakeAudio.played = []; FakeAudio.fail = false; vi.unstubAllGlobals(); });

  it("speaks each occurrence once, one after the other", async () => {
    vi.useFakeTimers();
    const made: FakeAudio[] = [];
    const s = new Speaker((url) => { const a = new FakeAudio(url); made.push(a); return a as unknown as HTMLAudioElement; });
    expect(s.say("a@1", "/a.m4a", { volume: 50 })).toBe(true);
    expect(s.say("a@1", "/a.m4a")).toBe(false);
    expect(s.say("b@1", "/b.m4a", { delayMs: 100 })).toBe(true);
    expect(s.say("c@1", "")).toBe(false);
    vi.advanceTimersByTime(0);
    expect(FakeAudio.played).toEqual(["/a.m4a"]);
    expect(made[0].volume).toBe(0.5);
    expect(s.busy).toBe(true);
    vi.advanceTimersByTime(100);
    expect(FakeAudio.played).toEqual(["/a.m4a"]);  // waits for the first to end
    made[0].end();
    expect(FakeAudio.played).toEqual(["/a.m4a", "/b.m4a"]);
    made[1].dispatchEvent(new Event("error"));
    expect(s.busy).toBe(false);
  });

  it("skips when autoplay is blocked", async () => {
    vi.useFakeTimers();
    FakeAudio.fail = true;
    const s = new Speaker((url) => new FakeAudio(url) as unknown as HTMLAudioElement);
    s.say("x@1", "/x.m4a");
    vi.advanceTimersByTime(0);
    await Promise.resolve();
    await Promise.resolve();
    expect(s.busy).toBe(false);
  });

  it("overlays speak after their sound, also when the file arrives later", () => {
    const say = vi.fn();
    const layer = new OverlayLayer({ say } as unknown as Speaker);
    const ov: Overlay = { id: "a", style: "banner", rank: 1, level: "Urgent", colour: "#dc2626", sound: "none",
                          title: "T", text: "x", windows: [[0, 100]] };
    layer.update([ov], 10, { audio: { enabled: true, volume: 80 } });
    expect(say).not.toHaveBeenCalled();
    layer.update([{ ...ov, speech: "/s.m4a" }], 11, { audio: { enabled: true, volume: 80 } });
    expect(say).toHaveBeenCalledWith("a@0", "/s.m4a", { volume: 80, delayMs: 0 });
    vi.stubGlobal("AudioContext", undefined);
    layer.update([{ ...ov, id: "b", sound: "chime", speech: "/b.m4a" }], 12, { audio: { enabled: true, volume: 80 } });
    expect(say).toHaveBeenLastCalledWith("b@0", "/b.m4a", { volume: 80, delayMs: SPEECH_DELAY_MS });
    say.mockClear();
    layer.update([{ ...ov, id: "c", speech: "/c.m4a" }], 13, { audio: { enabled: false, volume: 80 } });
    expect(say).not.toHaveBeenCalled();  // sound switched off for this screen
  });

  it("prefetches spoken files for offline playback", async () => {
    const fetchMock = vi.fn(async (u: string) => (u.includes("bad") ? Promise.reject(new Error("offline"))
      : { ok: true, body: { cancel: async () => undefined } }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await prefetchSpeech(["/a", "/a", "/bad"])).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
