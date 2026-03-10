# HttpRAGConnector

A generic HTTP RAG connector for any RAG service that exposes an HTTP API.

> **Note**: This plugin is a temporary solution for RAG services that do not yet have a dedicated connector plugin. For the best experience, we recommend using (or developing) a connector plugin tailored to your specific RAG service (e.g., RAGFlowConnector, DifyDatasetsConnector, FastGPTConnector). Dedicated connectors can leverage service-specific features and provide a better configuration experience.

## How It Works

Instead of writing code for each RAG service, this plugin lets you describe how to call the service's HTTP API through configuration:

1. **Request template** — Write a JSON body template with `{{ variable }}` placeholders (e.g., `{{ query }}`, `{{ top_k }}`)
2. **Response mapping** — Specify dot-separated paths to extract the results array, content field, score field, etc. from the response

## Configuration

### Connection Settings

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| API Base URL | string | Yes | Base URL of the RAG service (e.g., `http://localhost:8080`) |
| API Key | password | Yes | API key for authentication |
| Auth Header Prefix | string | No | Prefix in Authorization header (default: `Bearer`) |
| Dataset ID | string | No | Dataset/knowledge base ID, available as `{{ dataset_id }}` in templates |

### Retrieval Settings

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| Retrieval Endpoint | string | Yes | API path (e.g., `/api/v1/retrieval`), supports `{{ dataset_id }}` |
| Request Body Template | text | Yes | JSON template with `{{ variable }}` placeholders |
| Results Array Path | string | Yes | Dot path to results array in response (e.g., `data.chunks`) |
| Content Field(s) | string | Yes | Field name(s) for text content, comma-separated (e.g., `content` or `q,a`) |
| Score Field | string | No | Field name for similarity score (e.g., `similarity`) |
| ID Field | string | No | Field name for result ID (e.g., `id`) |

### Per-Query Settings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| Top K | integer | 5 | Max results to return (available as `{{ top_k }}` in template) |
| Similarity Threshold | float | 0.2 | Min similarity score (available as `{{ similarity_threshold }}` in template) |

### File Upload (Optional)

Enable "Enable File Upload" to show these fields:

| Field | Type | Description |
|-------|------|-------------|
| Upload Endpoint | string | API path for file upload, supports `{{ dataset_id }}` |
| File Field Name | string | Multipart form field name (default: `file`) |
| Upload Extra Data | text | Optional JSON data sent alongside the file |
| Document ID Response Path | string | Dot path to extract document ID from response |

### Document Deletion (Optional)

Enable "Enable Document Deletion" to show these fields:

| Field | Type | Description |
|-------|------|-------------|
| Delete Endpoint | string | API path, supports `{{ document_id }}` and `{{ dataset_id }}` |
| Delete HTTP Method | select | `DELETE` or `POST` |
| Delete Request Body Template | text | Optional JSON body template |

## Template Variables

| Variable | Available In | Source |
|----------|-------------|--------|
| `{{ query }}` | Retrieval | User's search query |
| `{{ top_k }}` | Retrieval | Per-query setting |
| `{{ similarity_threshold }}` | Retrieval | Per-query setting |
| `{{ dataset_id }}` | All | Creation setting |
| `{{ document_id }}` | Deletion | System-provided |

## Example: Connecting to a RAGFlow-like Service

**Retrieval Endpoint**: `/api/v1/retrieval`

**Request Body Template**:
```json
{
  "question": "{{ query }}",
  "dataset_ids": ["your-dataset-id-here"],
  "top_k": {{ top_k }},
  "similarity_threshold": {{ similarity_threshold }}
}
```

**Results Array Path**: `data.chunks`

**Content Field(s)**: `content`

**Score Field**: `similarity`

**ID Field**: `id`
