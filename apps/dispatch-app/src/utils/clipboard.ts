import { Platform } from "react-native";

/**
 * Copy text to clipboard — cross-platform.
 * Native: uses expo-clipboard. Web: uses navigator.clipboard.
 * Returns true on success, false on failure.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (Platform.OS === "web") {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
      return false;
    }

    // Native: dynamically import expo-clipboard
    const Clipboard = require("expo-clipboard");
    await Clipboard.setStringAsync(text);
    return true;
  } catch {
    return false;
  }
}
