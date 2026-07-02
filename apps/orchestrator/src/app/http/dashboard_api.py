from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class ProjectActionGate:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._in_flight: set[str] = set()

    def acquire(self, project_id: str) -> bool:
        with self._guard:
            if project_id in self._in_flight:
                return False
            self._in_flight.add(project_id)
            return True

    def release(self, project_id: str) -> None:
        with self._guard:
            self._in_flight.discard(project_id)


class DashboardApiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address,
        handler_class,
        summary_service,
        action_adapter,
        gate,
        job_service=None,
        script_editor=None,
        event_store=None,
        settings_service=None,
        settings_tester=None,
    ):
        super().__init__(server_address, handler_class)
        self.summary_service = summary_service
        self.action_adapter = action_adapter
        self.gate = gate
        self.job_service = job_service
        self.script_editor = script_editor
        self.event_store = event_store
        self.settings_service = settings_service
        self.settings_tester = settings_tester


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardApiServer

    def do_GET(self) -> None:
        parts = _path_parts(self.path)
        try:
            if parts == ["api", "health"]:
                self._write_json(200, {"ok": True})
                return
            if parts == ["api", "settings"]:
                self._write_json(200, self._require_settings_service().public_settings())
                return
            if parts == ["api", "projects"]:
                self._write_json(200, {"projects": self.server.summary_service.list_projects()})
                return
            if parts == ["api", "jobs"]:
                query = urlparse(self.path).query
                project_id = None
                if query:
                    for item in query.split("&"):
                        key, _, value = item.partition("=")
                        if key == "projectId":
                            project_id = value
                            break
                self._write_json(200, {"jobs": self._require_job_service().list_jobs(project_id)})
                return
            if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                self._write_json(200, {"job": self._require_job_service().get_job(parts[2])})
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "script":
                self._write_json(200, self._require_script_editor().read(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "events":
                self._write_json(200, {"events": self._require_event_store().list_events(parts[2])})
                return
            if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                self._write_json(200, self.server.summary_service.get_project(parts[2]))
                return
            self._write_json(404, {"ok": False, "error": "Not found."})
        except KeyError:
            self._write_json(404, {"ok": False, "error": "Project not found."})
        except FileNotFoundError:
            self._write_json(404, {"ok": False, "error": "Project not found."})
        except ValueError as error:
            self._write_json(400, {"ok": False, "error": str(error)})

    def do_PUT(self) -> None:
        parts = _path_parts(self.path)
        try:
            if parts != ["api", "settings"]:
                if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "script":
                    body = self._read_json_body(require_json=True)
                    active_job = _active_job_for_project(self._require_job_service(), parts[2])
                    if active_job is not None:
                        self._write_json(409, {"ok": False, "error": "active job", "job": active_job})
                        return
                    revision = body.get("revision")
                    scenes = body.get("scenes")
                    if not isinstance(revision, str):
                        raise ValueError("revision must be a string")
                    if not isinstance(scenes, list):
                        raise ValueError("scenes must be a list")
                    self._write_json(200, self._require_script_editor().update(parts[2], revision, scenes))
                    return
                self._write_json(404, {"ok": False, "error": "Not found."})
                return
            body = self._read_json_body(require_json=True)
            self._write_json(200, self._require_settings_service().update(body))
        except ValueError as error:
            self._write_json(400, {"ok": False, "error": str(error)})

    def do_POST(self) -> None:
        parts = _path_parts(self.path)
        if parts == ["api", "settings", "test"]:
            try:
                body = self._read_json_body(require_json=True)
                provider = body.get("provider")
                if provider not in {"gemini", "cloudflare"}:
                    raise ValueError("provider must be one of: cloudflare, gemini")
                self._write_json(200, self._require_settings_tester().test(provider))
            except ValueError as error:
                self._write_json(400, {"ok": False, "error": str(error)})
            return
        if parts == ["api", "projects"]:
            try:
                body = self._read_json_body(require_json=True)
                self._write_json(201, self.server.summary_service.create_project(body))
            except ValueError as error:
                self._write_json(400, {"ok": False, "error": str(error)})
            return
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "copy":
            try:
                self._read_json_body(require_json=True)
                self._write_json(201, self.server.summary_service.copy_project(parts[2]))
            except KeyError:
                self._write_json(404, {"ok": False, "error": "Project not found."})
            except ValueError as error:
                self._write_json(400, {"ok": False, "error": str(error)})
            return
        if len(parts) != 4 or parts[:2] != ["api", "projects"]:
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
                try:
                    self._write_json(200, {"job": self._require_job_service().cancel_job(parts[2])})
                except KeyError:
                    self._write_json(404, {"ok": False, "error": "Job not found."})
                except ValueError as error:
                    self._write_json(400, {"ok": False, "error": str(error)})
                return
            self._write_json(404, {"ok": False, "error": "Not found."})
            return

        project_id = parts[2]
        action = parts[3]

        try:
            if action == "run":
                payload = {"job": self._require_job_service().enqueue(project_id, "run")}
                self._write_json(202, payload)
                return
            elif action == "resume":
                payload = {"job": self._require_job_service().enqueue(project_id, "resume")}
                self._write_json(202, payload)
                return
            elif action in {"approve-script", "approve-final"}:
                if not self.server.gate.acquire(project_id):
                    self._write_json(409, {"ok": False, "error": f"Action already running for {project_id}."})
                    return
                body = self._read_json_body()
                approved = body.get("approved")
                if not isinstance(approved, bool):
                    raise ValueError("approved must be a boolean")
                reviewer = body.get("reviewer", "human")
                if not isinstance(reviewer, str):
                    raise ValueError("reviewer must be a string")
                if len(reviewer.strip() or "human") > 64:
                    raise ValueError("reviewer must be at most 64 characters")
                stage = "script" if action == "approve-script" else "final"
                if stage == "script":
                    active_job = _active_job_for_project(self._require_job_service(), project_id)
                    if active_job is not None:
                        self._write_json(409, {"ok": False, "error": "active job", "job": active_job})
                        return
                    revision = body.get("revision")
                    if not isinstance(revision, str):
                        raise ValueError("revision must be a string")
                    current = self._require_script_editor().read(project_id)
                    if revision != current.get("revision"):
                        self._write_json(409, {"ok": False, "error": "revision conflict", "revision": current.get("revision")})
                        return
                payload = self.server.action_adapter.approve(stage, project_id, approved, reviewer)
            else:
                self._write_json(404, {"ok": False, "error": "Not found."})
                return
            self._write_json(200, payload)
        except ValueError as error:
            if str(error) == "active job":
                active_job = None
                for job in self._require_job_service().list_jobs(project_id):
                    if job.get("status") in {"queued", "running", "cancelling"}:
                        active_job = job
                        break
                self._write_json(409, {"ok": False, "error": str(error), "job": active_job})
                return
            self._write_json(400, {"ok": False, "error": str(error)})
        except KeyError:
            self._write_json(404, {"ok": False, "error": "Project not found."})
        except FileNotFoundError:
            self._write_json(404, {"ok": False, "error": "Project not found."})
        finally:
            if action in {"approve-script", "approve-final"}:
                self.server.gate.release(project_id)

    def do_DELETE(self) -> None:
        parts = _path_parts(self.path)
        try:
            if len(parts) != 3 or parts[:2] != ["api", "projects"]:
                self._write_json(404, {"ok": False, "error": "Not found."})
                return
            body = self._read_json_body(require_json=True)
            confirm_project_id = body.get("confirmProjectId")
            if not isinstance(confirm_project_id, str):
                raise ValueError("confirmProjectId must be a string")
            self._write_json(
                200,
                self.server.summary_service.delete_project(
                    parts[2],
                    confirm_project_id=confirm_project_id,
                ),
            )
        except KeyError:
            self._write_json(404, {"ok": False, "error": "Project not found."})
        except ValueError as error:
            self._write_json(400, {"ok": False, "error": str(error)})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _read_json_body(self, *, require_json: bool = False) -> dict[str, object]:
        if require_json and not self._is_json_request():
            raise ValueError("Content-Type must be application/json")
        length = int(self.headers.get("Content-Length", "0"))
        if length > 65536:
            raise ValueError("JSON body must be 65536 bytes or smaller")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid JSON body") from error
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _is_json_request(self) -> bool:
        content_type = self.headers.get("Content-Type", "")
        return content_type.split(";", 1)[0].strip().lower() == "application/json"

    def _require_settings_service(self):
        if self.server.settings_service is None:
            raise ValueError("settings service is not configured")
        return self.server.settings_service

    def _require_settings_tester(self):
        if self.server.settings_tester is None:
            raise ValueError("settings tester is not configured")
        return self.server.settings_tester

    def _require_job_service(self):
        if self.server.job_service is None:
            raise ValueError("job service is not configured")
        return self.server.job_service

    def _require_script_editor(self):
        if self.server.script_editor is None:
            raise ValueError("script editor is not configured")
        return self.server.script_editor

    def _require_event_store(self):
        if self.server.event_store is None:
            raise ValueError("event store is not configured")
        return self.server.event_store

    def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_dashboard_api_server(
    summary_service,
    action_adapter,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    gate: ProjectActionGate | None = None,
    job_service=None,
    script_editor=None,
    event_store=None,
    settings_service=None,
    settings_tester=None,
):
    return DashboardApiServer(
        (host, port),
        DashboardRequestHandler,
        summary_service,
        action_adapter,
        gate or ProjectActionGate(),
        job_service=job_service,
        script_editor=script_editor,
        event_store=event_store,
        settings_service=settings_service,
        settings_tester=settings_tester,
    )


def serve_dashboard_api(
    summary_service,
    action_adapter,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    gate: ProjectActionGate | None = None,
    job_service=None,
    script_editor=None,
    event_store=None,
    settings_service=None,
    settings_tester=None,
) -> int:
    server = create_dashboard_api_server(
        summary_service,
        action_adapter,
        host=host,
        port=port,
        gate=gate,
        job_service=job_service,
        script_editor=script_editor,
        event_store=event_store,
        settings_service=settings_service,
        settings_tester=settings_tester,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def _path_parts(path: str) -> list[str]:
    return [part for part in urlparse(path).path.split("/") if part]


def _active_job_for_project(job_service, project_id: str):
    for job in job_service.list_jobs(project_id):
        if job.get("status") in {"queued", "running", "cancelling"}:
            return job
    return None
