/**
 * Name corrections for speech recognition — fix common misrecognitions.
 * Corrections are loaded from app.yaml at build time via expo config,
 * with a runtime fallback to the display name.
 */

import Constants from "expo-constants";

function loadCorrections(): Record<string, string> {
  // Try to load from app.yaml speechCorrections (baked into extra at build time)
  const extra = Constants.expoConfig?.extra as Record<string, any> | undefined;
  if (extra?.speechCorrections && typeof extra.speechCorrections === "object") {
    return extra.speechCorrections as Record<string, string>;
  }

  // Fallback: correct the display name's lowercase variant to proper case
  const displayName = extra?.displayName || Constants.expoConfig?.name || "";
  if (displayName) {
    return { [displayName.toLowerCase()]: displayName };
  }

  return {};
}

const NAME_CORRECTIONS = loadCorrections();

export function applyNameCorrections(text: string): string {
  if (Object.keys(NAME_CORRECTIONS).length === 0) return text;

  return text.replace(/\b(\w+)\b/g, (match) => {
    const lower = match.toLowerCase();
    return NAME_CORRECTIONS[lower] ?? match;
  });
}
