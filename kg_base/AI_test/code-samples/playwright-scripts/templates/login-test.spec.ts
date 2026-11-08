/**
 * 登录测试脚本模板
 * ==============
 * AI 生成的 Playwright 测试脚本示例。
 * 展示：页面对象模式 + 数据驱动 + 截图上报。
 *
 * 运行: npx playwright test --grep "@smoke"
 */

import { test, expect, Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// 页面对象
// ---------------------------------------------------------------------------
class LoginPage {
  constructor(private page: Page) {}

  /** 导航到登录页 */
  async goto(url: string) {
    await this.page.goto(url, { waitUntil: "networkidle" });
  }

  /** 执行登录 */
  async login(username: string, password: string) {
    await this.page.fill('[data-testid="username-input"]', username);
    await this.page.fill('[data-testid="password-input"]', password);
    await this.page.click('[data-testid="login-button"]');
    // 等待导航完成
    await this.page.waitForURL("**/dashboard", { timeout: 10000 });
  }

  /** 获取错误提示（登录失败时） */
  async getErrorMessage(): Promise<string> {
    const el = this.page.locator('[data-testid="login-error"]');
    return (await el.isVisible()) ? (await el.textContent()) ?? "" : "";
  }
}

// ---------------------------------------------------------------------------
// 数据驱动：测试数据集
// ---------------------------------------------------------------------------
interface LoginTestCase {
  id: string;
  username: string;
  password: string;
  expectSuccess: boolean;
  description: string;
}

const TEST_DATA: LoginTestCase[] = [
  { id: "TC-LOGIN-001", username: "admin@test.com",   password: "Test123!",   expectSuccess: true,  description: "正向—正确凭据" },
  { id: "TC-LOGIN-002", username: "wrong@test.com",   password: "WrongPwd!", expectSuccess: false, description: "异常—错误密码" },
  { id: "TC-LOGIN-003", username: "",                  password: "",          expectSuccess: false, description: "边界—空用户名密码" },
  { id: "TC-LOGIN-004", username: "admin@test.com",   password: "",          expectSuccess: false, description: "边界—密码为空" },
  { id: "TC-LOGIN-005", username: "a".repeat(256),    password: "Test123!",  expectSuccess: false, description: "边界—超长用户名" },
];

// ---------------------------------------------------------------------------
// 测试
// ---------------------------------------------------------------------------
test.describe("登录功能 @smoke", () => {
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    await loginPage.goto(process.env.BASE_URL ?? "http://localhost:3000/login");
  });

  for (const tc of TEST_DATA) {
    test(`[${tc.id}] ${tc.description}`, async ({ page }, testInfo) => {
      // 上报测试开始
      await _reportTestStart(tc.id);

      await loginPage.login(tc.username, tc.password);

      if (tc.expectSuccess) {
        // 正向：验证跳转到仪表盘
        await expect(page).toHaveURL(/\/dashboard/);
        await expect(page.locator('[data-testid="user-avatar"]')).toBeVisible();
      } else {
        // 负向：验证停留在登录页且有错误提示
        await expect(page).toHaveURL(/\/login/);
        const errMsg = await loginPage.getErrorMessage();
        expect(errMsg).not.toBe("");
      }

      // 截图上报（失败时自动附加，这里显式示例）
      await testInfo.attach("screenshot", {
        body: await page.screenshot(),
        contentType: "image/png",
      });
    });
  }
});

// ---------------------------------------------------------------------------
// 上报工具（示意）
// ---------------------------------------------------------------------------
async function _reportTestStart(testcaseId: string) {
  // 实际实现：调用 Azure Function 上报执行状态到 Dataverse
  // 或者写本地 JSON 供后续收集
  console.log(`[REPORT] 开始执行: ${testcaseId}`);
}
