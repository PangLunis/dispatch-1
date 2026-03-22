#!/usr/bin/env node
/**
 * Start Metro bundler with remote access support.
 *
 * Reads `metroHost` from app.yaml and sets REACT_NATIVE_PACKAGER_HOSTNAME
 * so the dev server binds to a reachable IP (e.g. Tailscale) instead of localhost.
 *
 * Usage: node scripts/start-metro.js [-- ...expo-start-args]
 */

const { execSync, spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

// Read metroHost from app.yaml
let metroHost = "";
try {
  const YAML = require("yaml");
  const yamlPath = path.join(__dirname, "..", "app.yaml");
  if (fs.existsSync(yamlPath)) {
    const config = YAML.parse(fs.readFileSync(yamlPath, "utf8")) || {};
    metroHost = config.metroHost || "";
  }
} catch {
  // No app.yaml or yaml parse error — use default
}

// Pass through any extra args (e.g. --clear, --port)
const args = ["start", ...process.argv.slice(2)];

const env = { ...process.env };
if (metroHost) {
  env.REACT_NATIVE_PACKAGER_HOSTNAME = metroHost;
  console.log(`Metro binding to ${metroHost} (from app.yaml metroHost)`);
}

const child = spawn("npx", ["expo", ...args], {
  env,
  stdio: "inherit",
  cwd: path.join(__dirname, ".."),
});

child.on("exit", (code) => process.exit(code || 0));
