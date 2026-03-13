from __future__ import annotations

import json
import logging
import re
from typing import Any

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
_SPLIT_PATTERN = re.compile(r"[\n,]+")


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


def _truncate(value: Any, limit: int = 500) -> str:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, default=str)
    )
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated>"


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if any(secret in lowered for secret in ("authorization", "api-key", "token", "secret", "key")):
            if not value:
                sanitized[key] = value
            elif " " in value:
                prefix, _, tail = value.partition(" ")
                sanitized[key] = f"{prefix} ***{tail[-4:]}" if tail else f"{prefix} ***"
            else:
                sanitized[key] = f"***{value[-4:]}"
        else:
            sanitized[key] = value
    return sanitized


def _parse_mapping(mapping_raw: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for part in _SPLIT_PATTERN.split(mapping_raw or ""):
        item = part.strip()
        if not item:
            continue
        if "=" in item:
            key, path = item.split("=", 1)
            key = key.strip()
            path = path.strip()
        else:
            path = item
            key = path.split(".")[-1].strip()
        if key and path:
            mapping[key] = path
    return mapping


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, default=str)


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
    def _is_debug(config: dict) -> bool:
        return bool(config.get("debug_mode", False))

    @staticmethod
    def _timeout(config: dict, default: float) -> float:
        raw = config.get("request_timeout_seconds", default)
        try:
            return max(float(raw), 1.0)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _verify_ssl(config: dict) -> bool:
        return bool(config.get("verify_ssl", True))

    @classmethod
    def _auth_headers(cls, config: dict) -> dict[str, str]:
        api_key = config.get("api_key", "")
        if not api_key:
            return {}

        header_name = (config.get("auth_header_name", "Authorization") or "Authorization").strip()
        prefix = (config.get("auth_header_prefix", "Bearer") or "").strip()
        header_value = f"{prefix} {api_key}".strip() if prefix else str(api_key)
        return {header_name: header_value}

    @classmethod
    def _extra_headers(cls, config: dict, variables: dict) -> tuple[dict[str, str], str | None]:
        raw = config.get("extra_headers_template", "")
        if not raw or not str(raw).strip():
            return {}, None

        try:
            rendered = _render_template(str(raw), variables)
            payload = json.loads(rendered)
        except json.JSONDecodeError as exc:
            return {}, f"Extra Headers Template is not valid JSON: {exc}"

        if not isinstance(payload, dict):
            return {}, "Extra Headers Template must render to a JSON object."

        headers: dict[str, str] = {}
        for key, value in payload.items():
            if value is None:
                continue
            headers[str(key)] = str(value)
        return headers, None

    @classmethod
    def _build_headers(cls, config: dict, variables: dict, content_type: str | None = None) -> dict[str, str]:
        headers = cls._auth_headers(config)
        extra_headers, extra_headers_error = cls._extra_headers(config, variables)
        if extra_headers_error:
            raise ValueError(extra_headers_error)
        headers.update(extra_headers)
        if content_type:
            headers.setdefault("Content-Type", content_type)
        return headers

    @classmethod
    def _log_debug(cls, config: dict, message: str, **details: Any) -> None:
        if not cls._is_debug(config):
            return
        serialized = ", ".join(
            f"{key}={_truncate(value, 800)}" for key, value in details.items()
        )
        logger.info(
            f"[HttpRAG][debug] {message}" + (f": {serialized}" if serialized else "")
        )

    @staticmethod
    def _render_json_template(
        template: str,
        variables: dict,
        *,
        template_name: str,
        require_object: bool = False,
    ) -> Any:
        rendered = _render_template(template, variables)
        try:
            payload = json.loads(rendered)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{template_name} is not valid JSON after variable substitution: {exc}. "
                f"Rendered preview: {_truncate(rendered, 300)}"
            ) from exc
        if require_object and not isinstance(payload, dict):
            raise ValueError(f"{template_name} must render to a JSON object.")
        return payload

    @staticmethod
    def _build_metadata(item: dict, metadata_mapping_raw: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key, path in _parse_mapping(metadata_mapping_raw).items():
            value = _extract_by_path(item, path)
            if value is not None:
                metadata[key] = value
        return metadata

    @staticmethod
    def _response_shape_hint(data: Any) -> str:
        if isinstance(data, dict):
            return f"dict keys={list(data.keys())[:20]}"
        if isinstance(data, list):
            return f"list length={len(data)}"
        return type(data).__name__

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
            "auth_header_name",
            "auth_header_prefix",
            "extra_headers_template",
            "debug_mode",
            "verify_ssl",
            "request_timeout_seconds",
            "retrieve_endpoint",
            "retrieve_method",
            "retrieve_payload_mode",
            "retrieve_body_template",
            "retrieve_results_path",
            "retrieve_content_fields",
            "retrieve_score_field",
            "retrieve_id_field",
            "retrieve_metadata_fields",
            "retrieve_skip_empty_content",
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
        endpoint = retrieval.get("retrieve_endpoint", "")
        method = (retrieval.get("retrieve_method", "POST") or "POST").upper()
        payload_mode = (retrieval.get("retrieve_payload_mode", "json") or "json").lower()
        body_template = retrieval.get("retrieve_body_template", "")
        if not body_template or not body_template.strip():
            body_template = '{"query": "{{ query }}", "top_k": {{ top_k }}}'
        results_path = retrieval.get("retrieve_results_path", "")
        content_fields_raw = retrieval.get("retrieve_content_fields", "content")
        score_field = retrieval.get("retrieve_score_field", "")
        id_field = retrieval.get("retrieve_id_field", "")
        metadata_fields_raw = retrieval.get("retrieve_metadata_fields", "")
        skip_empty_content = bool(retrieval.get("retrieve_skip_empty_content", True))

        if not api_base_url or not endpoint:
            logger.error(
                "[HttpRAG] Missing required retrieval configuration: "
                "api_base_url and retrieve_endpoint are required."
            )
            return RetrievalResponse(results=[], total_found=0)
        if not content_fields_raw or not str(content_fields_raw).strip():
            logger.error("[HttpRAG] Missing required retrieval configuration: retrieve_content_fields")
            return RetrievalResponse(results=[], total_found=0)
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            logger.error(f"[HttpRAG] Unsupported retrieve_method '{method}'")
            return RetrievalResponse(results=[], total_found=0)
        if payload_mode not in {"json", "form", "query"}:
            logger.error(f"[HttpRAG] Unsupported retrieve_payload_mode '{payload_mode}'")
            return RetrievalResponse(results=[], total_found=0)

        variables = self._build_variables(config, retrieval, query=context.query)

        # Render endpoint (may contain {{ dataset_id }} etc.)
        rendered_endpoint = _render_template(endpoint, variables)
        url = f"{api_base_url}{rendered_endpoint}"

        # Render request body
        try:
            payload = self._render_json_template(
                body_template,
                variables,
                template_name="Retrieval Request Body Template",
                require_object=payload_mode in {"form", "query"},
            )
        except ValueError as exc:
            logger.error(f"[HttpRAG] {exc}")
            return RetrievalResponse(results=[], total_found=0)

        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "timeout": self._timeout(config, 30.0),
        }
        try:
            if payload_mode == "json":
                headers = self._build_headers(config, variables, "application/json")
                request_kwargs["json"] = payload
            elif payload_mode == "form":
                headers = self._build_headers(config, variables)
                request_kwargs["data"] = {
                    str(key): _stringify_value(value)
                    for key, value in payload.items()
                }
            else:
                headers = self._build_headers(config, variables)
                request_kwargs["params"] = {
                    str(key): _stringify_value(value)
                    for key, value in payload.items()
                }
            request_kwargs["headers"] = headers
        except ValueError as exc:
            logger.error(f"[HttpRAG] {exc}")
            return RetrievalResponse(results=[], total_found=0)

        self._log_debug(
            config,
            "retrieve request",
            query=context.query,
            method=method,
            payload_mode=payload_mode,
            url=url,
            headers=_sanitize_headers(headers),
            payload=payload,
        )

        results: list[RetrievalResultEntry] = []
        first_result_preview: str | None = None
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl(config)) as client:
                response = await client.request(**request_kwargs)
                response.raise_for_status()
                try:
                    data = response.json()
                except json.JSONDecodeError as exc:
                    logger.error(
                        f"[HttpRAG] Retrieval response from {url} is not valid JSON: {exc}. "
                        f"Response preview: {_truncate(response.text, 500)}"
                    )
                    return RetrievalResponse(results=[], total_found=0)

            self._log_debug(
                config,
                "retrieve response",
                status_code=response.status_code,
                response_shape=self._response_shape_hint(data),
                response_preview=data,
            )

            # Extract results array
            items = _extract_by_path(data, results_path)
            if not isinstance(items, list):
                logger.warning(
                    f"[HttpRAG] results_path '{results_path}' did not resolve to a list "
                    f"(got {type(items).__name__}); response shape: {self._response_shape_hint(data)}"
                )
                return RetrievalResponse(results=[], total_found=0)

            content_fields = [f.strip() for f in content_fields_raw.split(",") if f.strip()]
            if not content_fields:
                logger.error("[HttpRAG] retrieve_content_fields did not contain any valid field path.")
                return RetrievalResponse(results=[], total_found=0)

            for item in items:
                if not isinstance(item, dict):
                    logger.warning(
                        f"[HttpRAG] Retrieved item is not an object; skipped item type={type(item).__name__}"
                    )
                    continue

                # content
                parts = []
                for cf in content_fields:
                    val = _extract_by_path(item, cf)
                    if val:
                        parts.append(str(val))
                content_text = "\n".join(parts) if parts else ""
                if skip_empty_content and not content_text.strip():
                    self._log_debug(
                        config,
                        "skip empty retrieval item",
                        item_preview=item,
                    )
                    continue

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

                metadata = self._build_metadata(item, metadata_fields_raw)
                results.append(
                    RetrievalResultEntry(
                        id=item_id,
                        content=[ContentElement.from_text(content_text)],
                        metadata=metadata,
                        distance=1.0 - score,
                        score=score,
                    )
                )
                if first_result_preview is None:
                    first_result_preview = content_text

            logger.info(f"[HttpRAG] Retrieved {len(results)} results from {url}")
            if results:
                first = results[0]
                self._log_debug(
                    config,
                    "retrieve mapped first result",
                    id=first.id,
                    score=first.score,
                    metadata=first.metadata,
                    content_preview=first_result_preview,
                )

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[HttpRAG] HTTP {e.response.status_code} from {url}: "
                f"{e.response.text[:500]}"
            )
        except httpx.HTTPError as e:
            logger.error(f"[HttpRAG] HTTP client error during retrieval from {url}: {repr(e)}")
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

        try:
            headers = self._build_headers(config, variables)
        except ValueError as exc:
            return IngestionResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_message=str(exc),
            )
        files = {file_field: (filename, file_bytes)}
        form_data: dict = {}

        if extra_body and extra_body.strip():
            try:
                rendered_extra = _render_template(extra_body, variables)
                form_data["data"] = rendered_extra
            except Exception as e:
                logger.warning(f"[HttpRAG] Failed to render upload extra data: {e}")

        self._log_debug(
            config,
            "ingest request",
            url=url,
            headers=_sanitize_headers(headers),
            file_field=file_field,
            filename=filename,
            form_data=form_data,
        )

        try:
            async with httpx.AsyncClient(verify=self._verify_ssl(config)) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    files=files,
                    data=form_data,
                    timeout=max(self._timeout(config, 30.0), 120.0),
                )
                response.raise_for_status()
                try:
                    resp_data = response.json()
                except json.JSONDecodeError as exc:
                    error_message = (
                        f"Upload response is not valid JSON: {exc}. "
                        f"Response preview: {_truncate(response.text, 300)}"
                    )
                    logger.error(f"[HttpRAG] {error_message}")
                    return IngestionResult(
                        document_id=doc_id,
                        status=DocumentStatus.FAILED,
                        error_message=error_message,
                    )

            self._log_debug(
                config,
                "ingest response",
                status_code=response.status_code,
                response_shape=self._response_shape_hint(resp_data),
                response_preview=resp_data,
            )

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
        except httpx.HTTPError as e:
            logger.error(f"[HttpRAG] Upload HTTP client error for {filename}: {repr(e)}")
            return IngestionResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_message=repr(e),
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

        try:
            payload = None
            if body_template and body_template.strip():
                payload = self._render_json_template(
                    body_template,
                    variables,
                    template_name="Delete Request Body Template",
                )

            headers = self._build_headers(config, variables, "application/json")
            self._log_debug(
                config,
                "delete request",
                method=method,
                url=url,
                headers=_sanitize_headers(headers),
                payload=payload,
            )

            async with httpx.AsyncClient(verify=self._verify_ssl(config)) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout(config, 30.0),
                )
                response.raise_for_status()

            self._log_debug(
                config,
                "delete response",
                status_code=response.status_code,
            )

            logger.info(f"[HttpRAG] Document {document_id} deleted from kb {kb_id}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[HttpRAG] Delete failed: HTTP {e.response.status_code}: "
                f"{e.response.text[:500]}"
            )
            return False
        except httpx.HTTPError as e:
            logger.error(f"[HttpRAG] Delete HTTP client error for document {document_id}: {repr(e)}")
            return False
        except Exception:
            logger.exception(f"[HttpRAG] Error deleting document {document_id}")
            return False
