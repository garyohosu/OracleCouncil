---
task_id: S-9
status: pending
---

# 今回実行するタスク

X-8.20は完了済みです。再実装しないでください。

今回実行するのは次の1件だけです。

S-9: Adapter設定数、適格Agent数、Run参加者数の分離とparticipants定義の統一

## 現在状態

S-9は部分実装済みです。

既存部分実装には、少なくとも次が含まれます。

- MAX_RUN_PARTICIPANTS = 4
- select_run_participants()
- configured adaptersから決定的に最大4件を選ぶ処理
- 5件から4件を選ぶunit test
- SPEC.mdおよびQandA.mdの一部更新

既存実装を削除して最初から作り直さないでください。

現在のコード、テスト、Git履歴を確認し、不足部分だけを完成させてください。

## 採用仕様

概念を次のように分離します。

1. configured adapters
   - 設定から読み込まれたAdapter全件
   - 0..*

2. eligible agents
   - Run開始時に既存処理で利用可能と判定されたAgent
   - probe/capabilitiesの正本化は今回変更しない

3. selected participants
   - そのRunのCouncil構成員
   - 2..4
   - eligible agentsを既存の決定的優先順位で並べた先頭最大4件
   - 5件目以降はselected participantsに含めない

4. executions
   - 実際に開始された個別Agent実行
   - failure、skip、途中停止によりselected participantsの一部だけになる場合がある

## participantsの定義

公開されるparticipantsはselected participantsを表します。

次のすべてで意味を統一してください。

- ExecutionPlanまたはRunの正本
- run_createdイベント
- CLI JSONトップレベル
- Run metadata
- 設計資料

executionsからparticipantsを逆算してはいけません。

実際に実行されたAgentはexecutionsで表現してください。

## 今回完成させる内容

既存部分実装を確認し、最低限次を完成させてください。

- selected participantsを決める正本箇所を1か所にする
- 5件以上の場合に決定的に最大4件を選ぶ
- run_created.participantsをselected participantsへ統一
- CLI JSON participantsをselected participantsへ統一
- executionsの一部しか実行されなくてもparticipantsを維持
- 必要ならRun metadataも同じ定義へ統一
- QandA.mdのS-9を正式に回答済みへする
- SPEC.md、CLASS.md、SEQUENCE.md、TESTCASE.mdを整合
- FIX_PLAN.md、hikitsugi.md、instructions/result.mdでS-9完了を記録

## 必須テスト

最低限、次を検証してください。

1. configured adaptersが5件以上でもselected participantsは最大4件
2. 既存の決定的優先順位で先頭4件を選ぶ
3. 同一入力では順序が常に同じ
4. run_createdのparticipantsがselected participantsと一致
5. CLI JSONのparticipantsがselected participantsと一致
6. executionsが一部だけでもparticipantsは変化しない
7. 4件以下の既存挙動を維持
8. 2件未満の既存事前停止規則を維持
9. retry、substitution、process_exit_code、oracle_exit_codeを壊さない

Fake、unit、integrationテストだけを使用してください。

## 非対象

- S-10
- T-3
- probe/capabilitiesの設計変更
- DNS rebinding
- 実Claude
- OracleCouncilによる実Codex
- Web検索
- 実HTTP
- liveテスト
- 有料API
- 別タスク
- 大規模リファクタリング
- git commit
- git push
- PR作成
- dream.md
- loop/
- loop.zip

## 検証

必ず次を実行してください。

py -m pytest -q
git diff --check

## 完了報告

stdoutとinstructions/result.mdへ次を記録してください。

1. チェックポイント時点で実装済みだった内容
2. 今回追加・修正した不足部分
3. configured、eligible、selected、executionsの違い
4. selected participantsの正本箇所
5. 5件以上の場合の挙動
6. run_createdとCLI JSONの統一結果
7. 変更ファイル
8. 追加・更新したテスト
9. 全通常テスト結果
10. S-10とT-3へ踏み込んでいないこと
11. 未解決事項
12. 次の推奨タスク

S-9以外へ進まず、1サイクルで停止してください。
