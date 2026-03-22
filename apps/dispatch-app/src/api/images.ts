import { getApiBaseUrl } from "../config/constants";
import { getDeviceToken } from "./client";

/**
 * Build the full URL for an image resource.
 * Mirrors buildAudioUrl pattern in audio.ts.
 *
 * No local caching needed — expo-image handles disk caching internally.
 */
export function buildImageUrl(imageUrl: string): string {
  const token = getDeviceToken();
  const params = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${getApiBaseUrl()}${imageUrl}${params}`;
}
