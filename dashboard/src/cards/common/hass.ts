/**
 * Minimal subset of the Home Assistant frontend API that the cards use.
 *
 * The typings are intentionally narrow. Every access to `hass` MUST be
 * defensive because operators may install the card on Home Assistant builds
 * newer than the cards were compiled against.
 */

export interface HassEntityAttributes {
  readonly friendly_name?: string;
  readonly unit_of_measurement?: string;
  readonly device_class?: string;
  readonly state_class?: string;
  readonly [key: string]: unknown;
}

export interface HassEntityState {
  readonly entity_id: string;
  readonly state: string;
  readonly attributes: HassEntityAttributes;
  readonly last_updated?: string;
  readonly last_changed?: string;
}

export interface HassLike {
  readonly states: Readonly<Record<string, HassEntityState>>;
  readonly locale?: { readonly language?: string };
  readonly language?: string;
}

export const INVALID_STATES = new Set(["", "unknown", "unavailable", "none"]);

export function isInvalidState(state: string | undefined | null): boolean {
  if (state === undefined || state === null) {
    return true;
  }
  return INVALID_STATES.has(state.toLowerCase());
}

export function resolveLocale(hass: HassLike | undefined | null): string {
  if (!hass) {
    return "en";
  }
  const localeLang = hass.locale?.language;
  if (typeof localeLang === "string" && localeLang.length > 0) {
    return localeLang;
  }
  if (typeof hass.language === "string" && hass.language.length > 0) {
    return hass.language;
  }
  return "en";
}
