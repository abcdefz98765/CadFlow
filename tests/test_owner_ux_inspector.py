from __future__ import annotations

from ai_native_cad.workflow_console.attempt_ui import (
    render_stopped_attempt,
    stopped_attempt_copy,
)
from ai_native_cad.workflow_console.selected_node_inspector_ui import (
    SelectedInspectorRenderers,
    render_selected_node_inspector,
    selected_node_action_state_copy,
)
from ai_native_cad.workflow_console.workflow_graph_ui import current_attention_is_redundant
from ai_native_cad.workflow_console.work_outcome import project_stopped_attempt
from ai_native_cad.workflow_console.agent_activity import significant_activity


class _Element:
    def __init__(self, ui, tag, text=None):
        self.ui = ui
        self.tag = tag
        self.text = text

    def classes(self, value):
        self.ui.events.append((self.tag, self.text, value))
        return self

    def props(self, _value):
        return self

    def tooltip(self, _value):
        return self

    def on(self, _event, _callback):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _RecordingUI:
    def __init__(self):
        self.events = []

    def element(self, tag):
        return _Element(self, tag)

    def row(self):
        return _Element(self, "row")

    def column(self):
        return _Element(self, "column")

    def label(self, value):
        return _Element(self, "label", str(value))

    def expansion(self, *_args, **_kwargs):
        return _Element(self, "expansion")

    def button(self, *_args, **_kwargs):
        return _Element(self, "button")


def _label_text(ui):
    return [text for tag, text, _classes in ui.events if tag == "label"]


def test_stopped_attempt_is_short_natural_language_without_audit_matrix():
    recovery = {
        "title": "Design stopped",
        "what_happened": "The candidate could not be executed.",
        "why": "The local CAD runtime was unavailable.",
        "resolution_owner": "environment",
        "retryable": True,
        "geometry_generated": False,
        "result_published": False,
        "next_action": "Retry this attempt.",
    }

    title, copy = stopped_attempt_copy(recovery, "en")
    ui = _RecordingUI()
    render_stopped_attempt(ui, recovery, "en")
    rendered = _label_text(ui)

    assert title == "Design stopped"
    assert "The local CAD environment needs attention before retrying." in copy
    assert "Retry is useful" not in rendered
    assert "Next" not in rendered and "Retry this attempt." not in rendered
    assert "Yes" not in rendered and "No" not in rendered
    assert not any("attempt-fact-grid" in classes for _tag, _text, classes in ui.events)


def test_generic_agent_stop_does_not_claim_an_action_format_problem():
    recovery = {
        "resolution_owner": "agent",
        "retryable": True,
        "impact": "No CAD was executed and no model was generated.",
    }

    _title, copy = stopped_attempt_copy(recovery, "en")

    assert any("another allowed action" in message for message in copy)
    assert not any("action-format issue" in message for message in copy)
    assert "No CAD was executed and no model was generated." in copy


def test_blocked_action_copy_names_owner_instead_of_generic_readiness():
    node = {"status": "blocked"}

    assert selected_node_action_state_copy(
        node, {"primary_action": {"key": "retry_agent"}},
        {"recovery": {"resolution_owner": "environment", "retryable": True}}, "en"
    )[0] == "Local environment needs attention"
    assert selected_node_action_state_copy(
        node, {"primary_action": {"key": "retry_agent"}},
        {"recovery": {"resolution_owner": "user", "user_input_required": True}}, "en"
    )[0] == "Your input is needed"
    assert selected_node_action_state_copy(
        node, {"primary_action": {"key": "retry_agent"}},
        {"recovery": {"resolution_owner": "agent", "retryable": True}}, "en"
    )[0] == "A new design attempt can be started"


def test_work_design_diagnosis_precedes_cta_and_suppresses_repeated_grid(monkeypatch):
    import ai_native_cad.workflow_console.selected_node_inspector_ui as inspector

    events = []
    monkeypatch.setattr(inspector, "render_stopped_attempt", lambda *_args: events.append("diagnosis"))
    monkeypatch.setattr(inspector, "render_work_design", lambda *_args: events.append("work_design"))
    monkeypatch.setattr(inspector, "render_agent_activity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(inspector, "render_lazy_technical_evidence", lambda *_args, **_kwargs: None)
    feedback_options = []
    renderers = SelectedInspectorRenderers(
        action_feedback=lambda *_args, **kwargs: (
            feedback_options.append(kwargs),
            events.append("transient" if kwargs.get("transient_only") else "feedback"),
        ),
        display_status=lambda status, _language: str(status),
        pending_action_matches=lambda *_args: False,
        node_actions=lambda *_args: events.append("cta"),
        key_values=lambda *_args: events.append("grid"),
        agent_design_summary=lambda *_args: None,
        preview=lambda *_args: None,
        workbench_result=lambda *_args, **_kwargs: None,
    )
    page = {
        "selected_node": {
            "id": "work-design",
            "label": "Work Design",
            "status": "blocked",
            "summary": "A durable stop is recorded.",
            "interaction": {"primary_action": {"key": "retry_agent"}},
            "detail": {
                "type": "work_design",
                "recovery": {"resolution_owner": "agent", "retryable": True},
                "work_design": {"status": "blocked", "generated_parts": []},
            },
        },
        "source": {"overview": {"work": {}, "part_jobs": []}},
    }

    render_selected_node_inspector(
        _RecordingUI(), page, type("Actions", (), {"backend": object()})(), {},
        lambda: None, lambda _run_id: None, "en", renderers=renderers,
    )

    assert events.index("diagnosis") < events.index("cta")
    assert "grid" not in events
    assert events[0] == "transient"
    assert feedback_options == [{"transient_only": True, "has_durable_recovery": True}]


def test_running_retry_hides_previous_terminal_diagnosis(monkeypatch):
    import ai_native_cad.workflow_console.selected_node_inspector_ui as inspector

    events = []
    monkeypatch.setattr(inspector, "render_stopped_attempt", lambda *_args: events.append("diagnosis"))
    monkeypatch.setattr(inspector, "render_work_design", lambda *_args: None)
    monkeypatch.setattr(inspector, "render_agent_activity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(inspector, "render_lazy_technical_evidence", lambda *_args, **_kwargs: None)
    renderers = SelectedInspectorRenderers(
        action_feedback=lambda *_args, **_kwargs: None,
        display_status=lambda status, _language: str(status),
        pending_action_matches=lambda *_args: True,
        node_actions=lambda *_args: None,
        key_values=lambda *_args: events.append("grid"),
        agent_design_summary=lambda *_args: None,
        preview=lambda *_args: None,
        workbench_result=lambda *_args, **_kwargs: None,
    )
    page = {
        "selected_node": {
            "id": "work-design",
            "label": "Work Design",
            "status": "blocked",
            "interaction": {"primary_action": {"key": "retry_agent"}},
            "detail": {
                "type": "work_design",
                "recovery": {"resolution_owner": "agent", "retryable": True},
                "work_design": {"status": "blocked"},
            },
        },
        "source": {"overview": {"work": {}, "part_jobs": []}},
    }
    ui = _RecordingUI()

    render_selected_node_inspector(
        ui, page, type("Actions", (), {"backend": object()})(), {},
        lambda: None, lambda _run_id: None, "en", renderers=renderers,
    )

    assert "diagnosis" not in events
    assert "grid" not in events
    assert "A new Agent design attempt is running" in _label_text(ui)


def test_current_attention_hides_only_repeated_single_selection():
    single = {
        "current_attention": [{"node_id": "attempt-1"}],
        "nodes": [{"id": "attempt-1", "selected": True}],
    }
    multi = {
        "current_attention": [{"node_id": "attempt-1"}, {"node_id": "attempt-2"}],
        "nodes": [{"id": "attempt-1", "selected": True}, {"id": "attempt-2", "selected": False}],
    }

    assert current_attention_is_redundant(single) is True
    assert current_attention_is_redundant(multi) is False


def test_action_feedback_keeps_raw_action_metadata_out_of_normal_copy():
    from ai_native_cad.workflow_console.nicegui_app import _render_action_feedback_panel

    ui = _RecordingUI()
    _render_action_feedback_panel(ui, {
        "action_execution": {
            "status": "pending",
            "action_key": "retry_agent",
            "target_work_id": "secret-work-id",
            "runtime_outcome": "runtime-internal",
            "message": "Starting a new attempt.",
        }
    }, "en")

    rendered = _label_text(ui)
    assert "Starting a new attempt." in rendered
    assert not any("retry_agent" in value or "secret-work-id" in value for value in rendered)

    succeeded_ui = _RecordingUI()
    _render_action_feedback_panel(succeeded_ui, {
        "action_execution": {"status": "succeeded", "message": "Done"}
    }, "en")
    assert succeeded_ui.events == []


def test_selected_inspector_keeps_terminal_failure_only_without_recovery():
    from ai_native_cad.workflow_console.nicegui_app import _render_action_feedback_panel

    failed = {
        "action_execution": {"status": "failed", "message": "The request could not be started."}
    }
    visible = _RecordingUI()
    _render_action_feedback_panel(
        visible, failed, "en", transient_only=True, has_durable_recovery=False
    )
    assert "The request could not be started." in _label_text(visible)

    suppressed = _RecordingUI()
    _render_action_feedback_panel(
        suppressed, failed, "en", transient_only=True, has_durable_recovery=True
    )
    assert suppressed.events == []


def test_repair_exhaustion_projects_clean_owner_copy_and_activity():
    recovery = project_stopped_attempt(
        stop_reason="policy_blocked",
        episode={"execution_succeeded": False, "contract_repair_exhausted": True, "contract_repair_turn_count": 2},
        agent_items=[],
        scope_label="Bracket",
        language="en",
        failure_diagnostic={
            "schema_version": 1,
            "rejection_stage": "action_contract_validation",
            "rejected_action": "ask_user",
            "reason_code": "invalid_question_contract",
            "requested_capability_or_context": "acceptance_criteria",
            "human_safe_detail": "Question must contain one focused field.",
            "side_effect_started": False,
            "contract_repair_exhausted": True,
            "contract_repair_turn_count": 2,
        },
    )
    _title, copy = stopped_attempt_copy(recovery, "en")
    activity = significant_activity([{
        "kind": "system_observation",
        "observation": "action_contract_feedback",
        "contract_repair_exhausted": True,
    }], language="en")

    assert recovery["contract_repair_exhausted"] is True
    assert recovery["contract_repair_turn_count"] == 2
    assert any("repeatedly submitted" in line for line in copy)
    assert any("Last invalid field: acceptance_criteria" in line for line in copy)
    assert sum("2 correction attempts" in line for line in copy) == 1
    assert any("No CAD" in line for line in copy)
    assert any("no additional design input" in line for line in copy)
    assert activity == [{
        "key": "action_contract_exhausted",
        "label": "Stopped after repeated invalid action submissions",
        "summary": None,
        "count": 1,
    }]


def test_agent_stop_uses_format_copy_only_for_allowlisted_diagnostic():
    generic = {
        "resolution_owner": "agent",
        "retryable": True,
        "technical_reason": "action_not_registered",
    }
    format_error = {
        "resolution_owner": "agent",
        "retryable": True,
        "technical_reason": "invalid_question_contract",
    }

    assert any("another allowed action" in message for message in stopped_attempt_copy(generic, "en")[1])
    assert any("valid action format" in message for message in stopped_attempt_copy(format_error, "en")[1])
