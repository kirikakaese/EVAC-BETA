// SPDX-License-Identifier: AGPL-3.0-or-later
// Ed25519 signature verification (RFC 8032) and SHA-512 (FIPS 180-4) in plain TypeScript, so a screen can check
// alarm messages from fallback origins even where WebCrypto is missing (insecure LAN origins, older kiosks).
// Verification only: screens never hold a private key (ADR-0003). Small and not constant-time: it only handles
// public data.

const MASK64 = (1n << 64n) - 1n;
const K512 = [
  "428a2f98d728ae22", "7137449123ef65cd", "b5c0fbcfec4d3b2f", "e9b5dba58189dbbc", "3956c25bf348b538",
  "59f111f1b605d019", "923f82a4af194f9b", "ab1c5ed5da6d8118", "d807aa98a3030242", "12835b0145706fbe",
  "243185be4ee4b28c", "550c7dc3d5ffb4e2", "72be5d74f27b896f", "80deb1fe3b1696b1", "9bdc06a725c71235",
  "c19bf174cf692694", "e49b69c19ef14ad2", "efbe4786384f25e3", "0fc19dc68b8cd5b5", "240ca1cc77ac9c65",
  "2de92c6f592b0275", "4a7484aa6ea6e483", "5cb0a9dcbd41fbd4", "76f988da831153b5", "983e5152ee66dfab",
  "a831c66d2db43210", "b00327c898fb213f", "bf597fc7beef0ee4", "c6e00bf33da88fc2", "d5a79147930aa725",
  "06ca6351e003826f", "142929670a0e6e70", "27b70a8546d22ffc", "2e1b21385c26c926", "4d2c6dfc5ac42aed",
  "53380d139d95b3df", "650a73548baf63de", "766a0abb3c77b2a8", "81c2c92e47edaee6", "92722c851482353b",
  "a2bfe8a14cf10364", "a81a664bbc423001", "c24b8b70d0f89791", "c76c51a30654be30", "d192e819d6ef5218",
  "d69906245565a910", "f40e35855771202a", "106aa07032bbd1b8", "19a4c116b8d2d0c8", "1e376c085141ab53",
  "2748774cdf8eeb99", "34b0bcb5e19b48a8", "391c0cb3c5c95a63", "4ed8aa4ae3418acb", "5b9cca4f7763e373",
  "682e6ff3d6b2b8a3", "748f82ee5defb2fc", "78a5636f43172f60", "84c87814a1f0ab72", "8cc702081a6439ec",
  "90befffa23631e28", "a4506cebde82bde9", "bef9a3f7b2c67915", "c67178f2e372532b", "ca273eceea26619c",
  "d186b8c721c0c207", "eada7dd6cde0eb1e", "f57d4f7fee6ed178", "06f067aa72176fba", "0a637dc5a2c898a6",
  "113f9804bef90dae", "1b710b35131c471b", "28db77f523047d84", "32caab7b40c72493", "3c9ebe0a15c9bebc",
  "431d67c49c100d4c", "4cc5d4becb3e42b6", "597f299cfc657e2a", "5fcb6fab3ad6faec", "6c44198c4a475817",
].map((h) => BigInt(`0x${h}`));
const H512 = ["6a09e667f3bcc908", "bb67ae8584caa73b", "3c6ef372fe94f82b", "a54ff53a5f1d36f1", "510e527fade682d1",
  "9b05688c2b3e6c1f", "1f83d9abfb41bd6b", "5be0cd19137e2179"].map((h) => BigInt(`0x${h}`));

const rotr = (x: bigint, n: bigint): bigint => ((x >> n) | (x << (64n - n))) & MASK64;

export function sha512(msg: Uint8Array): Uint8Array {
  const bitLen = BigInt(msg.length) * 8n;
  const padLen = (msg.length + 17 + 127) & ~127;
  const buf = new Uint8Array(padLen);
  buf.set(msg);
  buf[msg.length] = 0x80;
  for (let i = 0; i < 16; i++) buf[padLen - 1 - i] = Number((bitLen >> BigInt(8 * i)) & 0xffn);
  const h = [...H512];
  const w = new Array<bigint>(80);
  for (let off = 0; off < padLen; off += 128) {
    for (let i = 0; i < 16; i++) {
      let v = 0n;
      for (let j = 0; j < 8; j++) v = (v << 8n) | BigInt(buf[off + i * 8 + j]);
      w[i] = v;
    }
    for (let i = 16; i < 80; i++) {
      const s0 = rotr(w[i - 15], 1n) ^ rotr(w[i - 15], 8n) ^ (w[i - 15] >> 7n);
      const s1 = rotr(w[i - 2], 19n) ^ rotr(w[i - 2], 61n) ^ (w[i - 2] >> 6n);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & MASK64;
    }
    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 80; i++) {
      const S1 = rotr(e, 14n) ^ rotr(e, 18n) ^ rotr(e, 41n);
      const ch = (e & f) ^ (~e & MASK64 & g);
      const t1 = (hh + S1 + ch + K512[i] + w[i]) & MASK64;
      const S0 = rotr(a, 28n) ^ rotr(a, 34n) ^ rotr(a, 39n);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) & MASK64;
      hh = g; g = f; f = e; e = (d + t1) & MASK64; d = c; c = b; b = a; a = (t1 + t2) & MASK64;
    }
    [a, b, c, d, e, f, g, hh].forEach((v, i) => { h[i] = (h[i] + v) & MASK64; });
  }
  const out = new Uint8Array(64);
  h.forEach((v, i) => { for (let j = 0; j < 8; j++) out[i * 8 + j] = Number((v >> BigInt(56 - 8 * j)) & 0xffn); });
  return out;
}

// ---------------------------------------------------------------- curve25519 (twisted Edwards form)
const P = (1n << 255n) - 19n;
const L = (1n << 252n) + 27742317777372353535851937790883648493n;
const mod = (a: bigint, m = P): bigint => { const r = a % m; return r >= 0n ? r : r + m; };
function pow(b: bigint, e: bigint, m = P): bigint {
  let r = 1n;
  b = mod(b, m);
  while (e > 0n) {
    if (e & 1n) r = (r * b) % m;
    b = (b * b) % m;
    e >>= 1n;
  }
  return r;
}
const inv = (a: bigint): bigint => pow(a, P - 2n);
const D = mod(-121665n * inv(121666n));
const SQRT_M1 = pow(2n, (P - 1n) / 4n);

type Point = [bigint, bigint, bigint, bigint]; // extended coordinates X, Y, Z, T
const ZERO: Point = [0n, 1n, 1n, 0n];

function add(p: Point, q: Point): Point {
  const [x1, y1, z1, t1] = p;
  const [x2, y2, z2, t2] = q;
  const a = mod((y1 - x1) * (y2 - x2));
  const b = mod((y1 + x1) * (y2 + x2));
  const c = mod(2n * D * t1 * t2);
  const d = mod(2n * z1 * z2);
  const e = b - a, f = d - c, g = d + c, h = b + a;
  return [mod(e * f), mod(g * h), mod(f * g), mod(e * h)];
}

function mul(p: Point, n: bigint): Point {
  let r = ZERO;
  let q = p;
  while (n > 0n) {
    if (n & 1n) r = add(r, q);
    q = add(q, q);
    n >>= 1n;
  }
  return r;
}

const leInt = (b: Uint8Array): bigint => b.reduceRight((acc, v) => (acc << 8n) | BigInt(v), 0n);

function decompress(bytes: Uint8Array): Point | null {
  if (bytes.length !== 32) return null;
  const sign = (bytes[31] & 0x80) !== 0;
  const yb = bytes.slice();
  yb[31] &= 0x7f;
  const y = leInt(yb);
  if (y >= P) return null;
  const y2 = mod(y * y);
  const u = mod(y2 - 1n), v = mod(D * y2 + 1n);
  let x = mod(u * pow(v, 3n) * pow(u * pow(v, 7n), (P - 5n) / 8n));
  const vx2 = mod(v * x * x);
  if (vx2 === mod(-u)) x = mod(x * SQRT_M1);
  else if (vx2 !== u) return null;
  if (x === 0n && sign) return null;
  if ((x & 1n) === 1n) { if (!sign) x = P - x; } else if (sign) x = P - x;
  return [x, y, 1n, mod(x * y)];
}

function compress(p: Point): Uint8Array {
  const zi = inv(p[2]);
  const x = mod(p[0] * zi), y = mod(p[1] * zi);
  const out = new Uint8Array(32);
  let v = y;
  for (let i = 0; i < 32; i++) { out[i] = Number(v & 0xffn); v >>= 8n; }
  if (x & 1n) out[31] |= 0x80;
  return out;
}

const BASE = decompress(Uint8Array.from([0x58, ...new Array<number>(31).fill(0x66)])) as Point;

/** True when ``signature`` (64 bytes) is a valid Ed25519 signature of ``message`` by ``publicKey`` (32 bytes). */
export function verify(publicKey: Uint8Array, message: Uint8Array, signature: Uint8Array): boolean {
  if (signature.length !== 64 || publicKey.length !== 32) return false;
  const A = decompress(publicKey);
  const R = decompress(signature.slice(0, 32));
  const S = leInt(signature.slice(32));
  if (!A || !R || S >= L) return false;
  const h = sha512(Uint8Array.from([...signature.slice(0, 32), ...publicKey, ...message]));
  const k = mod(leInt(h), L);
  const left = compress(mul(BASE, S));
  const right = compress(add(R, mul(A, k)));
  return left.every((b, i) => b === right[i]);
}

export function b64url(text: string): Uint8Array {
  const s = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4);
  const bin = atob(s);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

export interface Signed { kid: string; m: string; s: string }

/** The signed core when one of ``keys`` (base64url) verifies it, else null. */
export function verifySigned(keys: string[], sig: Signed | undefined | null): Record<string, unknown> | null {
  if (!sig || typeof sig.m !== "string" || typeof sig.s !== "string") return null;
  const msg = new TextEncoder().encode(sig.m);
  for (const k of keys) {
    try {
      if (verify(b64url(k), msg, b64url(sig.s))) return JSON.parse(sig.m) as Record<string, unknown>;
    } catch {
      // malformed key or signature: try the next key
    }
  }
  return null;
}
