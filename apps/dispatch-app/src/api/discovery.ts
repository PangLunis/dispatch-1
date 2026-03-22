/**
 * Server auto-discovery for dispatch-api.
 *
 * Discovers dispatch-api servers on:
 * 1. Local network (subnet scan on port 9091)
 * 2. Tailscale network (API query + probe)
 *
 * Each discovered server is probed via GET /discover to get its identity.
 */

const DISCOVER_TIMEOUT = 2000; // 2s per probe
const PORT = 9091;

export interface DiscoveredServer {
  /** Display name (assistant name from config) */
  name: string;
  /** Machine hostname */
  hostname: string;
  /** URL to connect to (http://ip:port) */
  url: string;
  /** How it was found */
  source: "local" | "tailscale" | "manual";
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
 * Probe a single IP:port for dispatch-api /discover endpoint.
 * Returns server info or null if unreachable.
 */
async function probeServer(
  ip: string,
  source: "local" | "tailscale",
): Promise<DiscoveredServer | null> {
  const url = `http://${ip}:${PORT}`;
  const start = Date.now();

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), DISCOVER_TIMEOUT);

    const response = await fetch(`${url}/discover`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) return null;

    const data: DiscoverResponse = await response.json();
    const latencyMs = Date.now() - start;

    // Determine best URL: prefer tailscale IP for remote, local IP for LAN
    let bestUrl = url;
    if (source === "tailscale" && data.tailscale_ip) {
      bestUrl = `http://${data.tailscale_ip}:${PORT}`;
    }

    return {
      name: data.name || "Dispatch",
      hostname: data.hostname,
      url: bestUrl,
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
 * Get the device's local IP subnet prefix (e.g. "192.168.1" from "192.168.1.42").
 * On React Native, we can't easily get the local IP, so we try common subnets.
 */
function getCommonSubnets(): string[] {
  // Common home network subnets to scan
  return ["192.168.1", "192.168.0", "10.0.0", "10.0.1", "10.10.10", "172.16.0"];
}

/**
 * Scan a subnet for dispatch-api servers.
 * Probes IPs in parallel with batching to avoid overwhelming the network.
 */
async function scanSubnet(
  subnet: string,
  onProgress?: (scanned: number, total: number) => void,
): Promise<DiscoveredServer[]> {
  const results: DiscoveredServer[] = [];
  const BATCH_SIZE = 30;
  const total = 254;
  let scanned = 0;

  for (let batch = 0; batch < Math.ceil(total / BATCH_SIZE); batch++) {
    const promises: Promise<DiscoveredServer | null>[] = [];
    const start = batch * BATCH_SIZE + 1;
    const end = Math.min(start + BATCH_SIZE, 255);

    for (let i = start; i < end; i++) {
      const ip = `${subnet}.${i}`;
      promises.push(probeServer(ip, "local"));
    }

    const batchResults = await Promise.all(promises);
    for (const result of batchResults) {
      if (result) results.push(result);
    }

    scanned += end - start;
    onProgress?.(scanned, total);
  }

  return results;
}

/**
 * Query Tailscale API for devices on the tailnet, then probe each for dispatch-api.
 */
async function discoverViaTailscale(
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
    const devices: Array<{ addresses: string[]; hostname: string; os: string }> =
      data.devices || [];

    // Probe each device's IPv4 address for dispatch-api
    const probes = devices
      .filter((d) => d.addresses?.length > 0)
      .map((d) => {
        const ipv4 = d.addresses.find((a: string) => !a.includes(":"));
        if (!ipv4) return Promise.resolve(null);
        return probeServer(ipv4, "tailscale");
      });

    const results = await Promise.all(probes);
    return results.filter((r): r is DiscoveredServer => r !== null);
  } catch {
    return [];
  }
}

export interface DiscoveryOptions {
  /** Tailscale API key for remote discovery */
  tailscaleApiKey?: string;
  /** Specific subnets to scan (defaults to common subnets) */
  subnets?: string[];
  /** Progress callback */
  onProgress?: (phase: string, scanned: number, total: number) => void;
  /** Also probe currently configured URL */
  currentUrl?: string;
}

/**
 * Run full server discovery: local network + tailscale.
 * Returns deduplicated list of discovered servers.
 */
export async function discoverServers(
  options: DiscoveryOptions = {},
): Promise<DiscoveredServer[]> {
  const allServers: DiscoveredServer[] = [];
  const seenUrls = new Set<string>();

  const addServer = (server: DiscoveredServer) => {
    if (!seenUrls.has(server.url)) {
      seenUrls.add(server.url);
      allServers.push(server);
    }
  };

  // Phase 1: Probe current URL (instant feedback)
  if (options.currentUrl) {
    options.onProgress?.("current", 0, 1);
    const urlMatch = options.currentUrl.match(/\/\/([^:/]+)/);
    if (urlMatch) {
      const result = await probeServer(urlMatch[1], "local");
      if (result) {
        result.url = options.currentUrl;
        addServer(result);
      }
    }
    options.onProgress?.("current", 1, 1);
  }

  // Phase 2: Local subnet scan + Tailscale in parallel
  const localPromise = (async () => {
    const subnets = options.subnets ?? getCommonSubnets();
    for (const subnet of subnets) {
      options.onProgress?.(`lan:${subnet}`, 0, 254);
      const found = await scanSubnet(subnet, (scanned, total) => {
        options.onProgress?.(`lan:${subnet}`, scanned, total);
      });
      found.forEach(addServer);
      // If we found something on this subnet, skip remaining subnets
      if (found.length > 0) break;
    }
  })();

  const tailscalePromise = (async () => {
    if (!options.tailscaleApiKey) return;
    options.onProgress?.("tailscale", 0, 1);
    const found = await discoverViaTailscale(options.tailscaleApiKey);
    found.forEach(addServer);
    options.onProgress?.("tailscale", 1, 1);
  })();

  await Promise.all([localPromise, tailscalePromise]);

  // Sort: lowest latency first
  allServers.sort((a, b) => a.latencyMs - b.latencyMs);

  return allServers;
}
