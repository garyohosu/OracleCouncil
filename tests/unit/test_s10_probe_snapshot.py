from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from oracle_council.cli import create_adapter, probe_agents
from oracle_council.models import AgentProbeSnapshot, RunStatus
from oracle_council.adapters.claude import ClaudeAdapter
from oracle_council.adapters.codex import CodexAdapter
from oracle_council.cli import FakeAgentAdapter
from oracle_council.orchestrator import Orchestrator
from oracle_council.budget import TokenBudget
from oracle_council.fakes import FakeEvidenceProvider


def test_adapter_probe_caching():
    # 1. ClaudeAdapter のキャッシュ検証
    adapter_claude = ClaudeAdapter("claude-test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="claude version 1.0", stderr="")

        # 初回プローブ
        res1 = adapter_claude.probe()
        assert res1 == "OK"
        mock_run.assert_called_once()

        # 2回目のプローブ（モックが呼ばれずにキャッシュから返る）
        res2 = adapter_claude.probe()
        assert res2 == "OK"
        mock_run.assert_called_once()

    # 2. CodexAdapter のキャッシュ検証
    adapter_codex = CodexAdapter("codex-test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="codex version 1.0", stderr="")

        # 初回プローブ
        res1 = adapter_codex.probe()
        assert res1 == "OK"
        mock_run.assert_called_once()

        # 2回目のプローブ（キャッシュから返る）
        res2 = adapter_codex.probe()
        assert res2 == "OK"
        mock_run.assert_called_once()

    # 3. FakeAgentAdapter のキャッシュ検証
    adapter_fake = FakeAgentAdapter("fake-test", mock_status="OK")
    with patch.dict(os.environ, {"ORACLE_MOCK_PROBE_FAKE-TEST": "OK"}):
        res1 = adapter_fake.probe()
        assert res1 == "OK"

        # 環境変数定義を変更してみるが、キャッシュから返るため結果は変わらない
        with patch.dict(os.environ, {"ORACLE_MOCK_PROBE_FAKE-TEST": "TIMEOUT"}):
            res2 = adapter_fake.probe()
            assert res2 == "OK"


def test_snapshot_creation_and_merge():
    # Adapter capabilities と config capabilities のマージ確認
    config_agents = [
        {
            "id": "agent-a",
            "adapter": "fake",
            "enabled": True,
            "mock_status": "OK",
            "capabilities": {
                "supported_models": ["custom-model-from-config"],
                "custom_feature": True
            }
        }
    ]

    agents, snapshots = probe_agents(config_agents, "fake")
    assert len(agents) == 1
    assert len(snapshots) == 1

    snap = snapshots[0]
    assert snap.agent_id == "agent-a"
    assert snap.status == "OK"
    assert snap.capabilities["custom_feature"] is True
    # config の capabilities が優先（マージ）されていること
    assert snap.capabilities["supported_models"] == ["custom-model-from-config"]
    # FakeAgentAdapter のデフォルト capabilities が保持されていること
    assert snap.capabilities["supports_read_only"] is True


def test_snapshot_lifecycle_in_orchestrator():
    # Orchestrator が snapshots を受け取り、不変のまま run_created イベントと結果に保存することを確認
    snap_a = AgentProbeSnapshot(
        agent_id="agent-a",
        status="OK",
        capabilities={"supported_models": ["model-a"]},
        probed_at=datetime.now(timezone.utc)
    )
    snap_b = AgentProbeSnapshot(
        agent_id="agent-b",
        status="OK",
        capabilities={"supported_models": ["model-b"]},
        probed_at=datetime.now(timezone.utc)
    )

    mock_adapter_a = MagicMock()
    mock_adapter_a.execute.return_value = MagicMock(output={"answer": "Mock response"}, usage=None)
    mock_adapter_b = MagicMock()
    mock_adapter_b.execute.return_value = MagicMock(output={"status": "approved", "issues": []}, usage=None)

    from oracle_council.assignment import RegisteredAgent
    agents = [
        RegisteredAgent("agent-a", mock_adapter_a, {"respond": 10, "synthesize": 10}),
        RegisteredAgent("agent-b", mock_adapter_b, {"audit": 10})
    ]

    orchestrator = Orchestrator(
        agents=agents,
        evidence_provider=FakeEvidenceProvider([]),
        budget=TokenBudget(10**6, 10**6),
        snapshots=[snap_a, snap_b]
    )

    # モックによる実行
    with patch.object(orchestrator, "_execute_phase", return_value=None):
        result = orchestrator.run_verify("question")

        # snapshot が RunResult に正しく保持されていること
        assert len(result.agent_snapshots) == 2
        assert result.agent_snapshots[0].agent_id == "agent-a"
        assert result.agent_snapshots[1].agent_id == "agent-b"

        # metadata にもシリアライズされて保存されていること
        assert len(result.metadata.agent_snapshots) == 2
        assert result.metadata.agent_snapshots[0]["agent_id"] == "agent-a"
