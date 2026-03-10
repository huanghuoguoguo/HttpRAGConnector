from __future__ import annotations

import json
import logging
import re

import httpx

from langbot_plugin.api.definition.components.knowledge_engine.engine import (
    KnowledgeEngine,
    KnowledgeEngineCapability,
)
from langbot_plugin.api.entities.builtin.rag.context import (
    RetrievalContext,
    RetrievalResponse,
    RetrievalResultEntry,
)
from langbot_plugin.api.entities.builtin.rag.models import (
    IngestionContext,
    IngestionResult,
)
from langbot_plugin.api.entities.builtin.rag.enums import DocumentStatus
from langbot_plugin.api.entities.builtin.provider.message import ContentElement

logger = logging.getLogger(__name__)

# Matches {{ variable_name }} with optional whitespace
_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _render_template(template: str, variables: dict) -> str:
    """Replace {{ var }} placeholders in a template string.

    String values are JSON-escaped (without surrounding quotes) so they
    can be placed inside JSON string literals.  Numbers and booleans are
    emitted as raw JSON tokens.
    """

    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        if name not in variables:
            return match.group(0)
        value = variables[name]
        if isinstance(value, str):
            return json.dumps(value)[1:-1]  # escaped, no outer quotes
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return json.dumps(value)

    return _VAR_PATTERN.sub(_replacer, template)


def _extract_by_path(data, path: str):
    """Extract a value from nested dicts/lists using a dot-separated path.

    Examples:
        _extract_by_path({"a": {"b": [1, 2]}}, "a.b.0")  =>  1
        _extract_by_path({"records": [{"score": 0.9}]}, "records")  =>  [...]
    """
    if not path or not path.strip():
        return data
    current = data
    for part in path.strip().split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current


class HttpRag(KnowledgeEngine):
    """Generic HTTP RAG connector.

    Connects to any RAG service that exposes an HTTP API by using
    user-defined request templates and response field mappings.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._kb_configs: dict[str, dict] = {}

    @classmethod
    def get_capabilities(cls) -> list[str]:
        return [
            KnowledgeEngineCapability.DOC_INGESTION,
            KnowledgeEngineCapability.DOC_PARSING,
        ]

    # ── lifecycle ──

    async def on_knowledge_base_create(self, kb_id: str, config: dict) -> None:
        logger.info(f"[HttpRAG] Knowledge base created: {kb_id}")
        self._kb_configs[kb_id] = config

    async def on_knowledge_base_delete(self, kb_id: str) -> None:
        logger.info(f"[HttpRAG] Knowledge base deleted: {kb_id}")
        self._kb_configs.pop(kb_id, None)

    # ── helpers ──

    @staticmethod
    def _auth_headers(config: dict) -> dict[str, str]:
        api_key = config.get("api_key", "")
        prefix = config.get("auth_header_prefix", "Bearer").strip()
        return {"Authorization": f"{prefix} {api_key}"}

    @staticmethod
    def _build_variables(
        config: dict,
        retrieval: dict | None = None,
        **extra,
    ) -> dict:
        """Merge all available values into a flat variable dict for templates."""
        variables: dict = {}
        # creation settings (skip internal connection fields)
        _skip = {
            "api_key",
            "api_base_url",
            "auth_header_prefix",
            "retrieve_endpoint",
            "retrieve_body_template",
            "retrieve_results_path",
            "retrieve_content_fields",
            "retrieve_score_field",
            "retrieve_id_field",
            "enable_ingestion",
            "ingest_endpoint",
            "ingest_file_field",
            "ingest_extra_body",
            "ingest_doc_id_path",
            "enable_deletion",
            "delete_endpoint",
            "delete_method",
            "delete_body_template",
        }
        for key, value in config.items():
            if key not in _skip:
                variables[key] = value
        if retrieval:
            variables.update(retrieval)
        variables.update(extra)
        return variables

    # ── retrieve ──

    async def retrieve(self, context: RetrievalContext) -> RetrievalResponse:
        config = context.creation_settings
        retrieval = context.retrieval_settings

        api_base_url = config.get("api_base_url", "").rstrip("/")
        endpoint = config.get("retrieve_endpoint", "")
        body_template = config.get("retrieve_body_template", "")
        results_path = config.get("retrieve_results_path", "")
        content_fields_raw = config.get("retrieve_content_fields", "content")
        score_field = config.get("retrieve_score_field", "")
        id_field = config.get("retrieve_id_field", "")

        if not api_base_url or not endpoint or not body_template:
            logger.error("[HttpRAG] Missing required retrieval configuration")
            return RetrievalResponse(results=[], total_found=0)

        variables = self._build_variables(config, retrieval, query=context.query)

        # Render endpoint (may contain {{ dataset_id }} etc.)
        rendered_endpoint = _render_template(endpoint, variables)
        url = f"{api_base_url}{rendered_endpoint}"

        # Render request body
        try:
            rendered_body = _render_template(body_template, variables)
            payload = json.loads(rendered_body)
        except json.JSONDecodeError as e:
            logger.error(f"[HttpRAG] Failed to parse rendered body template as JSON: {e}")
            return RetrievalResponse(results=[], total_found=0)

        headers = {**self._auth_headers(config), "Content-Type": "application/json"}

        results: list[RetrievalResultEntry] = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, json=payload, headers=headers, timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            # Extract results array
            items = _extract_by_path(data, results_path)
            if not isinstance(items, list):
                logger.warning(
                    f"[HttpRAG] results_path '{results_path}' did not resolve to a list "
                    f"(got {type(items).__name__})"
                )
                return RetrievalResponse(results=[], total_found=0)

            content_fields = [f.strip() for f in content_fields_raw.split(",") if f.strip()]

            for item in items:
                # content
                parts = []
                for cf in content_fields:
                    val = _extract_by_path(item, cf)
                    if val:
                        parts.append(str(val))
                content_text = "\n".join(parts) if parts else ""

                # score
                score = 0.0
                if score_field:
                    raw = _extract_by_path(item, score_field)
                    if raw is not None:
                        try:
                            score = float(raw)
                        except (ValueError, TypeError):
                            pass

                # id
                item_id = ""
                if id_field:
                    raw = _extract_by_path(item, id_field)
                    if raw is not None:
                        item_id = str(raw)

                results.append(
                    RetrievalResultEntry(
                        id=item_id,
                        content=[ContentElement.from_text(content_text)],
                        metadata={},
                        distance=1.0 - score,
                        score=score,
                    )
                )

            logger.info(f"[HttpRAG] Retrieved {len(results)} results from {url}")

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[HttpRAG] HTTP {e.response.status_code} from {url}: "
                f"{e.response.text[:500]}"
            )
        except Exception:
            logger.exception("[HttpRAG] Error during retrieval")

        return RetrievalResponse(results=results, total_found=len(results))

    # ── ingest ──

    async def ingest(self, context: IngestionContext) -> IngestionResult:
        doc_id = context.file_object.metadata.document_id
        filename = context.file_object.metadata.filename
        config = context.creation_settings

        if not config.get("enable_ingestion", False):
            return IngestionResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_message="File upload is not enabled for this knowledge base.",
            )

        api_base_url = config.get("api_base_url", "").rstrip("/")
        endpoint = config.get("ingest_endpoint", "")
        file_field = config.get("ingest_file_field", "file") or "file"
        extra_body = config.get("ingest_extra_body", "")
        doc_id_path = config.get("ingest_doc_id_path", "")

        if not api_base_url or not endpoint:
            return IngestionResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_message="Missing upload endpoint configuration.",
            )

        variables = self._build_variables(config, document_id=doc_id)
        rendered_endpoint = _render_template(endpoint, variables)
        url = f"{api_base_url}{rendered_endpoint}"

        # Read file from host
        try:
            file_bytes = await self.plugin.get_knowledge_file_stream(
                context.file_object.storage_path
            )
        except Exception as e:
            logger.error(f"[HttpRAG] Failed to read file: {e}")
            return IngestionResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_message=f"Could not read file: {e}",
            )

        headers = self._auth_headers(config)
        files = {file_field: (filename, file_bytes)}
        form_data: dict = {}

        if extra_body and extra_body.strip():
            try:
                rendered_extra = _render_template(extra_body, variables)
                form_data["data"] = rendered_extra
            except Exception as e:
                logger.warning(f"[HttpRAG] Failed to render upload extra data: {e}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    files=files,
                    data=form_data,
                    timeout=120.0,
                )
                response.raise_for_status()
                resp_data = response.json()

            result_doc_id = doc_id
            if doc_id_path:
                extracted = _extract_by_path(resp_data, doc_id_path)
                if extracted is not None:
                    result_doc_id = str(extracted)

            logger.info(
                f"[HttpRAG] File '{filename}' uploaded (doc_id={result_doc_id})"
            )
            return IngestionResult(
                document_id=result_doc_id,
                status=DocumentStatus.PROCESSING,
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:500]}"
            logger.error(f"[HttpRAG] Upload failed: {error_msg}")
            return IngestionResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_message=error_msg,
            )
        except Exception as e:
            logger.exception(f"[HttpRAG] Upload failed for {filename}")
            return IngestionResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_message=str(e),
            )

    # ── delete ──

    async def delete_document(self, kb_id: str, document_id: str) -> bool:
        config = self._kb_configs.get(kb_id)
        if not config:
            logger.error(f"[HttpRAG] No cached config for kb_id={kb_id}")
            return False

        if not config.get("enable_deletion", False):
            logger.warning(f"[HttpRAG] Deletion not enabled for kb_id={kb_id}")
            return False

        api_base_url = config.get("api_base_url", "").rstrip("/")
        endpoint = config.get("delete_endpoint", "")
        method = config.get("delete_method", "DELETE")
        body_template = config.get("delete_body_template", "")

        if not api_base_url or not endpoint:
            logger.error(f"[HttpRAG] Missing delete endpoint for kb_id={kb_id}")
            return False

        variables = self._build_variables(config, document_id=document_id)
        rendered_endpoint = _render_template(endpoint, variables)
        url = f"{api_base_url}{rendered_endpoint}"

        headers = {**self._auth_headers(config), "Content-Type": "application/json"}

        try:
            payload = None
            if body_template and body_template.strip():
                rendered_body = _render_template(body_template, variables)
                payload = json.loads(rendered_body)

            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method, url, headers=headers, json=payload, timeout=30.0
                )
                response.raise_for_status()

            logger.info(f"[HttpRAG] Document {document_id} deleted from kb {kb_id}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[HttpRAG] Delete failed: HTTP {e.response.status_code}: "
                f"{e.response.text[:500]}"
            )
            return False
        except Exception:
            logger.exception(f"[HttpRAG] Error deleting document {document_id}")
            return False
