/**
 * Same-origin JSON fetcher used by every card.
 *
 * REQUIREMENTS.md and dashboard/AGENTS.md forbid cross-origin network
 * requests. The fetcher enforces that with a URL check *before* issuing the
 * request. Relative URLs are allowed. Absolute URLs must match the current
 * page origin.
 *
 * The fetcher supports abortion via an `AbortController` so callers can
 * discard superseded fetches (invariant I8).
 */

import { err, ok, type Result } from "../../report/schema";

export interface FetchOptions {
  readonly signal?: AbortSignal;
}

export function isSameOrigin(url: string): boolean {
  if (typeof url !== "string" || url.length === 0) {
    return false;
  }
  if (url.startsWith("/") && !url.startsWith("//")) {
    return true;
  }
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin;
  } catch {
    return false;
  }
}

export async function fetchJson(
  url: string,
  options: FetchOptions = {},
): Promise<Result<unknown>> {
  if (!isSameOrigin(url)) {
    return err("URL is not same-origin");
  }
  try {
    const request: RequestInit = {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    };
    if (options.signal !== undefined) {
      request.signal = options.signal;
    }
    const response = await fetch(url, request);
    if (!response.ok) {
      return err(`Fetch failed with HTTP ${response.status}`);
    }
    const parsed = (await response.json()) as unknown;
    return ok(parsed);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return err("Fetch aborted");
    }
    const message = error instanceof Error ? error.message : String(error);
    return err(message);
  }
}
