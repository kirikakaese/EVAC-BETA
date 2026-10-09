// SPDX-License-Identifier: AGPL-3.0-or-later
// Used by the service worker (kept in its own module: the worker bundle must not export anything).

/** Static files a player page needs (its versioned script, styles and icon). */
export function shellAssets(html: string): string[] {
  return [...new Set([...html.matchAll(/(?:src|href)="(\/static\/[^"]+)"/g)].map((m) => m[1].replace(/&amp;/g, "&")))];
}
