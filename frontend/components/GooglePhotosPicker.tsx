'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Loader2, Image as ImageIcon, ExternalLink } from 'lucide-react';

const PICKER_API_BASE = 'https://photospicker.googleapis.com/v1';

interface PickedPhoto {
  google_photo_id: string;
  base_url: string;
  filename: string;
  mime_type: string;
  creation_time: string;
  width: number | null;
  height: number | null;
}

interface GooglePhotosPickerProps {
  accessToken: string;
  onPhotosPicked: (photos: PickedPhoto[]) => void;
  onError: (message: string) => void;
  onDone: () => void;
}

type PickerState =
  | 'idle'
  | 'creating-session'
  | 'waiting-for-user'
  | 'fetching-results'
  | 'done'
  | 'error';

export function useGooglePhotosPicker({
  accessToken,
  onPhotosPicked,
  onError,
  onDone,
}: GooglePhotosPickerProps) {
  const [state, setState] = useState<PickerState>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pickerUri, setPickerUri] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const popupRef = useRef<Window | null>(null);

  const cleanup = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // Delete session when done
  const deleteSession = useCallback(
    async (sid: string) => {
      try {
        await fetch(`${PICKER_API_BASE}/sessions/${sid}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${accessToken}` },
        });
      } catch {
        // Best effort cleanup
      }
    },
    [accessToken],
  );

  // Fetch picked media items
  const fetchPickedMediaItems = useCallback(
    async (sid: string) => {
      setState('fetching-results');
      const allItems: PickedPhoto[] = [];
      let pageToken: string | undefined;

      try {
        do {
          const params = new URLSearchParams({ sessionId: sid, pageSize: '100' });
          if (pageToken) params.set('pageToken', pageToken);

          const resp = await fetch(`${PICKER_API_BASE}/mediaItems?${params}`, {
            headers: { Authorization: `Bearer ${accessToken}` },
          });

          if (!resp.ok) {
            const errText = await resp.text();
            console.error('Failed to fetch picked items:', resp.status, errText);
            onError(`Failed to retrieve picked photos (${resp.status})`);
            setState('error');
            return;
          }

          const data = await resp.json();
          const items: PickedPhoto[] = (data.mediaItems || [])
            .filter((item: any) => item.type === 'PHOTO')
            .map((item: any) => ({
              google_photo_id: item.id,
              base_url: item.mediaFile?.baseUrl || '',
              filename: item.mediaFile?.filename || 'photo',
              mime_type: item.mediaFile?.mimeType || 'image/jpeg',
              creation_time: item.createTime || new Date().toISOString(),
              width: item.mediaFile?.mediaFileMetadata?.width || null,
              height: item.mediaFile?.mediaFileMetadata?.height || null,
            }));

          allItems.push(...items);
          pageToken = data.nextPageToken;
        } while (pageToken);

        onPhotosPicked(allItems);
        setState('done');
        onDone();

        // Clean up the session
        await deleteSession(sid);
      } catch (err) {
        console.error('Error fetching picked items:', err);
        onError('Failed to retrieve picked photos');
        setState('error');
      }
    },
    [accessToken, onPhotosPicked, onError, onDone, deleteSession],
  );

  // Poll session status
  const pollSession = useCallback(
    async (sid: string) => {
      try {
        const resp = await fetch(`${PICKER_API_BASE}/sessions/${sid}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });

        if (!resp.ok) {
          console.error('Session poll failed:', resp.status);
          return;
        }

        const session = await resp.json();

        if (session.mediaItemsSet) {
          cleanup();
          await fetchPickedMediaItems(sid);
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    },
    [accessToken, cleanup, fetchPickedMediaItems],
  );

  // Start the picker flow
  const startPicker = useCallback(async () => {
    if (!accessToken) return;

    setState('creating-session');

    try {
      const resp = await fetch(`${PICKER_API_BASE}/sessions`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        console.error('Failed to create session:', resp.status, errText);
        onError(`Failed to start photo picker (${resp.status}). Try signing out and back in.`);
        setState('error');
        return;
      }

      const session = await resp.json();
      const sid = session.id;
      // Append /autoclose so Google auto-closes the tab when user finishes
      const uri = session.pickerUri + '/autoclose';
      const pollInterval = session.pollingConfig?.pollInterval
        ? parseFloat(session.pollingConfig.pollInterval) * 1000
        : 5000;

      setSessionId(sid);
      setPickerUri(uri);
      setState('waiting-for-user');

      // Open Google's picker in a popup
      const popup = window.open(
        uri,
        'google-photos-picker',
        'width=900,height=700,scrollbars=yes,resizable=yes',
      );
      popupRef.current = popup;

      // Start polling
      pollingRef.current = setInterval(() => {
        pollSession(sid);
      }, pollInterval);

      // Safety timeout — stop polling after 10 minutes
      setTimeout(() => {
        if (pollingRef.current) {
          cleanup();
          setState('idle');
        }
      }, 10 * 60 * 1000);
    } catch (err) {
      console.error('Error starting picker:', err);
      onError('Failed to start photo picker');
      setState('error');
    }
  }, [accessToken, onError, cleanup, pollSession]);

  // Cleanup on unmount
  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  const cancel = useCallback(() => {
    cleanup();
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.close();
    }
    if (sessionId) {
      deleteSession(sessionId);
    }
    setState('idle');
    setSessionId(null);
    setPickerUri(null);
  }, [cleanup, sessionId, deleteSession]);

  return {
    state,
    pickerUri,
    startPicker,
    cancel,
  };
}

// UI component shown while waiting for user to pick photos
export function PickerStatusOverlay({
  state,
  pickerUri,
  onCancel,
}: {
  state: PickerState;
  pickerUri: string | null;
  onCancel: () => void;
}) {
  if (state === 'idle' || state === 'done') return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-surface border border-border rounded-2xl shadow-2xl w-full max-w-md p-8 text-center">
        {state === 'creating-session' && (
          <>
            <Loader2 className="w-10 h-10 text-accent animate-spin mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Starting Google Photos...</h3>
            <p className="text-muted text-sm">Creating a picking session</p>
          </>
        )}

        {state === 'waiting-for-user' && (
          <>
            <div className="w-12 h-12 rounded-xl bg-accent-subtle flex items-center justify-center mx-auto mb-4">
              <ImageIcon className="w-6 h-6 text-accent" />
            </div>
            <h3 className="text-lg font-semibold mb-2">
              Pick your photos in Google Photos
            </h3>
            <p className="text-muted text-sm mb-4">
              A Google Photos window should have opened. Select your photos there and tap "Done"
              when finished.
            </p>
            {pickerUri && (
              <a
                href={pickerUri}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-accent hover:text-accent-hover text-sm font-medium mb-4"
              >
                <ExternalLink className="w-4 h-4" />
                Reopen Google Photos picker
              </a>
            )}
            <div className="flex items-center justify-center gap-2 text-muted/50 text-sm mt-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Waiting for you to finish picking...
            </div>
          </>
        )}

        {state === 'fetching-results' && (
          <>
            <Loader2 className="w-10 h-10 text-accent animate-spin mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Loading your photos...</h3>
            <p className="text-muted text-sm">Fetching the photos you picked</p>
          </>
        )}

        {state === 'error' && (
          <>
            <div className="w-12 h-12 rounded-xl bg-danger/10 flex items-center justify-center mx-auto mb-4">
              <span className="text-danger text-xl font-bold">!</span>
            </div>
            <h3 className="text-lg font-semibold mb-2">Something went wrong</h3>
            <p className="text-muted text-sm">Please try again</p>
          </>
        )}

        <button
          onClick={onCancel}
          className="mt-6 px-5 py-2 text-muted hover:text-foreground hover:bg-surface-hover rounded-lg font-medium text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
