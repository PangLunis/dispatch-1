import React, { useMemo } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { getApiBaseUrl } from "@/src/config/constants";

// Safe import — native module may not be in the current build
let WebView: typeof import("react-native-webview").default | null = null;
try {
  WebView = require("react-native-webview").default;
} catch {
  // react-native-webview not available in this build
}

export default function DashboardScreen() {
  const dashboardUrl = useMemo(() => {
    const base = getApiBaseUrl();
    return base ? `${base}/dashboard` : "/dashboard";
  }, []);

  // Fallback when WebView native module isn't available
  if (!WebView) {
    return (
      <View style={styles.container}>
        <View style={styles.fallbackContainer}>
          <Text style={styles.fallbackTitle}>Dashboard</Text>
          <Text style={styles.fallbackText}>
            WebView not available in this build.{"\n"}
            Rebuild with: npx expo run:ios
          </Text>
          <Pressable
            style={styles.openButton}
            onPress={() => Linking.openURL(dashboardUrl)}
          >
            <Text style={styles.openButtonText}>Open in Browser</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <WebView
        source={{ uri: dashboardUrl }}
        style={styles.webview}
        javaScriptEnabled
        domStorageEnabled
        startInLoadingState
        renderLoading={() => (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#71717a" />
          </View>
        )}
        containerStyle={{ backgroundColor: "#09090b" }}
        scalesPageToFit
        allowsInlineMediaPlayback
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  webview: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  loadingContainer: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#09090b",
    justifyContent: "center",
    alignItems: "center",
  },
  fallbackContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 32,
  },
  fallbackTitle: {
    color: "#fafafa",
    fontSize: 24,
    fontWeight: "700",
    marginBottom: 12,
  },
  fallbackText: {
    color: "#71717a",
    fontSize: 15,
    textAlign: "center",
    lineHeight: 22,
    marginBottom: 24,
  },
  openButton: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 10,
  },
  openButtonText: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "600",
  },
});
