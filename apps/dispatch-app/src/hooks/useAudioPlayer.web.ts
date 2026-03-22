import { useCallback, useRef, useState } from "react";

export interface AudioPlayerState {
  isPlaying: boolean;
  isPaused: boolean;
  currentMessageId: string | null;
  play: (messageId: string, audioUrl: string) => Promise<void>;
  pause: () => void;
  resume: () => void;
  stop: () => void;
}

export function useAudioPlayer(): AudioPlayerState {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [currentMessageId, setCurrentMessageId] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentMessageIdRef = useRef<string | null>(null);

  const resetState = useCallback(() => {
    setIsPlaying(false);
    setIsPaused(false);
    setCurrentMessageId(null);
    currentMessageIdRef.current = null;
  }, []);

  const cleanupAudio = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audioRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    cleanupAudio();
    resetState();
  }, [cleanupAudio, resetState]);

  const play = useCallback(
    async (messageId: string, audioUrl: string) => {
      // Stop any currently playing audio
      cleanupAudio();

      // On web, downloadAudio just returns the full URL
      const { downloadAudio } = await import("../api/audio");
      const url = await downloadAudio(audioUrl);

      const audio = new Audio(url);
      audioRef.current = audio;
      currentMessageIdRef.current = messageId;

      setCurrentMessageId(messageId);
      setIsPlaying(true);
      setIsPaused(false);

      audio.onended = () => {
        resetState();
        audioRef.current = null;
      };

      audio.onpause = () => {
        // Only set paused if we didn't explicitly stop or end
        if (currentMessageIdRef.current === messageId && audioRef.current) {
          setIsPlaying(false);
          setIsPaused(true);
        }
      };

      audio.onplay = () => {
        if (currentMessageIdRef.current === messageId) {
          setIsPlaying(true);
          setIsPaused(false);
        }
      };

      audio.onerror = () => {
        resetState();
        audioRef.current = null;
      };

      try {
        await audio.play();
      } catch {
        resetState();
        audioRef.current = null;
      }
    },
    [cleanupAudio, resetState],
  );

  const pause = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      // State will be set via the onpause handler
    }
  }, []);

  const resume = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.play();
      // State will be set via the onplay handler
    }
  }, []);

  return {
    isPlaying,
    isPaused,
    currentMessageId,
    play,
    pause,
    resume,
    stop,
  };
}
