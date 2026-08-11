/**
 * Minimal HTML entity escape used before inlining user-supplied text into
 * a card's shadow-root markup. The escape targets the five characters that
 * are syntactically significant in HTML attribute/text contexts.
 *
 * The cards never inline HTML strings from operators or from remote reports;
 * this helper is defense-in-depth for values that pass through
 * `innerHTML`.
 */

export function escapeHtml(input: string): string {
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
