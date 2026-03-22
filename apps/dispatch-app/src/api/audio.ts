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
    const cachedFile = new File(Paths.cache, `audio-${messageId}.wav`);

    if (cachedFile.exists) {
      return cachedFile.uri;
    }

    // Download via fetch and write to cache
    const response = await fetch(fullUrl);
    const blob = await response.blob();
    const arrayBuffer = await blob.arrayBuffer();
    await cachedFile.write(new Uint8Array(arrayBuffer));

    return cachedFile.uri;
  } catch {
    // If file system operations fail, fall back to direct URL
    return fullUrl;
  }
}
