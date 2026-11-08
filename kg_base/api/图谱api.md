# API 文档整理（library-kg）
---
## 1. Kg Nodes Chunks List
**接口地址**：`/tap/ai/library/kg/nodes/chunks/list`
- 请求方式：POST
- Path参数：无
- 请求体（Request Body，必填）
```json
{
  "node_id": "entity::1",
  "page": 1,
  "page_size": 20,
  "scope": "jp-poc"
}
```
- 响应 200 成功示例
```json
{
  "items": [
    {
      "chunk_id": "string",
      "source_file": "string",
      "page_or_sheet": "string",
      "label": "string",
      "direction": "string"
    }
  ],
  "total": 0,
  "page": 0,
  "page_size": 0
}
```
- 响应 422：Validation Error（参数校验错误）

---
## 2. Kg Nodes Search
**接口地址**：`/tap/ai/library/kg/nodes/search`
- 请求方式：POST
- Path参数：无
- 请求体（Request Body，必填）
```json
{
  "include_chunks": false,
  "keyword": "保险",
  "page": 1,
  "page_size": 20,
  "scope": "jp-poc"
}
```
- 响应 200 成功示例
```json
{
  "items": [
    {
      "id": "string",
      "name": "string",
      "type": "string",
      "source_files": [
        "string"
      ],
      "degree": 0
    }
  ],
  "total": 0,
  "page": 0,
  "page_size": 0
}
```

---
## 3. Kg Node Detail
**接口地址**：`/tap/ai/library/kg/nodes/{node_id}`
- 请求方式：POST
- Path参数：
| 参数名 | 类型 | 是否必填 | 说明 |
| ---- | ---- | ---- | ---- |
| node_id | string | ✅ 必填 | 路径参数 |
- 请求体（Request Body，必填）
```json
{
  "scope": "jp-poc"
}
```
- 响应 200 成功示例
```json
{
  "id": "string",
  "name": "string",
  "type": "string",
  "properties": {
    "additionalProp1": {}
  },
  "source_files": [
    "string"
  ],
  "degree": 0
}
```

---
## 4. Kg Files List
**接口地址**：`/tap/ai/library/kg/files/list`
- 请求方式：POST
- Path参数：无
- 请求体（Request Body，必填）
```json
{
  "page": 1,
  "page_size": 20,
  "scope": "jp-poc"
}
```
- 响应 200 成功示例
```json
{
  "items": [
    {
      "doc_id": "string",
      "source_file": "string",
      "chunk_count": 0,
      "entity_count": 0,
      "entity_edge_count": 0
    }
  ],
  "total": 0,
  "page": 0,
  "page_size": 0
}
```

---
## 5. Library Kg Scopes List
**接口地址**：`/tap/ai/library/kg/scopes/list`
- 请求方式：POST
- Path参数：无
- 请求体（Request Body，必填）
```json
{}
```
- 响应 200 成功示例
```json
{
  "items": [
    {
      "scope": "string",
      "entity_count": 0,
      "relation_count": 0,
      "chunk_count": 0,
      "document_count": 0,
      "last_updated": 0,
      "saas_ids": [],
      "has_graph": true
    }
  ]
}
```

# API 文档整理
> 基础地址：`[http://127.0.0.1:9006](http://127.0.0.1:9006)`
> 全部接口请求方式：`POST`，请求头固定：`Content-Type: application/json`
---

## 1. /tap/ai/library/kg/entities/list
**接口名称**：Kg Entities List
- 请求方式：POST
- Request Body
```json
{
  "page": 1,
  "page_size": 20,
  "scope": "jp-poc"
}
```
- 示例 Curl
```bash
curl -X 'POST' \
  '[http://127.0.0.1:9006/tap/ai/library/kg/entities/list](http://127.0.0.1:9006/tap/ai/library/kg/entities/list)' \
  -H 'accept: */*' \
  -H 'Content-Type: application/json' \
  -d '{
  "page": 1,
  "page_size": 20,
  "scope": "jp-poc"
}'
```
- Responses：
{
  "items": [
    {
      "id": "string",
      "type": "string",
      "type_zh": "string",
      "label": "string",
      "degree": 0,
      "updated_at": 0
    }
  ],
  "total": 0,
  "page": 0,
  "page_size": 0
}


---

## 2. /tap/ai/library/kg/stats
**接口名称**：Kg Stats
- 请求方式：POST
- Request Body（必填）
```json
{
  "scope": "jp-poc"
}
```
- Response 示例
```json
{
  "entity_nodes": {
    "total": 0,
    "type_counts": {
      "additionalProp1": 0,
      "additionalProp2": 0,
      "additionalProp3": 0
    }
  },
  "chunk_nodes": {
    "total": 0,
    "type_counts": {
      "additionalProp1": 0,
      "additionalProp2": 0,
      "additionalProp3": 0
    }
  },
  "entity_edges": {
    "total": 0,
    "type_counts": {
      "additionalProp1": 0,
      "additionalProp2": 0,
      "additionalProp3": 0
    }
  },
  "chunk_edges": {
    "total": 0,
    "type_counts": {
      "additionalProp1": 0,
      "additionalProp2": 0,
      "additionalProp3": 0
    }
  }
}
```

---

## 3. /tap/ai/library/kg/graph/overview
**接口名称**：Kg Graph Overview
- 请求方式：POST
- Request Body（必填）
```json
{
  "limit": 300,
  "scope": "jp-poc"
}
```
- Response 示例
```json
{
  "nodes": [
    {
      "id": "string",
      "name": "string",
      "type": "string",
      "properties": {
        "additionalProp1": {}
      },
      "source_files": [
        "string"
      ]
    }
  ],
  "edges": [
    {
      "id": "string",
      "source": "string",
      "target": "string",
      "type": "string",
      "properties": {
        "additionalProp1": {}
      }
    }
  ],
  "truncated": true
}
```

---

## 4. /tap/ai/library/kg/nodes/expand
**接口名称**：Kg Nodes Expand
- 请求方式：POST
- Request Body（必填）
```json
{
  "depth": 1,
  "include_chunks": false,
  "limit": 100,
  "node_id": "entity::1",
  "scope": "jp-poc"
}
```
- Response 示例
```json
{
  "nodes": [
    {
      "id": "string",
      "name": "string",
      "type": "string",
      "properties": {
        "additionalProp1": {}
      },
      "source_files": [
        "string"
      ]
    }
  ],
  "edges": [
    {
      "id": "string",
      "source": "string",
      "target": "string",
      "type": "string",
      "properties": {
        "additionalProp1": {}
      }
    }
  ],
  "truncated": true
}
```