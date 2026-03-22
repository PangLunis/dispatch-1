import Constants from "expo-constants";

const extra = Constants.expoConfig?.extra ?? {};

export const branding = {
  appName: (Constants.expoConfig?.name as string) || "Dispatch",
  displayName: (extra.displayName as string) || "Dispatch",
  accentColor: (extra.accentColor as string) || "#2563eb",
  variant: (extra.appVariant as string) || "dispatch",
} as const;

/** Session prefix for SDK session IDs — always "dispatch-app" */
export const sessionPrefix: string = (extra.sessionPrefix as string) || "dispatch-app";
