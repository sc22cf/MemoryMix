import { NextRequest, NextResponse } from 'next/server';

/**
 * Store the Google OAuth access token in an httpOnly cookie.
 * The frontend calls this after a successful Google sign-in so the
 * image proxy route can read the token server-side.
 */
export async function POST(request: NextRequest) {
  try {
    const { accessToken } = await request.json();

    if (!accessToken || typeof accessToken !== 'string') {
      return NextResponse.json({ error: 'Missing access token' }, { status: 400 });
    }

    const response = NextResponse.json({ success: true });
    response.cookies.set('google_access_token', accessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: 3600, // 1 hour — matches Google token lifetime
    });

    return response;
  } catch {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
}

/**
 * Clear the Google token cookie on sign-out.
 */
export async function DELETE() {
  const response = NextResponse.json({ success: true });
  response.cookies.delete('google_access_token');
  return response;
}
