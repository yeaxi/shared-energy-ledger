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
  "shared-energy-ledger-report": {
    globalName: "SharedEnergyLedgerReportCard",
    fileName: "shared-energy-ledger-report",
    entry: resolve(rootDir, "src/cards/report-card.ts"),
  },
};

function pickCard(): CardEntry {
  const requested = process.env["CARD_ENTRY"] ?? "shared-energy-ledger-report";
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
