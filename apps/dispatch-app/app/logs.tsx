import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack } from "expo-router";
import { apiRequest } from "@/src/api/client";

interface LogEntry {
  line: string;
  lineNumber: number;
}

const LOG_FILES = [
  "manager.log",
  "dispatch-api.log",
  "client.log",
  "signal-daemon.log",
  "watchdog.log",
];

export default function LogsScreen() {
  const [selectedFile, setSelectedFile] = useState("manager.log");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const flatListRef = useRef<FlatList>(null);
  const lastLineRef = useRef(0);

  const fetchLogs = useCallback(
    async (file: string, sinceLine?: number) => {
      try {
        const params: Record<string, string> = {
          file,
          lines: "200",
        };
        if (sinceLine && sinceLine > 0) {
          params.since_line = String(sinceLine);
        }
        const data = await apiRequest<{
          lines: string[];
          total_lines: number;
          returned_from_line: number;
        }>("/api/dashboard/logs", { params });

        const startLine = data.returned_from_line;
        const newEntries = data.lines.map((line, i) => ({
          line,
          lineNumber: startLine + i + 1,
        }));

        if (sinceLine && sinceLine > 0) {
          // Append new lines
          setLogs((prev) => [...prev, ...newEntries]);
        } else {
          setLogs(newEntries);
        }

        lastLineRef.current = data.total_lines;
        setIsLoading(false);
      } catch {
        setIsLoading(false);
      }
    },
    [],
  );

  // Initial load
  useEffect(() => {
    setIsLoading(true);
    setLogs([]);
    lastLineRef.current = 0;
    fetchLogs(selectedFile);
  }, [selectedFile, fetchLogs]);

  // Poll for new lines every 2s
  useEffect(() => {
    const interval = setInterval(() => {
      if (lastLineRef.current > 0) {
        fetchLogs(selectedFile, lastLineRef.current);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [selectedFile, fetchLogs]);

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (autoScroll && logs.length > 0) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: false });
      }, 100);
    }
  }, [logs.length, autoScroll]);

  const renderLogLine = useCallback(
    ({ item }: { item: LogEntry }) => {
      const isError =
        item.line.includes("ERROR") || item.line.includes("Traceback");
      const isWarning = item.line.includes("WARNING");
      const isInfo = item.line.includes("INFO");

      return (
        <View style={styles.logLine}>
          <Text style={styles.lineNumber}>{item.lineNumber}</Text>
          <Text
            style={[
              styles.logText,
              isError && styles.logError,
              isWarning && styles.logWarning,
              isInfo && styles.logInfo,
            ]}
            selectable
          >
            {item.line}
          </Text>
        </View>
      );
    },
    [],
  );

  return (
    <View style={styles.container}>
      <Stack.Screen
        options={{
          title: "Logs",
          headerStyle: { backgroundColor: "#09090b" },
          headerTintColor: "#fafafa",
        }}
      />

      {/* File selector */}
      <View style={styles.fileTabs}>
        {LOG_FILES.map((file) => (
          <Pressable
            key={file}
            style={[
              styles.fileTab,
              selectedFile === file && styles.fileTabActive,
            ]}
            onPress={() => setSelectedFile(file)}
          >
            <Text
              style={[
                styles.fileTabText,
                selectedFile === file && styles.fileTabTextActive,
              ]}
              numberOfLines={1}
            >
              {file.replace(".log", "")}
            </Text>
          </Pressable>
        ))}
      </View>

      {/* Auto-scroll toggle */}
      <View style={styles.toolbar}>
        <Text style={styles.logCount}>{logs.length} lines</Text>
        <Pressable
          style={[
            styles.autoScrollBtn,
            autoScroll && styles.autoScrollBtnActive,
          ]}
          onPress={() => setAutoScroll(!autoScroll)}
        >
          <Text
            style={[
              styles.autoScrollText,
              autoScroll && styles.autoScrollTextActive,
            ]}
          >
            Auto-scroll {autoScroll ? "ON" : "OFF"}
          </Text>
        </Pressable>
      </View>

      {/* Log output */}
      {isLoading ? (
        <View style={styles.centered}>
          <Text style={styles.loadingText}>Loading logs...</Text>
        </View>
      ) : logs.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.emptyText}>No logs found</Text>
        </View>
      ) : (
        <FlatList
          ref={flatListRef}
          data={logs}
          renderItem={renderLogLine}
          keyExtractor={(item, index) => `${item.lineNumber}-${index}`}
          style={styles.logList}
          contentContainerStyle={styles.logContent}
          onScrollBeginDrag={() => setAutoScroll(false)}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  fileTabs: {
    flexDirection: "row",
    paddingHorizontal: 8,
    paddingVertical: 8,
    gap: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  fileTab: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: "#18181b",
  },
  fileTabActive: {
    backgroundColor: "#3b82f6",
  },
  fileTabText: {
    color: "#71717a",
    fontSize: 12,
    fontWeight: "600",
  },
  fileTabTextActive: {
    color: "#fff",
  },
  toolbar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  logCount: {
    color: "#52525b",
    fontSize: 12,
  },
  autoScrollBtn: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    backgroundColor: "#18181b",
  },
  autoScrollBtnActive: {
    backgroundColor: "#1e3a5f",
  },
  autoScrollText: {
    color: "#52525b",
    fontSize: 11,
    fontWeight: "600",
  },
  autoScrollTextActive: {
    color: "#3b82f6",
  },
  logList: {
    flex: 1,
  },
  logContent: {
    paddingVertical: 4,
  },
  logLine: {
    flexDirection: "row",
    paddingHorizontal: 8,
    paddingVertical: 1,
  },
  lineNumber: {
    color: "#3f3f46",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    width: 40,
    textAlign: "right",
    marginRight: 8,
  },
  logText: {
    color: "#a1a1aa",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    flex: 1,
  },
  logError: {
    color: "#ef4444",
  },
  logWarning: {
    color: "#eab308",
  },
  logInfo: {
    color: "#a1a1aa",
  },
  centered: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    color: "#71717a",
    fontSize: 14,
  },
  emptyText: {
    color: "#52525b",
    fontSize: 14,
  },
});
