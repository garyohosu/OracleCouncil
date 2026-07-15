---
task_id: S-10
status: pending
---

# 今回実行するタスク

S-9はコミット388fd75で完了済みです。再実装しないでください。

今回実行するのは次の1件だけです。

S-10: probe結果とcapabilitiesの正本統一

## 背景

現在の実装では、Agentの利用可能性とcapabilitiesに複数の取得経路があります。

確認対象:

- CLIのRun開始前probe
- Adapter.execute()内の再probe
- agents status用に再生成されるFakeAgentAdapter
- agents validate用に再生成されるFakeAgentAdapter
- config/agents.yamlのcapabilities
- adapter.capabilities()

このため、同じAgentについて次の不整合が起こり得ます。

- Run開始時は利用可能だがexecute直前の再probeで別判定になる
- 1コマンド中に同じAgentを複数回probeする
- 実Adapter設定なのにagents statusではFakeの状態を表示する
- configのcapabilitiesとAdapterのcapabilitiesのどちらが正本か不明
- availabilityとcapabilitiesが別時点の値になる
- テストと実運用で異なるAdapter生成経路を使う

## 目的

1回のコマンドまたは1回のRunについて、各有効Agentのprobe結果とcapabilitiesを一度だけ取得し、その結果を不変のスナップショットとして扱ってください。

既存クラス名との整合を確認したうえで、必要なら次に相当するモデルを導入してください。

AgentProbeSnapshotまたは既存設計に適合する同等モデル:

- agent_id
- statusまたはavailability
- reason_codeまたはerror_code
- capabilities
- probed_at
- 必要なら実Adapterへの参照とは分離した識別情報

名称は既存設計に合わせて変更可能です。

## 正本規則

### 1. Adapter生成

設定から実際のAdapterを生成する処理を共通化してください。

次のコマンドが、同じAdapter生成経路を使用するようにしてください。

- ask
- agents status
- agents validateのうち実行時確認を行う部分

実Adapterとして設定されたAgentを、statusまたはvalidateだけFakeAgentAdapterへ置き換えてはいけません。

### 2. probe

各有効Agentのprobeは、1コマンドまたは1 Runの事前確認で原則1回だけ実行してください。

その結果をスナップショットへ保存し、次へ渡してください。

- 利用可能Agentの選定
- 2 Agent未満の事前停止判定
- ExecutionPlanまたはRunのavailability情報
- agents statusの表示
- 必要なmetadataまたはevent

Runへ参加済みのAdapterがexecuteするたび、同じ事前probeを無条件に繰り返してはいけません。

実行開始後に発生したcommand not found、timeout、quota、認証、非0終了などは、probe結果を書き換えるのではなく、個別executionの結果として既存のAgentFailure経路で扱ってください。

### 3. capabilities

Runtimeで使用するcapabilitiesの正本を1つにしてください。

原則:

- 実Adapterの実行時capabilitiesはAdapterが提供する
- configのcapabilitiesはFake fixture、明示的な設定値、または要求条件として扱う
- config値とAdapter値を、根拠なく別々の正本として参照しない
- どちらを優先または統合するかをQandA.mdのS-10へ明記する
- 同じスナップショットにstatusとcapabilitiesを保存し、別時点に独立取得しない

config capabilitiesをAdapter capabilitiesへ上書きする仕様を採用する場合は、上書き可能な項目、禁止項目、競合時の扱いを明記してください。

安全な既定案が存在する場合は自動決定し、QandA.mdへAUTO_DECIDEDとして記録してください。

### 4. statusとvalidate

`agents status`は実際に設定されたAdapterを使用し、取得したスナップショットを表示してください。

`agents validate`については、次を区別してください。

- 設定構文の静的検証
- Adapter生成可能性
- runtime probeが必要な動的検証

既存CLI互換性を優先し、1コマンド中に同じprobeを重複実行しないでください。

### 5. Runの不変性

Run開始時に確定したAgentスナップショットは、そのRunの監査記録として保持してください。

実行途中の失敗で、Run開始時のsnapshotを過去にさかのぼって書き換えないでください。

実行時の失敗はexecutionsへ記録してください。

## 実装方針

既存コードへの最小変更を優先してください。

推奨される分離:

1. configからAdapterを生成する共通factoryまたはhelper
2. 各Adapterを1回確認してsnapshotを生成する共通helper
3. snapshotからeligible agentsを選択
4. snapshotまたはavailability情報をExecutionPlan／Runへ渡す
5. execute時は事前probeを再実行せず、実行結果の失敗を既存のtyped errorへ変換

ただし、既存設計上さらに小さい変更で正本を統一できる場合は、その案を採用して構いません。採用理由をinstructions/result.mdへ記録してください。

## 必須テスト

最低限、次をFakeまたはstubで検証してください。

1. 有効Agentごとのprobe回数が1コマンドまたは1 Runにつき1回
2. capabilities取得回数が1回
3. statusとcapabilitiesが同じsnapshotに保存される
4. askがsnapshotを利用してeligible agentsを決める
5. probe失敗AgentがRun参加者から除外される
6. 利用可能Agentが2件未満ならRunを作成せず事前停止
7. Run開始後のexecution失敗がsnapshotを書き換えない
8. Adapter.execute()が同じ事前probeを無条件に再実行しない
9. agents statusが実設定AdapterをFakeへ置き換えない
10. agents validateの静的検証と動的確認が混同されない
11. config capabilitiesとAdapter capabilitiesの採用規則が決定的
12. 同じ入力ではsnapshotとeligible順序が決定的
13. S-9のselected participants上限2..4を壊さない
14. retry、substitution、process_exit_code、oracle_exit_codeを壊さない
15. Claude／Codexの実CLIをテスト中に起動しない

既存テストの意味を弱めないでください。

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

QandA.mdのS-10には次を記録してください。

- 問題だった二重化
- 比較した選択肢
- 採用した正本
- config capabilitiesの位置づけ
- snapshotのライフサイクル
- 実行途中の失敗との区別
- 採用理由
- 実装箇所
- テスト箇所

## 非対象

今回は次を行わないでください。

- S-9の再実装
- T-3 DNS rebinding
- q03 live確認
- L-3構造化出力回復
- J-3 quickモード
- 実Claude呼び出し
- OracleCouncilによる実Codex呼び出し
- Web検索
- 実HTTP
- liveテスト
- 有料API
- 別タスク
- 大規模リファクタリング
- git commit
- git push
- PR作成
- dream.mdの変更

## 検証

対象テストを実行した後、必ず次を実行してください。

```powershell
py -m pytest -q
git diff --check
```

## 完了報告

stdoutとinstructions/result.mdへ次を記録してください。

1. 変更前のprobe／capabilities取得経路
2. 採用した正本モデル
3. snapshotの生成箇所
4. snapshotのライフサイクル
5. config capabilitiesの位置づけ
6. execute時の再probeをどう扱ったか
7. agents status／validateの修正
8. 変更ファイル
9. 追加・更新したテスト
10. probe回数を検証した結果
11. 全通常テスト結果
12. S-9を壊していないこと
13. S-10以外へ踏み込んでいないこと
14. 未解決事項
15. 次の推奨タスク

S-10以外へ進まず、1サイクルで停止してください。
