# HttpRAGConnector

通用 HTTP RAG 连接器。把任何提供 HTTP API 的知识库服务接入 LangBot。

如果你接的是 Dify、RAGFlow、FastGPT 这类常见平台，**优先使用它们各自的专用插件**。只有在没有专用插件，或者你要接一个自定义 HTTP 检索接口时，再使用这个插件。

## 快速开始

最少只需要填 **3 个字段** 就能跑起来：

| 字段 | 填什么 | 示例 |
|------|--------|------|
| API Base URL | 你的 RAG 服务基础地址 | `https://your-rag.com/api/v1` |
| Retrieval Endpoint | 检索接口路径 | `/search` |
| API Key | 认证密钥（没有就留空） | `sk-xxx` |

其余字段都有合理默认值：

- **Request Body Template** 留空 → 自动发送 `{"query": "用户问题", "top_k": 5}`
- **Results Array Path** 默认 `results`
- **Content Field(s)** 默认 `content`
- **Score Field** 默认 `score`
- **ID Field** 默认 `id`

如果你的 API 返回格式刚好匹配这些默认值，不需要改任何东西，直接就能用。

## 它是怎么工作的

你告诉插件两件事：

1. **请求**：检索时应该请求哪个 HTTP 接口，请求体长什么样
2. **响应**：接口返回后，结果数组、文本内容、分数、ID 分别在哪个字段里

插件会自动把用户问题和检索参数填进请求里，再把响应转成 LangBot 可用的知识片段。

## 字段说明

### 创建时要填的字段

#### API Base URL（必填）

目标服务的基础地址，只填域名和路径前缀，不包含具体接口路径。

```
https://your-rag-service.com/api/v1
```

#### API Key

认证密钥。默认以 `Authorization: Bearer <key>` 方式发送。不需要认证则留空。

#### Dataset ID

数据集/知识库 ID。如果你的接口路径或请求体里用了 `{{ dataset_id }}`，运行时会替换成这里的值。不需要则留空。

### 检索设置

#### Retrieval Endpoint（必填）

检索接口路径。最终请求地址 = API Base URL + 这里的路径。支持 `{{ dataset_id }}` 变量。

```
/search
/datasets/{{ dataset_id }}/retrieve
/api/query
```

#### Request Body Template

检索请求的 JSON 模板。支持以下变量：

| 变量 | 来源 |
|------|------|
| `{{ query }}` | 用户当前问题 |
| `{{ top_k }}` | 检索设置里的返回数量 |
| `{{ similarity_threshold }}` | 检索设置里的相似度阈值 |
| `{{ dataset_id }}` | 创建时填写的 Dataset ID |

**留空则自动使用**：`{"query": "{{ query }}", "top_k": {{ top_k }}}`

自定义示例：

```json
{
  "query": "{{ query }}",
  "limit": {{ top_k }},
  "min_score": {{ similarity_threshold }},
  "collection": "{{ dataset_id }}"
}
```

注意：字符串变量要加引号（`"{{ query }}"`），数字变量不加引号（`{{ top_k }}`）。

#### Results Array Path（必填）

响应 JSON 中结果数组的位置。用点分路径。

| 你的响应结构 | 应该填 |
|---|---|
| `{"results": [...]}` | `results` |
| `{"data": {"records": [...]}}` | `data.records` |
| `{"hits": {"hits": [...]}}` | `hits.hits` |

#### Content Field(s)（必填）

每条结果中文本内容所在的字段。支持点分路径。多个字段用逗号分隔，会自动拼接。

| 你的结果结构 | 应该填 |
|---|---|
| `{"content": "..."}` | `content` |
| `{"segment": {"content": "..."}}` | `segment.content` |
| `{"question": "...", "answer": "..."}` | `question,answer` |

#### Score Field / ID Field

分数和 ID 字段。留空表示不使用。

#### Top K / Similarity Threshold

返回数量和相似度阈值。会替换模板中的 `{{ top_k }}` 和 `{{ similarity_threshold }}`。

### 高级连接设置

点击「显示高级连接设置」展开。大部分情况不需要修改。

| 字段 | 用途 | 什么时候改 |
|------|------|-----------|
| Auth Header Name | 认证头名称（默认 `Authorization`） | 服务要求 `X-API-Key` 等自定义头 |
| Auth Header Prefix | 认证头前缀（默认 `Bearer`） | 服务要求裸 token（留空）或其他前缀 |
| Extra Headers (JSON) | 附加请求头 | 多租户、版本头、自定义 trace header |
| Verify SSL | SSL 证书校验（默认开启） | 内网自签名证书 |
| Request Timeout | 请求超时（默认 30s） | 服务响应慢 |
| Debug Mode | 调试日志（默认关闭） | 首次对接或排查问题 |

### 高级检索设置

点击「显示高级检索设置」展开。大部分情况不需要修改。

| 字段 | 用途 | 什么时候改 |
|------|------|-----------|
| HTTP Method | 检索请求方法（默认 `POST`） | API 要求 `GET` 等其他方法 |
| Payload Mode | 请求发送方式（默认 JSON body） | API 要求表单提交或查询参数 |
| Metadata Field Mapping | 额外返回字段 | 需要来源、页码、URL 等信息 |
| Skip Empty Content | 跳过空内容（默认开启） | 所有场景建议保持开启 |

### 文件上传 / 文档删除

打开对应开关后才需要填写，按提示填入你的 API 对应信息即可。

## 常见场景配置示例

### 最简单的 API

API 接收 `POST {"query": "...", "top_k": N}`，返回 `{"results": [{"content": "...", "score": 0.9, "id": "1"}]}`。

只需填：
- **API Base URL**: `https://my-rag.com`
- **Retrieval Endpoint**: `/search`
- 其余全部留空/默认

### Dify

- **API Base URL**: `https://api.dify.ai/v1`
- **API Key**: 你的 Dify Dataset API Key
- **Dataset ID**: Dify 控制台中的数据集 ID
- **Retrieval Endpoint**: `/datasets/{{ dataset_id }}/retrieve`
- **Request Body Template**:

```json
{
  "query": "{{ query }}",
  "retrieval_model": {
    "search_method": "semantic_search",
    "reranking_enable": false,
    "reranking_mode": null,
    "reranking_model": {
      "reranking_provider_name": "",
      "reranking_model_name": ""
    },
    "weights": null,
    "top_k": {{ top_k }},
    "score_threshold_enabled": true,
    "score_threshold": {{ similarity_threshold }}
  }
}
```

- **Results Array Path**: `records`
- **Content Field(s)**: `segment.content`
- **Score Field**: `score`
- **ID Field**: `segment.id`

### GET 请求的简单搜索 API

API 使用 `GET /search?q=xxx&limit=5`，返回 `{"data": [{"text": "...", "relevance": 0.8}]}`。

- **API Base URL**: `https://my-search.com`
- **Retrieval Endpoint**: `/search`
- **Request Body Template**: `{"q": "{{ query }}", "limit": {{ top_k }}}`
- **Results Array Path**: `data`
- **Content Field(s)**: `text`
- **Score Field**: `relevance`
- 打开「高级检索设置」→ **HTTP Method**: `GET`，**Payload Mode**: `Query Params`

## 排障

1. 打开「高级连接设置」→ 开启 **Debug Mode**
2. 检查日志中的最终 URL、method、payload 是否符合预期
3. 检查响应中 results_path 指向的是否是数组
4. 检查 content_fields、score_field、id_field 是否命中了真实字段
5. 如果是内网 HTTPS 服务，确认是否需要关闭 Verify SSL
