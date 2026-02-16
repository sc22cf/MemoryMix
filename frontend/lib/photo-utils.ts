/**
 * Returns a URL for displaying a photo.
 *
 * Priority:
 *  1. localUrl (backend-served, permanent) — used for saved photos
 *  2. data: URIs (local uploads before save) — returned as-is
 *  3. Google Photos baseUrl — proxied through /api/photos/proxy (ephemeral, only for picker preview)
 */
export function getPhotoProxyUrl(
  baseUrl: string,
  width = 400,
  height = 400,
  localUrl?: string | null,
): string {
  // Prefer the permanent backend-served URL if available
  if (localUrl) {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    return `${apiBase}${localUrl}`;
  }

  // Data URIs (local uploads) don't need proxying
  if (!baseUrl || baseUrl.startsWith('data:')) return baseUrl;

  // Already a proxy URL
  if (baseUrl.startsWith('/api/photos/proxy')) return baseUrl;

  return `/api/photos/proxy?url=${encodeURIComponent(baseUrl)}&w=${width}&h=${height}`;
}
