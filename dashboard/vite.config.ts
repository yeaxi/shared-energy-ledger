/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = dirname(fileURLToPath(import.meta.url));

type CardEntry = {
  readonly globalName: string;
  readonly fileName: string;
  readonly entry: string;
};

const CARDS: Readonly<Record<string, CardEntry>> = {
  "energy-split-period-summary": {
    globalName: "EnergySplitPeriodSummary",
    fileName: "energy-split-period-summary",
    entry: resolve(rootDir, "src/cards/period-summary.ts"),
  },
  "energy-split-history-report": {
    globalName: "EnergySplitHistoryReport",
    fileName: "energy-split-history-report",
    entry: resolve(rootDir, "src/cards/history-report.ts"),
  },
  "energy-split-history-bridge": {
    globalName: "EnergySplitHistoryBridge",
    fileName: "energy-split-history-bridge",
    entry: resolve(rootDir, "src/cards/history-bridge.ts"),
  },
};

function pickCard(): CardEntry {
  const requested = process.env["CARD_ENTRY"] ?? "energy-split-period-summary";
  const card = CARDS[requested];
  if (!card) {
    const known = Object.keys(CARDS).join(", ");
    throw new Error(`Unknown CARD_ENTRY '${requested}'. Known: ${known}`);
  }
  return card;
}

const card = pickCard();

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: process.env["CARD_KEEP_DIST"] !== "1",
    target: "es2022",
    sourcemap: true,
    minify: "esbuild",
    lib: {
      entry: card.entry,
      name: card.globalName,
      formats: ["iife"],
      fileName: () => `${card.fileName}.js`,
    },
    rollupOptions: {
      output: {
        extend: true,
        inlineDynamicImports: true,
      },
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/report/**/*.ts", "src/i18n.ts"],
    },
  },
});
