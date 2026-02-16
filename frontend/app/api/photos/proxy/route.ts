import { NextRequest, NextResponse } from 'next/server';

/**
 * Server-side proxy for Google Photos images.
 *
 * Why: Google Photos media URLs (baseUrl) require an Authorization header.
 * Plain <img> tags cannot send headers, so we proxy through our own server.
 *
 * Usage: GET /api/photos/proxy?url=<encoded_baseUrl>&w=800&h=800
 *
 * Security:
 *  - Token is read from httpOnly cookie (never exposed in query string)
 *  - URL allowlist prevents SSRF (only lh3.googleusercontent.com allowed)
 *  - Max response size capped at 20 MB
 *  - 15s fetch timeout
 */

const ALLOWED_HOSTS = new Set([
  'lh3.googleusercontent.com',
  'video.googleusercontent.com',
]);

const MAX_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB
const TIMEOUT_MS = 15_000;

export async function GET(request: NextRequest) {
  // ── Read & validate params ──────────────────────────────────────────
  const rawUrl = request.nextUrl.searchParams.get('url');
  const width = request.nextUrl.searchParams.get('w') || '800';
  const height = request.nextUrl.searchParams.get('h') || '800';

  if (!rawUrl) {
    return NextResponse.json({ error: 'Missing "url" query parameter' }, { status: 400 });
  }

  // ── SSRF protection: only allow known Google Photos hosts ───────────
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return NextResponse.json({ error: 'Invalid URL' }, { status: 400 });
  }

  if (!ALLOWED_HOSTS.has(parsed.hostname)) {
    return NextResponse.json(
      { error: `Host "${parsed.hostname}" is not allowed` },
      { status: 403 },
    );
  }

  // ── Read token from httpOnly cookie ─────────────────────────────────
  const token = request.cookies.get('google_access_token')?.value;
  if (!token) {
    return NextResponse.json(
      { error: 'Google access token not found. Please sign in to Google Photos.' },
      { status: 401 },
    );
  }

  // ── Build the fetch URL with sizing params ──────────────────────────
  // Google Photos baseUrl requires appending =wXXX-hXXX to get sized bytes.
  const fetchUrl = `${rawUrl}=w${width}-h${height}`;

  // ── Fetch from Google with auth header ──────────────────────────────
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

    const upstream = await fetch(fetchUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!upstream.ok) {
      const status = upstream.status;
      const detail = await upstream.text().catch(() => '');
      console.error(`Photo proxy: Google returned ${status}`, detail);

      if (status === 401 || status === 403) {
        return NextResponse.json(
          { error: 'Google token expired or insufficient scopes. Please sign in again.' },
          { status: 401 },
        );
      }
      return NextResponse.json(
        { error: `Upstream error (${status})` },
        { status: status >= 500 ? 502 : status },
      );
    }

    // ── Size guard ────────────────────────────────────────────────────
    const contentLength = parseInt(upstream.headers.get('content-length') || '0', 10);
    if (contentLength > MAX_SIZE_BYTES) {
      return NextResponse.json({ error: 'Image exceeds maximum allowed size' }, { status: 413 });
    }

    // ── Stream image bytes back to client ─────────────────────────────
    const imageBytes = await upstream.arrayBuffer();
    if (imageBytes.byteLength > MAX_SIZE_BYTES) {
      return NextResponse.json({ error: 'Image exceeds maximum allowed size' }, { status: 413 });
    }

    const contentType = upstream.headers.get('content-type') || 'image/jpeg';

    return new NextResponse(imageBytes, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Length': imageBytes.byteLength.toString(),
        // Cache for 50 min (just under Google's 1hr token/URL lifetime)
        'Cache-Control': 'private, max-age=3000, must-revalidate',
        // Prevent sniffing
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return NextResponse.json({ error: 'Upstream request timed out' }, { status: 504 });
    }
    console.error('Photo proxy error:', err);
    return NextResponse.json({ error: 'Failed to fetch image' }, { status: 500 });
  }
}
