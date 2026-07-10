# Oracle Council ユースケース図

- 対象仕様: `SPEC.md` v0.3.2
- 対象範囲: MVP
- 表記: MermaidにUML Use Case専用構文がないため、`flowchart`の楕円ノードでユースケースを表す
- 関係: 実線はアクターの操作、`include`は必須処理、`extend`は条件付き処理

## 1. システムユースケース

```mermaid
flowchart LR
    user["利用者"]
    client["非対話クライアント"]
    operator["ローカル運用者"]
    claude["Claude Code"]
    codex["Codex CLI"]
    search["Web検索サービス"]
    source["公開HTTPS情報源"]

    subgraph council["Oracle Council MVP"]
        direction TB

        ask(["質問する"])
        choose_mode(["検証モードを指定する"])
        clarify(["不足条件を回答する"])
        assumptions(["仮定または処理不能理由を受け取る"])
        progress(["進捗を確認する"])
        result(["回答・検証状況・監査状況を受け取る"])
        json(["JSON結果を受け取る"])
        fallback(["quickへの明示切替を承認する"])
        strict_confirm(["strictへの切替を承認する"])

        run_agents(["Agentへ独立回答を依頼する"])
        evidence(["Evidenceを検索・取得する"])

        agent_status(["Agent利用状態を確認する"])
        agent_validate(["Agent設定を検証する"])
        history_list(["実行履歴を一覧する"])
        history_show(["実行履歴を表示する"])
        history_delete(["指定Runを削除する"])
        history_purge(["全Runを削除する"])
        store_content(["実行内容の保存を明示許可する"])
        no_store(["記録を残さず実行する"])
    end

    user --> ask
    user --> choose_mode
    user --> clarify
    user --> progress
    user --> result
    user --> fallback
    user --> strict_confirm
    user --> store_content
    user --> no_store

    client --> ask
    client --> choose_mode
    client --> assumptions
    client --> json
    client --> store_content
    client --> no_store

    operator --> agent_status
    operator --> agent_validate
    operator --> history_list
    operator --> history_show
    operator --> history_delete
    operator --> history_purge

    ask -. "include" .-> run_agents
    ask -. "verify / strictでinclude" .-> evidence
    ask -. "曖昧な場合extend" .-> clarify
    ask -. "非対話時extend" .-> assumptions
    ask -. "Evidence利用不能時extend" .-> fallback
    ask -. "高リスク検出時extend" .-> strict_confirm
    ask -. "--jsonでextend" .-> json
    ask -. "--store-contentでextend" .-> store_content
    ask -. "--no-storeでextend" .-> no_store

    run_agents --> claude
    run_agents --> codex
    evidence --> search
    evidence --> source
```

## 2. `verify`回答生成ユースケース

```mermaid
flowchart TD
    actor["利用者 / 非対話クライアント"]

    subgraph council["Oracle Council: verify"]
        direction TD
        ask(["質問を受け付ける"])
        refine(["質問と前提を整理する"])
        halt(["追加質問または処理不能理由を返して停止する"])
        respond(["2 Agentの独立回答を得る"])
        claims(["Claimを抽出し重要度を判定する"])
        collect(["主要Claim最大5件のEvidenceを検索・取得する"])
        classify(["決定規則でClaim状態を判定する"])
        criticize(["1 Agentで統合批評する"])
        synthesize(["最終回答案を統合する"])
        audit(["別Agentで監査する"])
        revise(["回答案を1回修正する"])
        publish(["回答と検証詳細を表示する"])
        withhold(["回答を保留または失敗として返す"])
        persist(["metadataをRun単位で記録する"])
    end

    actor --> ask
    ask -. "include" .-> refine
    refine -->|"ready / ready_with_assumptions"| respond
    refine -->|"needs_clarification / unsupported / safety_blocked"| halt
    respond -->|"Responder 2件を確保できない"| withhold
    respond -. "include" .-> claims
    claims -. "include" .-> collect
    collect -. "include" .-> classify
    classify -. "include" .-> criticize
    criticize -. "include" .-> synthesize
    synthesize -. "include" .-> audit
    audit -. "changes_requiredでextend" .-> revise
    revise -. "再監査" .-> audit
    audit -->|approved| publish
    audit -->|"blocked / 2回目も未承認"| withhold
    classify -->|"criticalがunverified"| withhold
    publish -. "no-store以外include" .-> persist
    withhold -. "no-store以外include" .-> persist
    halt -. "no-store以外include" .-> persist
```

metadata記録は既定で行い、`--no-store`指定時だけ行わない。途中失敗、キャンセル、停止のRunも記録対象とする。

## 3. ユースケースとCLIの対応

| ユースケース | CLI |
|---|---|
| 質問する | `oracle ask "質問"` |
| モードを指定する | `--mode quick\|verify\|strict` |
| 非対話で実行する | `--no-interactive` |
| JSON結果を受け取る | `--json` |
| 未検証への明示切替を許可する | `--allow-unverified-fallback` |
| strictへの切替を承認する | 対話プロンプトで承認。非対話時は`--mode`未指定なら`strict_required`で停止 |
| 内容を保存する | `--store-content`。非対話時は`--yes`も必須 |
| 記録を残さない | `--no-store` |
| Agent状態を確認する | `oracle agents status` |
| Agent設定を検証する | `oracle agents validate` |
| 履歴を一覧・表示する | `oracle history list` / `oracle history show <run-id>` |
| Runを削除する | `oracle history delete <run-id>` |
| 全Runを削除する | `oracle history purge --yes` |

## 4. 図に含めないMVP対象外

- Web UI
- SQLite
- 3つ目以降の公式サポートCLI
- Voter、Quorum、再投票
- JavaScriptレンダリング、PDF、OCR、paywall資料
- 中断Runの再開
- OSレベルの強制sandbox

## 5. 未確定箇所

- `quick`の内部ユースケースはQandA J-3が未回答のため、詳細図を作らない

Q-1（strict自動提案は確認制、非対話は`strict_required`停止）、Q-2（metadata Runの履歴は`content_saved: false`付きで正常表示）、Q-3（設定は直接編集＋`agents validate`、変更は次Runから反映）は回答確定し、SPEC v0.3.2と本書へ反映済み。

