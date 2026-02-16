'use client';

import { useEffect, useRef, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

function CallbackContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { login, connectSpotify } = useAuth();
  const loginAttempted = useRef(false);

  useEffect(() => {
    if (loginAttempted.current) return;

    const error = searchParams.get('error');
    if (error) {
      console.error('Auth error:', error);
      router.push('/?error=' + error);
      return;
    }

    // Spotify callback — has `code` param (connect flow only)
    const code = searchParams.get('code');
    // Last.fm callback — has `token` param
    const token = searchParams.get('token');

    if (code) {
      loginAttempted.current = true;
      // Spotify code is always for connecting (not login)
      localStorage.removeItem('spotify_connect');
      connectSpotify(code)
        .then(() => router.push('/dashboard'))
        .catch((err) => {
          console.error('Spotify connect failed:', err);
          loginAttempted.current = false;
          router.push('/dashboard?error=spotify_connect_failed');
        });
    } else if (token) {
      loginAttempted.current = true;
      login(token).catch((err) => {
        console.error('Login failed:', err);
        loginAttempted.current = false;
        router.push('/?error=login_failed');
      });
    } else {
      router.push('/');
    }
  }, [searchParams, login, connectSpotify, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-accent border-t-transparent mx-auto mb-5"></div>
        <p className="text-lg text-muted">Connecting your account...</p>
      </div>
    </div>
  );
}

export default function CallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent"></div>
      </div>
    }>
      <CallbackContent />
    </Suspense>
  );
}
