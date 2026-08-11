/**
 * Meta entry point. Importing this module registers all three custom
 * cards: `energy-split-period-summary`, `energy-split-history-report`,
 * and `energy-split-history-bridge`. Each card module also registers
 * itself when imported directly, so this file is optional in production
 * (Vite emits one IIFE per card entry).
 */

import "./period-summary";
import "./history-report";
import "./history-bridge";

export { EnergySplitPeriodSummary } from "./period-summary";
export { EnergySplitHistoryReport } from "./history-report";
export {
  EnergySplitHistoryBridge,
  ENERGY_SPLIT_REPORT_EVENT,
} from "./history-bridge";
