'use client';

import { useState, useEffect, useCallback } from 'react';

interface GoogleAuthState {
  isLoaded: boolean;
  isSignedIn: boolean;
  accessToken: string | null;
}

const SCOPES = 'https://www.googleapis.com/auth/photospicker.mediaitems.readonly';

export function useGoogleAuth() {
  const [authState, setAuthState] = useState<GoogleAuthState>({
    isLoaded: false,
    isSignedIn: false,
    accessToken: null,
  });

  useEffect(() => {
    const checkLoaded = setInterval(() => {
      if (typeof window !== 'undefined' && window.google?.accounts?.oauth2) {
        clearInterval(checkLoaded);
        setAuthState((prev) => ({ ...prev, isLoaded: true }));
      }
    }, 100);

    const timeout = setTimeout(() => clearInterval(checkLoaded), 10000);

    return () => {
      clearInterval(checkLoaded);
      clearTimeout(timeout);
    };
  }, []);

  const signIn = useCallback(() => {
    if (!window.google?.accounts?.oauth2) {
      alert('Google API not loaded yet. Please try again.');
      return;
    }

    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId || clientId.includes('your_google')) {
      alert('Please configure NEXT_PUBLIC_GOOGLE_CLIENT_ID in .env.local');
      return;
    }

    const tokenClient = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPES,
      callback: async (tokenResponse: any) => {
        if (tokenResponse.error) {
          console.error('Google OAuth error:', tokenResponse);
          alert(`Google sign-in error: ${tokenResponse.error}`);
          return;
        }
        if (tokenResponse.access_token) {
          console.log('Google OAuth success, scopes granted:', tokenResponse.scope);

          // Store token in httpOnly cookie so the image proxy can use it
          try {
            await fetch('/api/auth/google-token', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ accessToken: tokenResponse.access_token }),
            });
          } catch (err) {
            console.warn('Failed to store Google token in cookie:', err);
          }

          setAuthState({
            isLoaded: true,
            isSignedIn: true,
            accessToken: tokenResponse.access_token,
          });
        }
      },
      error_callback: (error: any) => {
        console.error('Google OAuth error callback:', error);
      },
    });

    tokenClient.requestAccessToken();
  }, []);

  const signOut = useCallback(() => {
    if (authState.accessToken && window.google?.accounts?.oauth2) {
      window.google.accounts.oauth2.revoke(authState.accessToken, () => {
        // Clear the httpOnly cookie
        fetch('/api/auth/google-token', { method: 'DELETE' }).catch(() => {});

        setAuthState({
          isLoaded: true,
          isSignedIn: false,
          accessToken: null,
        });
      });
    }
  }, [authState.accessToken]);

  return {
    ...authState,
    signIn,
    signOut,
  };
}
