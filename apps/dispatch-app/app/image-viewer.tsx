import React, { useCallback, useState } from "react";
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
import { Image } from "expo-image";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import * as FileSystem from "expo-file-system/legacy";
import { Gesture, GestureDetector, GestureHandlerRootView } from "react-native-gesture-handler";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";

const AnimatedImage = Animated.createAnimatedComponent(Image);

export default function ImageViewerScreen() {
  const { uri, title } = useLocalSearchParams<{ uri: string; title?: string }>();
  const router = useRouter();
  const [isSaving, setIsSaving] = useState(false);
  const [isSharing, setIsSharing] = useState(false);

  // Zoom/pan shared values
  const scale = useSharedValue(1);
  const savedScale = useSharedValue(1);
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const savedTranslateX = useSharedValue(0);
  const savedTranslateY = useSharedValue(0);

  const pinchGesture = Gesture.Pinch()
    .onUpdate((e) => {
      scale.value = savedScale.value * e.scale;
    })
    .onEnd(() => {
      if (scale.value < 1) {
        scale.value = withTiming(1);
        savedScale.value = 1;
        translateX.value = withTiming(0);
        translateY.value = withTiming(0);
        savedTranslateX.value = 0;
        savedTranslateY.value = 0;
      } else if (scale.value > 5) {
        scale.value = withTiming(5);
        savedScale.value = 5;
      } else {
        savedScale.value = scale.value;
      }
    });

  const panGesture = Gesture.Pan()
    .minPointers(1)
    .onUpdate((e) => {
      if (savedScale.value > 1) {
        translateX.value = savedTranslateX.value + e.translationX;
        translateY.value = savedTranslateY.value + e.translationY;
      }
    })
    .onEnd(() => {
      savedTranslateX.value = translateX.value;
      savedTranslateY.value = translateY.value;
    });

  const doubleTapGesture = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => {
      if (savedScale.value > 1) {
        // Reset to 1x
        scale.value = withTiming(1);
        savedScale.value = 1;
        translateX.value = withTiming(0);
        translateY.value = withTiming(0);
        savedTranslateX.value = 0;
        savedTranslateY.value = 0;
      } else {
        // Zoom to 3x
        scale.value = withTiming(3);
        savedScale.value = 3;
      }
    });

  const composedGesture = Gesture.Simultaneous(
    pinchGesture,
    panGesture,
    doubleTapGesture,
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: scale.value },
    ],
  }));

  const handleSaveToPhotos = useCallback(async () => {
    if (!uri) return;
    setIsSaving(true);
    try {
      // Download to a local file
      let localUri = uri;
      if (uri.startsWith("http")) {
        const filename = `image_${Date.now()}.jpeg`;
        const downloadResult = await FileSystem.downloadAsync(
          uri,
          FileSystem.cacheDirectory + filename,
        );
        localUri = downloadResult.uri;
      }

      // Try to dynamically import MediaLibrary — only works if native module is available
      try {
        const MediaLibrary = await import("expo-media-library");
        const { status } = await MediaLibrary.requestPermissionsAsync();
        if (status !== "granted") {
          Alert.alert("Permission needed", "Please allow access to save photos.");
          return;
        }
        await MediaLibrary.saveToLibraryAsync(localUri);
        Alert.alert("Saved", "Image saved to Photos.");
      } catch {
        // Native module not available — fall back to sharing the URL
        await Share.share({ url: localUri, message: uri });
      }
    } catch (err) {
      Alert.alert("Error", "Failed to save image.");
    } finally {
      setIsSaving(false);
    }
  }, [uri]);

  const handleShare = useCallback(async () => {
    if (!uri) return;
    setIsSharing(true);
    try {
      await Share.share({
        url: uri,
        message: uri,
      });
    } catch (err) {
      // User cancelled or share failed — that's fine
    } finally {
      setIsSharing(false);
    }
  }, [uri]);

  return (
    <>
      <Stack.Screen
        options={{
          presentation: "modal",
          title: title || "Image",
          headerStyle: { backgroundColor: "#000000" },
          headerTintColor: "#ffffff",
          headerShadowVisible: false,
        }}
      />
      <GestureHandlerRootView style={styles.container}>
        {uri ? (
          <GestureDetector gesture={composedGesture}>
            <AnimatedImage
              source={{ uri }}
              style={[styles.image, animatedStyle]}
              contentFit="contain"
              transition={200}
            />
          </GestureDetector>
        ) : (
          <Text style={styles.errorText}>No image to display</Text>
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
      </GestureHandlerRootView>
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
  image: {
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
