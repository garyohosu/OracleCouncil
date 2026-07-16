---
task_id: S-9
status: completed
---

# 今回実行するタスク（完了済み・要更新）

S-9は完了した（FIX_PLAN.md §0-11参照、`test_assignment.py`/`test_orchestrator.py`のS-9関連テストがpass）。

本ファイルはAutoLoopが読む唯一の実行対象タスクの正本である。AutoLoopは`status`が`pending`のときだけ動作し、`task_id`欄のタスクだけを実装して`status`を`completed`（または`blocked`）へ書き換えて停止する（`.autoloop/config.json`の`allow_task_chaining: false`、`C:\PROJECT\autoloop`のcontroller.py側で強制）。

**次にAutoLoopを実行する前に、人間がこのfront matterを次の未着手タスク（例: S-4、J-4、q03 live再評価など。FIX_PLAN.mdの未解決一覧を参照）へ書き換え、`status: pending`に戻すこと。** このセッションでは新しいタスクを選定していない。

以下は2026-07-15時点でのAutoLoop実行時に、実際にはS-9以外にS-10・T-3・L-3・S-6/T-2・J-3も連鎖的に実装されてしまった記録（FIX_PLAN.md §0-11〜0-16に正本あり）。S-4は着手途中でAPI利用枠が尽きて失敗し、その未完成分は本セッションで削除・復旧済み。

---

X-8.20 is completed. Do not re-implement.

今回実行するのは次の1件だけです。

S-9: Adapter設定数、適格Agent数、Run参加者数の分離とparticipants定義の統一

## 背景

既存コードには決定的なAgent割当てが実装されていますが、設計資料と実装が一致していません。

現在確認されている問題:

- Orchestratorが保持する設定済みAdapter数と、各Runが参加者として選ぶAgent数が区別されていない
- 5件以上の適格Agentが存在する場合にRun参加者を最大4件へ制限する処理がない
- run_createdイベントのparticipantsはprobe成功Agent全件
- CLI JSONのparticipantsは実際に実行されたAgentのユニーク集合
- 同じparticipantsという名前で異なる意味を持っている
- QandA、SPEC、CLASS、FIX_PLAN、hikitsugiではS-9が未解決のまま

## 正本として採用する仕様

次の概念を明確に分離してください。

1. configured adapters
   - 設定から読み込まれたAdapter全件
   - 多重度は0..*
   - Run参加者数の上限4とは別の概念

2. eligible agents
   - 現在の既存処理でRun開始時に利用可能と判定されたAgent
   - 今回はprobe/capabilitiesの正本化方法を変更しない
   - S-10へ踏み込まない

3. selected participants
   - そのRun의 Council構成員
   - 多重度は2..4
   - eligible agentsを既存の決定的優先順位で並べ、その先頭最大4件を選ぶ
   - 5件目以降はselected participantsに含めない
   - 2件未満の場合の既存の事前停止規則は維持する

4. executions
   - 実際に開始された個別Agent実行記録
   - failure、skip、途中停止などによりselected participantsの一部しか実行されない場合がある
   - executionsからparticipantsを逆算しない

## participantsの公開定義

次の全箇所でparticipantsをselected participantsへ統一してください。

- RunまたはExecutionPlan의 正本
- run_createdイベント
- CLI JSONトップレベル
- 永続化されるRun metadata
- 関連する設計資料

実際に実行されたAgentはexecutionsで表現してください。

participantsを「実行されたAgentのユニーク集合」として生成しないでください。

## 実装方針

既存の次の実装を尊重してください。

- 決定的なrole_priority
- 設定順によるタイブレーク
- ExecutionPlan
- retryおよびsubstitution
- 既存のAgentFailure処理
- 既存の2 Agent未満での停止規則
- oracle_exit_codeとprocess_exit_codeの分離

不要な全面リファクタリングは行わないでください。

参加者選定は、Run開始後に複数箇所で再計算せず、ExecutionPlanまたは同等の既存正本で1回決定してください。

既存構造上、別の最小変更の方が安全な場合は、その理由をinstructions/result.mdへ記録してください。ただし、公開participantsの意味はselected participantsへ統一してください。

## 必須テスト

少なくとも次を追加または更新してください。

1. configured adaptersが5件以上でもselected participantsは最大4件
2. 5件以上の場合、既存の決定的優先順位で先頭4件が選ばれる
3. 同一入力ではselected participantsの順序が常に同じ
4. run_createdイベントのparticipantsがselected participantsと一致
5. CLI JSONのparticipantsがselected participantsと一致
6. executionsがselected participantsの一部だけでもparticipantsは変化しない
7. configured adaptersが4件以下の場合は既存挙動を壊さない
8. 2件未満の場合は既存の事前停止規則を維持
9. retry、substitution、process_exit_code、oracle_exit_codeの既存テストを壊さない

Fake Agentとunit/integrationテストだけを使用してください。

## 更新する資料

必要に応じて次を最小限更新してください。

- QandA.md
- SPEC.md
- CLASS.md
- SEQUENCE.md
- TESTCASE.md
- FIX_PLAN.md
- hikitsugi.md
- instructions/result.md

QandA.mdのS-9には、採用仕様、選択肢、採用理由、実装との対応を記録してください。

FIX_PLAN.mdとhikitsugi.mdではS-9を完了済みにしてください。

## 非対象

今回は次を行わないでください。

- S-10 probe/capabilities正本化
- T-3 DNS rebindingまたはpinned transport
- 実Claude呼び出し
- OracleCouncilによる実Codex呼び出し
- Web検索
- 実HTTPアクセス
- 有料API
- liveテスト
- 別タスクの実装
- 大規模リファクタリング
- git commit
- git push
- PR作成
- dream.mdの変更

## 検証

対象テストの後、必ず次を実行してください。

```powershell
py -m pytest -q
git diff --check
```

## 完了報告

stdoutおよびinstructions/result.mdへ次を記録してください。

1. 変更前の矛盾
2. 採用したparticipants定義
3. configured、eligible、selected、executionsの違い
4. 参加者を選定する正本箇所
5. 5件以上の場合の選定規則
6. 変更ファイル
7. 追加・更新したテスト
8. 対象テスト結果
9. 全通常テスト結果
10. S-10へ踏み込んでいないこと
11. 未解決事項
12. 次の推奨タスク

S-9以外を実装せず、1サイクル終了時点で停止してください。
