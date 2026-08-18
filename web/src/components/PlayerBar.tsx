import { useEffect, useId, useRef, useState } from "react";

export interface PlayerBarTrack {
  rb_content_id: string;
  artist: string;
  title: string;
}

interface PlayerBarProps {
  track: PlayerBarTrack | null;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

// Review finding: the ffmpeg transcode fallback (US5 scenario 4) streams
// chunked with no Content-Length, so the browser reports `duration` as
// `Infinity` -- not 0. Treating only 0 as "not seekable" left the slider
// enabled with an invalid `max="Infinity"` and an aria-valuetext claiming
// "0:00 van 0:00" on exactly that non-seekable path. A non-finite duration
// (Infinity, or NaN before metadata loads) is the actual "can't seek" signal.
function isSeekable(duration: number): boolean {
  return Number.isFinite(duration) && duration > 0;
}

// T065 (FR-025/FR-026, WCAG; proof-of-value cut: progress + seek only, no
// waveform, per plan.md). Playing/paused state is exposed both visually
// (button label, aria-pressed) and to assistive tech via a live status
// region; a missing/unreadable file (spec.md US5 scenario 5) is reported
// by name, not a silent failure or a generic browser media error -- the
// native <audio> error event carries no HTTP detail, so a genuine fetch to
// the same stream URL recovers the backend's {code, message} on failure.
export function PlayerBar({ track }: PlayerBarProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const seekId = useId();

  useEffect(() => {
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setError(null);
  }, [track?.rb_content_id]);

  async function handlePlaybackError() {
    if (!track) return;
    try {
      // Review finding: this diagnostic fetch must not itself become a
      // second full download. A `Range: bytes=0-0` keeps the native path's
      // response to a single byte (still a real 206, still lets a
      // `file_missing`/`track_not_found` error return its usual {code,
      // message} JSON envelope -- that path resolves the id and raises
      // before any range/byte handling ever runs). On the transcode path
      // the backend ignores Range and always answers a plain 200, so
      // `response.body` is cancelled below rather than left to keep
      // piping a live ffmpeg process into a body nobody reads.
      const response = await fetch(`/api/player/stream/${track.rb_content_id}`, {
        headers: { Range: "bytes=0-0" },
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { code?: string } | null;
        setError(
          body?.code === "file_missing"
            ? "Audiobestand ontbreekt op schijf."
            : "Dit nummer kan niet worden afgespeeld.",
        );
        return;
      }
      void response.body?.cancel();
      setError("Dit nummer kan niet worden afgespeeld.");
    } catch {
      setError("Dit nummer kan niet worden afgespeeld.");
    }
  }

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
    } else {
      void audio.play();
    }
  }

  function handleSeek(event: React.ChangeEvent<HTMLInputElement>) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Number(event.target.value);
    setCurrentTime(audio.currentTime);
  }

  if (!track) return null;

  return (
    <div
      role="region"
      aria-label="Speler"
      className="flex flex-wrap items-center gap-16 rounded-md bg-graphite p-16 text-pure-white"
    >
      <audio
        ref={audioRef}
        src={`/api/player/stream/${track.rb_content_id}`}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => setIsPlaying(false)}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
        onError={() => void handlePlaybackError()}
      />

      <button
        type="button"
        onClick={togglePlay}
        aria-pressed={isPlaying}
        disabled={error !== null}
        className="min-h-24 min-w-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
      >
        {isPlaying ? "Pauzeer" : "Afspelen"}
      </button>

      <p className="text-body-lg">
        {track.artist} – {track.title}
      </p>

      <label htmlFor={seekId} className="sr-only">
        Voortgang
      </label>
      <input
        id={seekId}
        type="range"
        min={0}
        max={isSeekable(duration) ? duration : 0}
        step={1}
        value={currentTime}
        onChange={handleSeek}
        disabled={error !== null || !isSeekable(duration)}
        aria-valuetext={
          isSeekable(duration)
            ? `${formatTime(currentTime)} van ${formatTime(duration)}`
            : "Positie onbekend"
        }
        className="min-h-24 flex-1 accent-spotify-green focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
      />
      <p className="text-body-lg text-mist">
        {isSeekable(duration)
          ? `${formatTime(currentTime)} / ${formatTime(duration)}`
          : "Positie onbekend"}
      </p>

      <p role="status" className="sr-only">
        {isPlaying ? "Speelt af" : "Gepauzeerd"}
      </p>
      {error && (
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          {error}
        </p>
      )}
    </div>
  );
}
