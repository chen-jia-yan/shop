/**
 * 工作流测试脚本模板 — 采购审批流程
 * ==============================
 * 展示：涉及多步骤、多页面跳转的复杂业务流程测试。
 *
 * 核心模式：
 * 1. 每个测试方法覆盖一个完整业务场景
 * 2. 用 page object 封装页面交互
 * 3. 用 API mock / 测试账号隔离数据
 */

import { test, expect, Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// 页面对象
// ---------------------------------------------------------------------------
class PurchaseOrderPage {
  constructor(private page: Page) {}

  /** 创建采购单 */
  async createPO(items: Array<{ name: string; qty: number; price: number }>) {
    await this.page.click('[data-testid="btn-create-po"]');
    for (const item of items) {
      await this.page.fill('[data-testid="item-name"]', item.name);
      await this.page.fill('[data-testid="item-qty"]', String(item.qty));
      await this.page.fill('[data-testid="item-price"]', String(item.price));
      await this.page.click('[data-testid="btn-add-item"]');
    }
    await this.page.click('[data-testid="btn-submit-po"]');
    // 等待创建完成
    await expect(this.page.locator('[data-testid="po-success-toast"]')).toBeVisible();
  }

  /** 获取当前页面上的采购单号 */
  async getPONumber(): Promise<string> {
    return (await this.page.locator('[data-testid="po-number"]').textContent()) ?? "";
  }

  /** 审批采购单 */
  async approvePO(poNumber: string, comment?: string) {
    await this.page.goto(`/purchase-order/${poNumber}`);
    await this.page.click('[data-testid="btn-approve"]');
    if (comment) {
      await this.page.fill('[data-testid="approve-comment"]', comment);
    }
    await this.page.click('[data-testid="btn-confirm-approve"]');
    await expect(this.page.locator('[data-testid="approve-success"]')).toBeVisible();
  }

  /** 驳回采购单 */
  async rejectPO(poNumber: string, reason: string) {
    await this.page.goto(`/purchase-order/${poNumber}`);
    await this.page.click('[data-testid="btn-reject"]');
    await this.page.fill('[data-testid="reject-reason"]', reason);
    await this.page.click('[data-testid="btn-confirm-reject"]');
    await expect(this.page.locator('[data-testid="reject-success"]')).toBeVisible();
  }
}

// ---------------------------------------------------------------------------
// 测试
// ---------------------------------------------------------------------------
test.describe("采购审批流程 @regression", () => {
  let poPage: PurchaseOrderPage;

  test.beforeEach(async ({ page }) => {
    poPage = new PurchaseOrderPage(page);
    // 用测试专用账号，避免干扰正式数据
    await page.goto(process.env.APP_URL ?? "http://localhost:3000");
    // 以下假设已通过 cookie/api 完成登录
  });

  test("正向流程：创建并审批通过", async () => {
    await poPage.createPO([
      { name: "办公椅", qty: 10, price: 500 },
      { name: "显示器", qty: 5, price: 2000 },
    ]);
    const poNumber = await poPage.getPONumber();
    expect(poNumber).toMatch(/^PO-\d{8}$/);

    // 切到审批人视角（实际项目用不同 session，这里简化）
    await poPage.approvePO(poNumber, "审批通过");
  });

  test("负向场景：审批人驳回", async () => {
    await poPage.createPO([{ name: "服务器", qty: 1, price: 50000 }]);
    const poNumber = await poPage.getPONumber();

    await poPage.rejectPO(poNumber, "预算超限，需重新审批");
  });

  test("异常场景：提审金额超限自动拒绝", async () => {
    // 假设规则：单笔超过 10 万自动拒绝
    await poPage.createPO([{ name: "设备", qty: 1, price: 200000 }]);

    // 预期直接弹出拒绝提示，不进审批流程
    await expect(
      poPage["page"].locator('[data-testid="auto-reject-toast"]')
    ).toBeVisible();
  });
});
