import { StyleSheet } from "react-native";

/** Shared styles for inline picker panels (SessionPicker, SkillPicker) */
export const pickerBaseStyles = StyleSheet.create({
  container: {
    backgroundColor: "#1c1c1e",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
    maxHeight: 280,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  title: {
    color: "#fafafa",
    fontSize: 15,
    fontWeight: "600",
  },
  list: {
    flexGrow: 0,
  },
  loadingContainer: {
    paddingVertical: 24,
    alignItems: "center",
  },
  loadingText: {
    color: "#71717a",
    fontSize: 14,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 10,
  },
  rowPressed: {
    backgroundColor: "#27272a",
  },
  iconCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
  },
  itemInfo: {
    flex: 1,
    gap: 2,
  },
  itemName: {
    color: "#fafafa",
    fontSize: 15,
    fontWeight: "500",
    flexShrink: 1,
  },
  preview: {
    color: "#71717a",
    fontSize: 13,
  },
});
