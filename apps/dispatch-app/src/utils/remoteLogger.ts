/**
 * Remote logger — batches client-side logs and POSTs to dispatch-api.
 * Captures console.error, console.warn, and unhandled errors.
 */
import { Platform } from "react-native";
import { getApiBaseUrl } from "@/src/config/constants";

interface LogEntry {
  level: "error" | "warn" | "info" | "log";
  message: string;
  timestamp: string;
  device: string;
}

const buffer: LogEntry[] = [];
const FLUSH_INTERVAL = 3000; // 3 seconds
const MAX_BUFFER = 50;

const device = `${Platform.OS}/${Platform.Version || "unknown"}`;

function addEntry(level: LogEntry["level"], args: unknown[]) {
  const message = args
    .map((a) => {
      if (typeof a === "string") return a;
      try {
        return JSON.stringify(a);
      } catch {
        return String(a);
      }
    })
    .join(" ");

  buffer.push({
    level,
    message,
    timestamp: new Date().toISOString(),
    device,
  });

  // Prevent unbounded growth
  if (buffer.length > MAX_BUFFER) {
    buffer.splice(0, buffer.length - MAX_BUFFER);
  }
}

async function flush() {
  if (buffer.length === 0) return;

  const entries = buffer.splice(0, buffer.length);
  try {
    const url = `${getApiBaseUrl()}/api/client-logs`;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ logs: entries }),
    });
  } catch {
    // If flush fails, re-add entries (but don't grow unbounded)
    if (buffer.length < MAX_BUFFER) {
      buffer.unshift(...entries.slice(0, MAX_BUFFER - buffer.length));
    }
  }
}

let initialized = false;

export function initRemoteLogger() {
  if (initialized) return;
  initialized = true;

  // Intercept console.error and console.warn
  const originalError = console.error;
  const originalWarn = console.warn;

  console.error = (...args: unknown[]) => {
    addEntry("error", args);
    originalError.apply(console, args);
  };

  console.warn = (...args: unknown[]) => {
    addEntry("warn", args);
    originalWarn.apply(console, args);
  };

  // Capture unhandled JS errors
  const originalHandler = ErrorUtils?.getGlobalHandler?.();
  ErrorUtils?.setGlobalHandler?.((error: Error, isFatal?: boolean) => {
    addEntry("error", [
      `[UNHANDLED${isFatal ? " FATAL" : ""}] ${error.message}\n${error.stack || ""}`,
    ]);
    // Flush immediately for unhandled errors
    flush();
    originalHandler?.(error, isFatal);
  });

  // Flush on interval
  setInterval(flush, FLUSH_INTERVAL);
}
