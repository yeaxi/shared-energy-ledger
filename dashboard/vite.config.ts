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
  "shared-energy-ledger-period-summary": {
    globalName: "SharedEnergyLedgerPeriodSummary",
    fileName: "shared-energy-ledger-period-summary",
    entry: resolve(rootDir, "src/cards/period-summary.ts"),
  },
  "shared-energy-ledger-history-report": {
    globalName: "SharedEnergyLedgerHistoryReport",
    fileName: "shared-energy-ledger-history-report",
    entry: resolve(rootDir, "src/cards/history-report.ts"),
  },
  "shared-energy-ledger-history-bridge": {
    globalName: "SharedEnergyLedgerHistoryBridge",
    fileName: "shared-energy-ledger-history-bridge",
    entry: resolve(rootDir, "src/cards/history-bridge.ts"),
  },
};

function pickCard(): CardEntry {
  const requested = process.env["CARD_ENTRY"] ?? "shared-energy-ledger-period-summary";
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
