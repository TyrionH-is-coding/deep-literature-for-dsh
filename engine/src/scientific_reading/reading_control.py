"""Persistent parent stop intent. Short OS locks never cover a provider call."""
from __future__ import annotations

import copy
import os
import threading
import time
from contextlib import contextmanager

from .background_store import BackgroundJobStore, stable_job_id
from .data_guard import _file_lock, data_root_operation
from .scope import capture_scope, current_scope, ScopeError
from .workspace import atomic_write_json, read_json_file

CONTRACT = "reading-control-v1"
_local = threading.local()


class ReadingControlError(RuntimeError):
    pass


class ReadingControl:
    def __init__(self, store: BackgroundJobStore, job_id: str):
        self.store, self.job_id = store, job_id
        self.path = store.handle(job_id).root / "control.json"

    def authorize(self):
        request = self.store.load_request(self.job_id)
        if request.target_stage != "full_read_pipeline" or stable_job_id(request) != self.job_id:
            raise ReadingControlError("full_read_parent_mismatch")
        scope = capture_scope(self.store.data_root, request.paper_id)
        status = self.store.load_status(self.job_id)
        if current_scope() is not None and status.state != "completed" and status.scope != scope:
            raise ScopeError("scope_job_conflict")
        return request

    @contextmanager
    def lock(self):
        key = os.path.normcase(str(self.path.resolve()))
        held = getattr(_local, "held", set())
        if key in held:
            yield
            return
        with data_root_operation(self.store.data_root), _file_lock(
            key, "reading-control", exclusive=True, deadline=time.monotonic() + 10
        ):
            _local.held = held
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)

    def load(self):
        if not self.path.exists():
            return dict(contract=CONTRACT, parentJobId=self.job_id, revision=0,
                        stopRequested=False, requestId=None, acknowledgedRevision=None,
                        effectiveBoundary=None, activeStage=None, worker=None, operations={})
        try:
            value = read_json_file(self.path)
            required = {"contract", "parentJobId", "revision", "stopRequested", "requestId",
                        "acknowledgedRevision", "effectiveBoundary", "activeStage", "worker", "operations"}
            if (not isinstance(value, dict) or not required <= value.keys()
                or value["contract"] != CONTRACT or value["parentJobId"] != self.job_id
                or type(value["revision"]) is not int or value["revision"] < 0
                or type(value["stopRequested"]) is not bool
                or not isinstance(value["operations"], dict)):
                raise ValueError()
            for owner_key in ("activeStage", "worker"):
                owner = value[owner_key]
                if owner is not None and (not isinstance(owner, dict) or type(owner.get("pid")) is not int
                                          or owner["pid"] <= 0 or not isinstance(owner.get("identity"), (str, type(None)))):
                    raise ValueError()
            for request_id, operation in value["operations"].items():
                if (not isinstance(request_id, str) or not request_id or not isinstance(operation, dict)
                    or operation.get("kind") not in {"stop", "resume"}
                    or type(operation.get("expectedRevision")) is not int
                    or type(operation.get("revision")) is not int
                    or operation["revision"] != operation["expectedRevision"] + 1
                    or not 0 < operation["revision"] <= value["revision"]):
                    raise ValueError()
            revisions = [op["revision"] for op in value["operations"].values()]
            if len(revisions) != value["revision"] or sorted(revisions) != list(range(1, len(revisions) + 1)):
                raise ValueError()
            for operation in value["operations"].values():
                if operation["kind"] == "resume" and (not isinstance(operation.get("input"), dict)
                                                     or type(operation.get("dispatched")) is not bool):
                    raise ValueError()
            ack = value["acknowledgedRevision"]
            if ack is not None and (type(ack) is not int or ack != value["revision"] or not value["stopRequested"]):
                raise ValueError()
            if value["revision"]:
                operation = value["operations"].get(value["requestId"])
                if operation is None or operation["revision"] != value["revision"] or (operation["kind"] == "stop") != value["stopRequested"]:
                    raise ValueError()
            elif value["stopRequested"] or value["requestId"] is not None or value["operations"]:
                raise ValueError()
            if ack is not None and not isinstance(value["effectiveBoundary"], str):
                raise ValueError()
            return value
        except (OSError, TypeError, ValueError, KeyError) as error:
            raise ReadingControlError("reading_control_invalid") from error

    def save(self, value):
        atomic_write_json(self.path, value)

    @staticmethod
    def owner():
        from .background_launcher import process_start_identity
        return dict(pid=os.getpid(), identity=process_start_identity(os.getpid()))

    def alive(self, owner):
        from .background_launcher import process_start_identity
        if not owner or not self.store._pid_is_alive(owner["pid"]):
            return False
        actual = process_start_identity(owner["pid"])
        return not (actual and owner.get("identity") and actual != owner["identity"])

    def busy(self, value):
        if self.alive(value["activeStage"]):
            return True
        # A registered new worker is cooperative even between stages. Unknown
        # running workers/launchers are never inferred stopped from a missing PID.
        from .background_launcher import process_start_identity
        worker = value["worker"]
        if (self.alive(worker) and worker.get("identity")
            and process_start_identity(worker["pid"]) == worker["identity"]):
            return False
        status = self.store.load_status(self.job_id)
        if status.state == "running" and (status.pid is None or self.store._pid_is_alive(status.pid)):
            return True
        marker_path = self.path.parent / "launch.json"
        if marker_path.exists():
            try:
                marker = read_json_file(marker_path)
                pid = marker.get("pid")
                if type(pid) is not int or pid <= 0 or self.store._pid_is_alive(pid):
                    return True
            except (OSError, ValueError, TypeError, AttributeError):
                return True
        if (self.path.parent / ".launch_claim").exists():
            return True
        # Includes pre-control direct advance in an old process.
        claim = self.path.parent / ".claim_reading_pipeline"
        if claim.exists():
            try:
                owner = read_json_file(claim / "owner.json")
                if self.store._pid_is_alive(owner["pid"]):
                    return True
            except (OSError, ValueError, KeyError, TypeError):
                return True
        return False

    def acknowledge(self, value, boundary="between_stages"):
        if value["stopRequested"] and value["acknowledgedRevision"] is None and not self.busy(value):
            value["acknowledgedRevision"] = value["revision"]
            value["effectiveBoundary"] = boundary
            self.save(value)

    def result(self, value, *, replay=None):
        status = self.store.load_status(self.job_id)
        state = read_json_file(self.store.handle(self.job_id).reading_pipeline_path)
        terminal = status.state in {"completed", "failed"} or state.get("state") in {"completed", "failed"}
        phase = ("terminal" if terminal else "acknowledged" if value["stopRequested"] and
                 value["acknowledgedRevision"] == value["revision"] else "requested" if value["stopRequested"] else "active")
        return {**copy.deepcopy(value), "status": phase, "businessStatus": status.to_dict(),
                "pipelineState": state, "independentChildrenStopped": False,
                "compatibility": "unconfirmed_worker_or_stage" if phase == "requested" else "cooperative_boundary",
                "replayedOperation": replay}

    def validate_parent(self):
        request = self.authorize()
        state = read_json_file(self.store.handle(self.job_id).reading_pipeline_path)
        if (state.get("contract_version") != "reading-pipeline-v1"
            or state.get("parent_job_id") != self.job_id or state.get("paper_id") != request.paper_id):
            raise ReadingControlError("full_read_parent_mismatch")
        return request

    def read(self):
        with self.lock():
            self.validate_parent()
            value = self.load()
            self.acknowledge(value)
            return self.result(value)

    def operation(self, value, kind, request_id, expected_revision, supplied=None):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200 or type(expected_revision) is not int or expected_revision < 0:
            raise ReadingControlError("reading_control_operation_invalid")
        old = value["operations"].get(request_id)
        args = dict(kind=kind, expectedRevision=expected_revision)
        if kind == "resume":
            args["input"] = supplied
        if old is not None:
            if any(old.get(k) != v for k, v in args.items()):
                raise ReadingControlError("reading_control_request_conflict")
            return old
        if value["revision"] != expected_revision:
            raise ReadingControlError("reading_control_revision_conflict")
        return None

    def stop(self, request_id, expected_revision):
        with self.lock():
            self.validate_parent()
            value = self.load()
            old = self.operation(value, "stop", request_id, expected_revision)
            if old is None:
                value.update(revision=value["revision"] + 1, stopRequested=True, requestId=request_id,
                             acknowledgedRevision=None, effectiveBoundary=None)
                value["operations"][request_id] = dict(kind="stop", expectedRevision=expected_revision, revision=value["revision"])
                self.save(value)  # Intent is durable before acknowledgement.
            self.acknowledge(value)
            return self.result(value, replay=old)

    def blocked(self):
        with self.lock():
            self.authorize()
            value = self.load()
            self.acknowledge(value)
            return value["stopRequested"]

    def overlay(self, state):
        value = self.load()
        if value["stopRequested"] and state.state not in {"completed", "failed"}:
            state = type(state).from_dict(state.to_dict())
            state.state = "needs_user"
            state.required_action = dict(reason_code="pipeline_stop_requested", revision=value["revision"])
        return state

    @contextmanager
    def stage(self, stage):
        with self.lock():
            self.authorize()
            value = self.load()
            if value["stopRequested"]:
                self.acknowledge(value)
                admitted = False
            else:
                value["activeStage"] = {**self.owner(), "stage": stage}
                self.save(value)
                admitted = True
        try:
            yield admitted
        finally:
            if admitted:
                with self.lock():
                    value = self.load()
                    value["activeStage"] = None
                    self.save(value)
                    # Direct advance holds its legacy claim until returning.
                    # Known stage completion is a safe boundary despite that claim.
                    if value["stopRequested"]:
                        value["acknowledgedRevision"] = value["revision"]
                        value["effectiveBoundary"] = "after:" + stage
                        self.save(value)

    def register_worker(self):
        value = self.load()
        if value["stopRequested"]:
            self.acknowledge(value)
            return False
        if self.alive(value["worker"]):
            raise ReadingControlError("reading_control_worker_busy")
        value["worker"] = self.owner()
        operation = value["operations"].get(value["requestId"])
        if operation is not None and operation["kind"] == "resume":
            operation["dispatched"] = True
        self.save(value)
        return True

    def unregister_worker(self):
        with self.lock():
            value = self.load()
            value["worker"] = None
            self.save(value)
            self.acknowledge(value)

    def resume(self, request_id, expected_revision, supplied, *, validate, launcher):
        """Journal the input and revision before queueing; retry reconciles dispatch."""
        from types import SimpleNamespace
        from .reading_pipeline import ReadingPipeline
        from .library_service import LibraryService
        from .workspace import PaperWorkspace

        with self.lock():
            request = self.validate_parent()
            value = self.load()
            old = self.operation(value, "resume", request_id, expected_revision, supplied)
            if old is not None and (old["revision"] != value["revision"] or old.get("dispatched")):
                return self.result(value, replay=old)
            if old is not None:
                marker_path = self.path.parent / "launch.json"
                if marker_path.exists():
                    marker = read_json_file(marker_path)
                    if marker.get("controlRevision") == old["revision"]:
                        if type(marker.get("pid")) is not int or marker["pid"] <= 0:
                            raise ReadingControlError("reading_control_dispatch_uncertain")
                        old["dispatched"] = True
                        self.save(value)
                        return self.result(value, replay=old)
            if old is None:
                self.acknowledge(value)
                if not value["stopRequested"]:
                    raise ReadingControlError("reading_control_not_stopped")
                if value["acknowledgedRevision"] != value["revision"] or self.alive(value["worker"]) or self.busy(value):
                    raise ReadingControlError("reading_control_stop_unconfirmed")
                pipeline = ReadingPipeline(self.store.data_root)
                state = pipeline._load(self.job_id)
                status = self.store.load_status(self.job_id)
                if state.state == "completed" or status.state == "completed":
                    raise ReadingControlError("reading_control_terminal")
                library = LibraryService(self.store.data_root)
                try:
                    metadata = library.canonical_metadata(request.paper_id)
                    workspace = PaperWorkspace.create_for_paper_id(self.store.data_root, request.paper_id, metadata)
                    source = pipeline._validated_source_sha(workspace.source_pdf, metadata)
                    if state.source_pdf_sha256 is not None and source != state.source_pdf_sha256:
                        raise ReadingControlError("full_read_parent_mismatch")
                finally:
                    library.close()
                if state.state in {"needs_user", "waiting_agent", "failed"}:
                    gate = SimpleNamespace(state="failed" if state.state == "failed" else
                                           "waiting_user" if state.state == "needs_user" else "waiting_agent",
                                           reason_code=(state.required_action or {}).get("reason_code"))
                    validate(gate, supplied)
                elif supplied:
                    raise ReadingControlError("reading_control_resume_input_invalid")
                # The validated input must already be durable if a crash occurs
                # immediately after clearing stop intent. Any subsequent start
                # will then consume exactly this input.
                self.store.save_resume_input(self.job_id, supplied)
                value.update(revision=value["revision"] + 1, stopRequested=False, requestId=request_id,
                             acknowledgedRevision=None, effectiveBoundary=None)
                old = dict(kind="resume", expectedRevision=expected_revision, revision=value["revision"],
                           input=supplied, dispatched=False)
                value["operations"][request_id] = old
                self.save(value)
            # Only this revision may reconcile an interrupted dispatch. A replay
            # of an earlier resume never clears a later stop or launches a worker.
            status = self.store.load_status(self.job_id)
            if status.state not in {"queued", "running", "completed"}:
                self.store.save_resume_input(self.job_id, old["input"])
                (self.path.parent / "launch.json").unlink(missing_ok=True)
                self.store.transition(self.job_id, "queued")
            elif status.state == "queued":
                self.store.save_resume_input(self.job_id, old["input"])
            if status.state not in {"running", "completed"}:
                launcher.launch_existing(self.job_id)
            old["dispatched"] = True
            self.save(value)
            return self.result(value)
