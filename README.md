# HttpRAGConnector

通用 HTTP RAG 连接器。适合你的知识库服务已经提供 HTTP API，但还没有专门插件的情况。

如果你接的是 Dify、RAGFlow、FastGPT 这类常见平台，优先建议使用它们各自的专用插件。只有在没有专用插件，或者你要接一个自定义 HTTP 检索接口时，再使用这个插件。

## 这个插件到底怎么工作

你只需要告诉插件两件事：

1. 检索时应该请求哪个 HTTP 接口，请求体长什么样
2. 接口返回后，结果数组、文本内容、分数、ID 分别在哪个字段里

插件会自动把用户问题和检索参数填进请求里，再把响应转成 LangBot 可用的知识片段。

## 最简单的理解

如果你不知道每个字段怎么填，可以先按下面这套 Dify 示例填写。

这套默认示例对应 Dify 的数据集检索接口：

- API Base URL: `https://api.dify.ai/v1`
- Auth Header Prefix: `Bearer`
- Retrieval Endpoint: `/datasets/{{ dataset_id }}/retrieve`
- Request Body Template:

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

- Results Array Path: `records`
- Content Field(s): `segment.content`
- Score Field: `score`
- ID Field: `segment.id`

只要你再补上：

- API Key: 你的 Dify API Key
- Dataset ID: 你的 Dify 数据集 ID

就能直接拿这个通用插件去连 Dify。

## 前端字段怎么填

下面按 LangBot 创建知识库时的表单字段来说明。

### 创建时要填的字段

#### API Base URL

- 填什么：目标服务的基础地址，不带最后的具体接口路径
- Dify 示例：`https://api.dify.ai/v1`
- 程序怎么用：后端会把它和 `Retrieval Endpoint`、上传接口、删除接口路径拼成最终请求地址
- 常见错误：不要写成完整检索 URL，例如不要直接填 `https://api.dify.ai/v1/datasets/xxx/retrieve`

#### API Key

- 填什么：服务的认证密钥
- Dify 示例：你的 Dify Dataset API Key
- 程序怎么用：后端会把它放进请求头 `Authorization: Bearer <API Key>`
- 哪些情况必填：几乎所有需要鉴权的服务都必填；当前插件也按必填处理

#### Auth Header Prefix

- 填什么：`Authorization` 请求头里 API Key 前面的前缀
- 默认值：`Bearer`
- Dify 示例：`Bearer`
- 程序怎么用：如果你填的是 `Bearer`，最终请求头就是 `Authorization: Bearer <API Key>`
- 什么时候改：只有你的目标服务不是 Bearer 鉴权时才改

#### Retrieval Endpoint

- 填什么：检索接口路径，只填路径部分
- Dify 示例：`/datasets/{{ dataset_id }}/retrieve`
- 程序怎么用：后端会把 `API Base URL + Retrieval Endpoint` 拼成最终检索地址
- 支持变量：`{{ dataset_id }}`
- 常见错误：这里不要再重复写域名

#### Retrieval Request Body Template

- 填什么：检索请求体的 JSON 模板
- Dify 示例：直接使用表单默认值
- 程序怎么用：
  - `{{ query }}` 会替换成用户当前提问
  - `{{ top_k }}` 会替换成前端检索设置里的返回数量
  - `{{ similarity_threshold }}` 会替换成前端检索设置里的相似度阈值
  - `{{ dataset_id }}` 会替换成创建时填写的数据集 ID
- 注意：
  - 要填合法 JSON
  - 字符串变量要加引号，比如 `"{{ query }}"`
  - 数字变量一般不要加引号，比如 `{{ top_k }}`

#### Results Array Path

- 填什么：响应 JSON 里“结果数组”所在的位置
- Dify 示例：`records`
- 程序怎么用：后端会先找到这个数组，再逐条读取每个结果
- 怎么判断该填什么：看你的接口返回里，真正的结果列表在哪个字段里

#### Content Field(s)

- 填什么：每条结果中正文内容所在字段
- Dify 示例：`segment.content`
- 程序怎么用：这个字段会被当成最终返回给模型的知识文本
- 多字段写法：如果要把多个字段拼起来，可以写成 `question,answer`

#### Score Field

- 填什么：每条结果里的相关度/相似度分数字段
- Dify 示例：`score`
- 程序怎么用：用于记录检索分数，便于排序和调试
- 可不填：如果你的接口不返回分数，可以留空

#### ID Field

- 填什么：每条结果的唯一 ID 字段
- Dify 示例：`segment.id`
- 程序怎么用：用于标识结果来源；删除文档等场景也可能依赖它
- 可不填：如果接口没有返回唯一 ID，可以留空

#### Dataset ID

- 填什么：目标知识库或数据集的 ID
- Dify 示例：Dify 控制台 URL 中的那段 dataset id
- 程序怎么用：
  - 如果你的 Endpoint 里写了 `{{ dataset_id }}`，后端会替换进去
  - 如果你的请求体模板里写了 `{{ dataset_id }}`，后端也会替换进去
- 什么时候可留空：只有当你的接口根本不需要数据集 ID 时

### 每次检索可调的字段

#### Top K

- 填什么：最多取回多少条结果
- 默认值：`5`
- 程序怎么用：替换模板中的 `{{ top_k }}`
- 建议：一般填 `3` 到 `10` 即可

#### Similarity Threshold

- 填什么：最低相似度阈值
- 默认值：`0.2`
- 程序怎么用：替换模板中的 `{{ similarity_threshold }}`
- 说明：只有你的目标接口真的使用这个字段时，它才会生效

### 可选功能：文件上传

打开 `Enable File Upload` 后才需要填写。

#### Upload Endpoint

- Dify 示例：`/datasets/{{ dataset_id }}/document/create-by-file`
- 程序怎么用：上传文件时调用这个接口

#### File Field Name

- Dify 示例：`file`
- 程序怎么用：作为 multipart/form-data 里的文件字段名

#### Upload Extra Data

- Dify 示例：

```json
{
  "indexing_technique": "high_quality",
  "process_rule": {
    "mode": "automatic"
  }
}
```

- 程序怎么用：会作为表单中的 `data` 字段一起提交
- 注意：这里也支持 `{{ dataset_id }}` 这类变量替换

#### Document ID Response Path

- Dify 示例：`document.id`
- 程序怎么用：上传成功后，从响应里取出文档 ID

### 可选功能：文档删除

打开 `Enable Document Deletion` 后才需要填写。

#### Delete Endpoint

- Dify 示例：`/datasets/{{ dataset_id }}/documents/{{ document_id }}`
- 程序怎么用：删除文档时会把 `{{ dataset_id }}` 和 `{{ document_id }}` 替换后发请求

#### Delete HTTP Method

- Dify 示例：`DELETE`
- 程序怎么用：按你选的 HTTP 方法发删除请求

#### Delete Request Body Template

- Dify 示例：留空
- 程序怎么用：有些服务删除时需要 JSON 请求体，这里就填模板；不需要就留空

## 变量说明

| 变量 | 从哪里来 | 一般用在哪 |
|------|----------|------------|
| `{{ query }}` | 用户当前问题 | 检索请求体 |
| `{{ top_k }}` | 检索设置里的 Top K | 检索请求体 |
| `{{ similarity_threshold }}` | 检索设置里的 Similarity Threshold | 检索请求体 |
| `{{ dataset_id }}` | 创建知识库时填写的 Dataset ID | endpoint / 请求体 |
| `{{ document_id }}` | 系统在删除文档时提供 | 删除接口路径 / 删除请求体 |

## 什么时候必须填，什么时候可以不填

通常至少要填这些：

- API Base URL
- API Key
- Retrieval Endpoint
- Retrieval Request Body Template
- Results Array Path
- Content Field(s)

以下字段经常需要，但不是所有服务都需要：

- Dataset ID
- Score Field
- ID Field
- Similarity Threshold

以下字段只有启用对应功能才需要：

- Upload Endpoint / File Field Name / Upload Extra Data / Document ID Response Path
- Delete Endpoint / Delete HTTP Method / Delete Request Body Template

## 适合谁用

这个插件适合“我知道目标接口怎么调，但还没专门插件”的情况。

如果你连目标服务的请求体和返回结构都不清楚，建议优先使用专用插件；如果你已经在用 Dify，也建议直接使用 `DifyDatasetsConnector`，配置更少，前端字段也更明确。
