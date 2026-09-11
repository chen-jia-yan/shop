/**
 * Dataverse Web API 调用示例
 * =========================
 * 通过 Azure Functions 或 Node.js 后端操作 Dataverse。
 *
 * 认证方式：OAuth 2.0 (client credentials) 或 托管标识(Managed Identity)
 * 基础 URL：https://{org}.crm.dynamics.com/api/data/v9.2/
 *
 * 以下示例假设使用 Managed Identity 或已获取 Bearer Token。
 */

import https from "https";

// ---------------------------------------------------------------------------
// 配置
// ---------------------------------------------------------------------------
const DATAVERSE_BASE = "https://orgname.crm.dynamics.com";
const API_VERSION = "v9.2";
const BASE_URL = `${DATAVERSE_BASE}/api/data/${API_VERSION}`;

// 实际的 Token 获取取决于认证方式
// - Managed Identity: 使用 @azure/identity 的 DefaultAzureCredential
// - Client Credentials: 使用 MSAL 库获取 token
let _accessToken: string = "";

export async function setAccessToken(token: string) {
  _accessToken = token;
}

// ---------------------------------------------------------------------------
// 通用请求
// ---------------------------------------------------------------------------
async function request<T>(
  method: string,
  path: string,
  body?: any
): Promise<T> {
  const url = new URL(path, BASE_URL);
  const options: https.RequestOptions = {
    method,
    hostname: url.hostname,
    path: url.pathname + url.search,
    headers: {
      Authorization: `Bearer ${_accessToken}`,
      "Content-Type": "application/json",
      Accept: "application/json",
      "OData-MaxVersion": "4.0",
      "OData-Version": "4.0",
    },
  };

  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (chunk: string) => (data += chunk));
      res.on("end", () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data ? JSON.parse(data) : ({} as T));
        } else {
          reject(new Error(`Dataverse API error ${res.statusCode}: ${data}`));
        }
      });
    });
    req.on("error", reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

/** 创建记录，返回记录 ID */
export async function createRecord(
  entitySetName: string,
  data: Record<string, any>
): Promise<string> {
  const res = await request<{ [key: string]: string }>("POST", entitySetName, data);
  // POST 返回 204 No Content，Location header 包含 ID
  // 这里简化处理，实际需要从 response headers 提取
  return res["_id"] ?? "";
}

/** 批量创建（最大 100 条） */
export async function createBatch(
  entitySetName: string,
  records: Record<string, any>[]
): Promise<void> {
  // Dataverse 支持 $batch 端点，这里简化为循环
  for (const record of records) {
    await createRecord(entitySetName, record);
  }
}

/** 查询记录 */
export async function queryRecords<T>(
  entitySetName: string,
  options?: {
    select?: string[];
    filter?: string;
    expand?: string[];
    top?: number;
    orderBy?: string;
  }
): Promise<{ value: T[] }> {
  let query = `${entitySetName}?`;
  if (options?.select) query += `$select=${options.select.join(",")}&`;
  if (options?.filter) query += `$filter=${encodeURIComponent(options.filter)}&`;
  if (options?.top) query += `$top=${options.top}&`;
  if (options?.orderBy) query += `$orderby=${options.orderBy}&`;
  if (options?.expand) {
    for (const nav of options.expand) {
      query += `$expand=${nav}&`;
    }
  }
  return request<{ value: T[] }>("GET", query);
}

/** 更新记录 */
export async function updateRecord(
  entitySetName: string,
  recordId: string,
  data: Record<string, any>
): Promise<void> {
  await request("PATCH", `${entitySetName}(${recordId})`, data);
}

/** 删除记录 */
export async function deleteRecord(
  entitySetName: string,
  recordId: string
): Promise<void> {
  await request("DELETE", `${entitySetName}(${recordId})`);
}

// ---------------------------------------------------------------------------
// 业务示例
// ---------------------------------------------------------------------------

/** 创建测试执行批次 */
export async function createTestRun(data: {
  ai_name: string;
  "ai_testprojectid@odata.bind": string; // 如 "ai_testproject(guid)"
  ai_environment: number;
  ai_testtype: number;
  ai_totalcases: number;
  ai_pipelinerunid: string;
}) {
  return createRecord("ai_testruns", {
    ai_name: data.ai_name,
    "ai_testprojectid@odata.bind": data["ai_testprojectid@odata.bind"],
    ai_environment: data.ai_environment,
    ai_testtype: data.ai_testtype,
    ai_totalcases: data.ai_totalcases,
    ai_pipelinerunid: data.ai_pipelinerunid,
    ai_startedat: new Date().toISOString(),
    ai_status: 0, // Running
  });
}

/** 获取失败用例列表（给失败分析用） */
export async function getFailedResults(runId: string) {
  return queryRecords<any>("ai_testresults", {
    filter: `ai_testrunid/ai_testrunid eq ${runId} and ai_status eq 3`,
    select: [
      "ai_testresultid",
      "ai_testcasename",
      "ai_errormessage",
      "ai_screenshots",
    ],
    expand: ["ai_testcaseid"],
    top: 50,
  });
}

/** 更新失败分析结果 */
export async function updateFailureAnalysis(
  resultId: string,
  analysis: {
    category: number;   // 对应 Picklist value
    reason: string;
    suggestion: string;
    isFlaky: boolean;
    confidence: number;
  }
) {
  return updateRecord("ai_testresults", resultId, {
    ai_failurecategory: analysis.category,
    ai_failurereason: analysis.reason,
    ai_fixsuggestion: analysis.suggestion,
    ai_isflaky: analysis.isFlaky,
    ai_confidence: analysis.confidence,
  });
}

/** 获取最近 N 次趋势数据 */
export async function getTrendData(
  projectId: string,
  days: number = 30
): Promise<{ date: string; passRate: number }[]> {
  const res = await queryRecords<any>("ai_testruns", {
    select: ["ai_completedat", "ai_passrate"],
    filter: `ai_testprojectid/ai_testprojectid eq ${projectId} and ai_status eq 1`,
    orderBy: "ai_completedat desc",
    top: days,
  });
  return res.value.map((r) => ({
    date: r.ai_completedat?.split("T")[0] ?? "",
    passRate: r.ai_passrate ?? 0,
  }));
}
