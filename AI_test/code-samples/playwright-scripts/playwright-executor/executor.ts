/**
 * AI 测试执行器 — 入口
 * =================
 * 功能：接收 AI 生成的测试用例 JSON，动态生成并执行 Playwright 测试。
 *
 * 工作流：
 *   用例 JSON → AI 翻译为脚本 → 写入文件 → Playwright 执行 → 收集结果
 *
 * 注意：动态生成脚本在生产环境需谨慎（安全审计、沙箱执行）。
 * 这里展示概念实现，实际项目建议预生成脚本而非运行时动态执行。
 */

import { chromium, Browser, Page } from "playwright";
import * as fs from "fs";
import * as path from "path";

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------
interface TestAction {
  type: "navigate" | "click" | "fill" | "select" | "assertVisible"
       | "assertText" | "assertUrl" | "screenshot" | "wait";
  target?: string;       // 选择器或 URL
  value?: string;        // 输入值
  expected?: string;     // 预期值
  timeout?: number;      // 超时（ms）
}

interface AiTestCase {
  id: string;
  title: string;
  url: string;
  actions: TestAction[];
}

interface TestResult {
  testcaseId: string;
  title: string;
  status: "passed" | "failed" | "error";
  error?: string;
  duration: number;
  screenshots: string[];
}

// ---------------------------------------------------------------------------
// 执行器
// ---------------------------------------------------------------------------
export class TestExecutor {
  private browser: Browser | null = null;
  private results: TestResult[] = [];
  private screenshotDir: string;

  constructor(screenshotDir?: string) {
    this.screenshotDir = screenshotDir ?? "./screenshots";
    if (!fs.existsSync(this.screenshotDir)) {
      fs.mkdirSync(this.screenshotDir, { recursive: true });
    }
  }

  /** 初始化浏览器 */
  async init(headless = true) {
    this.browser = await chromium.launch({ headless });
  }

  /** 执行单个 AI 用例 */
  async executeTestCase(tc: AiTestCase): Promise<TestResult> {
    if (!this.browser) throw new Error("执行器未初始化，请先调用 init()");

    const start = Date.now();
    const context = await this.browser.newContext({
      viewport: { width: 1920, height: 1080 },
      // 模拟真实用户
      locale: "zh-CN",
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    });
    const page = await context.newPage();
    const screenshots: string[] = [];

    try {
      // 监听 console 错误
      page.on("pageerror", (err) => {
        console.error(`[${tc.id}] 页面异常:`, err.message);
      });

      for (let i = 0; i < tc.actions.length; i++) {
        const action = tc.actions[i];
        await this.executeAction(page, action, tc.id, i, screenshots);
      }

      // 截图收尾
      const finalScreenshot = path.join(
        this.screenshotDir,
        `${tc.id}_final.png`
      );
      await page.screenshot({ path: finalScreenshot, fullPage: true });
      screenshots.push(finalScreenshot);

      const result: TestResult = {
        testcaseId: tc.id,
        title: tc.title,
        status: "passed",
        duration: Date.now() - start,
        screenshots,
      };
      this.results.push(result);
      return result;
    } catch (err: any) {
      // 失败时截图
      const failScreenshot = path.join(
        this.screenshotDir,
        `${tc.id}_failed.png`
      );
      await page.screenshot({ path: failScreenshot }).catch(() => {});

      const result: TestResult = {
        testcaseId: tc.id,
        title: tc.title,
        status: "failed",
        error: err.message ?? String(err),
        duration: Date.now() - start,
        screenshots: [...screenshots, failScreenshot],
      };
      this.results.push(result);
      return result;
    } finally {
      await context.close();
    }
  }

  /** 执行一个 Action */
  private async executeAction(
    page: Page,
    action: TestAction,
    testcaseId: string,
    stepIndex: number,
    screenshots: string[]
  ) {
    const timeout = action.timeout ?? 5000;

    switch (action.type) {
      case "navigate":
        await page.goto(action.target!, { waitUntil: "networkidle", timeout });
        break;

      case "click":
        await page.click(action.target!, { timeout });
        break;

      case "fill":
        await page.fill(action.target!, action.value ?? "", { timeout });
        break;

      case "select":
        await page.selectOption(action.target!, action.value ?? "");
        break;

      case "assertVisible":
        await page.waitForSelector(action.target!, {
          state: "visible",
          timeout,
        });
        break;

      case "assertText":
        {
          const el = page.locator(action.target!);
          await expect(el).toHaveText(action.expected ?? "", { timeout });
        }
        break;

      case "assertUrl":
        await page.waitForURL(action.expected ?? "", { timeout });
        break;

      case "screenshot":
        {
          const sp = path.join(
            this.screenshotDir,
            `${testcaseId}_step${stepIndex}.png`
          );
          await page.screenshot({ path: sp, fullPage: false });
          screenshots.push(sp);
        }
        break;

      case "wait":
        await page.waitForTimeout(action.timeout ?? 1000);
        break;
    }
  }

  /** 批量执行用例 */
  async executeBatch(testCases: AiTestCase[]): Promise<TestResult[]> {
    const batchResults: TestResult[] = [];
    for (const tc of testCases) {
      console.log(`[执行] ${tc.id}: ${tc.title}`);
      const result = await this.executeTestCase(tc);
      batchResults.push(result);
    }
    return batchResults;
  }

  /** 清理 */
  async dispose() {
    await this.browser?.close();
  }

  /** 获取所有结果 */
  getResults(): TestResult[] {
    return [...this.results];
  }

  /** 生成结果汇总 */
  generateSummary(): string {
    const passed = this.results.filter((r) => r.status === "passed").length;
    const failed = this.results.filter((r) => r.status === "failed").length;
    return [
      `执行完成: ${this.results.length} 条用例`,
      `通过: ${passed} | 失败: ${failed}`,
      `通过率: ${passed / this.results.length}%`,
    ].join("\n");
  }
}

// 简化的 expect（实际项目中 import @playwright/test 的 expect）
function expect(locator: any) {
  return {
    toHaveText: async (expected: string, options?: any) => {
      const text = await locator.textContent();
      if (!text?.includes(expected)) {
        throw new Error(`预期文本 "${expected}"，实际 "${text}"`);
      }
    },
  };
}

// ---------------------------------------------------------------------------
// CLI 入口
// ---------------------------------------------------------------------------
async function main() {
  const testCasePath = process.argv[2];
  if (!testCasePath) {
    console.error("用法: npx ts-node executor.ts <test-case-json-path>");
    process.exit(1);
  }

  const raw = fs.readFileSync(testCasePath, "utf-8");
  const testCases: AiTestCase[] = JSON.parse(raw);

  const executor = new TestExecutor();
  await executor.init(true);
  const results = await executor.executeBatch(testCases);
  await executor.dispose();

  // 输出结果
  fs.writeFileSync(
    path.join(executor["screenshotDir"], "..", "execution-result.json"),
    JSON.stringify(results, null, 2)
  );
  console.log(executor.generateSummary());
}

if (require.main === module) {
  main().catch(console.error);
}
