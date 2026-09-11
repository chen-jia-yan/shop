/**
 * AI测试用例 → Playwright 脚本 翻译器
 * ================================
 * 功能：接收结构化测试用例 JSON，调用 Azure OpenAI 生成 Playwright 脚本。
 *
 * 这步是 AI 生成测试脚本的核心环节。
 * 用例生成（Function）产出结构化用例 → 本函数翻译成可执行脚本。
 */

import { AiTestCase, TestAction } from "./executor";

// 假设的 Azure OpenAI 客户端
interface LlmClient {
  chat(prompt: string): Promise<string>;
}

/**
 * 将结构化测试用例翻译为可执行脚本的 Action 列表。
 *
 * 策略：先用模板匹配常见模式，对复杂场景回退到 LLM 翻译。
 * 纯模板方式更快、更稳定，LLM 方式更灵活。
 */
export async function translateToActions(
  testCase: any,
  llmClient?: LlmClient
): Promise<AiTestCase> {
  const actions: TestAction[] = [
    { type: "navigate", target: testCase.url ?? "/" },
  ];

  // 遍历用例的步骤
  for (const step of testCase.steps ?? []) {
    const action = matchAction(step);
    if (action) {
      actions.push(action);
    } else if (llmClient) {
      // 模板未匹配，走 LLM
      const llmAction = await llmTranslate(step, llmClient);
      if (llmAction) actions.push(llmAction);
    } else {
      console.warn(`无法翻译步骤: "${step}"，跳过`);
    }
  }

  // 最后加个断言确保不被漏掉
  if (testCase.expected?.length) {
    for (const exp of testCase.expected) {
      const assertion = matchAssertion(exp);
      if (assertion) actions.push(assertion);
    }
  }

  actions.push({ type: "screenshot" });

  return {
    id: testCase.id ?? "UNKNOWN",
    title: testCase.title ?? "",
    url: testCase.url ?? "/",
    actions,
  };
}

// ---------------------------------------------------------------------------
// 模板匹配（覆盖 90% 的常见步骤）
// ---------------------------------------------------------------------------
function matchAction(stepText: string): TestAction | null {
  const trimmed = stepText.trim();

  // "点击 X" → click
  const clickMatch = trimmed.match(/^点击[：:]\s*(.+)$/);
  if (clickMatch) return { type: "click", target: selectorOf(clickMatch[1]) };

  // "输入 X 内容 Y" / "在 X 输入 Y" → fill
  const fillMatch = trimmed.match(
    /^(?:在\s*)?(.+?)(?:输入|填写)[：:]?\s*(.+)$/
  );
  if (fillMatch)
    return {
      type: "fill",
      target: selectorOf(fillMatch[1]),
      value: fillMatch[2],
    };

  // "选择 X 中的 Y" → select
  const selectMatch = trimmed.match(/^选择[：:]\s*(.+?)(?:中)?的\s*(.+)$/);
  if (selectMatch)
    return {
      type: "select",
      target: selectorOf(selectMatch[1]),
      value: selectMatch[2],
    };

  // "等待 N 秒" → wait
  const waitMatch = trimmed.match(/^等待\s*(\d+)\s*秒/);
  if (waitMatch)
    return { type: "wait", timeout: parseInt(waitMatch[1]) * 1000 };

  // "截屏" / "截图" → screenshot
  if (/截图|截屏/.test(trimmed)) return { type: "screenshot" };

  return null;
}

function matchAssertion(text: string): TestAction | null {
  const trimmed = text.trim();

  // "页面跳转到 X" → assertUrl
  const urlMatch = trimmed.match(/^(?:页面)?(?:跳转|导航)(?:到|至)[：:]?\s*(.+)$/);
  if (urlMatch) return { type: "assertUrl", expected: urlMatch[1] };

  // "出现 X" / "显示 X" → assertVisible
  if (/^(?:出现|显示|可以看到)/.test(trimmed)) {
    const target = trimmed.replace(/^(?:出现|显示|可以看到)/, "").trim();
    return { type: "assertVisible", target: selectorOf(target) };
  }

  // "X 包含 Y" → assertText
  const textMatch = trimmed.match(/^(.+?)(?:包含|显示为|应该是)[：:]?\s*(.+)$/);
  if (textMatch)
    return {
      type: "assertText",
      target: selectorOf(textMatch[1]),
      expected: textMatch[2],
    };

  return null;
}

// ---------------------------------------------------------------------------
// 选择器推断（简化版）
// ---------------------------------------------------------------------------
function selectorOf(text: string): string {
  // 常见的业务元素名 → data-testid 映射
  const MAPPING: Record<string, string> = {
    "登录按钮": '[data-testid="login-button"]',
    "用户名输入框": '[data-testid="username-input"]',
    "密码输入框": '[data-testid="password-input"]',
    "提交按钮": '[data-testid="submit-button"]',
    "确认按钮": '[data-testid="confirm-button"]',
    "取消按钮": '[data-testid="cancel-button"]',
    "搜索输入框": '[data-testid="search-input"]',
    "搜索按钮": '[data-testid="search-button"]',
    "新建按钮": '[data-testid="create-button"]',
    "编辑按钮": '[data-testid="edit-button"]',
    "删除按钮": '[data-testid="delete-button"]',
  };

  return MAPPING[text] ?? `text=${text}`;
}

// ---------------------------------------------------------------------------
// LLM 兜底翻译
// ---------------------------------------------------------------------------
async function llmTranslate(
  stepText: string,
  client: LlmClient
): Promise<TestAction | null> {
  const prompt = `将以下测试步骤翻译为 Playwright 操作（仅返回 JSON）：
步骤: "${stepText}"
可选操作类型: navigate, click, fill, select, assertVisible, assertText, wait, screenshot

返回格式: {"type": "...", "target": "...", "value": "..."} 或 null`;

  try {
    const raw = await client.chat(prompt);
    return JSON.parse(raw) as TestAction;
  } catch {
    return null;
  }
}
