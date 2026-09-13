/**
 * The key the theme preference is stored under.
 *
 * It lives here — in a module with no `'use client'` — because both sides need
 * the value. The provider writes it in the browser, and the root layout has to
 * interpolate it into the pre-paint script it renders on the server.
 *
 * Exporting it from the provider instead type-checked, linted, built, and
 * shipped broken. Next replaces a client module's exports with a throwing stub
 * when a server component reads one, and the template literal stringified that
 * stub, so every page went out asking localStorage for a key beginning
 * `function(){throw Error(`. It never matched what the provider had written,
 * `stored` was always null, and the OS preference quietly won on every load —
 * which is the exact flash the script exists to prevent.
 */
export const THEME_STORAGE_KEY = 'quantimental.theme'
