import { ExpoConfig, ConfigContext } from "expo/config";
import * as fs from "fs";
import * as path from "path";

const defaultConfig = require("./config.default.json");

// Load app.yaml if it exists (gitignored, user-specific)
let yamlConfig: Record<string, any> = {};
try {
  const yamlPath = path.join(__dirname, "app.yaml");
  if (fs.existsSync(yamlPath)) {
    const YAML = require("yaml");
    yamlConfig = YAML.parse(fs.readFileSync(yamlPath, "utf8")) || {};
  }
} catch {
  // No app.yaml — use defaults
}

// Try to load legacy local config override (not checked in)
let localConfig: Record<string, string> = {};
try {
  localConfig = require("./config.local.json");
} catch {
  // No local config — that's fine
}

// Merge: defaults < app.yaml < config.local.json < env vars
const merged = { ...defaultConfig, ...yamlConfig, ...localConfig };

// Environment variable overrides (for EAS builds)
const config = {
  appName: process.env.APP_NAME || merged.appName || "Dispatch",
  displayName: merged.displayName || merged.appName || "Dispatch",
  accentColor: process.env.ACCENT_COLOR || merged.accentColor || "#2563eb",
  bundleIdentifier: process.env.BUNDLE_ID || merged.bundleIdentifier || "com.dispatch.app",
  iconPath: merged.iconPath || "./assets/images/icon.png",
  adaptiveIconPath: merged.adaptiveIconPath || "./assets/images/adaptive-icon.png",
  splashColor: merged.splashColor || "#09090b",
  scheme: merged.scheme || "dispatch",
  apiHost: merged.apiHost || "",
  sessionPrefix: merged.sessionPrefix || "dispatch-app",
};

export default ({ config: _config }: ConfigContext): ExpoConfig => ({
  name: config.appName,
  slug: "dispatch-app",
  version: "1.0.0",
  orientation: "portrait",
  icon: config.iconPath,
  scheme: config.scheme,
  userInterfaceStyle: "automatic",
  splash: {
    image: "./assets/images/splash-icon.png",
    resizeMode: "contain",
    backgroundColor: config.splashColor,
  },
  ios: {
    supportsTablet: true,
    bundleIdentifier: config.bundleIdentifier,
    infoPlist: {
      CFBundleDisplayName: config.displayName,
      NSAppTransportSecurity: {
        NSAllowsArbitraryLoads: true,
      },
    },
  },
  android: {
    adaptiveIcon: {
      backgroundColor: config.splashColor,
      foregroundImage: config.adaptiveIconPath,
    },
  },
  web: {
    bundler: "metro",
    output: "static",
    favicon: "./assets/images/favicon.png",
  },
  plugins: [
      "expo-router",
      "expo-secure-store",
      [
        "@jamsch/expo-speech-recognition",
        {
          microphonePermission:
            "$(PRODUCT_NAME) needs access to your microphone for voice input.",
          speechRecognitionPermission:
            "$(PRODUCT_NAME) needs access to speech recognition for voice input.",
        },
      ],
    ],
  experiments: {
    typedRoutes: true,
    baseUrl: "/app",
  },
  extra: {
    accentColor: config.accentColor,
    displayName: config.displayName,
    apiHost: config.apiHost,
    sessionPrefix: config.sessionPrefix,
    speechCorrections: merged.speechCorrections || {},
  },
});
