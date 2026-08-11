import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, afterEach } from "vitest";

import {
  canonicalStringify,
  sha256Fallback,
  sha256Hex,
} from "../src/report/canonical";
import { parseReport } from "../src/report/validate";
import {
  advanceSelection,
  INITIAL_SELECTION,
  shouldAcceptSelection,
} from "../src/report/selection";

const HERE = fileURLToPath(new URL(".", import.meta.url));

async function loadFixture(name: string): Promise<unknown> {
  const raw = await readFile(resolve(HERE, "fixtures", name), "utf8");
  return JSON.parse(raw) as unknown;
}

async function loadHappy(): Promise<Record<string, unknown>> {
  return (await loadFixture("report.happy.json")) as Record<string, unknown>;
}

describe("parseReport (happy path)", () => {
  it("accepts a well-formed v2 report and verifies the revision", async () => {
    const raw = await loadHappy();
    const result = await parseReport(raw);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value.schema_version).toBe(2);
    expect(result.value.currency).toBe("EUR");
    expect(Object.keys(result.value.tenants).sort()).toEqual([
      "tenant-a",
      "tenant-b",
    ]);
    expect(result.value.tenants["tenant-a"]?.hourly).toHaveLength(24);
    expect(result.value.tenants["tenant-b"]?.hourly).toHaveLength(24);
  });
});

describe("parseReport (fail-closed rejections)", () => {
  it("rejects schema_version !== 2", async () => {
    const raw = (await loadFixture("report.bad-schema.json")) as Record<string, unknown>;
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/schema_version/);
  });

  it("rejects NaN anywhere in the payload", async () => {
    const raw = await loadHappy();
    raw["coverage_seconds"] = Number.NaN;
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/NaN|Infinity/);
  });

  it("rejects Infinity anywhere in the payload", async () => {
    const raw = await loadHappy();
    raw["unpriced_battery_kwh"] = Number.POSITIVE_INFINITY;
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/NaN|Infinity/);
  });

  it("rejects negative numeric fields", async () => {
    const raw = await loadHappy();
    raw["transition_excluded_seconds"] = -1;
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/transition_excluded_seconds/);
  });

  it("rejects an unknown tenant section shape", async () => {
    const raw = await loadHappy();
    const tenants = raw["tenants"] as Record<string, unknown>;
    tenants["tenant-a"] = { unexpected: "shape" };
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/tenant/);
  });

  it("rejects tenant slug with invalid characters", async () => {
    const raw = await loadHappy();
    const tenants = raw["tenants"] as Record<string, unknown>;
    tenants["Tenant A"] = tenants["tenant-a"];
    delete tenants["tenant-a"];
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/slug/);
  });

  it("rejects mismatching revision", async () => {
    const raw = await loadHappy();
    raw["revision"] = "0".repeat(64);
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/revision mismatch/);
  });

  it("rejects a malformed revision string", async () => {
    const raw = await loadHappy();
    raw["revision"] = "not-a-hash";
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/revision/);
  });

  it("rejects malformed hourly row source", async () => {
    const raw = await loadHappy();
    const tenants = raw["tenants"] as Record<string, unknown>;
    const tenantA = tenants["tenant-a"] as Record<string, unknown>;
    const hourly = tenantA["hourly"] as Array<Record<string, unknown>>;
    if (hourly[0] !== undefined) {
      hourly[0]["source"] = "guessed";
    }
    const result = await parseReport(raw);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toMatch(/source/);
  });

  it("rejects null input", async () => {
    const result = await parseReport(null);
    expect(result.ok).toBe(false);
  });
});

describe("selection guard", () => {
  it("accepts the first non-empty selection", () => {
    expect(
      shouldAcceptSelection(INITIAL_SELECTION, "2026-06-16T00:00:05Z"),
    ).toBe(true);
  });

  it("accepts a newer finalized_as_of and discards the older one", () => {
    const previous = { finalizedAsOf: "2026-06-15T00:00:00Z" };
    expect(shouldAcceptSelection(previous, "2026-06-16T00:00:05Z")).toBe(true);
    const next = advanceSelection(previous, "2026-06-16T00:00:05Z");
    expect(next.finalizedAsOf).toBe("2026-06-16T00:00:05Z");
  });

  it("rejects an older finalized_as_of after a newer one has been rendered", () => {
    const previous = { finalizedAsOf: "2026-06-16T00:00:05Z" };
    expect(shouldAcceptSelection(previous, "2026-06-15T00:00:00Z")).toBe(false);
    const next = advanceSelection(previous, "2026-06-15T00:00:00Z");
    expect(next.finalizedAsOf).toBe("2026-06-16T00:00:05Z");
  });

  it("rejects an equal finalized_as_of (strict monotonic)", () => {
    const previous = { finalizedAsOf: "2026-06-16T00:00:05Z" };
    expect(shouldAcceptSelection(previous, "2026-06-16T00:00:05Z")).toBe(false);
  });

  it("rejects a non-UTC finalized_as_of", () => {
    const previous = { finalizedAsOf: null };
    expect(shouldAcceptSelection(previous, "2026-06-16T02:00:05+02:00")).toBe(
      false,
    );
  });
});

describe("canonical stringifier", () => {
  it("sorts object keys recursively and omits whitespace", () => {
    const value = { b: 1, a: { z: 2, y: 3 } };
    expect(canonicalStringify(value)).toBe(`{"a":{"y":3,"z":2},"b":1}`);
  });

  it("throws on NaN and Infinity", () => {
    expect(() => canonicalStringify({ n: Number.NaN })).toThrow();
    expect(() => canonicalStringify({ n: Number.POSITIVE_INFINITY })).toThrow();
  });
});

describe("sha256 backends", () => {
  const originalCrypto = globalThis.crypto;

  afterEach(() => {
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: originalCrypto,
    });
  });

  it("agrees with the WebCrypto backend when available", async () => {
    const digest = await sha256Hex("hello world");
    expect(digest).toBe(
      "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
    );
  });

  it("falls back to the pure-JS SHA-256 when subtle is missing", async () => {
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: {},
    });
    const digest = await sha256Hex("hello world");
    expect(digest).toBe(
      "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
    );
    const bytes = new TextEncoder().encode("hello world");
    expect(sha256Fallback(bytes)).toBe(digest);
  });

  it("hashes an empty string identically on both backends", async () => {
    const digestNative = await sha256Hex("");
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: {},
    });
    const digestFallback = await sha256Hex("");
    expect(digestNative).toBe(digestFallback);
    expect(digestFallback).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });
});
