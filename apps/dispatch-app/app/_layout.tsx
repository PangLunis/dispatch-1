import { DarkTheme, ThemeProvider } from "@react-navigation/native";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";
import "react-native-reanimated";
import { LogBox } from "react-native";

// Suppress LogBox in dev to prevent it from covering the tab bar
LogBox.ignoreAllLogs(true);
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { usePushNotifications } from "../src/hooks/usePushNotifications";
import { useDeviceToken } from "../src/hooks/useDeviceToken";
import { setApiBaseUrl, API_URL_STORAGE_KEY } from "../src/config/constants";
import { getItem } from "../src/utils/storage";
import { initRemoteLogger } from "../src/utils/remoteLogger";

// Initialize remote logging as early as possible
initRemoteLogger();

export {
  // Catch any errors thrown by the Layout component.
  ErrorBoundary,
} from "expo-router";

export const unstable_settings = {
  // Ensure that reloading on `/modal` keeps a back button present.
  initialRouteName: "(tabs)",
};

// Prevent the splash screen from auto-hiding before asset loading is complete.
SplashScreen.preventAutoHideAsync();

// Dark theme customized to match our color scheme
const dispatchDarkTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: "#09090b",
    card: "#09090b",
    border: "#27272a",
    text: "#fafafa",
  },
};

export default function RootLayout() {
  const [loaded, error] = useFonts({
    SpaceMono: require("../assets/fonts/SpaceMono-Regular.ttf"),
  });

  // Load device token at the root so it's available before any API calls
  const { isLoading: tokenLoading } = useDeviceToken();

  // Load persisted API URL before any API calls
  useEffect(() => {
    (async () => {
      const savedUrl = await getItem(API_URL_STORAGE_KEY);
      if (savedUrl) {
        setApiBaseUrl(savedUrl);
      }
    })();
  }, []);

  // Expo Router uses Error Boundaries to catch errors in the navigation tree.
  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded && !tokenLoading) {
      SplashScreen.hideAsync();
    }
  }, [loaded, tokenLoading]);

  if (!loaded || tokenLoading) {
    return null;
  }

  return <RootLayoutNav />;
}

function RootLayoutNav() {
  // Register for push notifications on app launch
  usePushNotifications();

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ThemeProvider value={dispatchDarkTheme}>
        <Stack
          screenOptions={{
            headerBackTitle: "",
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false, headerBackTitle: " " }} />
          <Stack.Screen name="chat/[id]" options={{ headerShown: true }} />
          <Stack.Screen name="agents/[id]" options={{ headerShown: true }} />
          <Stack.Screen name="logs" options={{ headerShown: true, title: "Logs" }} />
          <Stack.Screen name="image-viewer" options={{ presentation: "modal" }} />
          <Stack.Screen name="modal" options={{ presentation: "modal" }} />
        </Stack>
      </ThemeProvider>
    </GestureHandlerRootView>
  );
}
