import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:9091/app",
    browserName: "chromium",
    headless: true,
    viewport: { width: 1280, height: 800 },
    screenshot: "off", // We take manual screenshots
  },
  reporter: [["list"]],
});
