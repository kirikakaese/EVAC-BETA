// SPDX-License-Identifier: AGPL-3.0-or-later
// NTP-like offset between this device and the server: offset = server - (send + receive) / 2.
// Several samples are kept and the one with the smallest round trip wins (least network noise).

interface Sample { offset: number; rtt: number }

export class Clock {
  private samples: Sample[] = [];
  offset = 0;

  add(sentAt: number, receivedAt: number, serverSeconds: number): void {
    const rtt = receivedAt - sentAt;
    if (rtt < 0 || !Number.isFinite(serverSeconds)) return;
    this.samples.push({ offset: serverSeconds * 1000 - (sentAt + receivedAt) / 2, rtt });
    if (this.samples.length > 8) this.samples.shift();
    this.offset = this.samples.reduce((best, s) => (s.rtt < best.rtt ? s : best)).offset;
  }

  now(): number {
    return Date.now() + this.offset;
  }
}
