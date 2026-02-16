'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { Music, ArrowLeft, RefreshCw, ChevronLeft, ChevronRight, ExternalLink, Search, Play } from 'lucide-react';
import Link from 'next/link';
import { format } from 'date-fns';
import SpotifyPlayer from '@/components/SpotifyPlayer';

export default function HistoryPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [syncing, setSyncing] = useState(false);
  const [syncingFull, setSyncingFull] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [playingUri, setPlayingUri] = useState<string | undefined>(undefined);
  const [searchingTrack, setSearchingTrack] = useState<number | null>(null);

  useEffect(() => {
    if (!loading && !user) {
      router.push('/');
    }
  }, [user, loading, router]);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['full-history', page, perPage],
    queryFn: () => apiClient.getFullListeningHistory(page, perPage),
    enabled: !!user,
  });

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await apiClient.syncListeningHistory(3);
      alert(`Synced ${result.tracks_added} new tracks!`);
      refetch();
    } catch (error) {
      console.error('Failed to sync:', error);
      alert('Failed to sync Last.fm history');
    } finally {
      setSyncing(false);
    }
  };

  const handleFullSync = async () => {
    if (!confirm('This will fetch up to 2000 tracks from your Last.fm history. Continue?')) {
      return;
    }
    setSyncingFull(true);
    try {
      const result = await apiClient.syncFullHistory(10);
      alert(`Synced ${result.tracks_added} new tracks!`);
      refetch();
    } catch (error) {
      console.error('Failed to sync:', error);
      alert('Failed to sync full Last.fm history');
    } finally {
      setSyncingFull(false);
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

  const tracks = data?.tracks || [];
  const totalPages = data?.total_pages || 0;
  const total = data?.total || 0;

  const filteredTracks = searchQuery
    ? tracks.filter(
        (track: any) =>
          track.track_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          track.artist_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          track.album_name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : tracks;

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
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 text-muted hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Dashboard
            </Link>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSync}
                disabled={syncing || syncingFull}
                className="flex items-center gap-2 px-3 py-1.5 bg-accent hover:bg-accent-hover text-background rounded-lg disabled:opacity-50 text-sm font-medium"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Syncing...' : 'Sync Recent'}
              </button>
              <button
                onClick={handleFullSync}
                disabled={syncing || syncingFull}
                className="flex items-center gap-2 px-3 py-1.5 bg-surface border border-border hover:border-accent/40 text-foreground rounded-lg disabled:opacity-50 text-sm font-medium"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${syncingFull ? 'animate-spin' : ''}`} />
                {syncingFull ? 'Syncing...' : 'Full Sync'}
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        {/* Title & Stats */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold flex items-center gap-3 mb-1.5">
            <Music className="w-6 h-6 text-accent" />
            Listening History
          </h1>
          <p className="text-sm text-muted">
            {total > 0
              ? `${total.toLocaleString()} scrobbles synced`
              : 'No tracks synced yet — click Sync to get started.'}
          </p>
        </div>

        {/* Search */}
        <div className="mb-6">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted/50" />
            <input
              type="text"
              placeholder="Search tracks, artists, albums..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-surface border border-border rounded-lg text-sm text-foreground placeholder:text-muted/40 focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors"
            />
          </div>
        </div>

        {/* Track List */}
        {isLoading ? (
          <div className="bg-surface border border-border rounded-xl p-12 text-center">
            <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent mx-auto mb-4"></div>
            <p className="text-sm text-muted">Loading history...</p>
          </div>
        ) : filteredTracks.length > 0 ? (
          <div className="bg-surface border border-border rounded-xl overflow-hidden">
            {/* Table Header */}
            <div className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-border text-xs font-medium text-muted uppercase tracking-wider">
              <div className="col-span-1">#</div>
              <div className="col-span-4">Track</div>
              <div className="col-span-3">Artist</div>
              <div className="col-span-2">Album</div>
              <div className="col-span-2 text-right">Played</div>
            </div>

            {/* Track Rows */}
            {filteredTracks.map((track: any, index: number) => (
              <div
                key={track.id}
                className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-border/50 last:border-b-0 hover:bg-surface-hover items-center transition-colors"
              >
                <div className="col-span-1 text-xs text-muted/50 tabular-nums flex items-center gap-1">
                  {user?.spotify_connected ? (
                    <button
                      onClick={() => handlePlayTrack(track)}
                      disabled={searchingTrack === track.id}
                      className="text-[#1DB954] hover:scale-110 transition-transform disabled:opacity-50"
                      title="Play on Spotify"
                    >
                      {searchingTrack === track.id ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Play className="w-3.5 h-3.5" fill="currentColor" />
                      )}
                    </button>
                  ) : (
                    <span>{(page - 1) * perPage + index + 1}</span>
                  )}
                </div>
                <div className="col-span-4 flex items-center gap-3 min-w-0">
                  {track.album_image_url ? (
                    <img
                      src={track.album_image_url}
                      alt={track.album_name}
                      className="w-9 h-9 rounded-md flex-shrink-0"
                    />
                  ) : (
                    <div className="w-9 h-9 rounded-md bg-accent-subtle flex items-center justify-center flex-shrink-0">
                      <Music className="w-4 h-4 text-accent/50" />
                    </div>
                  )}
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{track.track_name}</div>
                  </div>
                </div>
                <div className="col-span-3 text-sm text-muted truncate">
                  {track.artist_name}
                </div>
                <div className="col-span-2 text-sm text-muted/60 truncate">
                  {track.album_name}
                </div>
                <div className="col-span-2 text-xs text-muted/50 text-right flex items-center justify-end gap-2">
                  <span>{format(new Date(track.played_at), 'MMM dd, hh:mm a')}</span>
                  {track.track_url && (
                    <a
                      href={track.track_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent/50 hover:text-accent"
                      title="Open on Last.fm"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
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
              {searchQuery ? 'No matching tracks' : 'No listening history'}
            </h3>
            <p className="text-sm text-muted mb-6">
              {searchQuery
                ? 'Try a different search query.'
                : 'Sync your Last.fm history to see your scrobbles here.'}
            </p>
            {!searchQuery && (
              <button
                onClick={handleSync}
                className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-background px-5 py-2.5 rounded-lg font-medium text-sm"
              >
                <RefreshCw className="w-4 h-4" />
                Sync Now
              </button>
            )}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && !searchQuery && (
          <div className="flex items-center justify-between mt-6">
            <p className="text-xs text-muted">
              {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} of{' '}
              {total.toLocaleString()}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="flex items-center gap-1 px-3 py-1.5 bg-surface border border-border rounded-lg hover:border-accent/40 disabled:opacity-30 disabled:cursor-not-allowed text-sm"
              >
                <ChevronLeft className="w-4 h-4" />
                Prev
              </button>
              <span className="px-3 py-1.5 text-xs text-muted tabular-nums">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="flex items-center gap-1 px-3 py-1.5 bg-surface border border-border rounded-lg hover:border-accent/40 disabled:opacity-30 disabled:cursor-not-allowed text-sm"
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Spotify Player — sticky bottom */}
      {user?.spotify_connected && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-surface/95 backdrop-blur-md px-4 py-3">
          <div className="container mx-auto">
            <SpotifyPlayer spotifyUri={playingUri} />
          </div>
        </div>
      )}
    </div>
  );
}
