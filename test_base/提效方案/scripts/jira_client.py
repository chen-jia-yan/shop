"""Jira Cloud REST API 的最小封装：认证、重试、查重搜索、建单、评论、附件、字段查询。

认证使用 Atlassian 个人 API Token（Basic Auth：邮箱 + Token），从环境变量读取：
    JIRA_BASE_URL   例如 https://your-company.atlassian.net
    JIRA_EMAIL      你的 Atlassian 账号邮箱
    JIRA_API_TOKEN  在 https://id.atlassian.com/manage-profile/security/api-tokens 创建

不要把 Token 写进代码或配置文件。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from common import fail


class JiraClient:
    def __init__(self, base_url: str | None = None, email: str | None = None, token: str | None = None,
                 timeout: int = 30):
        self.base = (base_url or os.environ.get("JIRA_BASE_URL") or "").rstrip("/")
        email = email or os.environ.get("JIRA_EMAIL")
        token = token or os.environ.get("JIRA_API_TOKEN")
        if not (self.base and email and token):
            fail("缺少 Jira 连接信息，请设置环境变量 JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN")
        self.session = requests.Session()
        self.session.auth = (email, token)
        self.session.headers.update({"Accept": "application/json"})
        self.timeout = timeout

    # ------------------------------------------------------------ 底层请求

    def _request(self, method: str, path: str, retries: int = 4, **kwargs) -> requests.Response:
        url = f"{self.base}{path}"
        for attempt in range(retries + 1):
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == retries:
                    break
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 60))
                continue
            break
        if resp.status_code >= 400:
            detail = resp.text[:800]
            raise RuntimeError(f"Jira {method} {path} 返回 {resp.status_code}：{detail}")
        return resp

    def myself(self) -> dict:
        return self._request("GET", "/rest/api/3/myself").json()

    def find_account_id(self, email_or_name: str) -> str | None:
        """按邮箱或姓名查找用户 accountId（Jira Cloud 指派人必须用 accountId）。找到多个或找不到时返回 None。"""
        users = self._request("GET", "/rest/api/3/user/search", params={"query": email_or_name}).json()
        active = [u for u in users if u.get("active", True)]
        return active[0]["accountId"] if len(active) == 1 else None

    # ------------------------------------------------------------ 搜索

    def search(self, jql: str, fields: list[str], max_results: int = 5) -> list[dict]:
        """使用 /rest/api/3/search/jql（旧的 /rest/api/3/search 已被 Atlassian 废弃）。"""
        params = {"jql": jql, "fields": ",".join(fields), "maxResults": max_results}
        data = self._request("GET", "/rest/api/3/search/jql", params=params).json()
        return data.get("issues", [])

    # ------------------------------------------------------------ 写入

    def create_issue(self, fields: dict) -> str:
        """用 v2 接口建单：v2 的 description 接受 Jira 文本格式（wiki markup）字符串。"""
        resp = self._request("POST", "/rest/api/2/issue", json={"fields": fields},
                             headers={"Content-Type": "application/json"})
        return resp.json()["key"]

    def add_comment(self, issue_key: str, body: str) -> str:
        resp = self._request("POST", f"/rest/api/2/issue/{issue_key}/comment", json={"body": body},
                             headers={"Content-Type": "application/json"})
        return resp.json().get("id", "")

    def add_attachment(self, issue_key: str, file_path: str | Path, upload_name: str | None = None) -> str:
        """上传附件。Atlassian 要求必须带 X-Atlassian-Token: no-check 请求头。"""
        file_path = Path(file_path)
        url = f"{self.base}/rest/api/3/issue/{issue_key}/attachments"
        for attempt in range(4):
            with open(file_path, "rb") as f:  # 每次重试都重新打开文件
                resp = self.session.post(url, timeout=self.timeout * 2,
                                         headers={"X-Atlassian-Token": "no-check"},
                                         files={"file": (upload_name or file_path.name, f)})
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 3:
                time.sleep(min(float(resp.headers.get("Retry-After", 2 ** attempt)), 60))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"上传附件 {file_path.name} 到 {issue_key} 失败：{resp.status_code} {resp.text[:500]}")
            items = resp.json()
            return items[0]["filename"] if items else file_path.name
        raise RuntimeError(f"上传附件 {file_path.name} 到 {issue_key} 多次重试后仍失败")

    # ------------------------------------------------------------ 字段查询

    def issue_types(self, project_key: str) -> list[dict]:
        data = self._request("GET", f"/rest/api/3/issue/createmeta/{project_key}/issuetypes",
                             params={"maxResults": 100}).json()
        return data.get("issueTypes") or data.get("values") or []

    def create_fields(self, project_key: str, issue_type_id: str) -> list[dict]:
        out, start = [], 0
        while True:
            data = self._request("GET", f"/rest/api/3/issue/createmeta/{project_key}/issuetypes/{issue_type_id}",
                                 params={"startAt": start, "maxResults": 50}).json()
            batch = data.get("fields") or data.get("values") or []
            out.extend(batch)
            total = data.get("total")
            start += len(batch)
            if not batch or (total is not None and start >= total) or data.get("isLast"):
                break
        return out
