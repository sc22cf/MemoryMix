'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { useSpotifyPlayer } from '@/contexts/SpotifyPlayerContext';
import { apiClient } from '@/lib/api-client';
import { Music } from 'lucide-react';
import { format } from 'date-fns';
import { getPhotoProxyUrl } from '@/lib/photo-utils';
import { Memory } from '@/lib/types';

// ---- shared singleton so only one HTML5 preview plays at a time ----
let globalAudio: HTMLAudioElement | null = null;
let globalCardId: number | null = null;
let globalListeners: Set<() => void> = new Set();

function notifyListeners() {
  globalListeners.forEach((fn) => fn());
}

function stopGlobalAudio() {
  if (globalAudio) {
    globalAudio.pause();
    globalAudio.src = '';
    globalAudio = null;
    globalCardId = null;
    notifyListeners();
  }
}
// ---------------------------------------------------------------

interface MemoryCardProps {
  memory: Memory;
  onClick: (memory: Memory) => void;
  spotifyConnected: boolean;
}

function EqBars() {
  return (
    <div className="flex items-end gap-[2px] h-3.5 flex-shrink-0">
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className="w-[3px] rounded-full bg-accent"
          style={{
            animation: `eq-bounce 0.8s ease-in-out ${i * 0.15}s infinite alternate`,
          }}
        />
      ))}
      <style jsx>{`
        @keyframes eq-bounce {
          0%   { height: 20%; }
          100% { height: 100%; }
        }
      `}</style>
    </div>
  );
}

export default function MemoryCard({ memory, onClick, spotifyConnected }: MemoryCardProps) {
  const { isReady, playTrack, togglePlay, playerState } = useSpotifyPlayer();
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const hoverTimerRef = useRef<NodeJS.Timeout | null>(null);
  const hoverStartRef = useRef<number>(0);

  // Resolved track data (cached after first search)
  const resolvedRef = useRef(false);
  const previewUrlRef = useRef<string | null>(null);
  const spotifyUriRef = useRef<string | null>(null);
  // "preview" = HTML5 Audio, "sdk" = Spotify Web Playback SDK
  const playbackModeRef = useRef<'preview' | 'sdk' | null>(null);

  const photo = memory.photos?.[0];
  const mapping = memory.mappings?.[0];
  const track = mapping?.track;

  // SDK-based playing status for this card
  const isThisTrackViaSdk =
    spotifyUriRef.current && playerState.track?.uri === spotifyUriRef.current;
  const isSdkPlaying = isThisTrackViaSdk && playerState.isPlaying;

  const isPlaying =
    (playbackModeRef.current === 'preview' && isAudioPlaying) ||
    (playbackModeRef.current === 'sdk' && isSdkPlaying);

  // Subscribe to global audio changes (HTML5 Audio singleton)
  useEffect(() => {
    const sync = () =>
      setIsAudioPlaying(
        globalCardId === memory.id && !!globalAudio && !globalAudio.paused,
      );
    globalListeners.add(sync);
    return () => {
      globalListeners.delete(sync);
    };
  }, [memory.id]);

  // Resolve track data once (preview_url + spotify URI)
  const resolveTrack = useCallback(async () => {
    if (resolvedRef.current) return;
    if (!track || !spotifyConnected) return;
    resolvedRef.current = true;

    // Check stored spotify_uri first
    if (track.spotify_uri) {
      spotifyUriRef.current = track.spotify_uri;
    }

    try {
      const result = await apiClient.searchSpotifyTrack(
        track.track_name,
        track.artist_name,
      );
      if (result.found) {
        if (result.preview_url) previewUrlRef.current = result.preview_url;
        if (result.uri) spotifyUriRef.current = result.uri;
      }
    } catch (err) {
      console.error('Failed to resolve track:', err);
    }
  }, [track, spotifyConnected]);

  // Start playback — tries preview_url first, falls back to SDK
  const startPlayback = useCallback(async () => {
    console.log('[DEBUG MemoryCard] startPlayback called for memory:', memory.id);
    console.log('[DEBUG MemoryCard] Track:', track?.track_name, 'by', track?.artist_name);
    
    await resolveTrack();

    const previewUrl = previewUrlRef.current;
    const spotifyUri = spotifyUriRef.current;
    
    console.log('[DEBUG MemoryCard] Resolved URLs:', { previewUrl, spotifyUri });

    // ---- Strategy 1: HTML5 Audio preview clip ----
    if (previewUrl) {
      console.log('[DEBUG MemoryCard] Using HTML5 Audio strategy (preview_url)');
      // If this card already owns the global audio, just resume
      if (globalCardId === memory.id && globalAudio) {
        if (globalAudio.paused) {
          globalAudio.play().catch(() => {});
          playbackModeRef.current = 'preview';
          notifyListeners();
        }
        return;
      }

      stopGlobalAudio();

      const audio = new Audio(previewUrl);
      audio.volume = 0.5;
      globalAudio = audio;
      globalCardId = memory.id;

      audio.addEventListener('ended', () => {
        globalCardId = null;
        globalAudio = null;
        playbackModeRef.current = null;
        notifyListeners();
      });

      playbackModeRef.current = 'preview';
      audio.play().catch(() => {});
      notifyListeners();
      return;
    }

    // ---- Strategy 2: Spotify Web Playback SDK ----
    if (spotifyUri && isReady) {
      console.log('[DEBUG MemoryCard] Using SDK strategy');
      console.log('[DEBUG MemoryCard] Current player state:', {
        currentUri: playerState.track?.uri,
        targetUri: spotifyUri,
        isPlaying: playerState.isPlaying,
        isReady
      });
      
      // Stop any HTML5 audio first
      stopGlobalAudio();

      try {
        // If already playing this exact track, do nothing
        if (playerState.track?.uri === spotifyUri && playerState.isPlaying) {
          console.log('[DEBUG MemoryCard] Track already playing, skipping');
          playbackModeRef.current = 'sdk';
          return;
        }

        // Always call playTrack (never rely on togglePlay for resume)
        // because playerState might be stale or track might not be loaded
        console.log('[DEBUG MemoryCard] Calling playTrack()...');
        await playTrack(spotifyUri);
        console.log('[DEBUG MemoryCard] ✓ SDK playback succeeded');
        playbackModeRef.current = 'sdk';
      } catch (err) {
        console.error('❌ [MemoryCard] SDK playback failed:', err);
        console.error('[DEBUG MemoryCard] This could be autoplay policy or Premium requirement');
      }
    } else {
      console.warn('[DEBUG MemoryCard] Cannot use SDK:', { spotifyUri, isReady });
    }
  }, [memory.id, resolveTrack, isReady, playTrack, playerState]);

  const pausePlayback = useCallback(() => {
    if (playbackModeRef.current === 'preview') {
      if (globalCardId === memory.id && globalAudio) {
        globalAudio.pause();
        notifyListeners();
      }
    } else if (playbackModeRef.current === 'sdk') {
      if (isSdkPlaying) {
        togglePlay();
      }
    }
  }, [memory.id, isSdkPlaying, togglePlay]);

  const handleMouseEnter = useCallback(() => {
    console.log('[DEBUG MemoryCard] Mouse enter on memory:', memory.id);
    console.log('[DEBUG MemoryCard] State:', { 
      hasTrack: !!track, 
      spotifyConnected, 
      isReady,
      trackName: track?.track_name 
    });
    
    if (!track || !spotifyConnected) {
      console.log('[DEBUG MemoryCard] Hover ignored: no track or not connected');
      return;
    }
    hoverStartRef.current = Date.now();

    // If this card is already playing, nothing to do
    if (
      (playbackModeRef.current === 'preview' &&
        globalCardId === memory.id &&
        globalAudio &&
        !globalAudio.paused) ||
      (playbackModeRef.current === 'sdk' && isSdkPlaying)
    ) {
      return;
    }

    // 600ms initial delay before starting playback
    hoverTimerRef.current = setTimeout(() => {
      console.log('[DEBUG MemoryCard] 600ms hover delay complete, triggering startPlayback...');
      startPlayback();
    }, 600);
  }, [track, spotifyConnected, memory.id, isSdkPlaying, startPlayback]);

  const handleMouseLeave = useCallback(() => {
    // Cancel pending timer
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }

    const hoverDuration = Date.now() - hoverStartRef.current;
    if (hoverDuration >= 6000) {
      // Hovered 6s+ → keep playing ("sticky")
      // Only stops when another card starts
      return;
    }

    // Short hover → pause
    pausePlayback();
  }, [pausePlayback]);

  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    };
  }, []);

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    onClick(memory);
  };

  return (
    <div
      className="group relative bg-surface border border-border rounded-xl overflow-hidden cursor-pointer hover:border-accent/40 transition-all hover:shadow-[0_0_30px_rgba(20,184,166,0.08)]"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {/* Photo */}
      <div className="aspect-square bg-surface relative overflow-hidden">
        {photo ? (
          <img
            src={getPhotoProxyUrl(photo.base_url, 400, 400, photo.local_url)}
            alt={memory.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-accent/10 to-teal-900/20 flex items-center justify-center">
            <Music className="w-10 h-10 text-accent/30" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3">
        <p className="text-xs text-muted/60 mb-1">
          {format(new Date(memory.memory_date), 'MMM dd, yyyy')}
        </p>
        {track ? (
          <div className="flex items-center gap-2">
            {track.album_image_url && (
              <img
                src={track.album_image_url}
                alt={track.album_name}
                className="w-7 h-7 rounded flex-shrink-0"
              />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate">{track.track_name}</div>
              <div className="text-xs text-muted truncate">{track.artist_name}</div>
            </div>
            {isPlaying && <EqBars />}
          </div>
        ) : (
          <p className="text-xs text-muted/40 italic">No track linked</p>
        )}
      </div>

      {/* Playing indicator bar */}
      {isPlaying && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
      )}
    </div>
  );
}
