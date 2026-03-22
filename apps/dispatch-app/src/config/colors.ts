/**
 * Centralized color palette — zinc scale from Tailwind CSS.
 * All UI components should reference these instead of raw hex values.
 */
export const colors = {
  /** Main background — darkest */
  background: "#09090b",
  /** Elevated surface (cards, inputs, bubbles) */
  surface: "#18181b",
  /** Secondary surface (avatar bg, input bg) */
  surfaceSecondary: "#27272a",
  /** Borders and separators */
  border: "#27272a",
  /** Subtle borders (button outlines) */
  borderSubtle: "#3f3f46",
  /** Primary text */
  textPrimary: "#fafafa",
  /** Secondary text */
  textSecondary: "#a1a1aa",
  /** Tertiary / muted text */
  textMuted: "#71717a",
  /** Placeholder text */
  textPlaceholder: "#52525b",
  /** Error red */
  error: "#ef4444",
  /** Error background */
  errorBg: "#7f1d1d",
  /** Error text (light) */
  errorLight: "#fca5a5",
  /** Success green */
  success: "#22c55e",
  /** Warning yellow */
  warning: "#eab308",
  /** White */
  white: "#ffffff",
  /** Recording red dot */
  recordingRed: "#ef4444",
  /** Avatar text */
  avatarText: "#d4d4d8",
} as const;
