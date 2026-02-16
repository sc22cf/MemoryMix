/**
 * Thin wrapper around the Spotify Web API that adds:
 *  - automatic bearer-token injection via SpotifyTokenManager
 *  - 401 → single-flight token refresh + retry (once)
 *  - 429 → respect Retry-After header / exponential back-off
 *  - TTL-based response caching + single-flight deduplication for GET requests
 *
 * Playback commands (PUT/POST/DELETE) are NEVER cached.
 * DRM licence requests (/fairplay-license/) are not touched by this module.
 */

import { searchCache, trackCache } from './cache';
import { Cache } from './cache';
import { spotifyTokenManager } from './spotify-token';

const SPOTIFY_BASE = 'https://api.spotify.com/v1';

interface FetchOptions {
  method?: string;
  body?: unknown;
  /** Override the default TTL for this request. */
  cacheTtl?: number;
  /** Set `false` to skip cache entirely (default: true for GETs). */
  useCache?: boolean;
}

/* ── helpers ──────────────────────────────────────────────────── */

function cacheKeyFor(endpoint: string, method: string, body?: unknown): string {
  return `${method}:${endpoint}${body ? ':' + JSON.stringify(body) : ''}`;
}

function cacheFor(endpoint: string): Cache<any> {
  if (endpoint.includes('/search')) return searchCache;
  if (endpoint.includes('/tracks')) return trackCache;
  return trackCache; // sensible default for other metadata
}

function defaultTtl(endpoint: string): number {
  if (endpoint.includes('/search')) return 15 * 60 * 1000; // 15 min
  if (endpoint.includes('/tracks')) return 60 * 60 * 1000; // 1 hr
  return 15 * 60 * 1000;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/* ── core fetch with retry ───────────────────────────────────── */

async function spotifyFetch<T>(
  endpoint: string,
  opts: FetchOptions = {},
  retryState = { tokenRetried: false, attempt: 0, backoff: 1000 },
): Promise<T> {
  const { method = 'GET', body } = opts;
  const token = await spotifyTokenManager.getAccessToken();

  const url = endpoint.startsWith('http') ? endpoint : `${SPOTIFY_BASE}${endpoint}`;

  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  /* ---- 401 → refresh token once and retry ---- */
  if (res.status === 401 && !retryState.tokenRetried) {
    spotifyTokenManager.forceRefresh();
    return spotifyFetch<T>(endpoint, opts, { ...retryState, tokenRetried: true });
  }

  /* ---- 429 → respect Retry-After / exponential back-off ---- */
  if (res.status === 429 && retryState.attempt < 4) {
    const retryAfter = res.headers.get('Retry-After');
    const waitMs = retryAfter ? parseInt(retryAfter, 10) * 1000 : retryState.backoff;
    console.warn(`⏱ 429 rate-limited, retrying in ${waitMs}ms (attempt ${retryState.attempt + 1})`);
    await sleep(waitMs);
    return spotifyFetch<T>(endpoint, opts, {
      ...retryState,
      attempt: retryState.attempt + 1,
      backoff: retryState.backoff * 2,
    });
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Spotify ${method} ${endpoint} → ${res.status}: ${text}`);
  }

  // 204 No Content (e.g. successful play command)
  if (res.status === 204) return undefined as T;

  return res.json();
}

/* ── public API ──────────────────────────────────────────────── */

/**
 * Make a Spotify Web API request.
 * GETs are cached + deduped by default; mutations are never cached.
 */
export async function spotifyRequest<T = any>(
  endpoint: string,
  opts: FetchOptions = {},
): Promise<T> {
  const { method = 'GET', useCache = true, cacheTtl } = opts;
  const shouldCache = method === 'GET' && useCache;

  if (shouldCache) {
    const cache = cacheFor(endpoint);
    const key = cacheKeyFor(endpoint, method, opts.body);
    const ttl = cacheTtl ?? defaultTtl(endpoint);
    return cache.get(key, () => spotifyFetch<T>(endpoint, opts), ttl);
  }

  return spotifyFetch<T>(endpoint, opts);
}

/* ── convenience wrappers ────────────────────────────────────── */

/** Play a track on a device (never cached). */
export function playOnDevice(deviceId: string, uri: string) {
  return spotifyRequest(`/me/player/play?device_id=${deviceId}`, {
    method: 'PUT',
    body: { uris: [uri] },
    useCache: false,
  });
}

/** Transfer playback to a device (never cached). */
export function transferPlayback(deviceId: string, play = false) {
  return spotifyRequest('/me/player', {
    method: 'PUT',
    body: { device_ids: [deviceId], play },
    useCache: false,
  });
}

/** Invalidate all cached metadata (e.g. after receiving an error). */
export function invalidateAll() {
  searchCache.invalidate();
  trackCache.invalidate();
}
