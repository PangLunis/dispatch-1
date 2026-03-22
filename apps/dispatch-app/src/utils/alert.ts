import { Alert, Platform } from "react-native";

/**
 * Cross-platform alert — uses window.alert on web, Alert.alert on native.
 */
export function showAlert(title: string, message: string): void {
  if (Platform.OS === "web") {
    window.alert(`${title}: ${message}`);
  } else {
    Alert.alert(title, message);
  }
}

/**
 * Cross-platform confirm dialog.
 * Returns true if user confirmed, false if cancelled.
 */
export function showConfirm(title: string, message: string): Promise<boolean> {
  if (Platform.OS === "web") {
    return Promise.resolve(window.confirm(message));
  }

  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
      { text: "OK", onPress: () => resolve(true) },
    ]);
  });
}

/**
 * Cross-platform destructive confirm dialog.
 */
export function showDestructiveConfirm(
  title: string,
  message: string,
  destructiveLabel: string = "Delete",
): Promise<boolean> {
  if (Platform.OS === "web") {
    return Promise.resolve(window.confirm(message));
  }

  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
      {
        text: destructiveLabel,
        style: "destructive",
        onPress: () => resolve(true),
      },
    ]);
  });
}

/**
 * Cross-platform text prompt.
 * Returns the entered text, or null if cancelled.
 * NOTE: Alert.prompt is iOS-only — this function is for iOS+web targets.
 */
export function showPrompt(
  title: string,
  message: string,
  defaultValue?: string,
): Promise<string | null> {
  if (Platform.OS === "web") {
    const result = window.prompt(message, defaultValue);
    return Promise.resolve(result?.trim() || null);
  }

  return new Promise((resolve) => {
    Alert.prompt(
      title,
      message,
      [
        { text: "Cancel", style: "cancel", onPress: () => resolve(null) },
        {
          text: "OK",
          onPress: (text?: string) => resolve(text?.trim() || null),
        },
      ],
      "plain-text",
      defaultValue,
    );
  });
}
