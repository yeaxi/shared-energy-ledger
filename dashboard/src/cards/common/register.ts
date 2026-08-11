/**
 * Shared helpers to register a custom card with Home Assistant Lovelace.
 *
 * Every card MUST call `registerCustomCard` at module load so the operator
 * can pick it in the card picker.
 */

export interface CustomCardEntry {
  readonly type: string;
  readonly name: string;
  readonly description: string;
  readonly preview?: boolean;
}

interface WindowWithCards {
  customCards?: CustomCardEntry[];
}

export function registerCustomCard(entry: CustomCardEntry): void {
  const target = window as WindowWithCards;
  const list = target.customCards ?? [];
  const existing = list.find((item) => item.type === entry.type);
  if (existing) {
    return;
  }
  list.push(entry);
  target.customCards = list;
}

export function defineCustomElementOnce(
  tag: string,
  ctor: CustomElementConstructor,
): void {
  if (customElements.get(tag) === undefined) {
    customElements.define(tag, ctor);
  }
}
