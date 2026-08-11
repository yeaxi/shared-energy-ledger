/**
 * Deterministic stringifier used to recompute the report revision hash on the
 * card side. It mirrors the Python `report.canonical_json` contract:
 *
 * - Object keys are sorted lexicographically (recursively).
 * - No insignificant whitespace between tokens.
 * - `NaN` and `Infinity` are refused; the caller receives a thrown Error and
 *   MUST propagate that as `unavailable` (invariants I1, I10).
 * - Undefined values and functions are refused; they never belong in the
 *   report envelope.
 *
 * The stringifier operates on a *canonical body*, i.e. the report envelope
 * with the `revision` field removed. The hash is computed over the UTF-8
 * bytes of the string returned here.
 */

export class CanonicalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CanonicalError";
  }
}

export type CanonicalValue =
  | null
  | boolean
  | number
  | string
  | readonly CanonicalValue[]
  | { readonly [key: string]: CanonicalValue };

function encodeString(value: string): string {
  return JSON.stringify(value);
}

function encodeNumber(value: number): string {
  if (!Number.isFinite(value)) {
    throw new CanonicalError(`Non-finite number rejected: ${String(value)}`);
  }
  const encoded = JSON.stringify(value);
  if (encoded === undefined) {
    throw new CanonicalError("Number could not be encoded");
  }
  return encoded;
}

function encode(value: unknown): string {
  if (value === null) {
    return "null";
  }
  const kind = typeof value;
  if (kind === "boolean") {
    return value ? "true" : "false";
  }
  if (kind === "number") {
    return encodeNumber(value as number);
  }
  if (kind === "string") {
    return encodeString(value as string);
  }
  if (kind === "undefined") {
    throw new CanonicalError("undefined is not allowed in canonical bodies");
  }
  if (kind === "function" || kind === "symbol" || kind === "bigint") {
    throw new CanonicalError(`Unsupported value kind '${kind}' in canonical bodies`);
  }
  if (Array.isArray(value)) {
    const parts = value.map((item) => encode(item));
    return `[${parts.join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  const parts: string[] = [];
  for (const key of keys) {
    const raw = record[key];
    if (raw === undefined) {
      continue;
    }
    parts.push(`${encodeString(key)}:${encode(raw)}`);
  }
  return `{${parts.join(",")}}`;
}

/**
 * Serialize `body` into the canonical string form used for the revision hash.
 * The caller MUST have already stripped the `revision` field.
 */
export function canonicalStringify(body: CanonicalValue): string {
  return encode(body);
}

/**
 * SHA-256 hash of an ASCII/UTF-8 string, returned as a lower-case hex digest.
 *
 * The primary path uses the WebCrypto API (`crypto.subtle.digest`). Some
 * runtimes (older Node testing environments, sandboxed workers) do not expose
 * `crypto.subtle`; in that case we fall back to a small, self-contained
 * SHA-256 implementation so that the card can still verify report revisions
 * in a hostile environment. Both paths are covered by the unit tests.
 */
export async function sha256Hex(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const subtle = getSubtleCrypto();
  if (subtle !== null) {
    const digest = await subtle.digest("SHA-256", bytes);
    return bytesToHex(new Uint8Array(digest));
  }
  return sha256Fallback(bytes);
}

function getSubtleCrypto(): SubtleCrypto | null {
  try {
    const cryptoObj = (globalThis as { crypto?: Crypto }).crypto;
    if (cryptoObj && typeof cryptoObj.subtle?.digest === "function") {
      return cryptoObj.subtle;
    }
  } catch {
    return null;
  }
  return null;
}

function bytesToHex(bytes: Uint8Array): string {
  const chars = new Array<string>(bytes.length);
  for (let i = 0; i < bytes.length; i++) {
    const byte = bytes[i] ?? 0;
    chars[i] = byte.toString(16).padStart(2, "0");
  }
  return chars.join("");
}

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotr(x: number, n: number): number {
  return ((x >>> n) | (x << (32 - n))) >>> 0;
}

export function sha256Fallback(input: Uint8Array): string {
  const bitLen = input.length * 8;
  const padLen = ((input.length + 9 + 63) >> 6) << 6;
  const padded = new Uint8Array(padLen);
  padded.set(input);
  padded[input.length] = 0x80;
  const high = Math.floor(bitLen / 0x100000000);
  const low = bitLen >>> 0;
  const dv = new DataView(padded.buffer);
  dv.setUint32(padLen - 8, high);
  dv.setUint32(padLen - 4, low);

  const H = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
    0x1f83d9ab, 0x5be0cd19,
  ]);
  const W = new Uint32Array(64);

  for (let block = 0; block < padLen; block += 64) {
    for (let i = 0; i < 16; i++) {
      W[i] = dv.getUint32(block + i * 4);
    }
    for (let i = 16; i < 64; i++) {
      const w15 = W[i - 15] ?? 0;
      const w2 = W[i - 2] ?? 0;
      const s0 = rotr(w15, 7) ^ rotr(w15, 18) ^ (w15 >>> 3);
      const s1 = rotr(w2, 17) ^ rotr(w2, 19) ^ (w2 >>> 10);
      W[i] = ((W[i - 16] ?? 0) + s0 + (W[i - 7] ?? 0) + s1) >>> 0;
    }
    let a = H[0] ?? 0;
    let b = H[1] ?? 0;
    let c = H[2] ?? 0;
    let d = H[3] ?? 0;
    let e = H[4] ?? 0;
    let f = H[5] ?? 0;
    let g = H[6] ?? 0;
    let h = H[7] ?? 0;
    for (let i = 0; i < 64; i++) {
      const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + s1 + ch + (K[i] ?? 0) + (W[i] ?? 0)) >>> 0;
      const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (s0 + maj) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }
    H[0] = ((H[0] ?? 0) + a) >>> 0;
    H[1] = ((H[1] ?? 0) + b) >>> 0;
    H[2] = ((H[2] ?? 0) + c) >>> 0;
    H[3] = ((H[3] ?? 0) + d) >>> 0;
    H[4] = ((H[4] ?? 0) + e) >>> 0;
    H[5] = ((H[5] ?? 0) + f) >>> 0;
    H[6] = ((H[6] ?? 0) + g) >>> 0;
    H[7] = ((H[7] ?? 0) + h) >>> 0;
  }

  const out = new Uint8Array(32);
  const outView = new DataView(out.buffer);
  for (let i = 0; i < 8; i++) {
    outView.setUint32(i * 4, H[i] ?? 0);
  }
  return bytesToHex(out);
}
