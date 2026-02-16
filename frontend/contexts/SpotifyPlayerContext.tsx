'use client';

import { createContext, useContext, useEffect, useRef, useState, useCallback, ReactNode } from 'react';
import { spotifyTokenManager } from '@/lib/spotify-token';
import { playOnDevice, transferPlayback } from '@/lib/spotify-api';

declare global {
  interface Window {
    Spotify: any;
    onSpotifyWebPlaybackSDKReady: () => void;
  }
}

interface SpotifyPlayerState {
  track: {
    name: string;
    artist: string;
    album: string;
    image: string;
    uri: string;
  } | null;
  isPlaying: boolean;
  position: number;
  duration: number;
}

interface SpotifyPlayerContextType {
  deviceId: string | null;
  playerState: SpotifyPlayerState;
  isReady: boolean;
  error: string | null;
  playTrack: (uri: string) => Promise<void>;
  togglePlay: () => Promise<void>;
  nextTrack: () => Promise<void>;
  previousTrack: () => Promise<void>;
  setVolume: (volume: number) => Promise<void>;
  seek: (positionMs: number) => Promise<void>;
}

const SpotifyPlayerContext = createContext<SpotifyPlayerContextType | undefined>(undefined);

/* ── Module-level singletons (survive React StrictMode double-mount) ── */
let sdkScriptInjected = false;
let sdkReady = false;
let sdkReadyPromise: Promise<void> | null = null;

/** Inject the SDK script exactly once per page session. */
function ensureSDKScript(): Promise<void> {
  if (sdkReady) return Promise.resolve();
  if (sdkReadyPromise) return sdkReadyPromise;

  sdkReadyPromise = new Promise<void>((resolve) => {
    if (typeof window === 'undefined') return;

    // Already loaded (e.g. hot-reload)
    if (window.Spotify) {
      sdkReady = true;
      resolve();
      return;
    }

    // Register the global callback
    window.onSpotifyWebPlaybackSDKReady = () => {
      console.log('✓ Spotify SDK loaded');
      sdkReady = true;
      resolve();
    };

    // Inject <script> only once
    if (!sdkScriptInjected) {
      sdkScriptInjected = true;
      const s = document.createElement('script');
      s.src = 'https://sdk.scdn.co/spotify-player.js';
      s.async = true;
      document.body.appendChild(s);
    }
  });

  return sdkReadyPromise;
}

export function SpotifyPlayerProvider({ children }: { children: ReactNode }) {
  // ── refs (stable across re-renders & StrictMode double-mount) ──
  const playerRef = useRef<any>(null);
  const initializingRef = useRef(false);
  const initializedRef = useRef(false);   // prevents double-init in StrictMode
  const deviceIdRef = useRef<string | null>(null);
  const positionIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const audioUnlockedRef = useRef(false);   // tracks if audio context is unlocked

  // ── state ──
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playerState, setPlayerState] = useState<SpotifyPlayerState>({
    track: null,
    isPlaying: false,
    position: 0,
    duration: 0,
  });

  // ── position tracking ──
  const startPositionTracking = useCallback(() => {
    if (positionIntervalRef.current) return;
    positionIntervalRef.current = setInterval(() => {
      setPlayerState((prev) => ({
        ...prev,
        position: Math.min(prev.position + 1000, prev.duration),
      }));
    }, 1000);
  }, []);

  const stopPositionTracking = useCallback(() => {
    if (positionIntervalRef.current) {
      clearInterval(positionIntervalRef.current);
      positionIntervalRef.current = null;
    }
  }, []);

  // ── initialize player (once, StrictMode-safe) ──
  useEffect(() => {
    // Guard: if the player was already created (StrictMode re-mount), skip.
    if (initializedRef.current || initializingRef.current) return;
    initializingRef.current = true;

    let cancelled = false;

    const init = async () => {
      try {
        // 1. Wait for SDK script
        await ensureSDKScript();
        if (cancelled) return;

        // 2. Get a token for the SDK constructor
        const token = await spotifyTokenManager.getAccessToken();
        if (cancelled || !token) {
          setError('Failed to get Spotify token');
          return;
        }

        console.log('Initializing Spotify player…');

        // 3. Create the player ONCE
        const player = new window.Spotify.Player({
          name: 'MemoryMix Web Player',
          getOAuthToken: async (cb: (t: string) => void) => {
            try {
              cb(await spotifyTokenManager.getAccessToken());
            } catch {
              console.error('Token refresh failed inside SDK');
              cb('');
            }
          },
          volume: 0.5,
        });

        // ── Event listeners ──
        player.addListener('ready', async ({ device_id }: { device_id: string }) => {
          console.log('✓ Player ready, device:', device_id);
          console.log('[DEBUG] Device ready timestamp:', new Date().toISOString());
          deviceIdRef.current = device_id;
          setDeviceId(device_id);
          setIsReady(true);

          try {
            console.log('[DEBUG] Starting transfer playback to device:', device_id);
            await transferPlayback(device_id, false);
            console.log('✓ Playback transferred successfully');
            console.log('[DEBUG] Transfer timestamp:', new Date().toISOString());
          } catch (err) {
            console.warn('⚠️ Transfer playback failed (non-fatal):', err);
            console.warn('[DEBUG] This may cause hover play to fail until manual play');
          }
        });

        player.addListener('not_ready', () => {
          console.warn('Device offline');
          deviceIdRef.current = null;
          setDeviceId(null);
          setIsReady(false);
        });

        player.addListener('player_state_changed', (state: any) => {
          if (!state) return;
          const t = state.track_window?.current_track;
          setPlayerState({
            track: t
              ? {
                  name: t.name,
                  artist: t.artists?.map((a: any) => a.name).join(', ') || '',
                  album: t.album?.name || '',
                  image: t.album?.images?.[0]?.url || '',
                  uri: t.uri,
                }
              : null,
            isPlaying: !state.paused,
            position: state.position,
            duration: state.duration,
          });
          if (!state.paused) startPositionTracking();
          else stopPositionTracking();
        });

        player.addListener('initialization_error', ({ message }: { message: string }) => {
          console.error('Init error:', message);
          setError(`Initialization error: ${message}`);
        });
        player.addListener('authentication_error', ({ message }: { message: string }) => {
          console.error('Auth error:', message);
          spotifyTokenManager.forceRefresh();
          setError(`Authentication error: ${message}`);
        });
        player.addListener('account_error', ({ message }: { message: string }) => {
          console.error('Account error:', message);
          setError(`Account error: ${message}. Spotify Premium required.`);
        });
        player.addListener('playback_error', ({ message }: { message: string }) => {
          console.error('Playback error:', message);
        });

        // 4. Connect first (activateElement will be called on user gesture)
        console.log('[DEBUG] Connecting player...');
        const ok = await player.connect();
        if (!ok) throw new Error('player.connect() returned false');

        console.log('✓ Player connected');
        playerRef.current = player;
        initializedRef.current = true;
      } catch (err) {
        console.error('Failed to initialize player:', err);
        setError(err instanceof Error ? err.message : 'Failed to initialize player');
        initializedRef.current = false;
      } finally {
        initializingRef.current = false;
      }
    };

    init();

    return () => {
      cancelled = true;
      stopPositionTracking();
      if (playerRef.current) {
        console.log('Disconnecting player…');
        playerRef.current.disconnect();
        playerRef.current = null;
        initializedRef.current = false;
      }
      setIsReady(false);
      setDeviceId(null);
    };
  }, []); // intentionally empty — runs once

  // ── Unlock audio on first user interaction ──
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    const unlockAudio = () => {
      if (audioUnlockedRef.current || !playerRef.current) return;
      
      console.log('[DEBUG] First user click detected - unlocking audio context...');
      
      // activateElement() must be called from a user gesture
      playerRef.current.activateElement();
      audioUnlockedRef.current = true;
      
      console.log('✓ Audio context unlocked - playback should now work on hover');
    };
    
    // Listen for any user interaction
    document.addEventListener('click', unlockAudio, { once: true });
    document.addEventListener('keydown', unlockAudio, { once: true });
    
    return () => {
      document.removeEventListener('click', unlockAudio);
      document.removeEventListener('keydown', unlockAudio);
    };
  }, []);

  // ── playback controls (stable callback identities) ──
  const playTrack = useCallback(async (uri: string) => {
    const did = deviceIdRef.current;
    console.log('[DEBUG] playTrack called:', { uri, deviceId: did, isReady });
    
    if (!did) {
      console.error('❌ playTrack failed: no device ID');
      throw new Error('Player not ready');
    }
    
    console.log('[DEBUG] Calling playOnDevice...');
    await playOnDevice(did, uri);
    console.log('✓ Track started:', uri);
    console.log('[DEBUG] playOnDevice completed successfully');
  }, [isReady]);

  const togglePlay = useCallback(async () => {
    console.log('[DEBUG] togglePlay called');
    console.log('[DEBUG] Current player state:', playerState);
    console.log('[DEBUG] Player ref:', playerRef.current);
    playerRef.current?.togglePlay();
  }, []);

  const nextTrack = useCallback(async () => {
    playerRef.current?.nextTrack();
  }, []);

  const previousTrack = useCallback(async () => {
    playerRef.current?.previousTrack();
  }, []);

  const setVolume = useCallback(async (v: number) => {
    playerRef.current?.setVolume(v);
  }, []);

  const seek = useCallback(async (ms: number) => {
    playerRef.current?.seek(ms);
  }, []);

  const value: SpotifyPlayerContextType = {
    deviceId,
    playerState,
    isReady,
    error,
    playTrack,
    togglePlay,
    nextTrack,
    previousTrack,
    setVolume,
    seek,
  };

  return <SpotifyPlayerContext.Provider value={value}>{children}</SpotifyPlayerContext.Provider>;
}

export function useSpotifyPlayer() {
  const context = useContext(SpotifyPlayerContext);
  if (context === undefined) {
    throw new Error('useSpotifyPlayer must be used within a SpotifyPlayerProvider');
  }
  return context;
}
