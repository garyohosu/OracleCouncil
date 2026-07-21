from __future__ import annotations

import time
import threading
import subprocess
import sys
import pytest
from oracle_council.orchestrator import Orchestrator, EXIT_CANCELLED
from oracle_council.models import RunStatus, PhaseStatus, AgentExecutionStatus, AgentFailure, AgentRequest
from oracle_council.assignment import RegisteredAgent
from oracle_council.budget import TokenBudget
from oracle_council.fakes import FakeEvidenceProvider, ScriptedAgentAdapter
from oracle_council.adapters.claude import ClaudeAdapter
from oracle_council.adapters.codex import CodexAdapter

def test_orchestrator_cancel_propagates_and_returns_130():
    class SlowAgentAdapter:
        def __init__(self) -> None:
            self.agent_id = "slow-agent"
            self.called = False
            self.cancelled = False
            self._lock = threading.Lock()
            self._cancelled_ids: set[str] = set()

        def probe(self):
            from oracle_council.models import ProbeResult, AgentCapabilities
            caps = AgentCapabilities(
                adapter_family="fake",
                adapter_version="1.0",
                cli_version="1.0",
                supported_phases=("respond", "claim_extract", "verify", "criticize", "synthesize", "audit"),
            )
            return ProbeResult("OK", caps)

        def execute(self, request):
            self.called = True
            for _ in range(50):
                with self._lock:
                    if request.execution_id in self._cancelled_ids:
                        raise AgentFailure("CANCELLED", "cancelled")
                time.sleep(0.05)
            return {"answer": "slow"}

        def cancel(self, execution_id: str) -> None:
            with self._lock:
                self._cancelled_ids.add(execution_id)
                self.cancelled = True

    adapter_a = SlowAgentAdapter()
    adapter_b = ScriptedAgentAdapter([{"answer": "B"}])
    
    orchestrator = Orchestrator(
        [RegisteredAgent("agent-a", adapter_a), RegisteredAgent("agent-b", adapter_b)],
        FakeEvidenceProvider([]),
        TokenBudget(input_limit=10**6, output_limit=10**6),
        None
    )

    def cancel_after_start():
        for _ in range(100):
            if adapter_a.called:
                break
            time.sleep(0.01)
        
        active = []
        for _ in range(100):
            with orchestrator._registry._lock:
                active = list(orchestrator._registry._registry.items())
            if active:
                break
            time.sleep(0.01)
            
        assert len(active) > 0
        exec_id, (run_id, _) = active[0]
        orchestrator.cancel(run_id)

    cancel_thread = threading.Thread(target=cancel_after_start)
    cancel_thread.start()

    result = orchestrator.run_verify("test question")
    cancel_thread.join()

    assert adapter_a.called
    assert adapter_a.cancelled
    assert result.status is RunStatus.CANCELLED
    assert result.oracle_exit_code == EXIT_CANCELLED
    assert len(result.executions) > 0
    assert result.executions[0].status == AgentExecutionStatus.CANCELLED
    assert result.executions[0].error_code == "CANCELLED"
    assert len(result.phases) > 0
    respond_phases = [p for p in result.phases if p.phase == "respond"]
    assert any(p.status == PhaseStatus.CANCELLED for p in respond_phases)


def test_adapter_subprocess_cancel_logic(monkeypatch):
    infinite_sleep_cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
    
    adapter = ClaudeAdapter("claude-test", timeout_s=10)
    monkeypatch.setattr(adapter, "probe", lambda: type("ProbeResult", (object,), {"status": "OK"})())
    
    original_popen = subprocess.Popen
    popen_called = []
    
    def mock_popen(*args, **kwargs):
        if args[0][0] == "claude":
            new_args = (infinite_sleep_cmd,) + args[1:]
            proc = original_popen(*new_args, **kwargs)
        else:
            proc = original_popen(*args, **kwargs)
        popen_called.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    
    req = AgentRequest("run-1", "exec-1", "respond", {"question": "q"}, {})
    
    def cancel_thread_func():
        for _ in range(100):
            if popen_called:
                break
            time.sleep(0.01)
        assert popen_called
        adapter.cancel("exec-1")

    t = threading.Thread(target=cancel_thread_func)
    t.start()
    
    with pytest.raises(AgentFailure) as excinfo:
        adapter.execute(req)
        
    t.join()
    assert excinfo.value.error_code == "CANCELLED"
    proc = popen_called[0]
    assert proc.poll() is not None
