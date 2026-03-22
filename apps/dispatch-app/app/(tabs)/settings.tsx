import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router } from "expo-router";
import * as Notifications from "expo-notifications";
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
import {
  discoverServers,
  DiscoveredServer,
} from "@/src/api/discovery";

type ConnectionStatus = "checking" | "connected" | "disconnected";

const TAILSCALE_API_KEY_STORAGE = "dispatch_tailscale_api_key";

export default function SettingsScreen() {
  const { token } = useDeviceToken();
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("checking");
  const [copiedToken, setCopiedToken] = useState(false);
  const [currentUrl, setCurrentUrl] = useState(getApiBaseUrl());

  // Discovery state
  const [isScanning, setIsScanning] = useState(false);
  const [scanPhase, setScanPhase] = useState("");
  const [discoveredServers, setDiscoveredServers] = useState<
    DiscoveredServer[]
  >([]);
  const [showServerList, setShowServerList] = useState(false);

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

  // Scan for servers
  const handleScanServers = useCallback(async () => {
    setIsScanning(true);
    setShowServerList(true);
    setDiscoveredServers([]);
    setScanPhase("Starting scan...");

    try {
      // Load tailscale API key if saved
      const tsKey = await getItem(TAILSCALE_API_KEY_STORAGE);

      const servers = await discoverServers({
        currentUrl: currentUrl || undefined,
        tailscaleApiKey: tsKey ?? undefined,
        onProgress: (phase, scanned, total) => {
          if (phase === "current") {
            setScanPhase("Checking current server...");
          } else if (phase.startsWith("lan:")) {
            const subnet = phase.replace("lan:", "");
            const pct = Math.round((scanned / total) * 100);
            setScanPhase(`Scanning ${subnet}.* (${pct}%)`);
          } else if (phase === "tailscale") {
            setScanPhase("Querying Tailscale...");
          }
        },
      });

      setDiscoveredServers(servers);
      setScanPhase(
        servers.length === 0
          ? "No servers found"
          : `Found ${servers.length} server${servers.length > 1 ? "s" : ""}`,
      );
    } catch (err) {
      setScanPhase("Scan failed");
    } finally {
      setIsScanning(false);
    }
  }, [currentUrl]);

  // Select a discovered server
  const handleSelectServer = useCallback(
    async (server: DiscoveredServer) => {
      setApiBaseUrl(server.url);
      setCurrentUrl(server.url);
      await setItem(API_URL_STORAGE_KEY, server.url);
      setShowServerList(false);
      checkConnection();
    },
    [checkConnection],
  );

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

  // Configure Tailscale API key
  const handleConfigureTailscale = useCallback(async () => {
    const existing = await getItem(TAILSCALE_API_KEY_STORAGE);
    const key = await showPrompt(
      "Tailscale API Key",
      "Enter your Tailscale API key for remote server discovery.\n\nCreate one at: https://login.tailscale.com/admin/settings/keys",
      existing ?? "",
    );
    if (key === null) return; // cancelled
    if (key === "") {
      await deleteItem(TAILSCALE_API_KEY_STORAGE);
      showAlert("Removed", "Tailscale API key cleared.");
    } else {
      await setItem(TAILSCALE_API_KEY_STORAGE, key);
      showAlert("Saved", "Tailscale API key saved. Scan will now include remote devices.");
    }
  }, []);

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
    await Notifications.dismissAllNotificationsAsync();
    await Notifications.setBadgeCountAsync(0);
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
          <Pressable style={styles.row} onPress={handleScanServers}>
            <Text style={styles.rowLabel}>Scan for Servers</Text>
            {isScanning ? (
              <ActivityIndicator size="small" color="#71717a" />
            ) : (
              <Text style={styles.chevron}>&rsaquo;</Text>
            )}
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
          Tap API Server to enter manually, or Scan to auto-discover servers on your network.
        </Text>
      </View>

      {/* Server Discovery Results */}
      {showServerList && (
        <View style={styles.section}>
          <Text style={styles.sectionHeader}>DISCOVERED SERVERS</Text>
          <View style={styles.sectionCard}>
            {isScanning && discoveredServers.length === 0 && (
              <View style={styles.scanningRow}>
                <ActivityIndicator size="small" color="#71717a" />
                <Text style={styles.scanPhaseText}>{scanPhase}</Text>
              </View>
            )}
            {discoveredServers.map((server, index) => (
              <React.Fragment key={server.url}>
                {index > 0 && <View style={styles.separator} />}
                <Pressable
                  style={[
                    styles.row,
                    server.url === currentUrl && styles.selectedRow,
                  ]}
                  onPress={() => handleSelectServer(server)}
                >
                  <View style={styles.serverInfo}>
                    <Text style={styles.serverName}>{server.name}</Text>
                    <Text style={styles.serverDetail}>
                      {server.hostname}
                      {server.source === "tailscale" ? " (Tailscale)" : " (LAN)"}
                      {" · "}
                      {server.latencyMs}ms
                    </Text>
                  </View>
                  {server.url === currentUrl ? (
                    <Text style={styles.checkmark}>✓</Text>
                  ) : (
                    <Text style={styles.chevron}>&rsaquo;</Text>
                  )}
                </Pressable>
              </React.Fragment>
            ))}
            {!isScanning && discoveredServers.length === 0 && (
              <View style={styles.emptyRow}>
                <Text style={styles.emptyText}>
                  No servers found on your network
                </Text>
              </View>
            )}
          </View>
          {!isScanning && (
            <View style={styles.scanActions}>
              <Pressable onPress={handleScanServers}>
                <Text style={styles.scanAgainText}>Scan Again</Text>
              </Pressable>
              <Text style={styles.scanDivider}> · </Text>
              <Pressable onPress={handleChangeUrl}>
                <Text style={styles.scanAgainText}>Enter Manually</Text>
              </Pressable>
              <Text style={styles.scanDivider}> · </Text>
              <Pressable onPress={() => setShowServerList(false)}>
                <Text style={styles.dismissText}>Dismiss</Text>
              </Pressable>
            </View>
          )}
          {isScanning && discoveredServers.length > 0 && (
            <Text style={styles.sectionFooter}>{scanPhase}</Text>
          )}
        </View>
      )}

      {/* Tailscale Section */}
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>TAILSCALE</Text>
        <View style={styles.sectionCard}>
          <Pressable style={styles.row} onPress={handleConfigureTailscale}>
            <Text style={styles.rowLabel}>API Key</Text>
            <Text style={styles.rowValue}>Configure</Text>
          </Pressable>
        </View>
        <Text style={styles.sectionFooter}>
          Add a Tailscale API key to discover servers on your tailnet remotely.
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
  sectionHeaderDanger: {
    color: "#ef4444",
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
  selectedRow: {
    backgroundColor: "#1e3a2f",
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
  // Discovery styles
  scanningRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 16,
    gap: 12,
  },
  scanPhaseText: {
    color: "#71717a",
    fontSize: 14,
  },
  serverInfo: {
    flex: 1,
    marginRight: 12,
  },
  serverName: {
    color: "#fafafa",
    fontSize: 15,
    fontWeight: "600",
  },
  serverDetail: {
    color: "#71717a",
    fontSize: 12,
    marginTop: 2,
  },
  checkmark: {
    color: "#22c55e",
    fontSize: 18,
    fontWeight: "600",
  },
  emptyRow: {
    paddingHorizontal: 16,
    paddingVertical: 20,
    alignItems: "center",
  },
  emptyText: {
    color: "#52525b",
    fontSize: 14,
  },
  scanActions: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 8,
    paddingHorizontal: 4,
  },
  scanAgainText: {
    color: "#3b82f6",
    fontSize: 13,
  },
  scanDivider: {
    color: "#52525b",
    fontSize: 13,
  },
  dismissText: {
    color: "#71717a",
    fontSize: 13,
  },
});
