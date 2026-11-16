# 会议信息来源配置

> ⚠️ 待核实：TAP 能否通过 Microsoft Graph 访问用户日历。核实后修改下面的配置值。

```
MEETING_SOURCE = paste
```

可选值：`graph` / `paste` / `auto`。在核实之前，保持 `paste`，确保 skill 可以正常使用。

---

## 方式 A：Microsoft Graph（`graph` / `auto`）

### 核实清单（明天确认用）

- [ ] TAP 是否已在 Microsoft Entra ID（原 Azure AD）里注册了应用
- [ ] 该应用是否有 **委托权限**（delegated）`Calendars.Read`，并且管理员已同意
  - 只需要读取，不要申请 `Calendars.ReadWrite`
- [ ] 用户在 TAP 里登录时是否使用微软账号（SSO），TAP 能否拿到用户的访问令牌
- [ ] TAP 的 skill 运行环境里，是否有现成的工具或接口可以调用 Graph（如果有，记下工具名，替换下方"调用方式"）

### 调用方式（标准 Graph 接口，按 TAP 实际封装替换）

按时间范围查日历（会展开重复会议）：

```
GET https://graph.microsoft.com/v1.0/me/calendarView
    ?startDateTime=2026-11-17T00:00:00+08:00
    &endDateTime=2026-11-17T23:59:59+08:00
    &$select=subject,start,end,organizer,attendees,location,bodyPreview,body
    &$orderby=start/dateTime
Header: Prefer: outlook.timezone="China Standard Time"
```

使用到的返回字段：

| 字段 | 用途 |
|---|---|
| `subject` | 会议主题 |
| `start` / `end` | 时间 |
| `organizer.emailAddress` | 组织者 |
| `attendees[].emailAddress` / `attendees[].type` | 参会人（required / optional） |
| `location.displayName` | 地点 |
| `body.content` / `bodyPreview` | 议程正文（HTML，取文字即可） |

### 查找规则

- 用户说"明天""下午"等，先换算成时间范围再查。
- 用户提到关键词（如客户名），在 `subject` 和 `bodyPreview` 里匹配。
- 找到多个：列出时间和主题，请用户选。
- 一个都没找到：`auto` 模式下改为请用户粘贴；`graph` 模式下告诉用户没找到，请提供更多信息。

---

## 方式 B：用户粘贴或上传（`paste`）

用户可以用任意一种方式提供会议信息：

1. **上传 .ics 文件**：在 Outlook 里打开会议 → 文件 → 另存为 → 选择 iCalendar 格式。
2. **粘贴邀请内容**：在 Outlook 里打开会议邀请，全选复制正文。
3. **直接描述**：至少说明会议主题和参会方。

前两种用 `scripts/parse_invite.py` 解析。解析结果里缺主题或参会方时，再问用户补充。

给用户的提示语（可以直接使用）：

> 把会议邀请复制粘贴给我就行（在 Outlook 里打开邀请，全选复制）。没有邀请的话，告诉我会议主题和参会方也可以。
