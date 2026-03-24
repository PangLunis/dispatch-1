import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useVideoPlayer, VideoView } from "expo-video";
import * as FileSystem from "expo-file-system/legacy";

export default function VideoPlayerScreen() {
  const { uri, title } = useLocalSearchParams<{ uri: string; title?: string }>();
  const router = useRouter();
  const [isSaving, setIsSaving] = useState(false);
  const [isSharing, setIsSharing] = useState(false);

  const player = useVideoPlayer(uri ?? "", (p) => {
    p.loop = false;
    p.play();
  });

  const handleSaveToPhotos = useCallback(async () => {
    if (!uri) return;
    setIsSaving(true);
    try {
      let localUri = uri;
      if (uri.startsWith("http")) {
        const filename = `video_${Date.now()}.mp4`;
        const downloadResult = await FileSystem.downloadAsync(
          uri,
          FileSystem.cacheDirectory + filename,
        );
        localUri = downloadResult.uri;
      }

      try {
        const MediaLibrary = await import("expo-media-library");
        const { status } = await MediaLibrary.requestPermissionsAsync();
        if (status !== "granted") {
          Alert.alert("Permission needed", "Please allow access to save videos.");
          return;
        }
        await MediaLibrary.saveToLibraryAsync(localUri);
        Alert.alert("Saved", "Video saved to Photos.");
      } catch {
        await Share.share({ url: localUri, message: uri });
      }
    } catch {
      Alert.alert("Error", "Failed to save video.");
    } finally {
      setIsSaving(false);
    }
  }, [uri]);

  const handleShare = useCallback(async () => {
    if (!uri) return;
    setIsSharing(true);
    try {
      await Share.share({ url: uri, message: uri });
    } catch {
      // User cancelled
    } finally {
      setIsSharing(false);
    }
  }, [uri]);

  return (
    <>
      <Stack.Screen
        options={{
          presentation: "modal",
          title: title || "Video",
          headerStyle: { backgroundColor: "#000000" },
          headerTintColor: "#ffffff",
          headerShadowVisible: false,
          headerLeft: () => (
            <Pressable onPress={() => router.back()} hitSlop={8}>
              <Text style={{ color: "#007AFF", fontSize: 17 }}>Done</Text>
            </Pressable>
          ),
        }}
      />
      <View style={styles.container}>
        {uri ? (
          <VideoView
            player={player}
            style={styles.video}
            allowsFullscreen
            allowsPictureInPicture
            nativeControls
          />
        ) : (
          <Text style={styles.errorText}>No video to display</Text>
        )}

        {/* Bottom toolbar */}
        <View style={styles.toolbar}>
          <Pressable
            onPress={handleSaveToPhotos}
            style={({ pressed }) => [
              styles.toolbarButton,
              pressed && styles.toolbarButtonPressed,
            ]}
            disabled={isSaving}
          >
            {isSaving ? (
              <ActivityIndicator size={16} color="#ffffff" />
            ) : (
              <>
                <DownloadIcon />
                <Text style={styles.toolbarButtonText}>Save to Photos</Text>
              </>
            )}
          </Pressable>
          <Pressable
            onPress={handleShare}
            style={({ pressed }) => [
              styles.toolbarButton,
              pressed && styles.toolbarButtonPressed,
            ]}
            disabled={isSharing}
          >
            {isSharing ? (
              <ActivityIndicator size={16} color="#ffffff" />
            ) : (
              <>
                <ShareIcon />
                <Text style={styles.toolbarButtonText}>Share</Text>
              </>
            )}
          </Pressable>
        </View>
      </View>
    </>
  );
}

function DownloadIcon() {
  return (
    <View style={iconStyles.container}>
      <View style={iconStyles.arrowDown} />
      <View style={iconStyles.tray} />
    </View>
  );
}

function ShareIcon() {
  return (
    <View style={iconStyles.container}>
      <View style={iconStyles.arrowUp} />
      <View style={iconStyles.shareBox} />
    </View>
  );
}

const iconStyles = StyleSheet.create({
  container: {
    width: 20,
    height: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  arrowDown: {
    width: 0,
    height: 0,
    borderLeftWidth: 6,
    borderRightWidth: 6,
    borderTopWidth: 8,
    borderLeftColor: "transparent",
    borderRightColor: "transparent",
    borderTopColor: "#ffffff",
    marginBottom: 1,
  },
  tray: {
    width: 14,
    height: 2,
    backgroundColor: "#ffffff",
    borderRadius: 1,
  },
  arrowUp: {
    width: 0,
    height: 0,
    borderLeftWidth: 5,
    borderRightWidth: 5,
    borderBottomWidth: 7,
    borderLeftColor: "transparent",
    borderRightColor: "transparent",
    borderBottomColor: "#ffffff",
    marginBottom: 2,
  },
  shareBox: {
    width: 12,
    height: 8,
    borderWidth: 1.5,
    borderTopWidth: 0,
    borderColor: "#ffffff",
    borderBottomLeftRadius: 2,
    borderBottomRightRadius: 2,
  },
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#000000",
  },
  video: {
    flex: 1,
  },
  errorText: {
    color: "#71717a",
    fontSize: 16,
    textAlign: "center",
    marginTop: 100,
  },
  toolbar: {
    flexDirection: "row",
    justifyContent: "space-around",
    paddingVertical: 16,
    paddingBottom: Platform.OS === "ios" ? 40 : 16,
    backgroundColor: "#000000",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
  },
  toolbarButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: "#1c1c1e",
  },
  toolbarButtonPressed: {
    opacity: 0.7,
  },
  toolbarButtonText: {
    color: "#ffffff",
    fontSize: 14,
    fontWeight: "500",
  },
});
