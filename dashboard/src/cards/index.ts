/**
 * Meta entry point. Importing this module registers the single custom card,
 * `shared-energy-ledger-report`. The card module also registers itself when
 * imported directly, so this file is optional in production.
 */

import "./report-card";

export { SharedEnergyLedgerReportCard } from "./report-card";
