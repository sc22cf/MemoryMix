/**
 * Generic TTL-based in-memory cache with single-flight request deduplication.
 *
 * - TTL: cached values expire after a configurable duration.
 * - Single-flight: concurrent calls with the same key share ONE in-flight
 *   Promise, preventing thundering-herd / duplicate requests.
 *
 * Usage:
 *   const c = new Cache<TrackData>();
 *   const track = await c.get('track:abc', () => fetchTrack('abc'), 60_000);
 */

interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

export class Cache<T = any> {
  private store = new Map<string, CacheEntry<T>>();
  private inflight = new Map<string, Promise<T>>();

  /**
   * Return the cached value if fresh, otherwise call `fetcher` (deduped).
   *
   * @param key     – unique cache key
   * @param fetcher – async function that produces the value
   * @param ttlMs   – time-to-live in ms (default 15 min)
   */
  async get(key: string, fetcher: () => Promise<T>, ttlMs = 15 * 60 * 1000): Promise<T> {
    const now = Date.now();

    // 1. Cache hit?
    const cached = this.store.get(key);
    if (cached && cached.expiresAt > now) {
      return cached.value;
    }

    // 2. Already in-flight? Piggy-back on the existing promise.
    const pending = this.inflight.get(key);
    if (pending) return pending;

    // 3. New fetch — store the promise so concurrent callers reuse it.
    const promise = fetcher()
      .then((value) => {
        this.store.set(key, { value, expiresAt: Date.now() + ttlMs });
        this.inflight.delete(key);
        return value;
      })
      .catch((err) => {
        this.inflight.delete(key);
        throw err;
      });

    this.inflight.set(key, promise);
    return promise;
  }

  /** Pre-warm or overwrite a cache entry. */
  set(key: string, value: T, ttlMs = 15 * 60 * 1000): void {
    this.store.set(key, { value, expiresAt: Date.now() + ttlMs });
  }

  /** Invalidate one key, a pattern, or everything (no args). */
  invalidate(keyOrPattern?: string | RegExp): void {
    if (!keyOrPattern) {
      this.store.clear();
      this.inflight.clear();
      return;
    }
    if (typeof keyOrPattern === 'string') {
      this.store.delete(keyOrPattern);
      this.inflight.delete(keyOrPattern);
    } else {
      for (const k of this.store.keys()) {
        if (keyOrPattern.test(k)) this.store.delete(k);
      }
      for (const k of this.inflight.keys()) {
        if (keyOrPattern.test(k)) this.inflight.delete(k);
      }
    }
  }

  /** Check whether a fresh value exists for `key`. */
  has(key: string): boolean {
    const e = this.store.get(key);
    return !!e && e.expiresAt > Date.now();
  }

  /** Number of live entries + in-flight fetches. */
  stats() {
    return { cached: this.store.size, inflight: this.inflight.size };
  }
}

/* ── Shared singleton instances ──────────────────────────────── */
/** Spotify search results — moderate TTL (15 min). */
export const searchCache = new Cache<any>();
/** Spotify track metadata — long TTL (1 hr, tracks rarely change). */
export const trackCache = new Cache<any>();
/** Spotify access token — TTL managed dynamically by SpotifyTokenManager. */
export const tokenCache = new Cache<string>();
