import { Platform } from "react-native";

// expo-haptics has a web shim but may not be available in all environments
let Haptics: typeof import("expo-haptics") | null = null;
if (Platform.OS !== "web") {
  try {
    Haptics = require("expo-haptics") as typeof import("expo-haptics");
  } catch { /* native module not available */ }
}

export async function impactLight(): Promise<void> {
  await Haptics?.impactAsync(Haptics.ImpactFeedbackStyle.Light);
}

export async function impactMedium(): Promise<void> {
  await Haptics?.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
}

export async function impactHeavy(): Promise<void> {
  await Haptics?.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
}

export async function selectionFeedback(): Promise<void> {
  await Haptics?.selectionAsync();
}

export async function notificationSuccess(): Promise<void> {
  await Haptics?.notificationAsync(Haptics.NotificationFeedbackType.Success);
}

export async function notificationWarning(): Promise<void> {
  await Haptics?.notificationAsync(Haptics.NotificationFeedbackType.Warning);
}

export async function notificationError(): Promise<void> {
  await Haptics?.notificationAsync(Haptics.NotificationFeedbackType.Error);
}
