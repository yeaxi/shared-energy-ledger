/**
 * Meta entry point. Importing this module registers all three custom
 * cards: `shared-energy-ledger-period-summary`, `shared-energy-ledger-history-report`,
 * and `shared-energy-ledger-history-bridge`. Each card module also registers
 * itself when imported directly, so this file is optional in production
 * (Vite emits one IIFE per card entry).
 */

import "./period-summary";
import "./history-report";
import "./history-bridge";

export { SharedEnergyLedgerPeriodSummary } from "./period-summary";
export { SharedEnergyLedgerHistoryReport } from "./history-report";
export {
  SharedEnergyLedgerHistoryBridge,
  ENERGY_SPLIT_REPORT_EVENT,
} from "./history-bridge";
