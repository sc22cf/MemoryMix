/**
 * Spotify access-token manager.
 *
 * - Caches the token in memory (never localStorage — no secrets on disk).
 * - Refreshes proactively when < 5 min remaining.
 * - Single-flight: concurrent `getAccessToken()` calls share one refresh.
 * - Refresh happens via the backend `/spotify/token` endpoint which uses the
 *   server-side refresh token, so no Spotify secrets leak to the client.
 */

import { tokenCache } from './cache';

const TOKEN_CACHE_KEY = 'spotify_access_token';
const REFRESH_BUFFER_MS = 5 * 60 * 1000; // refresh 5 min before expiry

class SpotifyTokenManager {
  private expiresAt = 0;
  private refreshPromise: Promise<string> | null = null;

  /**
   * Return a valid access token, refreshing if needed.
   * Safe to call from many places concurrently — only one refresh runs.
   */
  async getAccessToken(): Promise<string> {
    const now = Date.now();

    // 1. If we already have a fresh token cached, return it.
    if (this.expiresAt > now + REFRESH_BUFFER_MS && tokenCache.has(TOKEN_CACHE_KEY)) {
      return tokenCache.get(TOKEN_CACHE_KEY, () => this.fetchToken(), this.expiresAt - now);
    }

    // 2. Single-flight refresh.
    if (this.refreshPromise) return this.refreshPromise;

    this.refreshPromise = this.fetchToken().finally(() => {
      this.refreshPromise = null;
    });

    return this.refreshPromise;
  }

  /**
   * Fetch a (possibly refreshed) token from the backend.
   * The backend's `/spotify/token` endpoint calls `ensure_valid_token`
   * which transparently refreshes when expired.
   */
  private async fetchToken(): Promise<string> {
    const appJwt = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (!appJwt) throw new Error('Not logged in');

    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/spotify/token`,
      { headers: { Authorization: `Bearer ${appJwt}` } },
    );

    if (!res.ok) {
      throw new Error(`Token fetch failed: ${res.status}`);
    }

    const data: { access_token: string; expires_in: number } = await res.json();
    const ttlMs = data.expires_in * 1000;

    this.expiresAt = Date.now() + ttlMs;
    tokenCache.set(TOKEN_CACHE_KEY, data.access_token, ttlMs);
    return data.access_token;
  }

  /** Force a refresh on next call (use after a 401 from Spotify). */
  forceRefresh(): void {
    this.expiresAt = 0;
    tokenCache.invalidate(TOKEN_CACHE_KEY);
  }

  /** Clear everything (logout). */
  clear(): void {
    this.expiresAt = 0;
    this.refreshPromise = null;
    tokenCache.invalidate(TOKEN_CACHE_KEY);
  }
}

export const spotifyTokenManager = new SpotifyTokenManager();
