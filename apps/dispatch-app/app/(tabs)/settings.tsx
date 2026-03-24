import React, { useCallback, useEffect, useState } from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router } from "expo-router";
// expo-notifications is iOS/Android only — conditionally import for web compat
let Notifications: typeof import("expo-notifications") | null = null;
if (Platform.OS !== "web") {
  try {
    Notifications = require("expo-notifications") as typeof import("expo-notifications");
  } catch { /* native module not available */ }
}
import { branding } from "@/src/config/branding";
import {
  getApiBaseUrl,
  setApiBaseUrl,
  getDefaultUrl,
  API_URL_STORAGE_KEY,
} from "@/src/config/constants";
import { useDeviceToken } from "@/src/hooks/useDeviceToken";
import { clearMessages, restartSession } from "@/src/api/chats";
import { apiRequest } from "@/src/api/client";
import { copyToClipboard } from "@/src/utils/clipboard";
import { getItem, setItem, deleteItem } from "@/src/utils/storage";
import {
  showAlert,
  showDestructiveConfirm,
  showPrompt,
} from "@/src/utils/alert";

type ConnectionStatus = "checking" | "connected" | "disconnected";

export default function SettingsScreen() {
  const { token } = useDeviceToken();
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("checking");
  const [copiedToken, setCopiedToken] = useState(false);
  const [currentUrl, setCurrentUrl] = useState(getApiBaseUrl());

  // Load persisted API URL on mount
  useEffect(() => {
    (async () => {
      const saved = await getItem(API_URL_STORAGE_KEY);
      if (saved) {
        setApiBaseUrl(saved);
        setCurrentUrl(saved);
      }
    })();
  }, []);

  // Check connection to the API server
  const checkConnection = useCallback(async () => {
    setConnectionStatus("checking");
    try {
      await apiRequest("/chats", { timeout: 5000 });
      setConnectionStatus("connected");
      return true;
    } catch {
      setConnectionStatus("disconnected");
      return false;
    }
  }, []);

  // Auto-retry connection every 5s when disconnected
  useEffect(() => {
    checkConnection();

    const interval = setInterval(async () => {
      try {
        await apiRequest("/chats", { timeout: 5000 });
        setConnectionStatus("connected");
      } catch {
        setConnectionStatus("disconnected");
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [checkConnection]);

  // Change API server URL manually
  const handleChangeUrl = useCallback(async () => {
    const newUrl = await showPrompt(
      "API Server URL",
      "Enter the full URL (e.g. http://100.70.178.37:9091)",
      currentUrl,
    );
    if (!newUrl || newUrl === currentUrl) return;

    // Normalize: remove trailing slash
    const normalized = newUrl.replace(/\/+$/, "");
    setApiBaseUrl(normalized);
    setCurrentUrl(normalized);
    await setItem(API_URL_STORAGE_KEY, normalized);

    // Test the new URL
    checkConnection();
  }, [currentUrl, checkConnection]);

  // Reset API URL to default
  const handleResetUrl = useCallback(async () => {
    const defaultUrl = getDefaultUrl();
    setApiBaseUrl(defaultUrl);
    setCurrentUrl(defaultUrl);
    await deleteItem(API_URL_STORAGE_KEY);
    checkConnection();
  }, [checkConnection]);

  // Copy device token to clipboard (cross-platform)
  const handleCopyToken = useCallback(async () => {
    if (!token) return;
    const success = await copyToClipboard(token);
    if (success) {
      setCopiedToken(true);
      setTimeout(() => setCopiedToken(false), 2000);
    }
  }, [token]);

  // Clear all data
  const handleClearData = useCallback(async () => {
    const confirmed = await showDestructiveConfirm(
      "Clear All Data",
      "Clear all message data? This cannot be undone.",
      "Clear",
    );
    if (!confirmed) return;

    try {
      await clearMessages("voice");
      showAlert("Success", "All data cleared.");
    } catch {
      showAlert("Error", "Failed to clear data.");
    }
  }, []);

  // Clear notifications
  const handleClearNotifications = useCallback(async () => {
    await Notifications?.dismissAllNotificationsAsync();
    await Notifications?.setBadgeCountAsync(0);
    showAlert("Done", "Notifications cleared.");
  }, []);

  // Restart session
  const handleRestartSession = useCallback(async () => {
    const confirmed = await showDestructiveConfirm(
      "Restart Session",
      "Restart the Claude session? This will clear the conversation context.",
      "Restart",
    );
    if (!confirmed) return;

    try {
      await restartSession("voice");
      showAlert("Success", "Session restarted.");
    } catch {
      showAlert("Error", "Failed to restart session.");
    }
  }, []);

  const displayUrl = currentUrl || "(same-origin)";
  const truncatedToken = token
    ? `${token.slice(0, 8)}...${token.slice(-4)}`
    : "Loading...";

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
    >
      {/* App Header */}
      <View style={styles.appHeader}>
        <Text style={styles.appName}>
          {branding.displayName}
        </Text>
        <Text style={styles.appVersion}>v1.0.0</Text>
        <Text style={styles.poweredBy}>Powered by Claude</Text>
      </View>

      {/* Connection Section */}
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>CONNECTION</Text>
        <View style={styles.sectionCard}>
          <Pressable style={styles.row} onPress={handleChangeUrl}>
            <Text style={styles.rowLabel}>API Server</Text>
            <Text style={styles.rowValue} numberOfLines={1}>
              {displayUrl}
            </Text>
          </Pressable>
          <View style={styles.separator} />
          <Pressable style={styles.row} onPress={checkConnection}>
            <Text style={styles.rowLabel}>Status</Text>
            <View style={styles.statusRow}>
              <View
                style={[
                  styles.statusDot,
                  connectionStatus === "connected" && styles.statusConnected,
                  connectionStatus === "disconnected" &&
                    styles.statusDisconnected,
                  connectionStatus === "checking" && styles.statusChecking,
                ]}
              />
              <Text
                numberOfLines={1}
                style={[
                  styles.statusText,
                  connectionStatus === "connected" && styles.textConnected,
                  connectionStatus === "disconnected" &&
                    styles.textDisconnected,
                ]}
              >
                {connectionStatus === "connected"
                  ? "Connected"
                  : connectionStatus === "disconnected"
                    ? "Disconnected"
                    : "Checking..."}
              </Text>
            </View>
          </Pressable>
          <View style={styles.separator} />
          <Pressable style={styles.row} onPress={handleResetUrl}>
            <Text style={styles.resetText}>Reset to Default</Text>
            <Text style={styles.defaultUrl} numberOfLines={1}>
              {getDefaultUrl()}
            </Text>
          </Pressable>
        </View>
        <Text style={styles.sectionFooter}>
          Tap API Server to change the URL manually.
        </Text>
      </View>

      {/* About Section */}
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>ABOUT</Text>
        <View style={styles.sectionCard}>
          <Pressable style={styles.row} onPress={handleCopyToken}>
            <Text style={styles.rowLabel}>Device Token</Text>
            <Text style={styles.rowValueMono}>
              {copiedToken ? "Copied!" : truncatedToken}
            </Text>
          </Pressable>
        </View>
        <Text style={styles.sectionFooter}>
          Tap to copy the full device token
        </Text>
      </View>

      {/* Debug Section */}
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>DEBUG</Text>
        <View style={styles.sectionCard}>
          <Pressable style={styles.row} onPress={() => router.push("/logs")}>
            <Text style={styles.rowLabel}>Logs</Text>
            <Text style={styles.chevron}>&rsaquo;</Text>
          </Pressable>
          <View style={styles.separator} />
          <Pressable style={styles.row} onPress={handleRestartSession}>
            <Text style={styles.rowLabel}>Restart Session</Text>
            <Text style={styles.chevron}>&rsaquo;</Text>
          </Pressable>
          <View style={styles.separator} />
          <Pressable style={styles.row} onPress={handleClearNotifications}>
            <Text style={styles.rowLabel}>Clear Notifications</Text>
            <Text style={styles.chevron}>&rsaquo;</Text>
          </Pressable>
          {__DEV__ && Platform.OS !== "web" && (
            <>
              <View style={styles.separator} />
              <Pressable
                style={styles.row}
                onPress={() => {
                  try {
                    const { NativeModules } = require("react-native");
                    if (NativeModules.DevMenu?.show) {
                      NativeModules.DevMenu.show();
                    } else if (NativeModules.DevSettings?.show) {
                      NativeModules.DevSettings.show();
                    } else {
                      showAlert("Dev Menu", "Shake your device to open the dev menu.");
                    }
                  } catch {
                    showAlert("Dev Menu", "Shake your device to open the dev menu.");
                  }
                }}
              >
                <Text style={styles.rowLabel}>Dev Tools</Text>
                <Text style={styles.chevron}>&rsaquo;</Text>
              </Pressable>
            </>
          )}
        </View>
        <Text style={styles.sectionFooter}>
          View live system logs, restart Claude's conversation context, or clear all notifications.
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  contentContainer: {
    paddingBottom: 48,
  },
  appHeader: {
    alignItems: "center",
    paddingTop: 32,
    paddingBottom: 24,
  },
  appName: {
    color: "#fafafa",
    fontSize: 28,
    fontWeight: "700",
  },
  appVersion: {
    color: "#71717a",
    fontSize: 14,
    marginTop: 4,
  },
  poweredBy: {
    color: "#52525b",
    fontSize: 13,
    marginTop: 2,
  },
  section: {
    marginTop: 24,
    paddingHorizontal: 16,
  },
  sectionHeader: {
    color: "#71717a",
    fontSize: 13,
    fontWeight: "600",
    letterSpacing: 0.5,
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  sectionCard: {
    backgroundColor: "#18181b",
    borderRadius: 12,
    overflow: "hidden",
  },
  sectionFooter: {
    color: "#52525b",
    fontSize: 12,
    marginTop: 6,
    paddingHorizontal: 4,
    lineHeight: 16,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 14,
    minHeight: 48,
  },
  rowLabel: {
    color: "#fafafa",
    fontSize: 15,
  },
  rowValue: {
    color: "#71717a",
    fontSize: 15,
    maxWidth: "60%",
    textAlign: "right",
  },
  rowValueMono: {
    color: "#71717a",
    fontSize: 13,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    textAlign: "right",
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#27272a",
    marginLeft: 16,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flexShrink: 0,
  },
  statusText: {
    color: "#71717a",
    fontSize: 15,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusConnected: {
    backgroundColor: "#22c55e",
  },
  statusDisconnected: {
    backgroundColor: "#ef4444",
  },
  statusChecking: {
    backgroundColor: "#eab308",
  },
  textConnected: {
    color: "#22c55e",
  },
  textDisconnected: {
    color: "#ef4444",
  },
  resetText: {
    color: "#71717a",
    fontSize: 14,
  },
  defaultUrl: {
    color: "#52525b",
    fontSize: 12,
    maxWidth: "50%",
    textAlign: "right",
  },
  dangerText: {
    color: "#ef4444",
    fontSize: 15,
    fontWeight: "500",
  },
  chevron: {
    color: "#52525b",
    fontSize: 22,
    fontWeight: "300",
  },
});
