"""Stdlib-only local HTTP bridge for the workflow console static UI."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ai_native_cad.pipeline.runner import PROJECT_ROOT
from ai_native_cad.workflow_console.backend import DOWNLOADABLE_FILES, WorkflowConsoleBackend
from ai_native_cad.workflow_console.routes import dispatch_route, error_response

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_ROOT = PROJECT_ROOT / "web-viewer"


def make_handler(
    backend: WorkflowConsoleBackend | None = None,
    static_root: str | Path | None = None,
) -> type[SimpleHTTPRequestHandler]:
    """Create a request handler bound to one backend instance."""
    console_backend = backend or WorkflowConsoleBackend(restore_saved_provider=True)
    web_root = Path(static_root or STATIC_ROOT).resolve()

    class WorkflowConsoleRequestHandler(SimpleHTTPRequestHandler):
        """Serve static UI files and a narrow JSON route bridge."""

        server_version = "CadFlowWorkflowConsole/0.1"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(web_root), **kwargs)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_response(302)
                self.send_header("Location", "/workflow-console.html")
                self.end_headers()
                return
            if parsed.path.startswith("/api/downloads/"):
                self._handle_download(parsed.path, parsed.query)
                return
            if parsed.path.startswith("/api/"):
                self._handle_api_get(parsed.path, parsed.query)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/actions/"):
                self._handle_api_action(parsed.path, parsed.query)
                return
            if parsed.path != "/api/route":
                self._send_json(error_response(FileNotFoundError("workflow console API route not found")))
                return
            try:
                request = self._read_json_body()
                response = dispatch_route(
                    console_backend,
                    _require_string(request, "route"),
                    path_params=_optional_dict(request, "path_params"),
                    body=_optional_dict(request, "body"),
                    query=_optional_dict(request, "query"),
                )
            except Exception as exc:
                response = error_response(exc)
            self._send_json(response)

        def _handle_api_get(self, path: str, query_string: str) -> None:
            parts = [unquote(part) for part in path.split("/") if part]
            query = _single_value_query(query_string)
            try:
                if parts == ["api", "runs"]:
                    response = dispatch_route(console_backend, "list_runs", query=query)
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "summary":
                    response = dispatch_route(
                        console_backend,
                        "read_run_metadata",
                        path_params={"run_id": parts[2]},
                        query=query,
                    )
                elif len(parts) >= 5 and parts[:2] == ["api", "runs"] and parts[3] == "artifacts":
                    response = dispatch_route(
                        console_backend,
                        "read_artifact",
                        path_params={"run_id": parts[2], "artifact": "/".join(parts[4:])},
                        query=query,
                    )
                else:
                    response = error_response(FileNotFoundError("workflow console API route not found"))
            except Exception as exc:
                response = error_response(exc)
            self._send_json(response)

        def _handle_api_action(self, path: str, query_string: str) -> None:
            route_name = {
                "/api/actions/part-request": "action_part_request",
                "/api/actions/part-review": "action_part_review",
                "/api/actions/reviewed-handoff": "action_reviewed_handoff",
                "/api/actions/reviewed-part-create": "action_reviewed_part_create",
                "/api/actions/part-result-review": "action_part_result_review",
                "/api/actions/stage-review": "action_save_stage_review",
                "/api/actions/workflow-review": "action_create_workflow_review",
                "/api/actions/rework": "action_run_rework",
                "/api/actions/requirement-clarification": "apply_requirement_clarification",
            }.get(path)
            if route_name is None:
                self._send_json(error_response(FileNotFoundError("workflow console API action not found")))
                return
            try:
                response = dispatch_route(
                    console_backend,
                    route_name,
                    body=self._read_json_body(),
                    query=_single_value_query(query_string),
                )
            except Exception as exc:
                response = error_response(exc)
            self._send_json(response)

        def _handle_download(self, path: str, query_string: str) -> None:
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) != 4:
                self._send_json(error_response(FileNotFoundError("workflow console downloadable not found")))
                return
            _, _, run_id, filename = parts
            query = parse_qs(query_string)
            root = query.get("root", [None])[0]
            try:
                file_path = resolve_downloadable(console_backend, run_id, filename, root=root)
            except Exception as exc:
                self._send_json(error_response(exc))
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
            self.end_headers()
            with file_path.open("rb") as handle:
                self.copyfile(handle, self.wfile)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("workflow console API request body must be a JSON object")
            return value

        def _send_json(self, response: dict[str, Any]) -> None:
            payload = json.dumps(response, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(int(response.get("status_code", 200)))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return WorkflowConsoleRequestHandler


def resolve_downloadable(
    backend: WorkflowConsoleBackend,
    run_id: str,
    filename: str,
    root: str | Path | None = None,
) -> Path:
    """Resolve a whitelisted downloadable file for local HTTP serving."""
    if filename not in DOWNLOADABLE_FILES:
        raise ValueError(f"workflow console downloadable is not allowed: {filename}")
    run_dir = backend.resolve_run(run_id, root=root)
    file_path = backend._require_child_path(run_dir, filename)
    if not file_path.exists():
        raise FileNotFoundError(f"workflow console downloadable not found: {filename}")
    return file_path


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Run the local workflow console server."""
    handler = make_handler()
    server = ThreadingHTTPServer((host, port), handler)
    print(f"CadFlow workflow console: http://{host}:{port}/workflow-console.html")
    server.serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local CadFlow workflow console.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Bind port. Defaults to 8765.")
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)


def _require_string(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"workflow console API request is missing string value: {key}")
    return value


def _optional_dict(values: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"workflow console API request {key} must be a JSON object")
    return value


def _single_value_query(query_string: str) -> dict[str, str]:
    query = parse_qs(query_string)
    return {key: values[0] for key, values in query.items() if values}


if __name__ == "__main__":
    main()
