/**
 * Shared CSS block used by every card. All colors, radii, and spacing use
 * Home Assistant CSS variables so both light and dark themes render
 * correctly (see dashboard/AGENTS.md, "render correctly in both light and
 * dark themes").
 */

export const CARD_BASE_CSS = `
  :host {
    display: block;
    color: var(--primary-text-color, #212121);
    background: var(--card-background-color, var(--ha-card-background, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, none);
    padding: 16px;
    font-family: var(--paper-font-body1_-_font-family, "Roboto", sans-serif);
  }

  .header {
    font-weight: 500;
    font-size: 1rem;
    margin: 0 0 12px 0;
    color: var(--primary-text-color, #212121);
  }

  .subtitle {
    color: var(--secondary-text-color, #757575);
    font-size: 0.85rem;
    margin-bottom: 12px;
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
  }

  .row:last-child {
    border-bottom: none;
  }

  .row .label {
    color: var(--secondary-text-color, #757575);
  }

  .row .value {
    font-variant-numeric: tabular-nums;
    color: var(--primary-text-color, #212121);
  }

  .row .value.unavailable {
    color: var(--error-color, var(--warning-color, #ff9800));
    font-style: italic;
  }

  .grid {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 4px 12px;
  }

  .footer {
    margin-top: 12px;
    font-size: 0.75rem;
    color: var(--secondary-text-color, #757575);
  }

  @media (max-width: 480px) {
    :host {
      padding: 12px;
    }
    .grid {
      grid-template-columns: 1fr;
    }
  }
`;
