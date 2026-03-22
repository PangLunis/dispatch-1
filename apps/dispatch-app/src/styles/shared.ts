import { StyleSheet } from "react-native";
import { colors } from "../config/colors";

/**
 * Shared screen styles used across chat and agent detail screens.
 */
export const screenStyles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  loadingContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  errorContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
  },
  errorText: {
    color: colors.error,
    fontSize: 15,
    textAlign: "center",
  },
  messageList: {
    paddingTop: 12,
    paddingBottom: 8,
  },
  /** Dismissable error banner for transient errors */
  errorBanner: {
    backgroundColor: colors.errorBg,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  errorBannerText: {
    color: colors.errorLight,
    fontSize: 14,
  },
});
