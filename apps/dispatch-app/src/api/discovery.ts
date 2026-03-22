/**
 * Server auto-discovery for dispatch-api.
 *
 * Discovers dispatch-api servers on:
 * 1. Local network (detects device subnet via expo-network, scans :9091)
 * 2. Tailscale network (local API at 100.100.100.100 or remote API)
 *
 * Each discovered server is probed via GET /discover to get its identity.
 * Results are deduplicated by hostname (not URL) since a single server
 * may be reachable on multiple IPs (LAN + Tailscale).
 */

import { Platform } from "react-native";
import * as Network from "expo-network";

/** Timeout for LAN subnet probes — LAN responses are sub-50ms */
const LAN_PROBE_TIMEOUT = 500;
/** Timeout for targeted probes (current URL, Tailscale peers) */
const TARGETED_PROBE_TIMEOUT = 2000;
const PORT = 9091;

export interface DiscoveredServer {
  /** Display name (assistant name from config) */
  name: string;
  /** Machine hostname — used as identity for dedup */
  hostname: string;
  /** URL to connect to (http://ip:port) */
  url: string;
  /** How it was found */
  source: "local" | "tailscale";
  /** Local network IP (if available) */
  localIp?: string;
  /** Tailscale IP (if available) */
  tailscaleIp?: string;
  /** Response time in ms */
  latencyMs: number;
}

interface DiscoverResponse {
  name: string;
  hostname: string;
  local_ip: string | null;
  tailscale_ip: string | null;
  port: number;
}

/**
 * Check if an IP is in Tailscale's CGNAT range (100.64.0.0/10).
 * Tailscale assigns IPs in 100.64-127.x.x.
 */
function isTailscaleIp(ip: string): boolean {
  const parts = ip.split(".");
  if (parts.length !== 4) return false;
  const first = parseInt(parts[0], 10);
  const second = parseInt(parts[1], 10);
  return first === 100 && second >= 64 && second <= 127;
}

/**
 * Probe a single IP:port for dispatch-api /discover endpoint.
 * Returns server info or null if unreachable.
 * Auto-detects source based on IP range.
 */
async function probeServer(
  ip: string,
  timeout: number = TARGETED_PROBE_TIMEOUT,
): Promise<DiscoveredServer | null> {
  const url = `http://${ip}:${PORT}`;
  const start = Date.now();

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(`${url}/discover`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) return null;

    const data: DiscoverResponse = await response.json();
    if (!data.hostname || typeof data.hostname !== "string") return null;

    const latencyMs = Date.now() - start;

    // Auto-detect source from IP range
    const source = isTailscaleIp(ip) ? "tailscale" : "local";

    return {
      name: data.name || "Dispatch",
      hostname: data.hostname,
      url,
      source,
      localIp: data.local_ip ?? undefined,
      tailscaleIp: data.tailscale_ip ?? undefined,
      latencyMs,
    };
  } catch {
    return null;
  }
}

/**
 * Get the device's local (non-Tailscale) IP and derive the /24 subnet prefix.
 * Returns null if on web, no IP, or on Tailscale CGNAT (subnet scan makes no sense there).
 */
async function getDeviceSubnet(): Promise<string | null> {
  try {
    if (Platform.OS === "web") return null;
    const ip = await Network.getIpAddressAsync();
    if (!ip || ip === "0.0.0.0") return null;
    // Don't subnet-scan Tailscale CGNAT range — use Tailscale API instead
    if (isTailscaleIp(ip)) return null;
    const parts = ip.split(".");
    if (parts.length !== 4) return null;
    return `${parts[0]}.${parts[1]}.${parts[2]}`;
  } catch {
    return null;
  }
}

/**
 * Scan a /24 subnet for dispatch-api servers.
 * Fires all 254 probes concurrently with short timeouts — LAN is fast.
 */
async function scanSubnet(
  subnet: string,
  onProgress?: (scanned: number, total: number) => void,
): Promise<DiscoveredServer[]> {
  const total = 254;
  let scanned = 0;

  const promises = Array.from({ length: total }, (_, i) =>
    probeServer(`${subnet}.${i + 1}`, LAN_PROBE_TIMEOUT).then((result) => {
      scanned++;
      // Report progress periodically (every ~25 probes)
      if (scanned % 25 === 0 || scanned === total) {
        onProgress?.(scanned, total);
      }
      return result;
    }),
  );

  const results = await Promise.all(promises);
  return results.filter((r): r is DiscoveredServer => r !== null);
}

/**
 * Discover Tailscale peers via the local API (no API key needed).
 * The Tailscale local API is available at 100.100.100.100 on any device
 * running Tailscale.
 */
async function discoverViaTailscaleLocal(): Promise<DiscoveredServer[]> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    const response = await fetch(
      "http://100.100.100.100/localapi/v0/status",
      {
        signal: controller.signal,
      },
    );
    clearTimeout(timeoutId);

    if (!response.ok) return [];

    const status = await response.json();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const peers = Object.values(status.Peer || {}) as any[];

    const probes = peers
      .filter((p) => p.Online && p.TailscaleIPs?.length > 0)
      .map((p) => {
        const ipv4 = (p.TailscaleIPs as string[]).find(
          (a) => !a.includes(":"),
        );
        if (!ipv4) return Promise.resolve(null);
        return probeServer(ipv4);
      });

    const results = await Promise.all(probes);
    return results.filter((r): r is DiscoveredServer => r !== null);
  } catch {
    return [];
  }
}

/**
 * Discover Tailscale peers via the remote API (requires API key).
 * Fallback when local API is unavailable.
 */
async function discoverViaTailscaleApi(
  apiKey: string,
): Promise<DiscoveredServer[]> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const response = await fetch(
      "https://api.tailscale.com/api/v2/tailnet/-/devices",
      {
        headers: { Authorization: `Bearer ${apiKey}` },
        signal: controller.signal,
      },
    );
    clearTimeout(timeoutId);

    if (!response.ok) return [];

    const data = await response.json();
    const devices: Array<{
      addresses: string[];
      hostname: string;
      os: string;
    }> = data.devices || [];

    const probes = devices
      .filter((d) => d.addresses?.length > 0)
      .map((d) => {
        const ipv4 = d.addresses.find((a: string) => !a.includes(":"));
        if (!ipv4) return Promise.resolve(null);
        return probeServer(ipv4);
      });

    const results = await Promise.all(probes);
    return results.filter((r): r is DiscoveredServer => r !== null);
  } catch {
    return [];
  }
}

export interface DiscoveryOptions {
  /** Tailscale API key for remote discovery (fallback if local API fails) */
  tailscaleApiKey?: string;
  /** Progress callback */
  onProgress?: (phase: string, scanned: number, total: number) => void;
  /** Also probe currently configured URL */
  currentUrl?: string;
}

/**
 * Run full server discovery: local network + tailscale.
 * Results are deduplicated by hostname — same server on multiple IPs
 * merges into one entry with the lowest latency route.
 */
export async function discoverServers(
  options: DiscoveryOptions = {},
): Promise<DiscoveredServer[]> {
  const serversByHostname = new Map<string, DiscoveredServer>();

  const addServer = (server: DiscoveredServer) => {
    const existing = serversByHostname.get(server.hostname);
    if (!existing) {
      serversByHostname.set(server.hostname, server);
    } else {
      // Merge: accumulate IPs, keep fastest route
      if (server.localIp) existing.localIp = server.localIp;
      if (server.tailscaleIp) existing.tailscaleIp = server.tailscaleIp;
      if (server.latencyMs < existing.latencyMs) {
        existing.url = server.url;
        existing.latencyMs = server.latencyMs;
        existing.source = server.source;
      }
    }
  };

  // Phase 1: Probe current URL (instant feedback)
  if (options.currentUrl) {
    options.onProgress?.("current", 0, 1);
    const urlMatch = options.currentUrl.match(/\/\/([^:/]+)/);
    if (urlMatch) {
      const result = await probeServer(urlMatch[1]);
      if (result) {
        result.url = options.currentUrl; // Preserve original URL format
        addServer(result);
      }
    }
    options.onProgress?.("current", 1, 1);
  }

  // Phase 2: LAN subnet scan + Tailscale discovery in parallel
  const localPromise = (async () => {
    const subnet = await getDeviceSubnet();
    if (!subnet) {
      options.onProgress?.("lan", 0, 0);
      return;
    }
    options.onProgress?.(`lan:${subnet}`, 0, 254);
    const found = await scanSubnet(subnet, (scanned, total) => {
      options.onProgress?.(`lan:${subnet}`, scanned, total);
    });
    found.forEach(addServer);
  })();

  const tailscalePromise = (async () => {
    options.onProgress?.("tailscale", 0, 1);
    // Try local API first (no key needed), fall back to remote API
    let found = await discoverViaTailscaleLocal();
    if (found.length === 0 && options.tailscaleApiKey) {
      found = await discoverViaTailscaleApi(options.tailscaleApiKey);
    }
    found.forEach(addServer);
    options.onProgress?.("tailscale", 1, 1);
  })();

  await Promise.all([localPromise, tailscalePromise]);

  const allServers = Array.from(serversByHostname.values());
  allServers.sort((a, b) => a.latencyMs - b.latencyMs);
  return allServers;
}
