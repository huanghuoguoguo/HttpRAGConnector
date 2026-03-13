# HttpRAGConnector

Generic HTTP RAG connector. Connect any knowledge base service with an HTTP API to LangBot.

If you are connecting to common platforms like Dify, RAGFlow, or FastGPT, **use their dedicated plugins first**. Use this plugin only when no dedicated plugin is available, or when you need to connect a custom HTTP retrieval endpoint.

## Quick Start

You only need to fill in **3 fields** to get started:

| Field | What to fill | Example |
|-------|-------------|---------|
| API Base URL | Base URL of your RAG service | `https://your-rag.com/api/v1` |
| Retrieval Endpoint | Path to the retrieval API | `/search` |
| API Key | Authentication key (leave empty if not needed) | `sk-xxx` |

All other fields have sensible defaults:

- **Request Body Template** left empty → automatically sends `{"query": "user question", "top_k": 5}`
- **Results Array Path** defaults to `results`
- **Content Field(s)** defaults to `content`
- **Score Field** defaults to `score`
- **ID Field** defaults to `id`

If your API response format matches these defaults, everything works out of the box.

## How It Works

You tell the plugin two things:

1. **Request**: Which HTTP endpoint to call and what the request body looks like
2. **Response**: Where to find the results array, text content, score, and ID in the response

The plugin automatically fills in the user's query and retrieval parameters, then converts the response into knowledge segments usable by LangBot.

## Field Reference

### Creation Settings

#### API Base URL (required)

Base URL of the target service. Only the domain and path prefix — do not include specific endpoint paths.

```
https://your-rag-service.com/api/v1
```

#### API Key

Authentication key. Sent as `Authorization: Bearer <key>` by default. Leave empty if no authentication is needed.

#### Dataset ID

Dataset/knowledge base ID. If your endpoint path or request body uses `{{ dataset_id }}`, it will be replaced with this value at runtime. Leave empty if not needed.

### Retrieval Settings

#### Retrieval Endpoint (required)

Path to the retrieval endpoint. The final request URL = API Base URL + this path. Supports the `{{ dataset_id }}` variable.

```
/search
/datasets/{{ dataset_id }}/retrieve
/api/query
```

#### Request Body Template

JSON template for the retrieval request. Supports the following variables:

| Variable | Source |
|----------|--------|
| `{{ query }}` | User's current question |
| `{{ top_k }}` | Number of results from retrieval settings |
| `{{ similarity_threshold }}` | Similarity threshold from retrieval settings |
| `{{ dataset_id }}` | Dataset ID from creation settings |

**If left empty, defaults to**: `{"query": "{{ query }}", "top_k": {{ top_k }}}`

Custom example:

```json
{
  "query": "{{ query }}",
  "limit": {{ top_k }},
  "min_score": {{ similarity_threshold }},
  "collection": "{{ dataset_id }}"
}
```

Note: String variables need quotes (`"{{ query }}"`), numeric variables do not (`{{ top_k }}`).

#### Results Array Path (required)

Location of the results array in the response JSON. Use dot-separated paths.

| Your response structure | Value to enter |
|---|---|
| `{"results": [...]}` | `results` |
| `{"data": {"records": [...]}}` | `data.records` |
| `{"hits": {"hits": [...]}}` | `hits.hits` |

#### Content Field(s) (required)

Field(s) containing the text content in each result. Supports dot-separated paths. Multiple fields can be separated by commas and will be concatenated.

| Your result structure | Value to enter |
|---|---|
| `{"content": "..."}` | `content` |
| `{"segment": {"content": "..."}}` | `segment.content` |
| `{"question": "...", "answer": "..."}` | `question,answer` |

#### Score Field / ID Field

Fields for score and ID. Leave empty if not applicable.

#### Top K / Similarity Threshold

Number of results and similarity threshold. These replace `{{ top_k }}` and `{{ similarity_threshold }}` in the template.

### Advanced Connection Settings

Click "Show Advanced Connection Settings" to expand. In most cases, no changes are needed.

| Field | Purpose | When to change |
|-------|---------|----------------|
| Auth Header Name | Auth header name (default: `Authorization`) | Service requires `X-API-Key` or other custom headers |
| Auth Header Prefix | Auth header prefix (default: `Bearer`) | Service requires a bare token (leave empty) or other prefix |
| Extra Headers (JSON) | Additional request headers | Multi-tenancy, version headers, custom trace headers |
| Verify SSL | SSL certificate verification (default: on) | Self-signed certificates on internal networks |
| Request Timeout | Request timeout (default: 30s) | Slow-responding services |
| Debug Mode | Debug logging (default: off) | Initial integration or troubleshooting |

### Advanced Retrieval Settings

Click "Show Advanced Retrieval Settings" to expand. In most cases, no changes are needed.

| Field | Purpose | When to change |
|-------|---------|----------------|
| HTTP Method | Retrieval request method (default: `POST`) | API requires `GET` or other methods |
| Payload Mode | Request delivery method (default: JSON body) | API requires form submission or query params |
| Metadata Field Mapping | Additional return fields | Need source, page number, URL, etc. |
| Skip Empty Content | Skip empty content (default: on) | Recommended to keep enabled for all scenarios |

### File Upload / Document Deletion

Enable the corresponding toggles first, then fill in your API information as prompted.

## Example Configurations

### Simplest API

API accepts `POST {"query": "...", "top_k": N}` and returns `{"results": [{"content": "...", "score": 0.9, "id": "1"}]}`.

Just fill in:
- **API Base URL**: `https://my-rag.com`
- **Retrieval Endpoint**: `/search`
- Leave everything else empty/default

### Dify

- **API Base URL**: `https://api.dify.ai/v1`
- **API Key**: Your Dify Dataset API Key
- **Dataset ID**: Dataset ID from the Dify console
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

### GET Request Search API

API uses `GET /search?q=xxx&limit=5` and returns `{"data": [{"text": "...", "relevance": 0.8}]}`.

- **API Base URL**: `https://my-search.com`
- **Retrieval Endpoint**: `/search`
- **Request Body Template**: `{"q": "{{ query }}", "limit": {{ top_k }}}`
- **Results Array Path**: `data`
- **Content Field(s)**: `text`
- **Score Field**: `relevance`
- Open "Advanced Retrieval Settings" → **HTTP Method**: `GET`, **Payload Mode**: `Query Params`

## Troubleshooting

1. Open "Advanced Connection Settings" → enable **Debug Mode**
2. Check that the final URL, method, and payload in the logs match your expectations
3. Verify that the results_path points to an array in the response
4. Verify that content_fields, score_field, and id_field match the actual field names
5. For internal HTTPS services, check whether you need to disable Verify SSL
