import React, { useCallback, useState } from "react";
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
import { useRouter } from "expo-router";
import { useAgentSessions } from "@/src/hooks/useAgentSessions";
import { AgentSessionRow } from "@/src/components/AgentSessionRow";
import { FilterPills } from "@/src/components/FilterPills";
import { EmptyState } from "@/src/components/EmptyState";
import { branding } from "@/src/config/branding";
import { showPrompt } from "@/src/utils/alert";
import type { AgentSession } from "@/src/api/types";

export default function AgentsScreen() {
  const router = useRouter();
  const {
    filteredSessions,
    isLoading,
    error,
    searchQuery,
    setSearchQuery,
    sourceFilter,
    setSourceFilter,
    createSession,
    refresh,
  } = useAgentSessions();

  const [isCreating, setIsCreating] = useState(false);

  const handleOpenSession = useCallback(
    (session: AgentSession) => {
      router.push({
        pathname: "/agents/[id]",
        params: {
          id: session.id,
          sessionName: session.name,
          sessionSource: session.source,
          sessionType: session.type,
        },
      });
    },
    [router],
  );

  const handleNewAgent = useCallback(async () => {
    const name = await showPrompt(
      "New Agent",
      "Enter a name for the new agent session:",
    );
    if (!name) return;

    setIsCreating(true);
    const session = await createSession(name);
    setIsCreating(false);
    if (session) {
      handleOpenSession(session);
    }
  }, [createSession, handleOpenSession]);

  const renderItem = useCallback(
    ({ item }: { item: AgentSession }) => (
      <AgentSessionRow
        session={item}
        onPress={() => handleOpenSession(item)}
      />
    ),
    [handleOpenSession],
  );

  const keyExtractor = useCallback((item: AgentSession) => item.id, []);

  const ListHeader = useCallback(
    () => (
      <View>
        {/* Search bar */}
        <View style={styles.searchContainer}>
          <TextInput
            style={styles.searchInput}
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Search sessions..."
            placeholderTextColor="#52525b"
            autoCapitalize="none"
            autoCorrect={false}
            clearButtonMode="while-editing"
          />
        </View>

        {/* Filter pills */}
        <FilterPills selected={sourceFilter} onSelect={setSourceFilter} />
      </View>
    ),
    [searchQuery, setSearchQuery, sourceFilter, setSourceFilter],
  );

  if (isLoading && filteredSessions.length === 0) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={branding.accentColor} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {error ? (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}
      <FlatList
        data={filteredSessions}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        refreshing={isLoading}
        onRefresh={refresh}
        ListHeaderComponent={ListHeader}
        contentContainerStyle={
          filteredSessions.length === 0 ? styles.emptyContainer : undefined
        }
        ListEmptyComponent={
          <EmptyState
            title={
              searchQuery || sourceFilter !== "all"
                ? "No matching sessions"
                : "No agent sessions"
            }
            subtitle={
              searchQuery || sourceFilter !== "all"
                ? "Try a different search or filter"
                : "Tap + to create a new agent session"
            }
          />
        }
      />

      {/* FAB - New Agent */}
      <Pressable
        onPress={handleNewAgent}
        disabled={isCreating}
        style={({ pressed }) => [
          styles.fab,
          { backgroundColor: branding.accentColor },
          pressed && styles.fabPressed,
          isCreating && styles.fabDisabled,
        ]}
      >
        {isCreating ? (
          <ActivityIndicator size="small" color="#fff" />
        ) : (
          <Text style={styles.fabText}>+</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#09090b",
  },
  emptyContainer: {
    flex: 1,
  },
  errorBanner: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  errorText: {
    color: "#fca5a5",
    fontSize: 14,
  },
  searchContainer: {
    paddingHorizontal: 16,
    paddingTop: 12,
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
  fab: {
    position: "absolute",
    right: 20,
    bottom: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 6,
  },
  fabPressed: {
    opacity: 0.8,
  },
  fabDisabled: {
    opacity: 0.6,
  },
  fabText: {
    color: "#fff",
    fontSize: 28,
    fontWeight: "400",
    marginTop: -2,
  },
});
