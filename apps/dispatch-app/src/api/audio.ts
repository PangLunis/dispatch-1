import { Platform } from "react-native";
import { getApiBaseUrl } from "../config/constants";
import { getDeviceToken } from "./client";

/**
 * Build the full URL for an audio resource.
 */
function buildAudioUrl(audioUrl: string): string {
  const token = getDeviceToken();
  const params = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${getApiBaseUrl()}${audioUrl}${params}`;
}

/**
 * Get a playable URL for an audio file.
 *
 * On web, returns the URL directly (browser cache handles caching).
 * On native, uses expo-file-system for local caching via the new Paths/File API.
 */
export async function downloadAudio(audioUrl: string): Promise<string> {
  const fullUrl = buildAudioUrl(audioUrl);

  if (Platform.OS === "web") {
    return fullUrl;
  }

  // On native, use expo-file-system new API for caching
  try {
    const { Paths, File } = require("expo-file-system") as typeof import("expo-file-system");
    const messageId = audioUrl.split("/").pop();

    // Check for existing cached files with known extensions
    for (const ext of [".wav", ".mp3", ".m4a", ".aac"]) {
      const existing = new File(Paths.cache, `audio-${messageId}${ext}`);
      if (existing.exists) {
        return existing.uri;
      }
    }

    // Clean up old extensionless cache files (they can't be played by AVPlayer)
    try {
      const oldFile = new File(Paths.cache, `audio-${messageId}`);
      if (oldFile.exists) {
        oldFile.delete();
      }
    } catch {
      // Ignore cleanup errors
    }

    // Download via fetch and write to cache with correct extension
    const response = await fetch(fullUrl);
    if (!response.ok) {
      throw new Error(`Audio download failed: ${response.status} ${response.statusText}`);
    }
    const contentType = response.headers.get("content-type") || "";
    // Map content type to extension for AVPlayer compatibility
    // Server generates WAV by default via Kokoro TTS
    let ext = ".wav"; // default — matches server TTS output
    if (contentType.includes("mp3") || contentType.includes("mpeg")) {
      ext = ".mp3";
    } else if (contentType.includes("m4a") || contentType.includes("mp4") || contentType.includes("aac")) {
      ext = ".m4a";
    }
    const cachedFile = new File(Paths.cache, `audio-${messageId}${ext}`);
    const blob = await response.blob();
    const arrayBuffer = await blob.arrayBuffer();
    await cachedFile.write(new Uint8Array(arrayBuffer));

    return cachedFile.uri;
  } catch (err) {
    console.warn("[downloadAudio] Cache failed, falling back to direct URL:", (err as Error)?.message || err);
    // If file system operations fail, fall back to direct URL
    return fullUrl;
  }
}
