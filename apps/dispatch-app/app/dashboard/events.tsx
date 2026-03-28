import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Stack } from "expo-router";
import { getDashboardEvents } from "@/src/api/dashboard";
import type { DashboardEvent } from "@/src/api/types";
import { relativeTime } from "@/src/utils/time";

const Separator = () => <View style={styles.separator} />;

export default function EventsDetailScreen() {
  const [events, setEvents] = useState<DashboardEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const data = await getDashboardEvents(200);
      if (mountedRef.current) {
        setEvents(data.events);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load");
      }
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => { mountedRef.current = false; };
  }, [load]);

  const filteredEvents = useMemo(() => {
    if (!searchQuery.trim()) return events;
    const q = searchQuery.trim().toLowerCase();
    return events.filter(
      (e) =>
        (e.type ?? "").toLowerCase().includes(q) ||
        (e.source ?? "").toLowerCase().includes(q) ||
        (e.key ?? "").toLowerCase().includes(q) ||
        (e.payload_preview ?? "").toLowerCase().includes(q),
    );
  }, [events, searchQuery]);

  const renderEvent = useCallback(
    ({ item }: { item: DashboardEvent }) => {
      const ts = new Date(item.timestamp).toISOString();
      return (
        <View style={styles.eventRow}>
          <View style={styles.eventHeader}>
            <Text style={styles.eventType}>{item.type}</Text>
            <Text style={styles.eventTime}>{relativeTime(ts)}</Text>
          </View>
          <View style={styles.eventMeta}>
            <Text style={styles.metaText}>src: {item.source}</Text>
            {item.key ? (
              <Text style={styles.metaText} numberOfLines={1}>
                key: {item.key}
              </Text>
            ) : null}
          </View>
          {item.payload_preview ? (
            <Text style={styles.preview} numberOfLines={2}>
              {item.payload_preview}
            </Text>
          ) : null}
        </View>
      );
    },
    [],
  );

  const ListHeader = useCallback(
    () => (
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          value={searchQuery}
          onChangeText={setSearchQuery}
          placeholder="Search events..."
          placeholderTextColor="#52525b"
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
        />
      </View>
    ),
    [searchQuery],
  );

  return (
    <>
      <Stack.Screen options={{ title: "Events" }} />
      <View style={styles.container}>
        {isLoading && events.length === 0 ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color="#71717a" />
          </View>
        ) : error && events.length === 0 ? (
          <View style={styles.center}>
            <Text style={styles.errorText}>{error}</Text>
            <Pressable style={styles.retryBtn} onPress={load}>
              <Text style={styles.retryText}>Retry</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {error && (
              <View style={styles.errorBanner}>
                <Text style={styles.errorBannerText}>⚠️ {error}</Text>
              </View>
            )}
            <FlatList
              data={filteredEvents}
              keyExtractor={(e) => `${e.offset}`}
              renderItem={renderEvent}
              ItemSeparatorComponent={Separator}
              ListHeaderComponent={ListHeader}
              contentContainerStyle={styles.listContent}
              ListEmptyComponent={
                <View style={styles.emptyCenter}>
                  <Text style={styles.emptyText}>
                    {searchQuery ? "No matching events" : "No events"}
                  </Text>
                </View>
              }
            />
          </>
        )}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 32,
  },
  emptyCenter: {
    paddingTop: 48,
    alignItems: "center",
  },
  listContent: {
    paddingBottom: 24,
  },
  searchContainer: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
  },
  searchInput: {
    backgroundColor: "#27272a",
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: Platform.OS === "ios" ? 10 : 8,
    fontSize: 15,
    color: "#fafafa",
    borderWidth: 1,
    borderColor: "#3f3f46",
  },
  eventRow: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 4,
  },
  eventHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  eventType: {
    color: "#fafafa",
    fontSize: 14,
    fontWeight: "600",
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  eventTime: {
    color: "#52525b",
    fontSize: 12,
  },
  eventMeta: {
    flexDirection: "row",
    gap: 12,
  },
  metaText: {
    color: "#71717a",
    fontSize: 12,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  preview: {
    color: "#52525b",
    fontSize: 12,
    lineHeight: 16,
    marginTop: 2,
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#27272a",
    marginLeft: 16,
  },
  errorBanner: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginHorizontal: 16,
    marginTop: 8,
    borderRadius: 8,
  },
  errorBannerText: {
    color: "#fca5a5",
    fontSize: 13,
  },
  errorText: {
    color: "#ef4444",
    fontSize: 15,
    textAlign: "center",
    marginBottom: 16,
  },
  retryBtn: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  retryText: {
    color: "#fafafa",
    fontSize: 15,
    fontWeight: "600",
  },
  emptyText: {
    color: "#52525b",
    fontSize: 15,
  },
});
