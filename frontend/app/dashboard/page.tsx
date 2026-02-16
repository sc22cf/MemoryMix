'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { Music, Camera, Plus, LogOut, RefreshCw, History, Link2, Play } from 'lucide-react';
import Link from 'next/link';
import { format } from 'date-fns';
import { getPhotoProxyUrl } from '@/lib/photo-utils';
import SpotifyPlayer from '@/components/SpotifyPlayer';
import MemoryCard from '@/components/MemoryCard';
import MemoryDetailModal from '@/components/MemoryDetailModal';
import { Memory } from '@/lib/types';

export default function DashboardPage() {
  const { user, loading, logout, refreshUser } = useAuth();
  const router = useRouter();
  const [playingUri, setPlayingUri] = useState<string | undefined>(undefined);
  const [searchingTrack, setSearchingTrack] = useState<number | null>(null);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);

  useEffect(() => {
    if (!loading && !user) {
      router.push('/');
    }
  }, [user, loading, router]);

  const { data: memories, refetch: refetchMemories } = useQuery({
    queryKey: ['memories'],
    queryFn: () => apiClient.getMemories(0, 100),
    enabled: !!user,
  });

  const { data: listeningHistory, refetch: refetchHistory } = useQuery({
    queryKey: ['listening-history'],
    queryFn: () => apiClient.getListeningHistory(10, 0),
    enabled: !!user,
  });

  const handleSyncLastfm = async () => {
    try {
      await apiClient.syncListeningHistory(3);
      refetchHistory();
      alert('Last.fm history synced successfully!');
    } catch (error) {
      console.error('Failed to sync:', error);
      alert('Failed to sync Last.fm history');
    }
  };

  const handleConnectSpotify = async () => {
    try {
      localStorage.setItem('spotify_connect', '1');
      const { auth_url } = await apiClient.getSpotifyLoginUrl();
      window.location.href = auth_url;
    } catch (error) {
      console.error('Failed to get Spotify URL:', error);
    }
  };

  const handlePlayTrack = async (track: any) => {
    if (!user?.spotify_connected) return;
    setSearchingTrack(track.id);
    try {
      const result = await apiClient.searchSpotifyTrack(track.track_name, track.artist_name);
      if (result.found && result.uri) {
        setPlayingUri(result.uri);
      } else {
        alert('Track not found on Spotify');
      }
    } catch (error) {
      console.error('Failed to search Spotify:', error);
    } finally {
      setSearchingTrack(null);
    }
  };

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-surface/50 backdrop-blur-md sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-accent-subtle flex items-center justify-center">
                <Music className="w-4 h-4 text-accent" />
              </div>
              <h1 className="text-xl font-bold tracking-tight">Memory<span className="text-accent">Mix</span></h1>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted">
                {user.display_name || 'User'}
              </span>
              <button
                onClick={logout}
                className="flex items-center gap-2 px-3 py-1.5 text-sm text-muted hover:text-danger rounded-lg hover:bg-danger/10 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        {/* Quick Actions */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 mb-10">
          <Link
            href="/memories/new"
            className="group bg-surface border border-border rounded-xl p-6 hover:border-accent/40 transition-all hover:shadow-[0_0_30px_rgba(20,184,166,0.06)]"
          >
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-lg bg-accent-subtle flex items-center justify-center group-hover:scale-110 transition-transform">
                <Plus className="w-5 h-5 text-accent" />
              </div>
              <h2 className="text-lg font-semibold">Create New Memory</h2>
            </div>
            <p className="text-sm text-muted ml-13">
              Add photos and match them with your listening history
            </p>
          </Link>

          {user.lastfm_username && (
            <button
              onClick={handleSyncLastfm}
              className="group bg-surface border border-border rounded-xl p-6 hover:border-accent/40 transition-all text-left hover:shadow-[0_0_30px_rgba(20,184,166,0.06)]"
            >
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-accent-subtle flex items-center justify-center group-hover:scale-110 transition-transform">
                  <RefreshCw className="w-5 h-5 text-accent" />
                </div>
                <h2 className="text-lg font-semibold">Sync Last.fm</h2>
              </div>
              <p className="text-sm text-muted ml-13">
                Update your listening history from Last.fm
              </p>
            </button>
          )}

          {user.spotify_connected ? (
            <div
              className="group bg-surface border border-[#1DB954]/20 rounded-xl p-6"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-[#1DB954]/10 flex items-center justify-center">
                    <svg className="w-5 h-5 text-[#1DB954]" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
                    </svg>
                  </div>
                  <h2 className="text-lg font-semibold">Spotify Connected</h2>
                </div>
                <button
                  onClick={handleConnectSpotify}
                  className="text-xs text-muted hover:text-[#1DB954] transition-colors px-2 py-1 rounded hover:bg-[#1DB954]/10"
                >
                  Reconnect
                </button>
              </div>
              <p className="text-sm text-muted ml-13">
                Play tracks directly from your listening history
              </p>
            </div>
          ) : (
            <button
              onClick={handleConnectSpotify}
              className="group bg-surface border border-border rounded-xl p-6 hover:border-[#1DB954]/40 transition-all text-left hover:shadow-[0_0_30px_rgba(29,185,84,0.06)]"
            >
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-[#1DB954]/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <Link2 className="w-5 h-5 text-[#1DB954]" />
                </div>
                <h2 className="text-lg font-semibold">Connect Spotify</h2>
              </div>
              <p className="text-sm text-muted ml-13">
                Link your Spotify account to play tracks
              </p>
            </button>
          )}
        </div>

        {/* Memories */}
        <div className="mb-10">
          <div className="flex justify-between items-center mb-5">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Camera className="w-5 h-5 text-accent" />
              Your Memories
            </h2>
          </div>

          {memories && memories.length > 0 ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {memories.map((memory: Memory) => (
                <MemoryCard
                  key={memory.id}
                  memory={memory}
                  onClick={setSelectedMemory}
                  spotifyConnected={!!user.spotify_connected}
                />
              ))}
            </div>
          ) : (
            <div className="bg-surface border border-border rounded-xl p-12 text-center">
              <div className="w-16 h-16 rounded-2xl bg-accent-subtle flex items-center justify-center mx-auto mb-4">
                <Camera className="w-8 h-8 text-accent/50" />
              </div>
              <h3 className="text-lg font-semibold mb-2">
                No memories yet
              </h3>
              <p className="text-sm text-muted mb-6">
                Create your first memory to get started
              </p>
              <Link
                href="/memories/new"
                className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-background px-5 py-2.5 rounded-lg font-medium text-sm"
              >
                <Plus className="w-4 h-4" />
                Create Memory
              </Link>
            </div>
          )}
        </div>

        {/* Recent Listening History */}
        <div>
          <div className="flex justify-between items-center mb-5">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Music className="w-5 h-5 text-accent" />
              Recent Listening
            </h2>
            <Link
              href="/history"
              className="text-sm text-accent hover:text-accent-hover font-medium flex items-center gap-1"
            >
              <History className="w-3.5 h-3.5" />
              Full History
            </Link>
          </div>

          {listeningHistory && listeningHistory.length > 0 ? (
            <div className="bg-surface border border-border rounded-xl overflow-hidden divide-y divide-border">
              {listeningHistory.map((track: any) => (
                <div
                  key={track.id}
                  className="flex items-center gap-4 p-4 hover:bg-surface-hover transition-colors"
                >
                  {track.album_image_url ? (
                    <img
                      src={track.album_image_url}
                      alt={track.album_name}
                      className="w-11 h-11 rounded-lg flex-shrink-0"
                    />
                  ) : (
                    <div className="w-11 h-11 rounded-lg bg-accent-subtle flex items-center justify-center flex-shrink-0">
                      <Music className="w-5 h-5 text-accent/50" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm truncate">
                      {track.track_name}
                    </div>
                    <div className="text-xs text-muted truncate">
                      {track.artist_name}
                    </div>
                  </div>
                  {user.spotify_connected && (
                    <button
                      onClick={() => handlePlayTrack(track)}
                      disabled={searchingTrack === track.id}
                      className="p-2 text-[#1DB954] hover:bg-[#1DB954]/10 rounded-lg transition-colors flex-shrink-0 disabled:opacity-50"
                      title="Play on Spotify"
                    >
                      {searchingTrack === track.id ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Play className="w-4 h-4" fill="currentColor" />
                      )}
                    </button>
                  )}
                  <div className="text-xs text-muted/70 flex-shrink-0">
                    {format(new Date(track.played_at), 'MMM dd, hh:mm a')}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-surface border border-border rounded-xl p-12 text-center">
              <div className="w-16 h-16 rounded-2xl bg-accent-subtle flex items-center justify-center mx-auto mb-4">
                <Music className="w-8 h-8 text-accent/50" />
              </div>
              <h3 className="text-lg font-semibold mb-2">
                No listening history
              </h3>
              <p className="text-sm text-muted mb-6">
                Sync your Last.fm history to see your scrobbles
              </p>
              <button
                onClick={handleSyncLastfm}
                className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-background px-5 py-2.5 rounded-lg font-medium text-sm"
              >
                <RefreshCw className="w-4 h-4" />
                Sync Now
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Spotify Player — sticky bottom */}
      {user.spotify_connected && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-surface/95 backdrop-blur-md px-4 py-3">
          <div className="container mx-auto">
            <SpotifyPlayer spotifyUri={playingUri} />
          </div>
        </div>
      )}

      {/* Memory Detail Modal */}
      {selectedMemory && (
        <MemoryDetailModal
          memory={selectedMemory}
          onClose={() => setSelectedMemory(null)}
          spotifyConnected={!!user.spotify_connected}
        />
      )}
    </div>
  );
}
