/**
 * Playwright 配置
 * =============
 * AI 测试执行器的 Playwright 配置文件。
 */

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./templates",
  timeout: 60000,
  retries: 1,
  use: {
    headless: true,
    viewport: { width: 1920, height: 1080 },
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
    // 用 data-testid 优先，避免 CSS 选择器耦合
    testIdAttribute: "data-testid",
  },
  projects: [
    {
      name: "smoke",
      use: { browserName: "chromium" },
      grep: /@smoke/,
    },
    {
      name: "regression",
      use: { browserName: "chromium" },
      grep: /@regression/,
    },
  ],
  reporter: [
    ["html", { outputFolder: "test-report" }],
    ["json", { outputFile: "test-report/results.json" }],
    // 自定义上报到 Dataverse / Azure DevOps
    ["list"],
  ],
});
