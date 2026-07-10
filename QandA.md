# Oracle Council — QandA（仕様レビュー不明点）

> SPEC.md v0.2.0 を読んで生じた疑問・確認事項をまとめたもの。  
> 回答が確定したら「回答」欄に記入し、必要であれば SPEC.md へ反映する。

---

## A. アーキテクチャ・役割分担

### A-1. 役割の割り当て方

**箇所**: §5 用語 / §9 回答生成と討論  
**疑問**:  
Clarifier・Responder・Critic・Verifier・Synthesizer・Auditor の 6 役割に対して、参加 Agent 数が 2〜4 のとき、どの Agent にどの役割を割り当てるか。  
- 割り当てはランダムか、設定ファイルで指定するか、実行時に Orchestrator が決定するか？  
- 同一 Agent が複数フェーズを連続で担う場合、前フェーズの出力がプロンプトに含まれることへの汚染対策は？

**回答**: 確定。役割はAgentへ固定せず、フェーズごとにOrchestratorが決定する。選定はランダムではなく、利用可否、`role_priority`、必要能力、設定順による決定的なルールとする。同一Agentが複数フェーズを担当してよいが、各フェーズは原則として新しいCLIプロセスまたは新しいセッションで実行し、前フェーズの会話履歴を継承しない。渡す情報は整理後の質問、匿名化回答、Claim、Evidence、説明可能な要約だけに限定する。SPEC.md §6.2、§6.5へ反映。

---

### A-2. 監査 Agent の選定方法

**箇所**: §5 / §21 未決事項  
**疑問**:  
「最終回答を作った Agent とは別の Agent が監査することを原則とする」とあるが、選定基準が未決。  
- 参加 Agent が 1 つのとき（単独回答）、監査はスキップするか、それとも同一 Agent が自己監査するか？  
- 監査スキップの場合、ユーザーへの表示はどうなるか？

**回答**: 確定。AuditorはSynthesizerとは別の利用可能Agentから、`role_priority`と設定順で選ぶ。2 Agent以上なら必ず分離する。1 Agentしか利用できない場合は同一Agentが自己監査するが、`self_audited: true`、`consensus_status: not_applicable`として「単独回答・自己監査」と明示する。監査を黙って省略しない。SPEC.md §6.3、§6.4へ反映。

---

### A-3. 各フェーズの担当 Agent の固定 vs 動的

**箇所**: §9 / §20 MVP 開発フェーズ案  
**疑問**:  
Responder フェーズでは全 Agent が独立回答する、という理解で合っているか？  
一方 Critic・Synthesizer・Auditor は「誰か 1 つの Agent」が担うのか、それとも「全員が批評して集約する」のか？  
設計の方向性によってプロンプト設計・並列化・トークン消費量が大きく変わる。

**回答**: 確定。Responder、Critic、Voterは利用可能な全Agentが担当する。Criticは全回答をまとめて1回で批評する。Claim Extractor、Verifier、Synthesizerは各1 Agent、AuditorはSynthesizerとは別の1 Agentとする。重要度`critical`のClaimはAuditorも再確認する。この担当方式をMVPの標準とする。SPEC.md §6.3へ反映。

---

## B. Evidence 収集

### B-1. Evidence 収集の手段

**箇所**: §21 未決事項  
**疑問**:  
「Evidence 収集を専用検索機能で行うか、各 AI CLI の検索機能を利用するか」は未決とあるが、実装方針として次のどれを想定するか？

1. AI CLI の組み込み検索（例: claude web search, gemini grounding）を利用する  
2. Oracle Council 自身が外部検索 API（Brave, SerpAPI, Tavily など）を叩く  
3. 両方をアダプター経由で切り替え可能にする  
4. MVP では省略し `quick` モード相当にする

方針によって依存ライブラリ・API キー管理・コストが変わる。

**回答**: 確定。選択肢3を採用するが、Oracle Council側の`EvidenceProvider`を正本とする。AI CLIの組み込み検索は補助情報として利用可能。ただしURL等をOracle Councilが直接取得し、Claim該当箇所と取得日時を記録できなければ`verified`の根拠に数えない。MVPでは`none`、`manual`、`web`のProviderインターフェースを用意し、最初の実検索サービスは交換可能にする。SPEC.md §10.1、§10.2へ反映。

---

### B-2. Evidence 収集の実行タイミング

**箇所**: §6.1 基本フロー / §10 ハルシネーション対策  
**疑問**:  
基本フローには「根拠資料を収集・照合」が「相違点・事実主張・要検証箇所を抽出」の後に来るが、  
- Claim 抽出 → Evidence 収集 → 批評 の順か？  
- それとも 批評 → Claim 抽出 → Evidence 収集 の順か？  
フロー図と §20 の Phase 順序（Phase 3: 評議会 → Phase 4: 検証）が、批評と根拠確認のどちらが先かを示しているが、批評が根拠を参照できるかどうかで品質が変わる。

**回答**: 確定。正式な順序は「独立回答 → 軽量差分スキャン → Claim抽出 → Evidence収集 → Verifier判定 → Evidence参照付き批評」とする。Evidenceなしの事前批評は独立フェーズとしては行わず、差分スキャンだけで検索クエリとClaim抽出を補助する。これによりCriticが根拠を参照できる。SPEC.md §9.1へ反映。

---

## C. タイムアウト・パフォーマンス

### C-1. タイムアウト値

**箇所**: §8.2 / §21 未決事項  
**疑問**:  
「既定のタイムアウト時間」は未決。参考として、次の単位・粒度で指定する予定か？  
- フェーズ単位（例: Responder フェーズ全体で 60 秒）？  
- Agent 単位（例: 1 Agent の 1 呼び出しで 30 秒）？  
また、`strict` モードではより長い時間が必要になる可能性があるが、モードごとに変えるか？

**回答**: 確定。Agent単位、フェーズ単位、実行全体の3段階を持つ。既定は`quick`: 90秒/120秒/5分、`verify`: 180秒/240秒/10分、`strict`: 300秒/420秒/20分（順に1呼び出し、1フェーズ、全体）。設定ファイルとCLIで変更可能にする。SPEC.md §8.4へ反映。

---

### C-2. 全体の想定所要時間

**箇所**: §6.1 基本フロー  
**疑問**:  
`verify` モードで 4 Agent が並列に動く場合、ユーザーが体感する待ち時間の目標値はあるか？  
長時間かかる場合の進捗表示（ストリーミングやプログレスバー）は MVP スコープか？

**回答**: 確定。保証値ではなく開発目標として、中央値を`quick` 90秒以内、`verify` 5分以内、`strict` 10分以内とする。MVPにフェーズ名、完了Agent数、経過時間の進捗表示を含める。トークン単位のストリーミングは将来対応。SPEC.md §12.4、§13.3へ反映。

---

## D. 合意・投票ロジック

### D-1. `agree_with_changes` の扱い

**箇所**: §11.2 / §11.3  
**疑問**:  
`agree_with_changes` は合意成立条件の「3 分の 2 以上」に `agree` と同等としてカウントするか？  
また、変更要求が反映されたかどうかの確認フローはあるか（例: Synthesizer が変更点を取り込んだ後、再投票するか）？

**回答**: 確定。`agree_with_changes`は初回投票では合意票に数えない。変更要求を統合し、Synthesizerが1回だけ修正、Auditor確認後に再投票する。再投票で`agree`になった票だけ合意票へ数える。再投票不能または重大問題が残る場合は`disagree`相当とする。SPEC.md §11.3へ反映。

---

### D-2. `critical_issue` の定義

**箇所**: §11.2 / §11.3  
**疑問**:  
`critical_issue: true` を返す基準が明記されていない。  
- Agent が自己判断で設定するのか？  
- Orchestrator がルールに基づいて付与するのか？  
- 「contradicted な主要 Claim が存在する」などの客観指標と連動するのか？

**回答**: 確定。Agentが返す自由なbooleanを正本にしない。Agentは構造化された`issues`を返し、OrchestratorがIssue種別、severity、Claim状態、監査結果からCritical Issueを導出する。`critical` Claimの未確認・矛盾、主要Claimの矛盾、捏造引用、危険な欠落、誤前提、致命的論理矛盾、インジェクション影響、安全違反を基準とする。SPEC.md §11.4へ反映。

---

### D-3. 「主要 Claim」の定義

**箇所**: §11.3  
**疑問**:  
「主要な Claim が `contradicted` ではない」という合意条件があるが、「主要」の判定基準が不明。  
- `importance` フィールドの値（例: `critical`）で決まるのか？  
- 誰が `importance` を決めるのか（Claim 抽出 Agent か Verifier か）？

**回答**: 確定。Claimの`importance`は`critical`、`major`、`minor`。主要Claimは`critical`または`major`を指す。Claim Extractorが初期値を付け、Verifierが確定し、Auditorが異議を出せる。`critical`は安全・健康・法律・重大損失、`major`は中心結論、`minor`は補足と定義する。SPEC.md §10.4へ反映。

---

## E. ストレージ・データモデル

### E-1. JSON vs SQLite

**箇所**: §3.1 / §19.5 / §21 未決事項  
**疑問**:  
「JSON または SQLite」とあるが、両方を同時にサポートするか、選択式にするか？  
MVP で JSONL を先行実装し、SQLite をオプションとする方針が現実的と思われるが、確認したい。

**回答**: 確定。MVPはJSONLのみ。`StorageBackend`で抽象化し、`data/runs.jsonl`へ追記型イベントを保存する。完了イベントには最終スナップショットを含める。SQLiteはデータモデルとJSONスキーマが安定した後に追加する。SPEC.md §15.1へ反映。

---

### E-2. AgentExecution の `phase` フィールド

**箇所**: §15.2  
**疑問**:  
`phase` に入る値（Clarifier / Responder / Critic / Verifier / Synthesizer / Auditor など）は  
Enum として仕様に列挙するか？ 同一 Agent が複数フェーズに登場する場合、レコードは 1 行か複数行か？

**回答**: 確定。`phase`はEnumとして`clarify`、`respond`、`claim_extract`、`verify`、`criticize`、`synthesize`、`audit`、`vote`を定義する。AgentExecutionは「1 Agentの1呼び出し」につき1レコード。同一Agentが複数フェーズを担当すれば複数レコードになる。SPEC.md §15.5へ反映。

---

### E-3. Run.status の値

**箇所**: §15.1  
**疑問**:  
`status` フィールドの取りうる値が未定義。  
例: `running` / `completed` / `failed` / `aborted` など。  
受け入れ条件（§19）で使われる `result_classification` の値（一部検証済みなど）も同様に列挙が必要では？

**回答**: 確定。Run.statusは`pending`、`running`、`completed`、`partial`、`failed`、`cancelled`。`result_classification`は`verified`、`partially_verified`、`unverified`、`conflicting`、`withheld`。合意状態は別フィールドで`reached`、`not_reached`、`not_applicable`とする。SPEC.md §15.2〜§15.4へ反映。

---

## F. セキュリティ・プロンプトインジェクション

### F-1. Webページ内の命令文への対策

**箇所**: §17  
**疑問**:  
「Web ページ内の命令文をシステム命令として扱わない」という要件があるが、  
Evidence 収集で取得したページ本文をそのままプロンプトへ渡す場合、プロンプトインジェクション対策の具体的な実装方針は？  
- サンドボックス化されたコンテキストで処理する？  
- ページ本文のタグを除去・エスケープする？  
- Evidence の要約のみをプロンプトに渡す？

**回答**: 確定。HTML除去だけに頼らず、Evidenceを信頼できない外部データとして隔離する。http/https限定、localhost・プライベートIP拒否、能動要素除去、Claim該当の短い抜粋だけを構造化JSONで渡す、抜粋内命令へ従わない、Evidenceからツール実行を許さない、件数・長さ制限、本文ハッシュ保存を組み合わせる。SPEC.md §16.2へ反映。

---

### F-2. ログへの生プロンプト保存の基準

**箇所**: §17 / §18  
**疑問**:  
「生のプロンプトや機密情報を既定で公開ログへ出さない」とあるが、  
- デバッグ用に詳細ログを有効化するオプションはあるか？  
- その場合、ユーザーへの警告（「詳細ログには質問内容が含まれます」）は必要か？

**回答**: 確定。生プロンプトは既定で保存しない。`--log-level debug --include-prompts`の明示指定時だけ保存し、対話時は警告、非対話時は追加で`--yes`を必須とする。詳細ログでも認証情報はマスクし、ローカル保存・所有者限定権限を基本とする。SPEC.md §17.2へ反映。

---

## G. CLI・UX

### G-1. デフォルトモード

**箇所**: §12 / §21 未決事項  
**疑問**:  
「既定モードを `quick` と `verify` のどちらにするか」は未決。  
判断に必要な情報として：  
- 初期ユーザーが最も使うシナリオはどちらか？  
- `verify` をデフォルトにした場合、Evidence 収集が未実装の MVP フェーズでの扱いはどうするか？

**回答**: 確定。既定は`verify`。EvidenceProviderが利用できない場合は暗黙に`quick`へ落とさない。対話時は切替確認、非対話時は`verification_unavailable`で終了し、`--allow-unverified-fallback`指定時のみ`quick`へ切り替える。MVPリリース条件にEvidenceProviderを含める。SPEC.md §12.2、§13.2へ反映。

---

### G-2. `--no-interactive` での仮定の自動生成

**箇所**: §13.2  
**疑問**:  
「合理的な仮定を明示して処理する」とあるが、仮定の生成は Orchestrator 内蔵ロジックか、あるいは AI CLI に委ねるか？  
仮定の内容が実行ごとに異なると再現性が失われる可能性があるが、許容するか？

**回答**: 確定。決定的な既定値・質問種別テンプレートを先に使い、不足分だけClarifier Agentが構造化仮定を生成する。高リスクまたは`critical`な不足情報は自動仮定せず、終了コード2で`needs_clarification`を返す。AI仮定は保存し、低ランダム性やseed対応で変動を抑える。SPEC.md §7.5へ反映。

---

### G-3. JSON 出力スキーマ

**箇所**: §13.3  
**疑問**:  
JSON 出力のスキーマ（フィールド一覧）が未定義。  
§15 のデータモデルをそのまま返すのか、表示用に整形した別構造にするのか？  
GUI 連携や自動化を想定するなら早期にスキーマを固定した方が良いと考える。

**回答**: 確定。内部モデルをそのまま返さず、外部連携用の安定スキーマを定義する。トップレベルに`schema_version`、`run_id`、`status`、`mode`、`question`、`participants`、`answer`、`claims`、`evidence`、`votes`、`warnings`、`errors`、`timing`を持つ。初期版は`schema_version: 1.0`。SPEC.md §14へ反映。

---

## H. 開発・運用

### H-1. Python バージョン・依存ライブラリ方針

**箇所**: §16 推奨ディレクトリ構成（`pyproject.toml`）  
**疑問**:  
`pyproject.toml` が前提とされているが、最低 Python バージョン・パッケージマネージャー（pip / uv / poetry）は確定しているか？  
また、外部ライブラリの利用方針（なるべく標準ライブラリのみ、vs 積極的に使う）は？

**回答**: 確定。最低Python 3.11、`pyproject.toml`を使用。開発時は`uv`推奨、利用者向けにpipもサポートする。標準ライブラリ縛りにはせず、Typer、Pydantic、httpx、PyYAML、pytest等、効果が明確な依存だけを採用する。SPEC.md §18.1へ反映。

---

### H-2. テスト戦略

**箇所**: §16（tests/unit/ tests/integration/）  
**疑問**:  
AI CLI の呼び出しをモックする方針はあるか？  
実際の CLI 呼び出しが必要な統合テストはどの環境（CI/CD）で実行することを想定するか？

**回答**: 確定。通常CIは`FakeAgentAdapter`と`FakeEvidenceProvider`を使い、実AI・有料APIを呼ばない。Adapter Contract Test、固定fixture、Fakeによる統合テストをPR必須にする。Live Integration Testは`live`マーカーを付け、ローカルまたはSecrets設定済みの手動・定期Workflowだけで実行する。SPEC.md §18.2へ反映。

---

### H-3. ライセンス

**箇所**: §21 未決事項  
**疑問**:  
MIT / Apache-2.0 / AGPL など、候補はあるか？  
AI CLI のライセンス条件（例: 商用利用制限）が Oracle Council のライセンス選定に影響する可能性がある。

**回答**: 確定。Oracle Council本体はMIT License。AI CLI、検索API、取得資料は別の利用規約・著作権に従い、MIT Licenseには含まれない。サービス固有の商用利用条件等は利用者が確認する旨をREADMEにも記載する。SPEC.md §18.3へ反映。

---

## I. スコープ・将来計画

### I-1. Phase 間の実装順序

**箇所**: §20 MVP 開発フェーズ案  
**疑問**:  
Phase 1〜5 の順番は実装順序として確定か？  
Phase 2（質問整理）は Phase 1（アダプター基盤）より先に着手できそうだが、意図的に後に置いているか？

**回答**: 確定。旧Phase順序は改訂する。Phase 0でデータ契約、Fake Adapter、JSONL、CLI骨格を作り、Phase 1で質問整理、Phase 2で実Agent実行、Phase 3でClaim/Evidence、Phase 4で評議会、Phase 5でUXと品質を実装する。質問整理は早期着手するが、最初にFakeを含む共通契約を用意する。SPEC.md §21へ反映。

---

### I-2. Web UI のリポジトリ配置

**箇所**: §21 未決事項  
**疑問**:  
「Web UI を同一リポジトリに含めるか」は未決。モノレポにする場合のディレクトリ構成への影響を先に考慮しておく必要があるか？

**回答**: 確定。将来のWeb UIは同一リポジトリの`web/`に置くモノレポ方針とする。PythonコアとWeb UIの境界はJSONスキーマで分離する。開発・リリース周期が独立する必要が生じた時点で別リポジトリ化を再検討する。SPEC.md §19へ反映。

---

*最終更新: 2026-07-10 — 全23問回答済み*
