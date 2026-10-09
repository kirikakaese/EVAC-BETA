// SPDX-License-Identifier: AGPL-3.0-or-later
// Remote management: a screenshot of what the screen really shows (screen capture of this tab; kiosks set up
// with deploy/kiosk allow it without a prompt), the log buffer, and clearing every cache.

export function canCapture(): boolean {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia;
}

function withTimeout<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${what} timed out`)), ms);
    p.then((v) => { clearTimeout(timer); resolve(v); }, (e) => { clearTimeout(timer); reject(e); });
  });
}

/** One frame of this tab as JPEG. Throws when the browser does not allow capturing (or takes over 10 s). */
export async function captureScreenshot(timeoutMs = 10_000): Promise<Blob> {
  return withTimeout(capture(), timeoutMs, "screen capture");
}

async function capture(): Promise<Blob> {
  if (!canCapture()) throw new Error("screen capture is not available in this browser");
  // a tab capture only delivers frames when the page repaints; a still slide would never produce the first
  // frame. A practically invisible 1 px dot that changes every frame guarantees one.
  const dot = document.createElement("div");
  dot.className = "evac-capture-dot";
  document.body.appendChild(dot);
  let n = 0;
  const flicker = setInterval(() => dot.classList.toggle("on", n++ % 2 === 0), 16);
  try {
    return await captureFrame();
  } finally {
    clearInterval(flicker);
    dot.remove();
  }
}

async function captureFrame(): Promise<Blob> {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "browser" }, audio: false, preferCurrentTab: true, selfBrowserSurface: "include",
  } as DisplayMediaStreamOptions);
  try {
    const video = document.createElement("video");
    video.muted = true;
    video.srcObject = stream;
    await video.play();
    // wait until a frame is decoded (rAF would stall in a hidden tab)
    if (!video.videoWidth) await new Promise((r) => video.addEventListener("loadeddata", r, { once: true }));
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || window.innerWidth;
    canvas.height = video.videoHeight || window.innerHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    video.srcObject = null;
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encoding failed"))), "image/jpeg", 0.85));
  } finally {
    stream.getTracks().forEach((t) => t.stop());
  }
}

export async function upload(api: string, token: string, kind: string, body: Blob | object): Promise<void> {
  const isBlob = typeof Blob !== "undefined" && body instanceof Blob;
  await fetch(`${api}upload/${kind}/`, {
    method: "POST", credentials: "omit", cache: "no-store",
    headers: { Authorization: `Screen ${token}`, "Content-Type": isBlob ? (body as Blob).type : "application/json" },
    body: isBlob ? (body as Blob) : JSON.stringify(body),
  });
}

/** Delete cached files, the content bundle and program, and the service worker (the device token stays). */
export async function clearCaches(): Promise<void> {
  try {
    if (typeof caches !== "undefined") for (const key of await caches.keys()) await caches.delete(key);
  } catch { /* ignore */ }
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("evac.player.") && key !== "evac.player.token") localStorage.removeItem(key);
    }
  } catch { /* ignore */ }
  try {
    for (const reg of (await navigator.serviceWorker?.getRegistrations?.()) ?? []) await reg.unregister();
  } catch { /* ignore */ }
}
