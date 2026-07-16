# Oracle Council — QandA（仕様レビュー不明点）

> SPEC.md v0.2.0 を読んで生じた疑問・確認事項をまとめ、Critical項目の回答をSPEC.md v0.3.0へ反映したもの。
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

**補足 (v0.3.0)**: 自己監査は廃止。SPEC.md §6.4で「1 Agent以下は回答不能」に変更されたため、`self_audited`フィールドは不要になった。本回答のうち自己監査の記述は失効。

---

### A-3. 各フェーズの担当 Agent の固定 vs 動的

**箇所**: §9 / §20 MVP 開発フェーズ案  
**疑問**:  
Responder フェーズでは全 Agent が独立回答する、という理解で合っているか？  
一方 Critic・Synthesizer・Auditor は「誰か 1 つの Agent」が担うのか、それとも「全員が批評して集約する」のか？  
設計の方向性によってプロンプト設計・並列化・トークン消費量が大きく変わる。

**回答**: 確定。Responder、Critic、Voterは利用可能な全Agentが担当する。Criticは全回答をまとめて1回で批評する。Claim Extractor、Verifier、Synthesizerは各1 Agent、AuditorはSynthesizerとは別の1 Agentとする。重要度`critical`のClaimはAuditorも再確認する。この担当方式をMVPの標準とする。SPEC.md §6.3へ反映。

**補足 (v0.3.0)**: J-1の採用により「全Agentが批評・投票」は廃止。MVPはResponder 2、Critic 1、Voterなしに変更（SPEC.md §6.3）。本回答のうち全員批評・Voterの記述は失効。

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

## J. 呼び出し回数・トークン・コスト

### J-1. 1 Runあたりの呼び出し上限

**重要度**: Critical
**箇所**: §6.3 MVPの担当方式 / §8.3 再試行 / §9.1 基本フロー / §11.3 再投票
**疑問**: 4 Agentの`verify`では、Clarifierを除いても通常時に最大16回（Responder 4 + Claim Extractor 1 + Verifier 1 + Critic 4 + Synthesizer 1 + Auditor 1 + Voter 4）のAI CLI呼び出しが必要になる。Clarifierを使えば17回、修正・監査・再投票まで行えばさらに6回増える。各呼び出しの再試行も含めると、上限・料金・待ち時間が決まらない。

- モード別の最大AI呼び出し回数をいくつにするか？
- 上限到達時は未実行フェーズを棄権扱いにするのか、Runを`partial`にするのか？
- 「差分の軽量スキャン」はローカル処理か、追加のAI呼び出しか？

**実装への影響**: 呼び出し予算、タイムアウト、進捗分母、受け入れテストを定義できない。現状の「1回だけ再試行」はRun全体の上限になっていない。
**現状の問題 / 曖昧さ**: 全AgentがResponder、Critic、Voterを担当するため、4 Agentでは通常17回、修正時23回となる。再試行を加えたRun全体の上限もない。

**推奨案 / 具体的な仕様**: MVPの既定参加数を2 Agentとし、全員批評と独立した投票フェーズを廃止する。標準`verify`はResponder 2、Claim Extractor 1、Verifier 1、Critic 1、Synthesizer 1、Auditor 1の7回とする。Clarifierは必要時だけ1回、修正はSynthesizerとAuditorを各1回だけ追加できる。したがって通常7回、質問整理あり8回、修正込み最大10回とする。AIによる差分スキャン、再投票、AIによるコンテキスト要約は行わない。各呼び出しの一時エラー再試行はRun全体で2回まで、同一Executionは1回までとし、再試行を含む絶対上限を12回とする。上限到達時は新規Executionを開始せず、回答案が監査済みなら`partial`、それ以外は`failed`とする。`quick`は別途J-3で確定する。

**採用理由 / 設計思想との整合性**: 4者投票より、独立回答、外部Evidence、別Agent監査にコストを集中できる。Agent数ではなく検証工程を価値の中心に置く。

**SPEC.md修正文**: §6.3、§9.1、§11を「MVPでは2 Agentを既定とし、`verify`のAI呼び出しは通常7回、条件付きClarifierを含め8回、修正込み10回、再試行込み12回を上限とする。Criticは1 Agent、Voterフェーズと再投票はMVP対象外とする。Auditorの判定を最終ゲートとし、`consensus_status`はMVPでは`not_applicable`とする。」へ変更する。

**優先度**: P0

---

### J-2. トークン予算と入力縮約の契約

**重要度**: Critical
**箇所**: §6.5 フェーズ間の汚染対策 / §8.3 再試行 / §9.4 批評 / §22 未決事項
**疑問**: 全回答、全Claim、全Evidenceを各Criticへ渡すため、Agent数とEvidence数に比例して同じ入力を繰り返し消費する。`CONTEXT_OVERFLOW`時の「要約」は、何を残し、誰が、何トークンまで、追加呼び出しなしで行うのか？

- Agent・フェーズ・Run単位の入力/出力トークン上限と概算料金上限を持つか？
- 切り詰めの優先順位は`critical` Claim、`major` Claim、一次資料、回答本文の順でよいか？
- CLIがusageを返さない場合、文字数から推定するか、`unknown`として予算判定から除外するか？

**実装への影響**: 4 CLI間で公平なコンテキストを保証できず、コスト暴走と再現不能な切り詰めが起きる。
**現状の問題 / 曖昧さ**: 全回答・全Evidenceを複数Agentへ重複投入する一方、予算、計測方法、縮約順序がない。

**推奨案 / 具体的な仕様**: `estimated_tokens = max(Unicode code point数, ceil(UTF-8 byte数 / 4))`を全Adapter共通の保守的推定値とする。CLIがusageを返した場合は実測値も保存するが、予算判定には推定値を使う。1 Executionは入力16,000、出力4,000推定token、1 Runは入力96,000、出力24,000推定tokenを上限とする。上限は設定で小さくできるが、CLIから得たcontext limitを超える値にはできない。

縮約は追加AI呼び出しを使わず、次の順で決定的に行う。(1) 重複Evidenceを`content_hash`で除去、(2) HTML等の非本文を除去、(3) `minor` Claimを除外、(4) 各EvidenceをClaim該当抜粋1,200文字まで、1 Claimあたり2件までに制限、(5) 各独立回答を「結論・前提・Claim参照・不確実性」の構造化出力に限定し本文6,000文字まで、(6) それでも超える場合は`major`をimportance、回答内出現数、claim_idの順で残す。`critical` Claimとその反証Evidenceは切り捨てない。収まらなければ`BUDGET_EXCEEDED`でRunを`failed`にする。Run残予算が1 Executionの予約出力分4,000未満なら開始しない。

**採用理由 / 設計思想との整合性**: モデル依存tokenizerを必須にせず実装でき、重要な検証情報を落とさない。AI要約を削るためコストと非決定性も増えない。

**SPEC.md修正文**: §8へ上記の推定式、Execution/Run予算、決定的縮約順、`BUDGET_EXCEEDED`を追加する。

**優先度**: P0

---

### J-3. `quick`の実行グラフ

**重要度**: Major
**箇所**: §12.1 `quick` / §6.3 MVPの担当方式
**疑問**: `quick`は「簡易比較・統合回答」とだけあり、Claim Extractor、Critic、Auditor、Voterのどれを実行するか不明。`quick`専用のフェーズ一覧、呼び出し数、合意判定方法を固定する必要があるのではないか？
**実装への影響**: モードごとの処理分岐と性能テストが書けない。
**回答**: **AUTO_DECIDED**
`quick` モード専用の実行グラフと処理フローを以下の通り確定する。
1. **フェーズ一覧と実行順（呼び出し数）**:
   フェーズは `respond` (スロット0) -> `respond` (スロット1) -> `compare` -> `synthesize` の順で実行される（合計4回のエージェント呼び出し）。
   外部Evidence収集 (`evidence_collect`)、Claim抽出 (`claim_extract`)、Claim検証 (`verify`)、および最終監査 (`audit`) は行わない。
2. **エージェント割り当てと制約**:
   `assignment.py` において、`build_execution_plan(..., mode)` を追加し、`quick` モード用のアサインメント `_QUICK_PLAN_ASSIGNMENTS` を定義する。
   `quick` では監査が存在しないため、`synthesize` フェーズに auditor との分離制約は適用しない（Responder 2名の独立性は維持する）。
3. **合意判定と Run 分類**:
   外部検証を行わないため、Run の最終分類 (`ResultClassification`) は常に `ResultClassification.UNVERIFIED` ("unverified") とし、`oracle_exit_code = 0` (成功) で終端する。回答保留 (`withheld`) は発生しない。
4. **出力メタデータ**:
   出力結果に `external_verification: false` を含める。また、CLI JSONやイベント、RunMetadataRecord に `mode` フィールドを保持し、進捗表示も `quick` に適合した4ステップ形式にする。

---

### J-4. Clarifier 2ラウンドと呼び出し上限8回の整合

**重要度**: Major
**箇所**: §6.3 呼び出し上限 / §7.4 対話ルール
**疑問**: §7.4は追加質問を最大2ラウンド許可するが、§6.3の上限は「Clarifierを含め8回」でClarifier分は1回しか見込んでいない。2ラウンド目の追加質問は(a)2回目のClarifier呼び出しが必要（上限9回になる）、(b)1回目の構造化出力から決定的に生成する、のどちらか？(b)の場合、1回目の呼び出しで2ラウンド分の質問候補を先に出させる出力スキーマにするのか？
**実装への影響**: 呼び出し予算の絶対上限12回の内訳と、Clarifierの出力スキーマ設計が変わる。
**回答**: **AUTO_DECIDED (2026-07-15)**
非対話モード（CLI既定）では、Clarifier Agent呼び出しは最大1回（1ラウンド）とする。対話モードで2ラウンド目の質問整理が発生し追加の Clarifier AI 呼び出しを行う場合は、`TokenBudget` の残り予算枠（最大12回）の範囲内で実行する。1回の Clarifier 呼び出しにおける出力スキーマは、その時点で不足している情報に対する質問リスト（最大3問）と仮定案を返すように設計する。これにより、呼び出し制限との整合性を維持する。

---

### J-5. トークン推定式とCritic/Synthesizer入力予算の数値矛盾

**重要度**: Critical
**箇所**: §8.6 トークン予算と縮約 / §10.2 Evidence上限
**疑問**: 推定式`max(Unicode code point数, ceil(UTF-8 byte数 / 4))`は、日本語でも英語でも実質「1文字=1token」になる（ASCIIでもcode point数が常にbyte数/4以上のため）。一方、縮約を最後まで適用した後の理論上のCritic入力は、回答6,000文字×2＋Evidence 1,200文字×10＝約24,000文字≒24,000推定tokenで、1 Executionの入力上限16,000を恒常的に超える。Synthesizer入力（回答＋Claim＋Evidence＋批評）はさらに大きい。

- §8.6と§10.2の各上限（回答6,000文字、Evidence 10件×1,200文字）と入力16,000 tokenのどちらを正とするか？
- 推定式は意図的に4倍保守的（英語で実トークンの約4倍）だが、その分予算を大きく取るのか、式を`ceil(byte数/2)`等へ緩めるのか？
- 上限超過時にstep 6（major除外）だけで16,000へ収まらないケース（critical Claimが多い場合）は`BUDGET_EXCEEDED`で`failed`になるが、それは正常な質問でも起きうる。

**実装への影響**: 現数値のままでは`verify`の批評・統合フェーズが構造的に予算超過し、正常系でRunが`failed`する。数値を確定しないと縮約ロジックのテスト期待値が書けない。
**回答**: 確定。入力上限を上げるのではなく、Criticへ渡す情報量を削る。「Criticへ全部載せる」設計を廃止し、フェーズ別の入力正規化を導入する。(1) Critic/Synthesizerへ渡す各回答は最大3,000文字へ正規化、(2) Evidence抜粋は1件最大500文字、`content_hash`で重複除去後にRun全体で最大8件（Claimごとの割当をやめる）、(3) Criticへは`critical`と`major`のClaimだけを渡し、`minor`はVerifier判定結果のみ、(4) 入力予算は12,000推定tokenを目標、16,000を絶対上限とする。超過時は回答の要約より先にEvidenceから削る。Responderの6,000文字上限とVerifierの1,200文字×2件/Claimは従来どおり（Verifier入力はClaim単位で小さいため）。SPEC.md §8.6、§9.4へ反映。

---

## K. Evidence検証の現実性

### K-1. `verified` / `supported`判定の機械的基準

**重要度**: Critical
**箇所**: §10.5 Claim状態 / §10.7 情報源の優先順位 / §10.8 出典確認
**疑問**: 「高品質」「有力」「適切」の判定が自然言語のままで、同じEvidenceから異なる状態になり得る。例えば、一次資料1件で`verified`にできるのか、独立した2資料が必要か、公式発表が自社製品の効果を述べる場合をどう扱うか？

- `source_type`、独立性、直接性、鮮度、支持/反証の組み合わせを判定表にするか？
- Evidenceが1件も取得できない場合と、取得したが該当記述がない場合を区別するか？
- Verifierの自由判断を許す場合、confidenceと判定理由を必須にするか？

**実装への影響**: 中核機能の結果が再現不能で、Contract Testと「検証済み」という表示の信頼性が成立しない。
**現状の問題 / 曖昧さ**: `verified`の「高品質」、`supported`の「有力」が判定不能で、同じ資料でも結果が変わる。

**推奨案 / 具体的な仕様**: Evidenceを`authority`（`primary_authoritative` / `official_subject` / `independent_expert` / `reputable_secondary` / `other`）、`directness`（`direct` / `indirect`）、`stance`（`supports` / `contradicts` / `neutral`）、`freshness`（`current` / `stale` / `unknown`）で分類する。独立性はregistrable domainと原資料IDが両方異なる場合だけ認め、転載は同一資料とする。

`verified`は、`direct`かつ`current`で、(a)法令・規格・公式仕様などの`primary_authoritative`が1件、または(b)`independent_expert`以上の相互独立な支持資料が2件あり、同等以上の反証が0件の場合に限る。`official_subject` 1件だけで確認できるのは、発売日、価格、提供条件など当事者が正本となる事実だけとし、効果・安全性・優位性には使わない。`supported`は、`direct`かつ`current`の`official_subject`、`independent_expert`、`reputable_secondary`が1件以上あるが`verified`条件を満たさず、同等以上の反証が0件の場合とする。同等以上の支持と反証があれば`conflicting`、反証だけが`verified`条件を満たせば`contradicted`、それ以外は`unverified`とする。

鮮度期限は、価格・在庫24時間、現職・サービス状態7日、製品仕様・提供条件30日、法令は施行日と取得日に有効性確認必須、その他は期限なしとする。`published_at`不明の時点依存資料は`freshness: unknown`で`verified`に使わない。VerifierはEvidence分類と規則適用だけを構造化出力し、最終状態はOrchestratorが決定する。

**採用理由 / 設計思想との整合性**: 真偽の最終決定をAgentの雰囲気的判断から決定規則へ移し、Evidence中心の設計をテスト可能にする。

**SPEC.md修正文**: §10.5〜§10.8へ上記Enum、独立性、状態決定表、鮮度期限を追加し、Claim状態はOrchestratorが決定すると明記する。

**優先度**: P0

---

### K-2. Web取得で扱える資料範囲

**重要度**: Critical
**箇所**: §10.2 EvidenceProvider / §10.8 出典確認 / §16.2 インジェクション対策
**疑問**: JavaScript描画、PDF、画像PDF、ログイン必須、Cookie同意、paywall、robots.txt、巨大文書、リダイレクト、非UTF-8をMVPでどこまで扱うか？取得不能理由のEnumと、ブラウザ利用の有無も未定義。
**実装への影響**: 「Oracle Councilが直接アクセス」の受け入れ範囲が決まらず、実検索Providerの選定もできない。
**回答**: 確定。多くはSPEC §4の既存MVP対象外とSafeHttpFetcherの実装で既に決着している。

- JavaScriptレンダリング、PDF、OCR、paywall資料: §4で明示的にMVP対象外。取得不能理由は`CONTENT_TYPE_BLOCKED`（許可Content-Typeは`text/*`、`application/json`のみ、§16.2）
- 巨大文書: 展開後2MB上限で`RESPONSE_TOO_LARGE`（§16.2、実装済み）
- リダイレクト: 最大3回、各hopでURL・DNS・IP再検証（§16.2、実装済み）
- 非UTF-8: デコード失敗は`FETCH_FAILED`として拒否（実装済み。文字化けした本文をEvidenceとして採用しない）
- ログイン必須・Cookie同意: 専用の検出ロジックは持たない。多くは非200応答またはHTML/JSON以外のContent-Typeとして自然に弾かれる。MVPでは追加の検出を行わず、既存のContent-Type/status処理へ委ねる
- robots.txt: MVPでは尊重しない。Oracle Councilは能動的なクロールを行わず、Claimに対応する特定URLだけを1件ずつ取得するため、汎用クローラーへのrobots.txt遵守要件は適用対象外とする。将来、検索結果由来のURL数が増える場合に再検討する
- ブラウザ利用: MVPでは行わない（§4のJSレンダリング対象外と整合）

**SPEC.md修正文**: §10.2・§10.8へ上記の取得不能理由の対応表を追記する。

---

### K-3. 検索停止条件とEvidence上限

**重要度**: Critical
**箇所**: §10.2 EvidenceProvider / §16.2 Evidence件数制限 / §22 未決事項
**疑問**: Claimごとの検索クエリ数、検索結果数、取得数、抜粋長、総バイト数、同一ドメイン上限、検索停止条件が未定義。反証検索を必須にするかも不明。
**実装への影響**: Evidenceコスト、所要時間、網羅性、テストfixtureの規模を確定できない。これはPhase 3開始時ではなくMVP成立性を判断する前に決める必要がある。
**現状の問題 / 曖昧さ**: 検索回数と停止条件がなく、Claim数に比例して費用と時間が無制限に増える。

**推奨案 / 具体的な仕様**: MVPで検索するのは`critical`と`major`を合わせて最大5 Claimとし、`critical`、`major`、claim_idの順で選ぶ。1 Claimにつき検索クエリ2本（中立クエリ1、反証クエリ1）、各クエリ上位5件、fetch成功3文書までとする。Run全体では検索10回、fetch 12文書、展開後本文24MB、Evidence 10件、Evidence処理時間90秒を上限とする。1文書は展開後2MB、抜粋は1,200文字までとする。

各Claimは、K-1の`verified`または`contradicted`が確定した時点、2クエリを消費した時点、fetch成功3件、Run上限、90秒のいずれかで停止する。中立クエリだけで`verified`相当になっても、反証クエリを1回実行して反証0件を確認してから確定する。収集上限到達で判定不能のClaimは`unverified`とし、`EvidenceErrorCode.BUDGET_EXHAUSTED`を付ける。90秒到達は`EvidenceErrorCode.EVIDENCE_TIMEOUT`とする。`critical`が`unverified`なら回答を`withheld`、`major`なら未確認表示または削除する。

**採用理由 / 設計思想との整合性**: 支持資料だけを集める偏りを防ぎながら、検索コストと待ち時間を固定できる。

**SPEC.md修正文**: §10.2へClaim選択順、クエリ/fetch/byte/time上限、反証検索必須、停止疑似コードを追加する。

**優先度**: P0

---

### K-4. Claim分割とEvidence対応の粒度

**重要度**: Major
**箇所**: §5 Claim定義 / §10.3 Claim抽出 / §10.6 Evidence情報
**疑問**: 複数の事実を含む文、条件付き主張、時点依存の主張をどう原子化するか？1つのEvidenceが複数Claimを支持する場合、現行の`Evidence.claim_id`では複製するのか、多対多にするのか？
**実装への影響**: Claim数が呼び出し・検索量を左右し、Evidence重複と判定不整合が生じる。
**回答**: 未回答。

---

### K-5. `critical` Claimが検索上限5件を超えた場合の必然的`withheld`

**重要度**: Major
**箇所**: §10.2 Evidence上限 / §10.5 Claim状態 / §11.3 回答公開条件
**疑問**: 検索対象は`critical`＋`major`で最大5 Claim、検索されなかったClaimは`unverified`、そして「`critical`が`unverified`なら回答を`withheld`」。つまり`critical` Claimが6件以上抽出された質問は、Evidence収集の内容に関係なく必ず`withheld`になる。

- Claim Extractorに`critical`の件数上限（例: 統合・分割で5件以内へ正規化）を課すか？
- それとも`critical`に限り検索予算を拡張する（`major`を後回しにする）か？
- 「criticalが多すぎて検証しきれない」ことを理由とする`withheld`は、ユーザーへどう説明するか？

**実装への影響**: 医療・法律など`critical`が多くなりがちな分野（strictの自動提案対象）ほど回答不能率が上がり、製品価値と矛盾する。
**回答**: 未回答。

---

### K-6. `freshness`判定の決定的手順

**重要度**: Major
**箇所**: §10.5 鮮度期限
**疑問**: 鮮度期限（価格24時間、現職7日、仕様30日、その他期限なし）はClaim側の分類に依存するが、Claimがどの鮮度カテゴリに属するかを誰がどう決めるかが未定義。また「期限なし」カテゴリの資料で`published_at`が不明な場合、`freshness`は`current`か`unknown`か？§10.5は「時点依存資料でpublished_at不明ならunknown」とだけ定めており、非時点依存資料の既定値がない。`verified`は`current`必須のため、この既定値がClaim状態を直接左右する。
**実装への影響**: K-1の決定表fixtureに鮮度カテゴリの割り当て主体と既定値がないと、100%一致の受け入れ条件が書けない。
**回答**: 未回答。

---

### K-7. Evidence処理90秒とfetch上限の整合・並列度

**重要度**: Minor
**箇所**: §10.2 Run上限 / §16.2 SafeHttpFetcher
**疑問**: fetchは1文書あたり最大20秒（全体タイムアウト）で、Run上限は12文書・Evidence処理90秒。逐次実行なら遅いサイトが4〜5件あるだけで90秒を使い切り、12文書の上限に到達し得ない。fetchの並列度（同時接続数、同一ドメイン同時1接続などの礼儀）を定めるか？90秒はwall-clockか、fetch時間の合計か？
**実装への影響**: EvidenceProviderの実装方式（asyncio.gatherの同時数）とEvidence網羅性が変わる。
**回答**: 未回答。

---

## L. 4 CLI Adapterの入出力契約

### L-1. 初期対応する「4 CLI」の定義

**重要度**: Critical
**箇所**: §2.4 AI CLI交換可能 / §8.1 設定例 / §19 ディレクトリ構成 / §22 未決事項
**疑問**: 仕様上確定しているのはClaude、Codex、Geminiと`custom`であり、4つ目は未決事項になっている。一方、MVP目標と受け入れ条件は「最大4 Agent」で、4種類の実CLI対応を要求しているようにも読める。

- MVPは「1実Adapter + Fake/Customで最大4 Agent」か、「4種類の実Adapter」か？
- 同じCLIを異なるモデル・設定で複数Agentとして登録してよいか？
- `custom`が満たす必須機能は何か？

**実装への影響**: MVPの工数と受け入れ条件が大幅に変わる。
**現状の問題 / 曖昧さ**: 「最大4 Agent」と「4種類の実CLI対応」が混同され、Phase 2は1実Adapter、ディレクトリ例は3実Adapter、未決事項は4つ目を要求している。

**推奨案 / 具体的な仕様**: MVPで公式サポートする実CLIはClaude CodeとCodex CLIの2種類とする。Gemini CLIはAdapter Contractのfixtureとexperimental実装までを許容するが、MVP受け入れ条件に含めない。1 Runの既定参加は異なる2 CLIを1 Agentずつとする。同一CLIをモデル違いで複数登録することは許可するが、独立Agent数ではなく同一`adapter_family`として表示する。Orchestratorと設定スキーマは最大4 Agentを扱える状態を維持する。`custom`は外部コマンドを直接指定する機能ではなく、Python entry pointで登録され、L-2のContract Testに合格したAdapterだけを読み込む。

**採用理由 / 設計思想との整合性**: 2つの独立回答があればEvidence検証と相互チェックの価値を実証できる。4 CLI固有差の吸収を初回リリース条件にすると、検証機能よりAdapter保守が主作業になる。

**SPEC.md修正文**: §3と§20.2を「MVPはClaude CodeとCodex CLIを公式サポートし、既定2 Agent、設定上最大4 Agentを実行できる。Gemini CLIと追加AdapterはMVP後にContract Test合格を条件として追加する。」へ変更する。

**優先度**: P0

---

### L-2. 共通Adapter Contract

**重要度**: Critical
**箇所**: §8 Agent管理 / §18.2 Contract Test / Phase 2 共通Agentインターフェース
**疑問**: 各CLIで異なる、入力方法（引数/stdin/file）、出力（text/JSON/JSONL）、モデル指定、system prompt、seed、temperature、最大トークン、タイムアウト、終了コード、認証確認、非対話フラグ、色・進捗出力の扱いが未定義。

- Adapterへの共通入力・出力モデルとcapabilities schemaを定義するか？
- stdoutは機械出力専用とし、stderrを診断用とみなすか？
- CLIバージョンの検出、対応範囲、未知バージョン時の挙動をどうするか？

**実装への影響**: `role_priority`の「必要能力」を判定できず、Contract Testの期待値も書けない。
**現状の問題 / 曖昧さ**: CLIごとの入力、構造化出力、能力、認証、エラー分類、バージョン差を正規化する契約がない。

**推奨案 / 具体的な仕様**: `AgentAdapter`は次の4メソッドだけを公開する。

```python
class AgentAdapter(Protocol):
    async def probe(self) -> ProbeResult: ...
    def capabilities(self) -> AgentCapabilities: ...
    async def execute(self, request: AgentRequest) -> AgentResult: ...
    async def cancel(self, execution_id: str) -> None: ...
```

`AgentRequest`必須項目は`execution_id`、`phase`、`system_instructions`、`input`、`output_schema`、`timeout_ms`、`max_output_tokens`、`working_directory`。`AgentCapabilities`は`adapter_family`、`adapter_version`、`cli_version`、`supported_phases`、`structured_output`、`max_context_tokens`、`supports_seed`、`supports_read_only`、`supports_no_tools`。`AgentResult`は`status`、`structured_output`、`raw_output_hash`、`usage`、`exit_code`、`started_at`、`finished_at`、`error_code`、`error_summary`を持つ。

入力はUTF-8のstdinまたはAdapter管理の一時ファイル、構造化結果はstdoutからAdapterが抽出し、stderrは診断専用とする。Orchestratorへ返す前にPydantic検証とsecret redactionを行う。未知のCLIバージョン、`supports_no_tools=false`、`supports_read_only=false`、schema不適合はfail closedとする。共通`error_code`は`AUTH_REQUIRED`、`QUOTA_EXCEEDED`、`RATE_LIMITED`、`TIMEOUT`、`CONTEXT_OVERFLOW`、`INVALID_OUTPUT`、`COMMAND_NOT_FOUND`、`UNSUPPORTED_VERSION`、`CANCELLED`、`EXECUTION_ERROR`。`shell=True`は禁止する。

**採用理由 / 設計思想との整合性**: CLI固有のフラグや出力をAdapter内へ閉じ込め、OrchestratorをAgent追加から独立させる最小契約である。

**SPEC.md修正文**: §8へ上記Protocolとモデルを追加し、Adapter Contract Testでprobe、成功、全error_code、timeout/cancel、schema違反、権限capabilityを検証すると記載する。

**優先度**: P0

---

### L-3. 構造化出力失敗時の回復

**重要度**: Major
**箇所**: §8.2 `INVALID_OUTPUT` / §16.1 Pydantic検証
**疑問**: Markdown fence付きJSON、JSON前後の説明、途中切れ、Enum外、schema違反をどこまで決定的に修復するか？修復をAIへ再依頼する場合、それは再試行1回に数えるか？
**実装への影響**: CLIごとの成功率と呼び出し回数が不安定になる。
**回答**: AUTO_DECIDED (2026-07-15)
プログラム側で決定的にパース可能なテキストクレンジング（Markdownコードフェンス ` ```json ... ``` ` の除去や前後の不要な説明テキストのトリミングなど）のみをAdapterの共通処理で実行し、それ以上の修復（JSONが途中で切れている、スキーマ違反やEnum値の不正があるなど）は行わない。また、AIへの再依頼や自動的な再試行も行わない。これらは `INVALID_OUTPUT` の `AgentFailure` とし、直ちにエラーとする。本決定は、決定表の整合性を維持し、不要なAI呼び出しコストを防ぐための安全な既定方針である。

---

### L-4. 公式2 CLIが必須capabilityを実際に満たすかの事前確認

**重要度**: Critical
**箇所**: §8.5 fail closed / §16.1 UNSAFE_CAPABILITY / §20.2
**疑問**: 仕様は`supports_no_tools=true`かつ`supports_read_only=true`をprobeで確認できなければ起動しない（fail closed）と定めるが、公式サポートのClaude CodeとCodex CLIの実フラグでこれを満たせるかが未確認。満たせなければMVPは2 Agentを構成できず即座に成立しない。

- 各CLIの「非対話・ツール無効・ファイル変更無効・セッション非永続」を実現する具体的なフラグ列を、実装前にspike（手動probe）で確定するか？
- `supports_seed`（§7.5のseed指定）は両CLIで提供されているか？なければ§7.5のseed記述は削除または「対応CLIのみ」と限定するか？
- CLIのバージョンアップでフラグが変わった場合の`UNSUPPORTED_VERSION`判定は、バージョン範囲のallowlistで行うか？

**実装への影響**: fail-closed方針の実現可能性そのものがMVP成立条件。Phase 2着手前ではなく実装開始前に確認が必要。
**回答**: 確定。実装開始前に小さなspikeを実施し、結果を`docs/adapter-spike.md`へ記録する。確認項目は、(1) Claude Codeを完全非対話で呼べるか、(2) ツール無効化または実行拒否を保証できるか、(3) 読み取り専用または空cwdで実行できるか、(4) Codex CLIで同等の制約が可能か、(5) stdout / stderr / exit codeが安定しているか、(6) seed指定の可否。確認できない項目があればfail-closed条件（§8.5、§16.1）を実装着手前に見直す。seed不可なら§7.5のseed記述を「対応CLIのみ」へ限定する。SPEC.md §21（Phase 0前spike）へ反映。

---

### L-5. フェーズ別の構造化出力スキーマが未定義

**X-8.18で確定**: 6フェーズの正式Schemaをpackage resourceとして共有する。`AgentRequest.output_schema`は必須で、各実行へdeep copyを渡す。全objectは`additionalProperties: false`とし、Adapter validator、Claude prompt、Codex `--output-schema`は同一Schemaを参照する。違反は`INVALID_OUTPUT`と固定summaryで扱い、L-3の自動修復/retryは行わない。

**重要度**: Major
**箇所**: §8.5 AgentRequest.output_schema / §15.5 phase / §14 JSON出力
**疑問**: `AgentRequest`は`output_schema`を必須とするが、`respond`、`claim_extract`、`verify`、`criticize`、`synthesize`、`audit`各フェーズの出力スキーマ（フィールド一覧、Enum、文字数上限）が仕様のどこにもない。例えばVerifierは「Evidence分類を構造化出力する」、Auditorは「構造化されたissuesを返す」とあるが、具体形が未定義。
**実装への影響**: Phase 0の「JSON Schema」成果物の範囲が不明確。スキーマがないとFakeAdapterのfixtureもContract Testの期待値も書けないため、実質的にPhase 0のブロッカー。
**回答**: 未回答。Phase 0開始時に6フェーズ分のスキーマをSPECの付録または`schemas/`として定義する想定でよいか確認したい。

---

## M. 失敗時の状態遷移

### M-1. Run / Phase / AgentExecutionの状態機械

**重要度**: Critical
**箇所**: §8.2 Agent状態 / §8.4 タイムアウト / §15.2 Run.status / §15.6 AgentExecution.status
**疑問**: 状態の一覧はあるが、遷移表と集約規則がない。`AgentExecution.completed`と`passed`の違い、Agent状態`OK`との対応も不明。

- どの失敗でRunが`partial`、`failed`、`completed`になるか？
- 各フェーズに最低何Agentの成功が必要か？Responderが1件、Criticが0件、Auditorが失敗などのケースをどう扱うか？
- 全体タイムアウトやCtrl+C後、子CLIをkillし、どのイベントを永続化するか？

**実装への影響**: Orchestratorの中心ロジック、終了コード、再開、障害テストを実装できない。
**現状の問題 / 曖昧さ**: Enumはあるが遷移と親状態への集約規則がなく、`completed`と`passed`、`partial`と`failed`を区別できない。

**推奨案 / 具体的な仕様**: 状態を次へ統一する。

| 対象 | 状態遷移 |
|---|---|
| AgentExecution | `pending -> running -> succeeded \| unavailable \| failed \| timed_out \| cancelled` |
| Phase | `pending -> running -> succeeded \| degraded \| failed \| skipped \| cancelled` |
| Run | `pending -> running -> completed \| partial \| failed \| cancelled` |

`succeeded`は有効な出力あり、`unavailable`はquota/auth/未導入により実行不能、`failed`は実行したが有効出力なしとする。終端状態からの遷移は禁止し、再試行は新しいAgentExecutionを作り`retry_of`で関連付ける。

Phaseの最低成功条件は、`respond`=2件、`claim_extract`=1件、`verify`=1件、`criticize`=1件、`synthesize`=1件、`audit`=1件。Clarifyは不要なら`skipped`。最低数を満たし一部Executionが失敗なら`degraded`、満たさなければ`failed`。Runは全必須Phase成功かdegraded、監査`approved`、回答ありなら`completed`。監査済み回答があるがEvidence予算切れ、非criticalなPhase劣化、major未確認があれば`partial`。必須Phase失敗、critical未確認、監査未完了、予算超過で回答案を監査できなければ`failed`。ユーザーのCtrl+Cは子プロセスを5秒以内にterminate、さらに5秒後killし、実行中Execution、Phase、Runを`cancelled`としてイベント保存する。

**採用理由 / 設計思想との整合性**: 状態名ではなく、最終回答を安全に返せるかという検証ゲートでRun結果を決められる。

**SPEC.md修正文**: §15.2と§15.6を上記状態と遷移表に置換し、Phaseエンティティ、最低成功条件、集約規則、再試行は別Executionであることを追加する。

**優先度**: P0

---

### M-2. フェーズ途中のAgent脱落と投票資格

**重要度**: Critical
**箇所**: §8.3 棄権 / §11.5 合意成立条件
**疑問**: Responderとして成功したAgentがCriticまたはVoterで失敗した場合、`eligible_votes`に含めるか？途中参加・途中復帰は許すか？再投票時だけ失敗したAgentを分母から外すと合意率が上がる問題をどう防ぐか？
**実装への影響**: Quorumを操作可能にしない固定ルールが必要。
**現状の問題 / 曖昧さ**: フェーズごとに分母が変わる投票は、脱落により合意率が上がる。MVPで独立投票を残す理由も弱い。

**推奨案 / 具体的な仕様**: MVPではVoterフェーズ、`eligible_votes`、Quorum、`reached`を使わない。`consensus_status`は常に`not_applicable`とする。Responder 2件が得られなければ`respond` Phaseを`failed`とし、1 Agentだけで継続しない。以後にAgentが脱落した場合は、残る利用可能Agentを決定的な`role_priority`順で1回だけ代替選定する。SynthesizerとAuditorは異なる`agent_id`かつ可能なら異なる`adapter_family`でなければならず、Auditorを確保できなければRunは`failed`。Auditorは`approved` / `changes_required` / `blocked`を返し、`approved`だけが回答公開可能である。

**採用理由 / 設計思想との整合性**: 動的な投票分母を廃止し、独立性と監査を品質条件として固定する。多数決ツールではないという思想に一致する。

**SPEC.md修正文**: §11をMVP監査ゲートとして改訂し、「投票とQuorumは将来機能。MVPの`consensus_status`は`not_applicable`。Auditorの`approved`を公開条件とする。」を追加する。

**優先度**: P0

---

### M-3. JSONLの破損・再開・同時実行

**重要度**: Major
**箇所**: §15.1 ストレージ方針 / §20.5 記録と出力
**疑問**: プロセス強制終了による末尾の半端な行、複数Runの同時追記、`sequence`重複、ディスクフルをどう扱うか？MVPは中断Runの再開を行うのか、閲覧のみか？
**実装への影響**: 「後から表示できる」の耐障害性とWindowsを含むロック方式が決まらない。
**回答**: 確定。S-3のStorageBackend Contractへ統合する。Storageがper-run lock下でsequenceを採番し、1 JSON行をflushしてからappend成功を返す。同一Runのthread/process同時追記を直列化し、異なるRunは並行可能とする。末尾の未改行・不完全な1行だけは`TRUNCATED_TAIL`警告で無視して完全行まで閲覧可能とするが、中間破損、schema違反、sequence重複・欠番・逆転は`StorageCorruptionError`として部分復元しない。MVPは中断Runを再開しない。ディスクフル等の書込み失敗はT-4のfail closed規則を適用する。SPEC v0.3.6 §15.1へ反映。

---

### M-4. Evidence収集フェーズが状態モデルに存在しない

**重要度**: Major
**箇所**: §9.1 基本フロー / §15.5 AgentExecution.phase / §15.7 Phase.status
**疑問**: Evidence収集はAI呼び出しではないためAgentExecutionにならないのは整合的だが、Phaseとしても定義されていない。§15.7の最低成功条件（respond=2、claim_extract=1、verify=1…）にEvidence収集がなく、次が決まらない。

- ネットワーク全断などでEvidenceが1件も取得できない場合、Runは`failed`か、全Claim`unverified`として続行し`withheld`/`partial`へ向かうのか？（§2.5の「処理を停止」とどちらか）
- 進捗表示`[4/7] Evidenceを収集中`はPhaseとして扱うのに、状態機械にPhaseレコードがないと`cancelled`時のイベント保存が書けない。
- Evidence収集の失敗理由（全fetch拒否、検索API認証切れ等）はどのエンティティのどのフィールドに残すか？

**推奨案**: 「処理が正常に終わったか」と「根拠が見つかったか」を分離した2軸モデルとする。PhaseのEnumへ`evidence_collect`を追加し（`claim_extract`と`verify`の間）、`AgentExecution.phase`には追加しない（AI呼び出しではないため実行レコードを作らない）。VerifierはAI呼び出しなので`verify`は別Phaseとして残す。

- **PhaseStatus（処理の成否）**: 既存の`pending` / `running` / `succeeded` / `degraded` / `failed` / `skipped` / `cancelled`を使う
- **EvidenceOutcome（得られた根拠の結果）**: `evidence_found` / `partial_evidence` / `no_evidence` / `conflicting_evidence` / `not_applicable`
- **EvidenceErrorCode（運用上の障害）**: `SEARCH_UNAVAILABLE` / `ALL_FETCH_BLOCKED` / `EVIDENCE_TIMEOUT` / `BUDGET_EXHAUSTED` / `FETCH_FAILED`

判定例:

| 状況 | PhaseStatus | EvidenceOutcome / ErrorCode | Claim状態 |
|---|---|---|---|
| 検索が正常終了、資料なし | `succeeded` | `no_evidence` | `unverified` |
| 5 Claim中3件まで収集、予算切れ | `degraded` | `partial_evidence`＋`BUDGET_EXHAUSTED` | 未処理分は`unverified` |
| 検索サービスが利用不能 | `failed` | `SEARCH_UNAVAILABLE` | — |
| 候補URLが全てSSRF防御で拒否 | `failed` | `ALL_FETCH_BLOCKED` | — |

「検索は成功したが根拠ゼロ」はPhase失敗ではない（succeeded＋no_evidence）。Phase `failed`はEvidence収集機能そのものが実行不能な場合だけで、§2.5に従いRunを`failed`とする。Run開始前の利用不能は従来どおり`verification_unavailable`。「分からないのか、調べられなかったのか」をユーザーへ正しく説明するための分離である。

**実装への影響**: M-1の状態機械fixture 30問にEvidence系障害ケースを含められない。
**回答**: 確定。上記2軸モデルを採用する。SPEC.md §15.7へ反映。CLASS.mdへEnum追加、TESTCASE.mdのM-4起因BLOCKEDを解除する。

---

### M-5. 代替Agent選定と再試行上限・12回上限の関係

**重要度**: Major
**箇所**: §6.3 呼び出し上限 / §8.3 再試行
**疑問**: §8.3は「一時エラーの再試行はRun全体で2回」と「失敗後の代替Agent選定を1回だけ許可」を別々に定めるが、代替Agentでの実行は(a)再試行2回の枠を消費するのか、(b)別枠なのか。別枠なら通常フローは7回＋再試行2回＋代替1回＝絶対上限12回とまだ整合するが、修正込み10回のRunでは10＋2＋1=13回となり絶対上限12回と矛盾する。また既定2 Agent構成では、Responder失敗時の代替は存在しない（3つ目のAgentがない）ため、代替選定が意味を持つのはどのフェーズか。
**実装への影響**: 呼び出しカウンタの実装と、受け入れ条件「絶対上限12回超過0件」のfixture設計が変わる。
**回答**: 確定。M-5とS-5は相互依存するため同時に確定する。retryは同じAgent・同じ論理実行slot・同じphaseの新しいExecution、substitutionは異なるAgentが同じslotとphaseを引き継ぐ新しいExecutionとする。retryはRun全体で最大2回、substitutionは別枠でRun全体で最大1回、全AI呼び出しは`TokenBudget.reserve()`が正本となる12回上限とする。retry対象は`TIMEOUT`/`RATE_LIMITED`だけで、`QUOTA_EXCEEDED`等は同一Agentで再試行せず候補を探す。retry/substitutionは各々新しいBudgetReservationを作り、`retry_of`と`substitute_for`は排他的に記録する。代替Agentの再retryと2人目のsubstituteは行わない。13回目はAgent呼び出し前のreserveで`BUDGET_EXCEEDED`として拒否する。

既定2 Agent構成では、Claudeのsynthesizeが`QUOTA_EXCEEDED`になった場合にCodexへ置換すると別Auditorが残らないため、Synthesizer/Auditor分離を破って救済しない。q03のRun生成前DNS失敗はAgentExecution substitutionとは別のfailure-boundary課題である。

---

## N. MVPスコープとテスト可能性

### N-1. MVPとしての最小価値単位

**重要度**: Critical
**箇所**: §3 MVP目標 / §20 受け入れ条件 / §21 開発フェーズ
**疑問**: 現仕様は質問整理、複数CLI、検索・取得、Claim判定、全員批評、統合、別Agent監査、再投票、履歴、セキュリティ対策を同時に必須としており、MVPというより製品版の縦断機能に近い。最初のリリース判定を次のどこに置くか？

1. 2 Agent + manual Evidence + Fake中心の技術実証
2. 2種類の実CLI + 1実検索Providerの限定MVP
3. 現仕様どおり最大4 Agentの全フロー

**実装への影響**: リリース可能な中間地点がなく、EvidenceProviderやCLI仕様変更が全体をブロックする。
**現状の問題 / 曖昧さ**: 現行MVPは4 Agent、全員批評、投票、再投票、履歴などを同時に要求し、Evidence検証という価値の検証前に工数が膨らむ。

**推奨案 / 具体的な仕様**: MVPは次の縦断構成に限定する。(1) Claude CodeとCodex CLIの2 Adapter、(2) 2 Agentの独立回答、(3) 最大5主要Claimの抽出、(4) 1つの実Web EvidenceProvider、(5) K-1規則による判定、(6) 1 Critic、1 Synthesizer、別AgentのAuditor、(7) text/JSON出力、(8) content非保存の監査メタデータログ、(9) Fakeを使う単体・Contract・障害統合テスト。

MVPから削るものは、3/4番目の実CLI、全員批評、Voter/Quorum/再投票、SQLite、Web UI、トークンストリーミング、中断Run再開、JSレンダリング、PDF/OCR、paywall資料、AI CLI内蔵検索のEvidence採用である。質問整理は決定的ルールを先に使い、AI Clarifierは曖昧時のみ1回とする。履歴はメタデータ閲覧と明示保存されたRunだけを対象にする。

受け入れ条件は、固定fixture 30問で状態機械が期待終端へ100%一致、Evidence規則が判定表fixtureへ100%一致、秘密文字列fixtureが永続ファイルへ0件、SSRF拒否fixtureが100%拒否、Fakeによる呼び出し上限超過が0件、手動live smoke testで両CLI各10 Run中9 Run以上がschema-validとする。回答内容の正確性ベンチマークはP1だが、MVP公開時に「実験的」と明示する。

**採用理由 / 設計思想との整合性**: 独立回答、外部Evidence、別Agent監査という固有価値を残し、Adapter数と合意儀式を削る。

**SPEC.md修正文**: §3、§4、§20、§21を上記MVP境界と定量的受け入れ条件へ改訂する。

**優先度**: P0

---

### N-2. 非決定的AI判定の受け入れテスト

**重要度**: Critical
**箇所**: §18.2 テスト戦略 / §20 MVP受け入れ条件
**疑問**: 「Claimを抽出できる」「誤前提を検出できる」などに合格基準がない。golden dataset、期待Claim集合、許容precision/recall、状態判定一致率を定義するか？
**実装への影響**: Fakeは配線しか検証せず、製品の中核品質が退行してもPR必須テストは通る。
**回答**: 未回答。

---

### N-3. 障害・時間・セキュリティの決定的テスト手段

**重要度**: Major
**箇所**: §8.3 再試行 / §8.4 タイムアウト / §16 セキュリティ / §18.2 テスト戦略
**疑問**: Fakeに仮想時計、遅延、ハング、部分出力、巨大出力、終了コード、レート制限、認証切れを注入する契約が必要ではないか？Evidence側もDNS rebinding、redirect先のprivate IP、圧縮爆弾、巨大レスポンスを再現できる必要がある。
**実装への影響**: 重要な失敗経路がLive Test依存になり、CIで再現できない。
**回答**: 未回答。

---

## O. セキュリティ・ログ漏えい

### O-1. ログ保存内容とデータ最小化の矛盾

**重要度**: Critical
**箇所**: §16.3 機密情報 / §17.1 既定ログ
**疑問**: 既定ログに元質問、全独立回答、Evidence抜粋、最終回答を保存すると、個人情報、社内情報、医療情報、取得資料の著作物が平文で残る。「機密情報を保存しない」の対象はAPIキー等だけか、ユーザー入力中の秘密情報も含むか？

- 保存を既定ONにする根拠と保持期間は？
- `--no-store`、項目別保存、run削除、全削除をMVPに含めるか？
- OS権限、暗号化、バックアップ、クラッシュレポートへの混入をどう扱うか？

**実装への影響**: ローカルツールでも最も現実的な漏えい経路になる。
**現状の問題 / 曖昧さ**: 元質問、全回答、Evidence抜粋を既定保存する仕様は「機密情報を保存しない」と両立せず、履歴機能が情報漏えい経路になる。

**推奨案 / 具体的な仕様**: 既定は`metadata`保存とし、質問・プロンプト・回答本文・Evidence URL/本文/抜粋・stderr/stdoutを永続化しない。保存するのはrun/execution ID、時刻、状態、phase、adapter family/version、モデル識別子、推定/実測usage、Claim/Evidence件数、error_code、elapsed_msである。`error_summary`は固定テンプレートのみとし、生例外文字列を保存しない。

`--store-content`指定時だけcontentを保存し、対話時は確認、非対話時は`--yes`を要求する。content保存時も認証情報redactionを行い、ファイルを所有者のみ読書き可能にする。`--no-store`ではRun完了後に一切保存しない。保持期間はmetadata 30日、content 7日で、CLI起動時に期限切れRunを削除する。`oracle history delete <run-id>`と`oracle history purge --yes`をMVPに含める。削除は主ログをRun単位ファイルへ分割して行い、単一`runs.jsonl`設計は廃止する。クラッシュレポートとtelemetry送信はMVPでは実装しない。

**採用理由 / 設計思想との整合性**: 検証工程の追跡に必要なメタデータを残しつつ、ユーザー内容を既定でディスクへ残さない。削除可能性を実装可能にするためストレージ形態も修正する。

**SPEC.md修正文**: §15.1を`data/runs/<run-id>/events.jsonl`のRun単位保存へ変更し、§17.1をmetadata既定、`--store-content` opt-in、保持期間、削除コマンド、`--no-store`へ置換する。

**優先度**: P0

---

### O-2. 認証情報マスキングの境界

**重要度**: Critical
**箇所**: §16.3 機密情報 / §17.2 詳細ログ
**疑問**: 環境変数、CLI引数、stderr、HTTP header/query/body、Evidence本文に埋め込まれたtokenを、保存前のどの層でマスクするか？既知キー名だけか、形式検出も行うか？マスク失敗時はログ自体を破棄するか？
**実装への影響**: Adapterが生stderrを返した時点で秘密情報がJSONLへ入る可能性がある。
**回答**: 未回答。

---

### O-3. SSRF対策の実装要件

**重要度**: Critical
**箇所**: §16.2 Evidence由来のプロンプトインジェクション対策
**疑問**: URL文字列の検査だけでは、DNS解決後のprivate IP、redirect、IPv6、IPv4埋め込み表現、DNS rebindingを防げない。各redirect hopで解決先IPを検証し、接続先を固定するか？プロキシ環境と企業内URLはサポート対象外か？
**実装への影響**: `web` Providerがローカルネットワーク探索手段になり得る。
**現状の問題 / 曖昧さ**: URL文字列でprivate IPを拒否するだけでは、redirect、複数A/AAAA、DNS rebinding、特殊IP表記を防げない。

**推奨案 / 具体的な仕様**: MVPのWeb fetchは専用`SafeHttpFetcher`だけを通す。schemeは`https`、portは443のみ、userinfo、IP literal、fragmentを拒否する。proxyと環境変数`HTTP_PROXY`等は使用しない。hostnameをIDNA正規化してDNS解決し、返った全A/AAAAがPython `ipaddress.is_global == true`でなければ拒否する。許可IPの1つへ接続先を固定し、HTTP HostとTLS SNI/証明書検証は元hostnameを使う。固定接続を実装できないHTTP clientは採用しない。

redirectは自動追従せず最大3回、各hopでscheme/port/hostname/DNS/IP検証を繰り返す。接続3秒、応答10秒、全体20秒、展開後2MBで打ち切る。Content-Typeは`text/html`、`text/plain`、`application/json`だけを許可し、gzip等は展開後サイズで制限する。取得中の追加URL、HTML内subresource、JavaScriptは実行しない。DNS結果、接続IP、redirect chain、bytes、content hashをmetadataへ保存する。拒否理由は`URL_SCHEME_BLOCKED`、`URL_PORT_BLOCKED`、`DNS_PRIVATE_ADDRESS`、`DNS_REBINDING_BLOCKED`、`REDIRECT_LIMIT`、`RESPONSE_TOO_LARGE`、`CONTENT_TYPE_BLOCKED`、`FETCH_TIMEOUT`とする。企業内URLと明示proxyはMVP対象外。

**採用理由 / 設計思想との整合性**: Web Evidenceを実装しながら、取得先の判定を文字列検査で終わらせずネットワーク接続まで拘束する。

**SPEC.md修正文**: §16.2へ`SafeHttpFetcher`の上記検証順、上限、error codeを追加し、全EvidenceProviderが直接HTTP clientを使うことを禁止する。

**優先度**: P0

---

### O-4. 子CLIの権限分離

**重要度**: Critical
**箇所**: §16.1 CLI実行
**疑問**: 「ファイル変更やコマンド実行の権限を既定で与えない」を、各CLI固有のフラグだけで保証するのか、空の作業ディレクトリ、環境変数allowlist、sandbox、ネットワーク制限も使うのか？親プロセスの全環境変数とリポジトリを継承する設計では要件を満たせない可能性がある。
**実装への影響**: 4 CLIそれぞれで権限制御能力が異なり、共通の安全保証ができない。（→ 公式2 CLIの実フラグ確認はL-4へ分離）
**現状の問題 / 曖昧さ**: `shell=False`だけでは、子CLIが親の作業ディレクトリ、環境変数、ツール、ファイル権限を継承する。3 CLIの安全フラグも同一ではない。

**推奨案 / 具体的な仕様**: MVPは「OS sandbox」ではなく「CLI capabilityによるfail-closed実行」を保証範囲とする。Adapterは`supports_no_tools=true`かつ`supports_read_only=true`をprobeで確認できる場合だけ利用する。各Executionは新規の空一時ディレクトリをcwdとし、質問・Evidenceをファイルへ置かずstdinで渡す。環境変数は`PATH`、OS動作用最小変数、Adapterが宣言した認証変数のallowlistだけを新しい辞書で渡し、親環境を継承しない。CLI引数は固定テンプレートから構築し、非対話、ツール無効、ファイル変更無効、セッション非永続の各フラグを必須とする。いずれかをCLIバージョンで確認できなければ`UNSAFE_CAPABILITY`で起動しない。

子プロセスはprocess group/job objectに入れ、timeout/cancel時に子孫を含めterminate/killする。stdin以外の入力、Orchestratorが作る出力上限付きpipe以外の出力、ユーザー指定cwd/任意コマンド/任意引数は許可しない。MVPは同一OSユーザーのCLIを敵対コードから隔離するものではないことをREADMEへ明記する。強いファイル・ネットワーク隔離が必要な利用向けcontainer/sandbox runnerはP1とする。

**採用理由 / 設計思想との整合性**: クロスプラットフォームの完全sandboxを偽って約束せず、MVPで検証可能な最小権限制御をfail closedで実現する。

**SPEC.md修正文**: §16.1へ一時cwd、環境allowlist、必須capability、固定引数、process tree終了、`UNSAFE_CAPABILITY`、非保証範囲を追加する。

**優先度**: P0

---

### O-5. metadata既定保存とRunエンティティ・最終スナップショットの矛盾

**重要度**: Critical
**箇所**: §15.1 run_completedイベント / §15.8 主要エンティティ / §17.1 既定ログ
**疑問**: §17.1は既定で「質問、回答本文、Evidence URL/抜粋を永続化しない」と定めるが、§15.8のRunエンティティは`original_question`、`refined_question`、`final_answer`を、Evidenceエンティティは`url`、`excerpt`を含み、§15.1は「完了時にrun_completedイベントへ最終スナップショットを含める」と定める。metadata既定のままスナップショットを保存すると質問・回答・URLがJSONLへ残り、§17.1と矛盾する。

- エンティティ定義をstorage policyと分離し、フィールドごとに`metadata` / `content`の保存区分を仕様に明記するか？
- metadataモードの`run_completed`スナップショットは、content区分フィールドをnull/省略にした縮退版とするか？
- Claim.text（Claim本文は質問内容を含み得る）はどちらの区分か？

**実装への影響**: O-1で確定した「metadata既定」の実装がフィールド単位で定義できず、secret/content漏えいfixture（受け入れ条件20.5）の期待値も書けない。
**回答**: 確定。実行時モデルと永続化レコードを分離する。エンティティ（Run、AgentExecution、Claim、Evidence）はin-memoryのRunRuntimeモデルとし、そのまま永続化しない。既定で永続化するのはRunMetadataRecord（run_id、created_at、mode、risk_level、status、result_classification、consensus_status、participant_count、claim_count、evidence_count、error_codes、elapsed_ms）のみ。content区分（質問・回答本文・AgentExecution.response・Claim本文・EvidenceのURL/題名/抜粋）は`--store-content`指定時だけ保存する。`run_completed`スナップショットはmetadataモードではRunMetadataRecordのみを含む。`--no-store`、`oracle history delete <run-id>`、`oracle history purge --yes`はMVPに含める（§17.1どおり）。SPEC.md §15.1、§15.8へ反映。

---

### O-6. 入力の受け渡し方法の矛盾（stdin限定 vs 一時ファイル許可）

**重要度**: Minor
**箇所**: §8.5 AgentAdapter Contract / §16.1 CLI実行
**疑問**: §16.1は「質問とEvidenceはstdinで渡し、作業ファイルへ保存しない」と定めるが、§8.5は「入力はUTF-8のstdinまたはAdapter管理の一時ファイルを使う」と一時ファイルを許可している。CLIによってはstdinで長文を受け取れず一時ファイルが必要になる可能性があるため、許可するなら「Execution専用一時ディレクトリ内、所有者のみ読書き、Execution終了時に削除」の条件付きへ§16.1を修正すべきではないか。
**実装への影響**: Adapter実装の自由度と、content非永続化保証の境界が変わる。
**回答**: 未回答。

---

## P. 有料記事で価値になる設計判断

### P-1. 「多数決ではなくEvidenceを優先」の評価方法

**重要度**: Major
**箇所**: §2.1 多数決を真実とみなさない / §11.6 Evidenceと多数意見の衝突
**疑問**: このプロジェクトの最も強い設計判断だが、優先によって正答率が改善したことを何で示すか？多数決ベースライン、単独最良Agent、Councilの3方式を同じ質問セットで比較し、正確性・費用・時間・保留率を測るか？
**記事価値**: 「AIを増やせば正しくなる」という直感を、実測で否定または条件付きで支持できる。
**回答**: 未回答。

---

### P-2. 「保留」を成功として扱う製品指標

**重要度**: Major
**箇所**: §2.2 保留できる / §12.3 `strict` / §15.3 `withheld`
**疑問**: 正答率だけを追うと、難しい質問をすべて保留する実装が有利になる。回答率、誤答率、適切な保留率、ユーザー有用性をどう同時評価するか？
**記事価値**: 「答えない能力」を品質として設計する際の実務的なトレードオフを示せる。
**回答**: 未回答。

---

### P-3. 匿名化と独立セッションの効果測定

**重要度**: Major
**箇所**: §6.5 汚染対策 / §9.2 独立回答 / §9.3 匿名化
**疑問**: 匿名化・独立セッションあり/なしで、回答の収束、誤答への追従、トークン消費がどう変わるかを比較するか？モデル文体から出自を推測できるため、ラベル置換だけを「匿名化」と呼ぶ限界も明記するか？
**記事価値**: マルチAgent設計で見落とされやすい同調バイアスを、再現可能な実験として提示できる。
**回答**: 未回答。

---

### P-4. 品質向上とコスト増の打ち切り点

**重要度**: Major
**箇所**: §6.3 全Agent批評 / §12.4 待ち時間目標
**疑問**: 2/3/4 Agent、Critic全員/1人、監査あり/なし、再投票あり/なしのablationを行い、追加1呼び出しあたりの品質改善を測るか？その結果でMVPフローを削る判断基準は何か？
**記事価値**: 豪華なAgent構成ではなく、費用対効果でアーキテクチャを決めた過程が読者に再利用可能な知見になる。
**回答**: 未回答。

---

## Q. ユースケース

### Q-1. `strict`自動提案の確認フロー

**重要度**: Major
**箇所**: §12.3 `strict` / §13 CLI・UX
**疑問**: 医療、法律、金融、安全の質問では`strict`を自動提案するとあるが、既定`verify`から自動的に切り替えるのか、対話時に確認するのかが不明。非対話モードで`--mode`未指定の場合の挙動も定義されていない。
**実装への影響**: 「モードを指定する」ユースケースの主体と、暗黙の機能変更を禁止する§2.5との整合が決まらない。
**回答**: 確定。勝手に`strict`へ変更しない。対話モードでは高リスク質問を検出したら`strict`を推奨し、ユーザーが承認すれば`strict`で続行、拒否すれば`verify`で続行するか終了を選べる。非対話モードでは`--mode`の明示指定がなければ`strict_required`で停止する（`--mode verify`または`--mode strict`が明示されていればそれに従う）。§2.5の暗黙の機能変更禁止と整合する。SPEC.md §12.3へ反映。

---

### Q-2. content非保存Runの履歴表示

**重要度**: Major
**箇所**: §13.1 `history show` / §15.1 ストレージ / §17.1 既定ログ
**疑問**: metadata保存が既定のRunに対して`oracle history show <run-id>`を実行した場合、metadataだけを正常表示するのか、「内容は保存されていない」というエラーにするのか。JSON出力時の欠落フィールドを省略、`null`、redacted markerのどれにするかも未定義。
**実装への影響**: 「実行履歴を表示する」ユースケースの正常終了条件と外部JSON契約が決まらない。
**回答**: 確定。metadataのみのRunも`history show`は正常表示とする。表示項目はrun_id、実行日時、モード、状態、参加Agent、Claim数、Evidence数、結果区分、所要時間、エラーコード、`content_saved: false`。本文欄には「本文は保存されていません」と明示する。JSON出力ではcontent区分フィールドを省略し（空文字やnullを最終回答として返さない。処理失敗と区別できなくなるため）、`content_saved`フラグを必ず含める。SPEC.md §17.1へ反映。

---

### Q-3. Agent設定を変更するユースケース

**重要度**: Minor
**箇所**: §8.1 Agent設定 / §13.1 `agents status`
**疑問**: Agent設定は利用者がYAMLを直接編集するだけか、将来を含めて`oracle agents add|enable|disable`の管理コマンドを提供するか。MVPには状態確認しかなく、設定変更をユースケースとして扱うかが不明。
**実装への影響**: ローカル運用者の責任範囲と、設定検証エラーをどの操作で返すかが決まらない。
**回答**: 確定。MVPでは設定ファイルはユーザーが直接編集し、確認手段として`oracle agents status`と`oracle agents validate`を提供する。`agents add|enable|disable`等の管理コマンドはMVP対象外。実行途中の設定変更は当該Runへ反映せず、Run開始時に設定スナップショット（ハッシュ）を保持して次のRunから反映する。これにより再現性が崩れない。SPEC.md §8.1、§13.1へ反映。

---

## R. シーケンス設計

### R-1. CLI終了コードの一覧が未定義

**重要度**: Major
**箇所**: §7.5 終了コード2 / §12.3 `strict_required` / §13.2 `verification_unavailable` / §15.2 Run.status
**疑問**: 終了コードが定義されているのは`needs_clarification`=2のみ。`strict_required`、`verification_unavailable`、`failed`、`withheld`、`partial`、`cancelled`、Agent不足による回答不能が、それぞれ何を返すか未定義。非対話クライアントは終了コードで分岐するため、成功=0、入力起因の停止=2、実行失敗=1のような対応表が必要ではないか。

**推奨案**: 終了コードは大分類6値のみとし、詳細はJSON出力の`status`、`result_classification`、`errors[]`を正本とする。

| oracleExitCode | 意味 | 対応する`result.status` |
|---:|---|---|
| 0 | 公開可能な回答あり | `completed`、`partial`（公開可能な`final_answer`が存在する場合だけ） |
| 1 | 実行失敗 | `failed`、`internal_error` |
| 2 | 入力・追加判断が必要 | `needs_clarification`、`strict_required`、`invalid_arguments`、`unsupported`、`safety_blocked`（§7.5の既定=2と互換） |
| 3 | 実行環境を整える必要あり | `verification_unavailable`、`insufficient_agents`、`auth_required`、`configuration_error` |
| 4 | 回答保留 | `withheld`（必ず4。実行は成功したが検証の結果として回答を止めた） |
| 130 | ユーザーキャンセル | `cancelled_by_user` |

- `partial`が0を返すのは、ユーザーへ公開可能な回答本文が存在する場合だけ
- `withheld`は必ず4。処理失敗ではなく、検証した結果として回答を止めたことをJSONを読まずに判別できる
- CLI引数不正は`invalid_arguments`として2に含め、`needs_clarification`とは`result.status`で区別する
- 子AI CLIの終了コードは`AgentResult.exit_code`（processExitCode）として別フィールドに保存し、Oracle Council自身のoracleExitCodeと混在させない
- 130はOracle CouncilがSIGINT相当として返す慣例値であり、子プロセスの終了コードをそのまま流用しない。Windowsでも同値を返す
- `configuration_error`は設定修正で復旧可能なので1ではなく3とする。新しい停止理由は既存6値へ割り当て、コードを増やさない

**実装への影響**: 非対話モードのシーケンス分岐と、CI等からの利用契約が書けない。
**回答**: 確定。上記対応表を採用する。SPEC.md §13.4へ反映。TESTCASE.mdのR-1起因BLOCKEDを解除する。

---

### R-2. `--json`指定時の進捗表示の出力先

**重要度**: Minor
**箇所**: §12.4 進捗表示 / §13.1 `--json` / §14 JSON出力
**疑問**: `--json`ではstdoutを機械可読なJSON専用にすべきだが、その場合§12.4の進捗表示はstderrへ出すのか、抑止するのか。Adapter側のstdout/stderr規約（§8.5）はあるが、`oracle` CLI自身の規約がない。
**実装への影響**: パイプ利用時の出力汚染とシーケンス図の表示先が決まらない。
**回答**: 未回答。

---

### R-3. ユーザー応答待ち時間と全体タイムアウトの関係

**重要度**: Major
**箇所**: §7.4 追加質問 / §8.4 タイムアウト / §12.3 strict確認 / §13.2 quick切替確認
**疑問**: 追加質問への回答待ち、strict切替の承認待ち、quick切替の確認待ちは、実行全体タイムアウト（`verify` 10分）に含めるか。含めるとユーザーが数分離席しただけでRunが`failed`する。対話待ちは時計を止める（タイムアウトは処理時間のみ計測する）か、対話待ち専用の別タイムアウトを設けるか。
**実装への影響**: タイムアウト計測の実装と、対話フローのシーケンス図の前提が決まらない。
**回答**: 未回答。

---

### R-4. `probe()`の実行方式とAI呼び出しカウント

**重要度**: Minor
**箇所**: §6.3 呼び出し上限 / §8.5 AgentAdapter Contract
**疑問**: `probe()`は子CLIを起動して利用可否・バージョン・capabilityを確認すると思われるが、(a)`--version`等の軽量コマンドで済ませるのか、モデル呼び出しを伴う疎通確認まで行うのか、(b)モデル呼び出しを伴う場合は§6.3の呼び出し上限（絶対上限12回）に数えるのか、(c)Runごとに毎回probeするのか、結果をキャッシュするのか（キャッシュするなら認証切れの検出が遅れる）。
**実装への影響**: Run開始のレイテンシ、呼び出しカウンタ、`AUTH_REQUIRED`検出タイミングが変わる。
**回答**: 未回答。

---

## S. クラス設計

### S-1. `EvidenceProvider.fetch()`と`SafeHttpFetcher`の責務が重複している

**重要度**: Critical
**箇所**: SPEC §10.2 EvidenceProvider / SPEC §16.2 SafeHttpFetcher / SEQUENCE §1 正常系
**疑問**: `EvidenceProvider` Protocolは`fetch(result)`を持つが、正常系シーケンスはOrchestratorが`SafeHttpFetcher.fetch(候補URL)`を直接呼ぶ。WebEvidenceProviderがSafeHttpFetcherを内部利用するのか、Orchestratorがsearchとfetchを別サービスとして組み合わせるのかが不明。

- `EvidenceProvider`を検索専用`EvidenceSearchProvider`へ変更し、取得はOrchestratorから`SafeHttpFetcher`へ依頼するか？
- または`WebEvidenceProvider.fetch()`が必ず`SafeHttpFetcher`へ委譲し、OrchestratorはEvidenceProviderだけを見るか？
- `manual`と`none`にfetch操作を要求するか？

**推奨案**: Provider内部委譲を採用する。依存方向は`Orchestrator → EvidenceProvider → SafeHttpFetcher`とし、OrchestratorはEvidenceProvider Protocol（`search`/`fetch`）だけを見る。OrchestratorがSafeHttpFetcherを直接見ると、Providerによっては安全取得を迂回できる構造になるため。

- `WebEvidenceProvider.fetch()`はDIされた`SafeHttpFetcher`へ必ず委譲する。HTTPクライアントを直接保持してよいのは`SafeHttpFetcher`のみ
- `ManualEvidenceProvider.fetch()`は固定資料を返す（ネットワークなし）
- `NoneEvidenceProvider.search()`は空配列を返す。`fetch()`は通常呼ばれず、呼ばれた場合は型付き例外を送出する
- OrchestratorはProvider以外のHTTP取得機能を参照しない
- 「直接HTTP接続を持たないことを型で完全に防ぐ」はPythonでは不可能なので、Contract Testでは (1) SafeHttpFetcherへの委譲確認、(2) socket接続のモックで直接通信がないことの検査、(3) アーキテクチャルールの静的検査、を組み合わせる
- SEQUENCE.md §1（Orchestrator直接呼び出しの表記）とCLASS.mdの依存線を修正する

**実装への影響**: SSRF対策を迂回できない依存方向、Provider交換単位、Contract Testの対象が確定しない。
**回答**: 確定。Provider内部委譲を採用。SPEC.md §10.2へ反映。SEQUENCE.md §1とCLASS.md §1の依存線を修正済み。

---

### S-2. `Phase`と`AuditIssue`の正式モデルがない

**重要度**: Major
**箇所**: SPEC §11.2 Critical Issue / SPEC §15.7 Phase.status / SPEC §15.8 主要エンティティ / SEQUENCE §3
**疑問**: 状態遷移ではPhaseを独立対象として扱い、監査では構造化`issues`を扱うが、§15.8にPhaseとAuditIssueのエンティティ定義がない。

- Phaseに`phase_id`、`run_id`、`phase`、`status`、開始/終了時刻、最低成功数、error codeを持たせるか？
- AuditIssueに`issue_id`、`run_id`、`audit_execution_id`、`issue_type`、`severity`、`claim_id`、`status`、`comment`を持たせるか？
- 両者はmetadata保存か、`--store-content`時だけ保存か？

**実装への影響**: Runの状態集約、再監査でIssueが解消したかの追跡、JSONLイベントschemaを実装できない。
**回答**: 確定。正式モデルを次とする。

- **Phase**: `phase_id`、`run_id`、`phase`（RunPhase）、`status`、`started_at`、`finished_at`、`minimum_success_count`、`success_count`、`error_code`（PhaseErrorCode。`evidence_collect`ではEvidenceErrorCodeも使用可）、`error_summary`、`raw_diagnostic`。加えてM-4確定の`outcome`（EvidenceOutcome、`evidence_collect`のみ使用）
- **AuditIssue**: `issue_id`、`run_id`、`audit_execution_id`、`issue_type`、`severity`、`claim_id`、`status`、`comment`、`created_at`、`resolved_at`
- **AuditIssue.status**はMVPでは`open` / `resolved`の2値。再監査で「指摘が解消したか」を`open -> resolved`で追跡する。`accepted_risk`は将来対応とし、導入時も次の制約を課す: (1) `critical` severityには設定できない、(2) 安全違反・捏造引用・プロンプトインジェクション影響には設定できない、(3) 公開可否判定上`resolved`と同一扱いにしない、(4) 誰がどの理由で受容したかを記録する、(5) 自動設定せず明示的なユーザー操作または管理操作に限定する
- 保存区分: `error_code`は正式Enumでmetadata保存。`error_summary`はOracle Councilが生成した定型文のみ（最大200文字、secret redaction済み）をmetadata保存し、子CLIのstderr、例外本文、質問・回答・Evidence断片、コマンド文字列、ファイルパスを直接保存しない。生のstderr・例外を残す場合は`raw_diagnostic`（content区分、redaction済み、`--store-content`時のみ）へ分離する。同じ規則をAgentExecutionにも適用し、`raw_diagnostic`を正式フィールドへ追加する。AuditIssueは`comment`のみcontent区分、他はmetadata区分

SPEC.md §15.8へ反映。CLASS.mdの正式モデル化、TESTCASE.mdのS-2起因BLOCKEDを解除する。

---

### S-3. `StorageBackend`のContractが未定義

**重要度**: Major
**箇所**: SPEC §15.1 ストレージ方針 / SEQUENCE §1・§3・§4・§5
**疑問**: `StorageBackend`で抽象化するとあるが、必要な操作、追記の原子性、sequence採番の責任、破損行の扱いが定義されていない。シーケンスではイベント追記と履歴読込の両方を行う。

- 最小Contractを`append(run_id, event)`、`load(run_id)`、`delete(run_id)`、`purge()`とするか？
- `sequence`はOrchestratorとStorageBackendのどちらが採番するか？
- append失敗時にRun処理を停止するか、`--no-store`相当で継続するか？

**実装への影響**: JSONL実装、将来のSQLite差替え、同時書込みと障害テストの共通契約が書けない。
**回答**: 確定。最小Contractを`append(run_id, event_without_sequence) -> RunEvent`、`load(run_id) -> StorageLoadResult`、`delete(run_id) -> DeleteResult`、`purge() -> PurgeResult`とする。sequenceはStorageが所有し、appendの採番・1行追記・flush・可視化をper-run排他下の原子的操作にする。delete/purgeは冪等、実行中Runとの競合はlock error。metadata-onlyはcontentキーを渡さず、store-contentだけcontentを渡す。`--no-store`ではStorageBackendを生成・参照・呼出しせず全操作0回。破損規則と保存障害はM-3/T-4回答を適用する。SPEC v0.3.6 §15.1、CLASS、TESTCASEへ反映。

---

### S-4. ClarificationEngineからClarifier Agentを呼ぶ経路がない

**重要度**: Critical
**箇所**: `CLASS.md` §1 / `SPEC.md` §6.3、§7
**疑問**: SPECではClarifierを1 Agentが担当するが、`ClarificationEngine`は`AgentAdapter`への依存もAgent選定結果を受け取る引数もない。質問整理を規則だけで行うのか、AI呼び出しを含むのか、OrchestratorがAIを呼んでClarificationEngineが結果を判定するのか。
**推奨案**: OrchestratorがClarifier用AgentRequestを実行し、ClarificationEngineは構造化結果への決定規則適用を担当する。
**実装への影響**: 質問整理フェーズのOrchestratorとClarificationEngine間のデータフローおよび責務境界が決定できない。
**テストへの影響**: 質問整理の単体・結合テストのモック・引数設計ができない。
**回答**: **AUTO_DECIDED (2026-07-15)**
推奨案を採用する。
- 責務境界: Orchestratorは、設定された適格なエージェントの中から最も `clarify` の優先度（`role_priority`値）が高いエージェントを決定的に選出し、そのエージェントに対して質問整理のための `AgentRequest` （フェーズ `clarify`）を実行する。`ClarificationEngine` は、エージェントが返却した構造化結果（JSON出力）の検証、および決定規則（SPEC §7.2、§7.5）の適用を担当し、最終的な判定ステータス（`ready`、`ready_with_assumptions`、`needs_clarification` など）と仮定リスト（`assumptions`）または追加質問（`questions`）を判定する。
- 処理フロー: 非対話モードにおいて、判定ステータスが `ready` または `ready_with_assumptions` であればそのまま Run の生成と検証フローへ進行する。`needs_clarification` などの事前停止ステータスの場合は、Run を生成せずに終了コード `2` で処理を停止する。
- 設計資料への反映: SPEC.md §7.5、CLASS.md にこの責務境界とデータフローを最小限反映する。

---

### S-5. `selectAgent(phase)`では複数担当と代替候補を表現できない

**重要度**: Major
**箇所**: `CLASS.md` §1 / `SPEC.md` §6.3 / `QandA.md` M-5
**疑問**: Responder 2 Agent、SynthesizerとAuditorの分離、失敗時の代替候補、呼び出し上限を単一の`selectAgent()`では表現しにくい。
**推奨案**: `buildExecutionPlan(runContext)`で主担当、並列担当、代替候補、分離制約をまとめて決定する。
**実装への影響**: OrchestratorのAgentアロケーション実装および実行計画モデルの設計が決定できない。
**テストへの影響**: 代替Agentアロケーションと制約の単体テストが書けない。
**回答**: 確定。単一`selectAgent(phase)`を正本にせず、Run開始時に決定的な`ExecutionPlan`を構築する。Planは`run_id`、設定Agent一覧、phaseごとの`PhaseAssignment`、Run全体のretry=2、substitution=1、AI call=12を保持し、各Assignmentはphase、slot、必要成功数、候補Agent順、制約を持つ。候補はprobe/capability適格、`role_priority`降順、設定順tie-break、失敗AgentとRun全体unavailable Agent除外、phase固有の独立性制約の順で確定する。`RunAgentAvailability`はAgent単位の`available`/`run_unavailable`と理由を記録し、Run途中で設定を再読込しない。

Responderの2 slotは異なるAgentでなければ成功扱いにせず、成功済みのもう一方を代替に使わない。Synthesizer候補は別Auditor候補が最低1名残るlook-aheadを満たし、Auditor substitutionでもSynthesizerを除外する。適格候補がない場合は元のerror codeを保持してfailedとし、`agent_substitution_unavailable`を安全なmetadata eventとして記録する。

---

### S-6. Runキャンセル時に実行中Agentを特定する所有者がない

**重要度**: Major
**箇所**: `Orchestrator.cancel(runId)` / `AgentAdapter.cancel(executionId)`
**疑問**: Runと実行中executionIdの対応を保持するクラスがない。並列Responder、再試行、通常完了とcancelの競合、process tree終了確認を誰が管理するか未定。
**推奨案**: `ExecutionRegistry`を設け、runId、executionId、状態、cancel tokenを管理する。cancelは冪等にする。
**実装への影響**: キャンセル機能、プロセスツリー監視、リソース解放の並行処理構造が設計できない。
**テストへの影響**: 非同期キャンセルテストでのアサーション対象クラスが確定しない。
**回答**: AUTO_DECIDED (2026-07-15)
推奨案を採用する。
- 選択肢：
  - 案A: 各 `AgentAdapter` が独自に自身の実行状態を管理し、Orchestratorは各アダプターのライフサイクルやキャンセルを直接意識しない。
  - 案B: `Orchestrator` の下にスレッドセーフな `ExecutionRegistry` を設け、Orchestrator が開始前に `register(run_id, execution_id, adapter)` し、終了時に `unregister()` する。キャンセル時はここからアクティブな execution を検索してアダプターにキャンセルを伝える。
- 採用理由：
  並列実行や再試行、通常完了とキャンセルの競合が発生するマルチスレッド/非同期環境において、現在アクティブな実行を一元的かつスレッドセーフに特定して漏れなくキャンセル処理を委譲するには、案Bの中央レジストリが最も堅牢であるため。
- 実装との対応：
  - `src/oracle_council/orchestrator.py` 内にスレッドセーフな `ExecutionRegistry` クラスを実装し、`Orchestrator` がインスタンスメンバー `self._registry` として保持する。
  - `_attempt` の実行時に `adapter` と `execution_id` を登録し、`try-finally` で登録解除する。
  - `Orchestrator.cancel(run_id)` は、registry から該当 `run_id` のアクティブな execution と adapter を特定し、並行して `adapter.cancel(execution_id)` を呼び出す。


---

### S-7. TokenBudgetの並列予約が原子の記述になっていない

**重要度**: Major
**箇所**: `TokenBudget.reserve()` / Responder並列実行
**疑問**: 並列タスクが同時に残予算を確認すると、上限超過が起こり得る。予約解除、実使用量との差分、再試行時の扱いも未定。
**推奨案**: `reserve()`は`BudgetReservation`を返し、`commit(actualUsage)`または`release()`で精算する。呼び出し回数とトークン量を同じ排他制御下で更新する。
**実装への影響**: トークン管理の並行性制御、例外時のロールバック処理の実装が設計できない。
**テストへの影響**: 並列予約・競合状態の多重シミュレーションテストが書けない。
**回答**: 確定。`reserve(request) -> BudgetReservation | BudgetExceededError`、`commit(reservation_id, actual_usage|null)`、`release(reservation_id)`、`snapshot()`を正式Contractとする。Reservationは`reservation_id/run_id/execution_id/phase/estimated_input_tokens/estimated_output_tokens/reserved_call_count/status/actual_input_tokens/actual_output_tokens/created_at/finished_at`を持ち、statusは`reserved/committed/released`のみ。入力・出力・call countを同一lock下で原子的に予約する。子process生成前はrelease、生成後の成功・失敗・timeout・cancelはcommit。usage不明でも予約推定量をcommitし、実測usageは観測値として別記録する。retry/代替実行は別Execution・別予約。異なる終端への変更は禁止、同一commit/releaseの再呼出しは冪等。12回上限もreserve内で判定する。SPEC v0.3.6 §8.7、CLASS、TESTCASEへ反映。

---

### S-8. Oracle CLI終了コードと子CLI終了コードが混在する

**重要度**: Major
**箇所**: `AgentExecution.exitCode` / `AgentResult.exitCode` / `QandA.md` R-1
**疑問**: R-1の終了コードは`oracle`コマンドの外部契約。一方、クラス図のexitCodeはClaude CodeやCodex CLIのprocess exit codeと考えられる。同じ名前ではログとJSON出力で混同する。
**推奨案**: 子CLIは`processExitCode`、Oracle全体は`oracleExitCode`、意味的結果は`AgentExecutionStatus`と`AgentErrorCode`へ分離する。
**実装への影響**: モデルフィールド、ログ、およびJSON出力のAPI契約が設計できない。
**テストへの影響**: CLI結合テストとAdapter Contract Testの期待値アサーションが混同する。
**回答**: 確定（X-8.19、SPEC v0.3.10）。推奨案どおり分離する。

- 子CLI processのOS終了コードは`process_exit_code`（`AgentResult`／`AgentFailure`／`AgentExecutionRecord`）。正常終了0、非0は実値、起動不能・timeout・取得不能・Fake Agentは`null`。process 0後のparse/schema失敗は`INVALID_OUTPUT`かつ`process_exit_code=0`
- Oracle Council全体の外部終了コードは`oracle_exit_code`（`RunResult`／`RunMetadataRecord`／CLI JSONトップレベル）。R-1の0/1/2/3/4/130対応表は変更しない
- 意味的結果は従来どおり`AgentExecutionStatus`／`AgentErrorCode`／`RunStatus`／`ResultClassification`で表し、終了コードだけから推測しない
- CLI JSONトップレベルの旧`exit_code`はschema version 1.xの互換エイリアスとして残し、全経路で`oracle_exit_code`と同値。`executions[]`には`process_exit_code`だけを出力し、曖昧な`exit_code`を出力しない
- `RunResult.exit_code`はPython内部互換の読み取り専用propertyで、保存フィールドの正本は`oracle_exit_code`

---

### S-9. Adapter設定数とRun参加数の多重度が混同されている

**重要度**: Major
**箇所**: `Orchestrator o-- "2..4" AgentAdapter`
**疑問**: 設定済みAdapter数、probe成功数、そのRunの 参加数は別概念。利用不能時もAdapter自体は存在するため、常に2〜4保持する表現は不正確。
**推奨案**: Orchestratorは`0..* configured adapters`を保持し、ExecutionPlanまたはCouncilに`2..4 selected participants`を持たせる。
**実装への影響**: クラス間の多重度、初期化処理、例外ハンドリング of データモデルが決定できない。
**テストへの影響**: 1 Agent脱落時のフォールバックおよびエラーテストケースの構成が制限される。
**回答**: AUTO_DECIDED
Orchestratorが保持する設定済みAdapter数は `0..*` とし、Runごとに作成される `ExecutionPlan` が `2..4 selected participants` を保持する。
- 選択肢:
  - 案A: `Orchestrator` の保持数を `2..4` に制限（5件以上の設定がある場合や、利用不能なエージェントがある場合に、設計と乖離する）。
  - 案B: `Orchestrator` は `0..* configured adapters` を保持し、`ExecutionPlan` に `selected participants` (2..4件) を持たせる。
- 採用理由: 設定されたアダプタ数と特定のRunで選ばれる参加者は本来異なる概念である。5件以上の設定がある場合や、利用不能なエージェントがある場合に対応するため、正しく選出された参加者のみを `selected participants` として扱うことで、データモデルの整合性とフォールバック動作の整合性が保たれる。
- 実装との対応:
  - `Orchestrator` は `0..*` の configured adapters を保持する。
  - `ExecutionPlan` は `participants: tuple[str, ...]` (多重度2..4) を保持する。
  - `build_execution_plan` 内で、eligible agents を全体の決定的優先順位（`role_priority`値の最大値の降順、同順位なら設定順の昇順）でソートし、その先頭最大4件を `selected participants` として選定。
  - 選定された `selected participants` を元の設定順に並び戻したリストに基づいて、各フェーズの `PhaseAssignment` を計算。これにより5件目以降のエージェントは一切実行されない。
  - `run_created` イベント、永続化される `RunMetadataRecord`、CLI JSONトップレベルの `participants` はすべて `ExecutionPlan` の `participants` を参照し統一する。

---

### S-10. `probe()`と`capabilities()`の正本が二重化している

**重要度**: Minor
**箇所**: `AgentAdapter` / `ProbeResult` / `AgentCapabilities` / `QandA.md` R-4
**疑問**: `probe()`がcapabilitiesを返す一方、`capabilities()`も存在する。CLI更新や設定変更後に値が食い違う可能性がある。
**推奨案**: probe結果を実行開始時のcapability snapshotとして正本化し、そのsnapshotをAgent選定と履歴保存に使う。
**実装への影響**: アダプターのライフサイクルとキャッシュ、状態管理の実装方針が決定できない。
**テストへの影響**: 能力判定のモックテストでのモック対象メソッドが二重化する。
**回答**: AUTO_DECIDED (2026-07-15)
推奨案を採用する。`AgentAdapter`の`capabilities()`メソッドを廃止し、`probe()`が`ProbeResult`オブジェクトを返すように統一する。`ProbeResult`は`status`（OKなどの文字列）と`capabilities`（`AgentCapabilities`データクラス、失敗時はNoneでもよい）を保持する。
これにより、プローブ呼び出しと同時にエージェントの能力スナップショットをアトミックに取得して「正本」として扱い、二重化と不整合を防ぐ。


---

## レビュー時点の優先判断

v0.2.0レビューのP0（J-1、J-2、K-1、K-3、L-1、L-2、M-1、M-2、N-1、O-1、O-3、O-4）はv0.3.0で確定済み。

v0.3.0レビューのCritical 3問（J-5、O-5、L-4）は回答確定し、SPEC v0.3.1へ反映済み。残る未回答は次の2群（詳細はFIX_PLAN.md）。

- **実装開始前に確定（ブロッカー）**: J-3（quickの実行グラフ）、L-5（フェーズ別出力スキーマ）、M-5（代替Agentと12回上限）、M-4（Evidence収集の状態モデル）、O-6（stdin限定と一時ファイルの矛盾）、R-1（CLI終了コード一覧）
- **該当Phase開始時に確定**: J-4、K-2、K-4、K-5、K-6、K-7、L-3、M-3、N-2、N-3、O-2、R-2、R-3、R-4
- **クラス実装前に確定**: S-1、S-2、S-3
- **実験・記事用（仕様ではなく実験計画）**: P-1、P-2、P-3、P-4

Q-1〜Q-3（ユースケース）は回答確定し、SPEC v0.3.2・USECASE.mdへ反映済み。R-1〜R-4はSEQUENCE.md作成時に発見した未回答。

S-1〜S-3はCLASS.md作成時に発見した未回答。

---

## T. テスト設計と例外系挙動

### T-1. `TokenBudget.reserve` 失敗時の Orchestrator 挙動の検証基準

**重要度**: Major
**箇所**: SPEC §8.6 / CLASS §1 `TokenBudget` / CLASS_REVIEW S-7 / SEQUENCE §1・§3
**疑問**: `reserve()`が予算不足を返したとき、新しいAgent呼び出しを開始しないことは確定しているが、監査済み回答案の有無に応じたRun状態、公開可否、予約のrelease/commit、保存イベントが未定義。S-7は予約の原子性を扱い、本項はreserve失敗後の製品挙動を扱うため重複しない。
**選択肢**:
1. 常に`failed`、回答非公開、`BUDGET_EXCEEDED`を保存する
2. 監査済み回答があれば`partial`で公開し、それ以外は`failed`
3. 小さいモデルや別Agentへ自動切替する
**推奨案**: 選択肢1。暗黙のモデル切替を追加せず、予約失敗前までのExecution usageだけcommitし、未開始予約はreleaseする。呼び出し回数は増やさない。
**実装への影響**: `Orchestrator.run()`の終端分岐、BudgetReservation lifecycle、RunEventが決まる。
**テストへの影響**: UT-TB-01/03/04/07/09、IT-E2E-22/23のRun状態・保存イベント・終了コードがBLOCKED。
**回答**: 確定。reserve失敗時は予約を作らず、新しいAgent呼出し、retry、代替Agentを開始しない。現在RunにAuditor承認済みのschema-validな公開可能回答がある場合だけ`Run.status=partial`、`result_classification=partially_verified`、final_answer公開、exit 0とする。承認済み回答がなければ対象PhaseとRunを`failed`、`BUDGET_EXCEEDED`、final_answer非公開、exit 1とする。Claim検証による`withheld + completed + exit 4`とは分離する。保存有効時は`budget_exceeded`と終端イベントのappend成功を必須とし、保存失敗はT-4へ従う。SPEC v0.3.6 §15.2決定表へ反映。

### T-2. `Orchestrator.cancel` 時の各 Adapter への非同期キャンセル伝播の検証方法

**重要度**: Major
**箇所**: SPEC §15.7, §16.1 / SEQUENCE §4c / CLASS `Orchestrator.cancel`, `AgentAdapter.cancel` / CLASS_REVIEW S-6
**疑問**: S-6は実行中executionの所有者を扱う。本項ではcancelの合格基準として、全Adapterへの伝播期限、冪等性、通常完了との競合、terminateからkillへ移る5秒の測定起点、残留process判定範囲が未定義。
**選択肢**:
1. cancel要求後ただちに全cancel coroutineを開始し、FakeClockで5秒後にkill、全process tree消滅を必須とする
2. Adapterごとに逐次cancelし、全体timeoutだけを設ける
3. 親processの終了だけを確認し、子孫はbest effortとする
**推奨案**: 選択肢1。`cancel(runId)`は冪等、cancel開始後の成功結果は破棄し、全稼働Executionを`cancelled`へ収束させる。OSテストでは開始前後のprocess tree差分が0になることを10秒以内に確認する。
**実装への影響**: ExecutionRegistry、cancel token、Adapterのprocess handle管理が決まる。
**テストへの影響**: UT-CLI-11、UT-ORCH-11、UT-AA-04/15、IT-E2E-24、ST-PROC-01がBLOCKED。
**回答**: AUTO_DECIDED (2026-07-15)
推奨案（選択肢1）を採用する。
- 採用理由：
  CLI強制終了時やキャンセル実行時に、呼び出されたエージェントの外部プロセス（subprocess）がゾンビプロセスとして生存するのを防ぎ、かつ速やかにリソースを解放するため。
- 実装との対応：
  - `AgentAdapter` インターフェース（`ClaudeAdapter`、`CodexAdapter`）に `cancel(execution_id: str)` を追加する。
  - アダプターは `execute()` で subprocess を実行する際、`subprocess.Popen` を用い、実行中の `Popen` オブジェクトと `execution_id` の対応をスレッドセーフに管理する。
  - `cancel(execution_id)` が呼ばれた場合、対象プロセスの `terminate()` を呼び出したのち、最大5秒待機する。それでも終了しなかった場合は `kill()` を実行して強制終了する。
  - キャンセルされた実行は、スレッド側で `AgentFailure("CANCELLED", "execution cancelled")` の例外を送出させる。
  - `Orchestrator` 側で `AgentFailure` の `error_code == "CANCELLED"` を検知した場合、該当の `PhaseRecord` のステータスを `PhaseStatus.CANCELLED`、Run全体のステータスを `RunStatus.CANCELLED` とし、oracle_exit_codeを `130` (ユーザーキャンセル) で終了する。


### T-3. `SafeHttpFetcher` における DNS ピンニング（DNS Rebinding 対策）のテスト容易性

**重要度**: Major
**箇所**: SPEC §16.2 / CLASS `SafeHttpFetcher.resolveAndPin` / SEQUENCE §1
**疑問**: DNS解決結果の全IP検査、選択IPへの接続固定、元hostnameでのSNI/証明書検証を、外部DNSなしのCIで観測できるtransport境界が未定義。
**選択肢**:
1. DNS resolverとpinned connectorをProtocol化し、FakeDNSResolver/FakePinnedTransportで全分岐をCI検証する
2. ローカル権威DNSサーバーをCIで起動する
3. 実DNSを使うnightlyだけで検証する
**推奨案**: 選択肢1を必須CT、選択肢2を任意ST、選択肢3をopt-in smokeとする。最初の解決がpublic、2回目がprivateとなるfixtureでも、接続先が最初にpinしたpublic IPから変化しないことをassertする。
**実装への影響**: HTTP client/transport選定と依存注入点が決まる。
**テストへの影響**: UT-SHF-07/08、CT-SHF-01/LIVE-01、ST-SSRF-01を決定的に自動化できない。
**回答**: AUTO_DECIDED (2026-07-15)
選択肢1を採用する。`SafeHttpFetcher` の構築時に custom resolver と custom opener / transport を DI 可能にする。
DNS解決結果の全IPを事前検証し、安全なIPアドレスの1つを「ピン留め（Pin）」する。
実際のHTTP接続時（`urllib`による接続開始時）には、ピン留めされたIPアドレスを接続先アドレスとして強制使用する一方、HostヘッダーおよびTLS/SNI証明書検証（HTTPS接続）には元のホスト名を使用する。
具体的には、リクエストごとに一時的に構築される `urllib` のカスタムHTTP/HTTPSハンドラーにおいて、`socket.getaddrinfo` の呼び出しをピン留めされたIPのみを返すようにフックする方式を採用し、これにより余計な内部依存の追加や複雑なTCPコネクターの再実装を避ける。
このDNS Pinning機構をCIで検証するため、FakeDNSResolverやFakeの接続フックを用いた単体テスト（UT-SHF-07）を追加する。

### T-4. `StorageBackend` 障害時のフォールバック方針

**重要度**: Major
**箇所**: SPEC §15.1, §17.1 / CLASS `StorageBackend` / CLASS_REVIEW S-3 / SEQUENCE §1・§3・§4
**疑問**: S-3/M-3はStorage contractと破損処理を扱う。本項ではmetadata保存が有効なRunでappendが失敗した場合、回答生成を継続するか、どのRun状態・oracleExitCode・stderrを返すかが未定義。
**選択肢**:
1. metadata保存が有効ならfail closed。`--no-store`だけはStorageを呼ばず継続する
2. in-memoryへ縮退し`partial`で回答する
3. warningだけ出して`completed`で回答する
**推奨案**: 選択肢1。監査証跡を保存できないのに正常完了と表示しない。append失敗後の再帰的な保存試行は行わず、redaction済みstderrとoracleExitCodeだけで通知する。
**実装への影響**: Storage例外境界、Run終端、CLI通知経路が決まる。
**テストへの影響**: UT-ORCH-12、UT-SB-08/09、CT-SB-01、IT-E2E-25/34/35がBLOCKED。
**回答**: 確定。選択肢1を採用する。保存有効時は初回、途中、最終のどのappend失敗もfail closedとし、以後の保存を停止、in-memory Runを`failed`、`STORAGE_WRITE_FAILED`、final_answer非公開、exit 1とする。最終結果生成後の保存失敗でも回答を表示しない。失敗を記録する再帰的appendは行わず、redaction済みstderrだけで通知する。`--no-store`だけはStorage呼出し0回の正常経路。load時の破損は`STORAGE_CORRUPTED`として対象履歴の表示だけを失敗させる。SPEC v0.3.6 §15.1・§15.2へ反映。

### T-5. Claim状態からRun全体の`result_classification`を導出する規則

**重要度**: Critical
**箇所**: SPEC §10.5, §10.9, §14, §15.3 / USECASE §2 / SEQUENCE §1
**疑問**: Claim単位の`verified`等とRun全体の`result_classification` Enumはあるが、複数Claimの組合せから`verified`、`partially_verified`、`unverified`、`conflicting`、`withheld`を選ぶ優先順位がない。例えばmajor verified 2件とconflicting 1件、minor unverifiedのみ、major contradicted、critical unverifiedの結果が一意に決まらない。
**選択肢**:
1. severity優先の決定表をOrchestratorへ実装する
2. SynthesizerまたはAuditorに自由判断させる
3. Claim配列だけを返しRun全体分類を廃止する
**推奨案**: 選択肢1。`withheld`を最優先、次に`conflicting`、`unverified`、`partially_verified`、全主要Claim verified時だけ`verified`とする。ただしminorだけの未確認を全体分類へ反映するかも表で明記する。
**実装への影響**: `Orchestrator.classifyResult()`、JSON出力、RunMetadataRecordの値が決まる。
**テストへの影響**: IT-E2E-15/16/17とJSON Schema Contractの期待値がBLOCKED。
**回答**: 確定。AIの自由判断ではなく、Orchestratorが二段判定で導出する。まず「公開可能か」を判定し、公開可能な場合だけ「どの分類か」を決める。これにより`withheld`とresult_classificationが混ざらない。

**第1段（安全判定）**: `verify` Phase完了後、全対象Claimの検証状態が確定してから判定する。次のいずれかに該当すれば`withheld`とし、§11.5の開示範囲だけを返す。

1. `critical` Claimに`unverified`または`contradicted`が1件でもある
2. `major` Claimに`contradicted`が1件でもある

**第2段（公開可能な場合の分類、上から順に最初に一致した行）**:

| 条件 | 分類 |
|---|---|
| `critical`または`major`に`conflicting`がある | `conflicting` |
| 主要Claim（critical＋major）が1件以上あり、その全てが`unverified` | `unverified` |
| `major`に`unverified`がある | `partially_verified` |
| `minor`に`unverified`、`conflicting`または`contradicted`がある | `partially_verified` |
| 検証対象Claimが1件以上あり、その全てが`verified`または`supported` | `verified` |
| 検証対象Claimが0件（全て`not_applicable`） | `unverified` |

優先順位は`withheld` > `conflicting` > `unverified` > `partially_verified` > `verified`。「majorのconflicting/contradicted」の曖昧さは、`contradicted`=第1段でwithheld、`conflicting`=第2段でconflictingとして決定的に解消した。

**採用に伴う決定（R-1・U-1との整合）**: 第1段で`withheld`が確定した場合、以降の`criticize`、`synthesize`、`audit`は`skipped`とし、Runは`completed`（result_classification: `withheld`、oracleExitCode=4）とする。`withheld`はRun失敗ではないため（R-1でexit 4をexit 1と分離済み）、`failed`にしない。監査対象の統合回答を作らないので、Auditorが止めた内容の漏えいも構造的に起きない。SPEC.md §15.2、§15.3へ反映。

---

## U. 出力と開示境界

### U-1. `withheld`時の開示範囲

**重要度**: Major
**箇所**: SPEC §10.9 最終回答への反映 / §11.3 回答公開条件 / §14 JSON出力 / §15 履歴・保存
**疑問**: Auditorが最終回答を承認せずRunが`withheld`となった場合、ユーザーへ何を表示するか。「未承認の最終回答本文を公開しない」（§11.3）という制約と、「確認できた地点までユーザーを連れていく」という製品方針を両立するには、次を別々の公開ゲートとして扱う必要がある。

- 統合された最終回答本文
- Claimごとの検証状態
- Claimを支持・否定したEvidenceの概要
- 保留理由
- 確認できた範囲を説明する安全な要約

対象ユーザーは`withheld`を「誠実な回答」ではなく「答えてくれなかった」と受け取りやすいため、保留画面を失敗画面にしてはいけない。「回答できませんでした」ではなく「AとBは複数の資料で確認できました。Cは信頼できる根拠が見つからなかったため、断定を避けています」と返す。

**選択肢**:
1. 最終回答もClaim情報も表示せず、保留理由だけを表示する
2. 最終回答本文は表示せず、Claim状態とEvidence概要を表示する
3. 検証済みClaimだけからOrchestratorが機械的に要約を生成して表示する
4. Synthesizerへ安全な部分回答を再生成させる

**推奨案**: 選択肢2をMVPで採用する。

- `final_answer`は非公開
- `claims[]`の`text`、`importance`、`status`、採否、短い理由を表示
- Evidenceはタイトル、発行元、URL、対応関係の概要まで表示
- 保留理由を表示
- 自由生成による新しい「部分回答」は作らない（Auditorが止めた内容をAIが言い換えて復活させる危険があるため）
- verifiedなClaimだけを文章として再構成する機能は将来対応

表示規則: Claim本文をそのまま先頭へ出すと誤情報を目立つ形で再掲する恐れがあるため、必ず「確認状態 → 確認対象 → 扱い」の順で構成する。

```text
確認状態: 未確認
確認対象: 「製品Aは2025年に発売された」
扱い: この主張は回答に採用していません
```

`contradicted`の場合は次まで表示する。

```text
確認状態: 信頼できる資料と矛盾
扱い: この主張は回答から除外しました
```

開示しないもの: Evidence本文の長い抜粋、内部プロンプト、Agentの生出力、監査前の`final_answer`。`--json`と履歴表示でも同じ開示境界を守る。

**実装への影響**: `withheld`を失敗画面ではなく検証結果画面として実装できる。未承認の統合回答が誤って公開されることも防げる。統合回答の公開ゲート（Auditor承認）とClaim検証結果の開示ゲートを分離してSPECへ明記する必要がある。
**テストへの影響**: `withheld`時に`final_answer`が公開されない、Claim検証結果は表示される、Evidence本文や秘密情報は表示されない、`--json`でも同じ公開境界を守る、履歴表示でも`content_saved`設定を越えて本文を復元しない、の各ケースが必要。
**回答**: 確定。選択肢2＋上記表示規則を採用する。SPEC.md §11.5へ反映。TESTCASE.mdへ開示境界ケースを追加する。


---

## V. 状態遷移図レビューで判明した未決事項

### V-1. 実行前停止時のRun生成・終端状態

**重要度**: Major
**箇所**: SPEC §7.4、§12.3、§13.4、§15.2 / SEQUENCE §2・§3 / CLASS RunStatus
**疑問**: `needs_clarification`、`strict_required`、`verification_unavailable`、`insufficient_agents`等はCLIの`result.status`と終了コードが確定している一方、Runレコードを生成・保存するか、生成する場合にどの`Run.status`で終端するかが定義されていない。`Run.status`の正式Enumにはこれらの値がなく、すべてを`failed`へ寄せると入力待ちと実行障害を区別できない。
**選択肢**:
1. 実行前停止ではRunを生成せず、CLI結果だけを返す
2. Runを生成し、`failed`で終端して停止理由を別フィールドへ保存する
3. Runを生成し、`partial`で終端して停止理由を別フィールドへ保存する
4. RunStatusへ入力待ち・環境待ちの新しい状態を追加する
**推奨案**: 選択肢1。AI実行またはEvidence処理を開始していない停止をRun履歴へ混ぜず、CLIの構造化結果だけで理由を返す。質問整理自体を履歴化する要件が後から必要になった場合は、Runとは別のRequestAttemptモデルを検討する。
**実装への影響**: `OracleCLI`がRun生成前に行うvalidation、clarification、mode/evidence availability判定の順序と、Storage呼出し有無が確定する。
**テストへの影響**: exit 2/3の各ケースでRun保存イベントが0件か、特定のRun終端イベントがあるかをassertできる。
**回答**: 確定。選択肢1を採用する。引数・設定検証、質問整理、mode判定、EvidenceProvider利用可否、最低Agent数の事前検査が全て通過し、最初のPhaseを開始する直前にRunを生成する。`needs_clarification`、`strict_required`、`verification_unavailable`、`insufficient_agents`等の事前停止ではRunを生成・保存せず、`history show`の対象にしない。CLIは`run_id: null`、停止理由の`status`、R-1の`exit_code`、安全な`message`をJSON結果へ必ず含める。`--no-store`では事前停止結果もRun開始後のイベントも永続化しない。SPEC v0.3.5 §14・§15.1へ反映。

### V-2. completedとpartialが重なる場合の優先順位

**重要度**: Major
**箇所**: SPEC §15.2 / CLASS RunStatus / TESTCASE Run状態遷移ケース
**疑問**: `completed`は「全必須Phaseが`succeeded`、`degraded`または`skipped`」の場合を許容する一方、`partial`は「非criticalなPhase劣化」または「major未確認」を条件に含む。同じ公開可能Runが両方の条件を満たす場合、どちらを選ぶかが一意でない。
**選択肢**:
1. `partial`を優先し、`completed`はpartial条件に該当しない場合だけ使う
2. `completed`を優先し、`partial`を廃止する
3. Phase劣化は`completed`、major未確認だけ`partial`とする
**推奨案**: 選択肢1。`partial`を`completed`の具体的な縮退終端として先に判定すれば、既存Enumと利用者への劣化表示を維持できる。判定順を`cancelled/failed -> withheld completed -> partial -> completed`として明記する。
**実装への影響**: OrchestratorのRun終端決定表と、`result_classification`から独立したRunStatus算出順が確定する。
**テストへの影響**: Phase degraded、major unverified、両方同時、minorのみunverifiedの各RunStatus期待値を一意にassertできる。
**回答**: 確定。選択肢1を採用する。RunStatusとresult_classificationを別軸とし、判定順は`cancelled`、`failed`、`withheldを伴うcompleted`、`partial`、`completed`とする。`partial`はAuditor承認済みの公開可能な回答があり、`result_classification=partially_verified`の場合だけ使用する。公開可能な回答がなければPhaseが一部成功していても`partial`ではなく`failed`。`verified`、`conflicting`、`unverified`の公開回答は`completed + exit 0`、`withheld`は`completed + withheld + exit 4`とする。SPEC v0.3.5 §15.2へ反映。

### V-3. Evidence予算切れコードの名称統一

**重要度**: Major
**箇所**: SPEC §10.2、§15.7 / CLASS EvidenceErrorCode / STATE evidence_collect
**疑問**: Evidence検索停止条件では`EVIDENCE_BUDGET_EXHAUSTED`を記録すると記載される一方、M-4で確定した`EvidenceErrorCode` Enumは`BUDGET_EXHAUSTED`である。同じ事象に二つの識別子が存在する。
**選択肢**:
1. 正式Enumの`BUDGET_EXHAUSTED`へ統一する
2. Enumを`EVIDENCE_BUDGET_EXHAUSTED`へ改名する
3. 両方を別コードとして残す
**推奨案**: 選択肢1。`EvidenceErrorCode`型の文脈でEvidence由来は明白であり、M-4・CLASS・既存テストとの変更量が最小になる。
**実装への影響**: EvidenceProvider、Phase.error_code、JSON Schemaで単一のEnum値を使用できる。
**テストへの影響**: 予算切れContract Testで期待する文字列を一意にできる。
**回答**: 確定。選択肢1を採用し、正式名を`EvidenceErrorCode.BUDGET_EXHAUSTED`へ統一する。検索回数、fetch数、展開後文書量、Evidence件数の収集上限に使用し、90秒の時間上限には`EvidenceErrorCode.EVIDENCE_TIMEOUT`を使用する。一部処理済みなら`PhaseStatus=degraded`、`EvidenceOutcome=partial_evidence`、未処理Claimは`unverified`とする。AI呼び出し回数、token、コンテキスト予算の不足は`AgentErrorCode.BUDGET_EXCEEDED`とし、Evidence側の上限と混在させない。SPEC v0.3.5 §10.2・§15.7へ反映。

---

## W. 実装レビュー

### W-1. §15.3決定表のfall-throughと実装の整合

**重要度**: Major
**箇所**: SPEC §15.3 第2段決定表 / `src/oracle_council/classification.py` / hikitsugi.md §5
**疑問**: Phase 0実装（`classify()`）の作成中に、決定表に次のfall-through候補が見つかった。(1) `critical`の`conflicting`がどの行にも一致しない、(2) `minor`の`contradicted`が第2段row4に含まれない、(3) どの行にも一致しない場合の既定値が未定義。
**検証結果**: (1)(2)はSPEC v0.3.5/v0.3.6の改訂で解消済みであることを確認した。row1は「`critical`または`major`に`conflicting`」、row4は「`minor`に`unverified`、`conflicting`または`contradicted`」になっており、row5も「検証対象Claimが1件以上あり、その全てが`verified`または`supported`」へ拡張済み。この結果、第1段通過後の表は網羅的であり、(3)の未一致は発生しない。
**実装への影響**: 逆に実装側がv0.3.4時点の表を前提にしており、「検証対象が`minor`のみで全て`verified`/`supported`」の場合に仕様の`verified`ではなく`partially_verified`を返す齟齬があった。実装をv0.3.6の表へ修正し、防御的な既定値`partially_verified`（到達不能だが断定を避ける安全側）はコメント付きで残した。テストへminorのみ確認済み→`verified`のケースを追加。
**回答**: 確定。SPECは変更不要（v0.3.6の表が正）。実装とテストをv0.3.6へ整合させた。教訓として、実装は必ずSPECの最新版を参照し、hikitsugi等の中間メモを仕様の代わりにしないことをレビュー観点へ加える。

---

### W-2. 修正・再監査フローの終端と「修正込み10回」の内訳

**重要度**: Major
**箇所**: SPEC §6.3 呼び出し上限 / §11.1 監査ゲート / §15.2 Run.status / IT-E2E-21
**疑問**: (1) 「修正込み10回」は通常7回＋修正2回＝9回と合わない。10回目は何を指すか。(2) 再監査でも`approved`にならない場合、旧§11.1は`failed`としていたが、「保留は失敗ではない」（R-1のexit 4、U-1の開示境界）と整合するか。
**検証結果**: (1) 10回＝条件付きClarifier(1)＋通常(7)＋修正(1)＋再監査(1)。Clarifierなしの修正フローは9回で、一時エラーの再試行は別枠（Run全体2回、絶対上限12回）。修正フローとretryの呼び出し上限は既に分離されており混在しない。
**回答**: 確定。監査の終端を次へ改訂する（SPEC v0.3.7 §11.1）。初回`approved`→完了。初回`changes_required`→Synthesizer再実行1回→同じAuditorで再監査1回。再監査`approved`→公開。再監査`changes_required`/`blocked`→`withheld`（`final_answer`非公開、Run `completed`、exit 4）。初回`blocked`→修正へ進まず即`withheld`。Auditor確保不能のみ`failed`（環境問題であり保留ではない）。§15.2の「監査がblocked→failed」は削除。AuditIssueは初回`open`、再監査で解消確認されたものだけ`resolved`、未解消は`open`のまま。イベントは`revision_started`、`synthesis_revised`、`reaudit_started`、`reaudit_completed`を記録する。

---

### W-3. 再試行対象エラーの固定

**重要度**: Major
**箇所**: SPEC §8.2 Agent状態 / §8.3 再試行 / `orchestrator.py` `_RETRYABLE_ERROR_CODES`
**疑問**: どの`error_code`を再試行対象にするか。レビュー案は「TIMEOUT、RATE_LIMITED、一時的なEXECUTION_ERROR」だったが、SPEC正本と一致させる必要がある。INVALID_OUTPUTを1回だけ再試行する設計もあり得る。
**検証結果**: SPEC §8.3の正本は「一時的なタイムアウトとレート制限は同一Executionにつき最大1回のみ」であり、EXECUTION_ERRORは列挙されていない。INVALID_OUTPUTの回復（AIへの修復再依頼を再試行に数えるか）はL-3が未回答。
**回答**: 確定。再試行対象は`TIMEOUT`と`RATE_LIMITED`のみとする。`AUTH_REQUIRED`、`QUOTA_EXCEEDED`、`COMMAND_NOT_FOUND`、`UNSUPPORTED_VERSION`、`UNSAFE_CAPABILITY`は同一Agent retryなしでRun全体unavailableとし、適格候補があればsubstitutionへ進む。`EXECUTION_ERROR`はslot-localのsubstitution対象だがRun全体unavailableにはしない。`INVALID_OUTPUT`、`CONTEXT_OVERFLOW`、`BUDGET_EXCEEDED`、`CANCELLED`、Evidence障害、Run生成前のCLI/DNS/設定例外はM-5 substitution対象外とする。retryは同一Agent・同じslotの新Execution、最大1回/slotかつRun全体2回、substitutionは別枠でRun全体1回。全て別予約・履歴保持・起動後失敗の安全側commitを行い、代替後のretryと2人目の代替は行わない。

M-5/S-5はこの回答とExecutionPlan仕様を同時確定した。q08の2 Agent quota障害を必ず救済する仕様ではなく、q03は別failure-boundary課題として残す。

---

### W-4. Phase / AgentExecution正式レコード化の実装判断

**重要度**: Major
**箇所**: SPEC §15.8 / STATE.md §1・§4・§5 / `models.py` / `orchestrator.py`
**疑問**: (1) 再監査・修正は同一Phase instanceへのExecution追加か、別Phase instanceか。(2) `evidence_collect`のレコード表現。(3) STATE.mdにW-2以前の「audit blocked→failed」が残っていた。
**回答**: 確定。(1) **同一Phase instanceへのExecution追加**とする。STATE §5の最低成功数がphase名単位（`audit`=1）で定義されており、再監査で`success_count`が2になるのは正常。Phase instanceはRunにつきphase名ごとに1つ。(2) `evidence_collect`はAgentExecutionを作らずPhaseレコードのみ（M-4どおり）。`outcome`はFake実装では`evidence_found` / `no_evidence`の2値から開始。(3) STATE.md §1・§4・§5の「audit blocked→failed / exit 1」をW-2確定の「withheld終端（completed・exit 4）」へ修正した。あわせて`error_summary`は定型テンプレート（`"{phase} execution ended with {error_code}."`、200字以内、生テキスト混入なし）、`raw_diagnostic`は`--store-content`時のみ、RunMetadataRecordは終端時スナップショットを正本としイベントログから再集計しない（O-5）、を実装で固定した。

---

### W-5. 実機E2Eの分割とprobeで検出できない利用上限の扱い

**重要度**: Major
**箇所**: SPEC §6.4・§8.2・§18.2 / M-2 / R-4 / `cli.py` / `tests/contract/test_adapters.py` / `tests/e2e/`
**疑問**: (1) 実機E2Eが全体skipになる設計は「何が動き、何が未達か」を隠す。(2) liveテストが既定スイートで実CLIを起動していた（§18.2違反）。(3) 実機検証で「`probe()`は正常でも`execute()`でQUOTA_EXCEEDED」という実挙動が判明。probe（`--version`）では利用上限を検出できない。
**回答**: 確定。(1) liveテストを4分割した: `test_codex_adapter_live_execute`（Codex正常時pass）、`test_claude_adapter_live_execute`（quota時skip）、`test_real_two_agent_council`（quota時skip）、`test_real_insufficient_agents_when_claude_unavailable`（Claude probe不能環境でpass）。テスト結果だけで可動状況が分かる。(2) `addopts = -q -m "not live"`で既定スイートからliveを除外（`-m "live and expensive"`の明示実行でのみ起動）。(3) CLIへpre-flight probeフィルタを追加: probeがOKでないAgentは欠席とし、参加可能2未満は`insufficient_agents`/exit 3で停止（Run生成なし、V-1準拠）。probeで検出できない利用上限は実行中の`QUOTA_EXCEEDED`となり、M-2どおりrespond Phase failed→Run failed。「Claude不在でskipではなくinsufficient_agentsを返す」検証は、Fakeのprobe環境変数（`ORACLE_MOCK_PROBE_CLAUDE`）を使う決定的な既定スイートテストとして常時実行する。probe（`--version`）はAI呼び出しに数えない（R-4の部分回答）。

---

### W-6. 実機2 Agent完走までに見つかった5件のAdapter実装バグ

**重要度**: Critical
**箇所**: `adapters/base.py` / `adapters/claude.py` / `adapters/codex.py`
**背景**: W-5でprobe/execute乖離とlive test分割を確定した後、Claude利用上限が一時的に解け、`test_real_two_agent_council`を反復実行しながら実機のみで踏める障害を1つずつ修正した。設計上の穴ではなく、すべて実装のバグ。
**発見と修正**:

1. **429「out of usage credits」が`EXECUTION_ERROR`に誤分類**: `classify_cli_error`の文字列一致が「quota」「session limit」を含まない実際のエラー文言を拾えなかった。構造化JSON（`api_error_status`）を優先的にパースする方式へ変更し、`QUOTA_EXCEEDED`/`RATE_LIMITED`/`AUTH_REQUIRED`を判定するよう修正（`base.py`）
2. **Claude Adapterがフェーズschemaを一切指示していなかった**: `claude`CLIに`--output-schema`相当の機能がなく、`--output-format json`の応答はCLIメタデータの封筒（`{"type":"result","result":"<回答文>",...}`）でラップされる。Adapterは封筒全体をフェーズschemaとして直接パースしており、成功時でも`missing field: answer`で失敗していた。フェーズごとのJSON形式指示をプロンプトへ追加し、`envelope["result"]`からフェーズJSONを抽出する処理を追加（`claude.py`）
3. **Adapter層がClaim enumを検証していなかった**: `validate_phase_output`は`claims`が配列であることしか見ておらず、`importance: "high"`のような不正値がOrchestrator内部の`Claim.from_dict`まで届いて未捕捉の`ValueError`となり、`internal_error`として現れていた（SPEC §8.5「Orchestratorへ返す前にschema検証を行う」違反）。`_validate_claims`を追加し、Adapter境界で`INVALID_OUTPUT`として止めるよう修正（`base.py`）
4. **Codexの`verify`フェーズschemaにenum制約がなかった**: `claim_extract`スキーマは`importance`にenumがあったが、`verify`スキーマは`{"type": "string"}`のみで、Codex自身の構造化出力がenumを守れなかった（3の症状の実際の原因）。`verify`にも`claim_extract`と同じenumを追加（`codex.py`）
5. **Codexの`audit`フェーズschemaがOpenAI厳格モード違反**: `additionalProperties: false`を再帰付与する`_strict_schema`と、`required`に全プロパティを含めていなかった`issues.items`（`issue_id`のみrequired）およびトップレベル（`status`のみrequired）が衝突し、`invalid_json_schema`でモデル実行前にAPIが拒否していた。全プロパティをrequiredへ追加し、意味的に任意な`claim_id`はnullable型（`["string","null"]`）にして対応（`codex.py`）

**結果**: 5件すべて修正後、`test_real_two_agent_council`が実機で完走（`status: completed`、7フェーズ、約180秒）。既定スイート108件は無傷。
**教訓**: Contract Test（Fake経由）は「入出力の形」は検証できるが、「モデルが実際にその形を守るか」「CLI固有のラッパー形式」「外部APIのschema制約」はFakeでは再現できない。L-4 spikeの目的（実装開始前にAdapter capabilityを確認する）が、実際には実装後の実機テストでしか埋まらない種類の欠陥だったことも分かった。

---

### W-7. Adapter実行タイムアウトがSPEC §8.4より短くハードコードされていた

**重要度**: Critical
**箇所**: SPEC §8.4 / `adapters/claude.py` / `adapters/codex.py`
**背景**: metrics収集ハーネスの初回live実行（質問1件）で`TIMEOUT`が2回発生し、W-3のRun全体再試行上限（2回）を使い切って`failed`になった。原因を調査したところ、両Adapterの`execute()`が`subprocess.run(..., timeout=45)`（Claude）/`timeout=60`（Codex）とハードコードされており、SPEC §8.4が`verify`モードに定める「1 Agent・1呼び出し180秒」を守っていなかった。W-6完走時はたまたま応答が速かっただけで、通常の応答速度でも45〜60秒を超えることがある。
**回答**: 確定。両Adapterのコンストラクタへ`timeout_s: int = 180`を追加し、`execute()`の`subprocess.run`タイムアウトへ使用する。`quick`/`strict`モードはOrchestrator側が未実装（J-3）のため、モード別配線は行わず、既定値をverifyの180秒に固定した。J-3実装時にCLIからmodeに応じた`timeout_s`を渡すよう拡張する。`probe()`の5秒（バージョン確認のみ、モデル呼び出しなし）は変更しない。
**実装への影響**: 正常な応答速度でもRun全体の再試行予算を無駄に消費しなくなる。

---

### W-8. 既定設定のagent_idが実Adapter時も`fake-*`のままだった

**重要度**: Minor
**箇所**: `config/agents.yaml`
**背景**: W-7後のmetrics再実行（quota枯渇で`failed`）のJSON出力を確認したところ、`participants: ["fake-claude"]`と、実Adapter（`ORACLE_COUNCIL_USE_REAL=1`）で実行しているにもかかわらずFake時代の識別子が残っていた。動作に影響はないが、実測データやnote記事で「Fakeで動いているのか実Adapterで動いているのか」を混乱させる。
**原因**: `cli.py`は`RegisteredAgent(agent_id=entry["id"], ...)`と設定ファイルの`id`をそのまま使う。`id`は実装（mock/real）を問わず固定の参加者識別子だが、既定の`config/agents.yaml`が`id: fake-claude`/`id: fake-codex`とPhase 0時代の名前のままだった。
**回答**: 確定。`config/agents.yaml`の`id`を`claude-code`/`codex-cli`へ変更した。`id`は「今回mockかrealか」ではなく「どのAgentか」を表す識別子であることをコメントで明記した。テストは全て独自の一時configを使うため（`ORACLE_COUNCIL_CONFIG`環境変数で上書き）影響なし。124件全パス確認済み。

---

## X. SearchProvider Contract

### X-1. SearchProviderの型契約とエラーEnum

**重要度**: Major
**箇所**: SPEC §10.2 EvidenceProvider / K-2 / S-1
**疑問**: 実検索サービスをいきなり特定APIへ固定せず、最初にSearchProvider Contractを閉じるべきではないか。
**回答**: 確定。次の契約をSPEC正本とする。

```text
SearchResult:
  url: str
  title: str
  snippet: str
  rank: int
  source: str
  retrieved_at: str

SearchProvider (Protocol):
  search(query: str, limit: int) -> list[SearchResult]
```

エラーは`SearchError(code, message)`として送出する。

- `SEARCH_AUTH_REQUIRED`
- `SEARCH_QUOTA_EXCEEDED`
- `SEARCH_RATE_LIMITED`
- `SEARCH_TIMEOUT`
- `SEARCH_UNAVAILABLE`
- `INVALID_SEARCH_RESPONSE`

責務分離（S-1と同じ線）: SearchProviderは候補URL（`SearchResult`）を返すだけで、本文取得を行わない。本文取得・SSRF防御・Content-Type・サイズ制限は引き続き`SafeHttpFetcher`が一元的に担う。`WebEvidenceProvider`は`SearchProvider`と`SafeHttpFetcher`を別々にDIで受け取り、`search()`は`SearchProvider`だけ、`fetch()`は`SafeHttpFetcher`だけを呼ぶ。

最初の実検索実装を選ぶ条件（今回は選定しない、契約のみ確定）:
- APIキーの扱いが明確
- 検索結果にURL・タイトル・スニペットがある
- 無料または低コストで試せる
- レート制限を検出できる
- テストでFakeへ差し替え可能
- SafeHttpFetcherと責務が重ならない

**実装への影響**: `models.py`に`SearchResult`・`SearchError`、`evidence.py`に`SearchProvider` Protocol、`fakes.py`に`FakeSearchProvider`を追加。`WebEvidenceProvider.__init__`の`searcher`引数を生callableから`SearchProvider`へ変更（未接続のため破壊的変更の影響なし）。
**SPEC.md修正文**: §10.2へ上記契約とエラーEnumを追加する。

---

### X-2. 外部検索APIより先にAI CLI内蔵検索をSpikeする方針

**重要度**: Major
**箇所**: X-1 / SPEC §10.1（AI CLI組み込み検索は補助情報） / §16.1（任意シェルコマンド禁止、MVP対象外）
**背景**: レビュアーからBrave Search API等の外部契約より先に、Claude Code・Codex CLIが既に持つWeb検索能力を`CliSearchProvider`として使えないかSpikeすべきという指摘があった。二段構え（1. AI CLIに検索させ候補URLを構造化出力させる、2. SafeHttpFetcherでOracle Councilが再取得・検証する）は、既にSPEC §10.1の「AI CLIの組み込み検索は補助情報として利用できるが、Oracle Councilが直接アクセスし記録できなければ`verified`の根拠に数えない」と整合する。
**Spike結果（ヘルプ出力調査、API呼び出しなし）**:

- **Codex CLI**: 現バージョンでWeb検索機能は無効。`codex features list`で`search_tool: removed`、`standalone_web_search: under development(false)`、`web_search_cached`/`web_search_request: deprecated(false)`。`-s`サンドボックスは`read-only`/`workspace-write`/`danger-full-access`のいずれもファイルアクセス軸であり、検索専用の許可軸がない。シェルコマンド経由（curl等）でのネットワークアクセスは、SPEC §4「AIが生成した任意のシェルコマンドの自動実行」の対象外条項に抵触するため採用しない。**結論: 現時点でCodexはCliSearchProviderの候補にならない**
- **Claude Code**: `--tools <tools...>`が実在し、`""`で全ツール無効、ツール名を指定して個別許可できる（例: `Bash,Edit,Read`）。ヘルプの例に`WebSearch`という具体名は載っていないため、実在確認には最低1回のlive呼び出し（`--tools WebSearch --disallowed-tools Bash,Edit,Write`等での実行）が必要。**未検証（次のlive予算消費として保留）**
- Claude in Chrome連携（`--chrome`）はブラウザ状態依存・ログイン済みページアクセス・再現性の問題があるため、レビュアー方針どおり将来機能とし今回のSpike対象外

**回答**: 方針は確定（二段構えを採用、Chrome操作は将来）。Claude側の`WebSearch`ツール名の実在確認と、ツールを検索専用へ絞れるか・構造化JSON（url/title/support）を返せるか・SafeHttpFetcherで再取得できるURLか、はlive呼び出しでの検証待ち。`SearchProvider`実装として`ManualSearchProvider`（既存のManualEvidenceProviderと同型）、`CliSearchProvider`（Claude検証後に実装）、将来`BraveSearchProvider`等の外部APIの3段構成とする。

---

### W-9. Phase.finished_atが自身の完了時刻ではなくRun全体の終了時刻になっていた

**重要度**: Major
**箇所**: `orchestrator.py` `_execute_phase` / `_finish`
**背景**: W-8修正後のmetrics再実行（quota回復、成功）で`phases[].elapsed_ms`を確認したところ、`respond: 89734ms`、`claim_extract: 65785ms`、`verify: 47385ms`…`audit: 8546ms`と開始順に単調減少していた。`executions[].elapsed_ms`（個別呼び出しの実測）は正常（respondの2呼び出しは10542msと13406ms）で、Phase集計側だけが異常だった。
**原因**: `_execute_phase`は成功パスで`record.finished_at`を一度も設定しておらず、`_finish()`の「まだNoneなRun.finished_atで埋める」というフォールバックが全成功Phaseへ適用されていた。結果、各Phaseの`elapsed_ms`は「そのPhase開始からRun全体終了まで」となり、後続する全Phaseの所要時間を含んでしまっていた（最後に実行されるauditだけが正しい値に近かった）。
**回答**: 確定。`_execute_phase`の成功パスで、呼び出し成功のたびに`record.finished_at = utc_now()`を更新するよう修正した。`respond`（最低成功数2）や`audit`（W-2の再監査で2回呼ばれ得る）のような複数回呼ばれるPhaseでも、最後の成功呼び出しの時刻が残るため、Phaseの実際の所要時間（開始〜最終成功）が正しく求まる。回帰テストは決定的な擬似時計（`utc_now`をmonkeypatch）で検証し、実時間sleepを使わない。既存のAgentExecution単位の時間は元々正しく、影響を受けていなかった。
**検証**: quota回復後の実機再実行で確認した成功条件4点はすべて満たされた——`participants: ["claude-code", "codex-cli"]`、`agent_call_count: 7`（7フェーズ完走）、全呼び出しが180秒設定内（最長22,105ms）、metrics JSONLは期待スキーマどおり。125テスト全パス。

---

### W-10. SafeHttpFetcherの既定opener構築がTypeErrorでクラッシュしていた

**重要度**: Critical
**箇所**: `evidence.py` `_NoRedirect` / `SafeHttpFetcher.__init__`
**背景**: X-2のWebSearch Spikeスクリプトから`SafeHttpFetcher()`を既定引数（`opener`省略）で構築したところ、`urllib.request.build_opener()`が`TypeError: expected BaseHandler instance, got <class 'oracle_council.evidence._NoRedirect'>`で例外を送出した。
**原因**: `_NoRedirect`クラスがどの基底クラスも継承しておらず、`urllib.request.OpenerDirector.add_handler()`の`isinstance(handler, BaseHandler)`チェックに落ちていた。既存の`test_evidence.py`は全テストで`opener`を独自モックとして注入しており、**既定opener経路（実運用で使われる唯一の経路）が一度もテストを通っていなかった**。
**回答**: 確定。`_NoRedirect(BaseHandler)`と修正し、`urllib.request.BaseHandler`をimportした。`SafeHttpFetcher()`が既定引数だけで構築できることを検証する回帰テストを追加（`opener`未注入）。126テスト全パス。
**教訓**: モックへ完全依存したテストは「モックへ正しく差し替えられるか」しか検証せず、「本番経路が実際に動くか」を検証しない。Contract Testに既定構成でのsmoke testを含めるべきだった。W-6（Adapter実機バグ）と同型の教訓——Fakeでは出ない、実際にコンストラクト/実行して初めて見つかる欠陥。

---

### X-3. CliSearchProvider Spike結果: Claude Code WebSearchは実用候補

**重要度**: Major
**箇所**: X-2 / `scripts/spike_claude_websearch.py`
**背景**: X-2で保留していたClaude Codeの`WebSearch`ツール実在確認をlive実行した（1回。W-10のバグにより2回クラッシュで空振りし、計3回のlive呼び出しを要した）。
**結果**: 5項目すべて確認できた。

- `--tools WebSearch`は有効なツール名として受理される（`tool_name_rejected: false`）
- 空の一時cwdはファイル変更・シェル実行後も空のまま（`cwd_stayed_clean: true`）
- `{"sources": [{"url", "title", "snippet"}]}`形式の構造化JSONを正しく返す（3件）
- 返された3件のURLは全てSafeHttpFetcherで独立に再取得成功（`docs.python.org`、実在ブログ、チュートリアルサイト。`content_type: text/html`、実サイズ取得）
- 取得不能URLを機械的に区別する仕組み（`fetch_error`フィールド）は実装済みだが、今回は3件とも成功したため否定側（実際に取得失敗するURL）は未検証

**回答**: 確定。**Claude CodeのWebSearchツールは`CliSearchProvider`の実用候補**と判断する。次に`CliSearchProvider`（`SearchProvider` Protocol実装）を`evidence.py`へ追加し、Claude Adapterの`search`用フェーズ指示（`_PHASE_SCHEMA_HINT`類似）を定義する作業が残る。外部API（Brave等）は「今は選定しない」のまま維持し、CliSearchProviderが安定しない場合の代替として温存する。

---

### X-4. CliSearchProviderの実装

**重要度**: Major
**箇所**: `adapters/claude.py` `CliSearchProvider`
**回答**: 確定。Spike（X-3）のロジックを本実装へ引き継いだ。`adapters/claude.py`へ`CliSearchProvider`を追加（`adapters/`配下——`evidence.py`へは依存させず、Protocolの構造的型付けだけで`SearchProvider`を満たす）。

- `search(query, limit) -> list[SearchResult]`は`claude -p <prompt> --tools WebSearch --output-format json --no-session-persistence --safe-mode`を実行し、既存の`classify_cli_error`・`_extract_json_object`を再利用してenvelopeを展開する
- エラーは`AgentFailure`のerror_code語彙をSearchError Enum（X-1）へ写像する専用マップ（`_SEARCH_ERROR_MAP`）で変換。`AUTH_REQUIRED→SEARCH_AUTH_REQUIRED`、`QUOTA_EXCEEDED→SEARCH_QUOTA_EXCEEDED`、`RATE_LIMITED→SEARCH_RATE_LIMITED`、未知のCLI状態は`SEARCH_UNAVAILABLE`、JSON解析失敗は`INVALID_SEARCH_RESPONSE`
- `rank`は1始まりの出現順、`source`は`"claude-code-websearch"`固定、`retrieved_at`は取得時刻。`url`欠落など不正なエントリはRun全体を失敗させずスキップする
- `WebEvidenceProvider(fetcher=SafeHttpFetcher(), searcher=CliSearchProvider())`で接続可能。CLI呼び出し部分のみ本文取得は行わず、S-1の責務分離を維持する

**テスト**: `subprocess.run`をモックした11ケース（正常系のSearchResult構築・rank・limit切り詰め・不正エントリのスキップ、異常系の7エラーコード対応、`--tools WebSearch`が実際にコマンドへ渡ることの確認）。CIは実CLIを呼ばない（SPEC §18.2）。137テスト全パス。

---

### X-5. CliSearchProviderのCLI実験接続

**重要度**: Major
**箇所**: `cli.py` / `evidence.py` / `tests/unit/test_cli.py` / `tests/unit/test_evidence.py`
**回答**: 確定。`oracle ask`へ`--evidence-provider {fake,cli-search}`を追加した。省略時は従来どおり`FakeEvidenceProvider`、`--evidence-file`単独は従来どおり`ManualEvidenceProvider`、`--evidence-provider fake`はFake、`--evidence-provider cli-search`は`WebEvidenceProvider(fetcher=SafeHttpFetcher(), searcher=CliSearchProvider())`を構築する。`--evidence-file`と`--evidence-provider`の同時指定は`configuration_error`/exit 3で拒否する。

`WebEvidenceProvider.collect()`はPhase 0互換レイヤーとしてのみ実装した。対象は`critical`/`major`の最大5 Claim、`critical`優先・同重要度は`claim_id`順、各Claimの`text`で`search(limit=5)`を1回、rank順にfetchし、成功はClaimごと最大3件、抜粋は最大1,200文字。`EvidenceFetchError`はそのURLだけスキップし、`SearchError`は握りつぶさず上位へ送出する。Evidenceには`authority: other`、`directness: indirect`、`stance: neutral`、`freshness: unknown`、`notes: experimental cli-search evidence`を付け、正式な§10.2品質判定として扱わない。

CLIでは`SearchError`を`verification_unavailable`/exit 3へ変換し、messageは`web evidence unavailable: <SearchError.code>`だけに限定する。通常テストは`CliSearchProvider`、`SafeHttpFetcher`、subprocess/HTTPをFakeまたはMockへ差し替え、実Claude、WebSearch、実HTTPは起動していない。実機WebSearch E2Eは未実行。

**テスト**: CLI選択・競合・JSONエラー・Fake fallback禁止と、`WebEvidenceProvider.collect()`の順序、上限、fetch失敗スキップ、SearchError伝播、保守的Evidence値を追加。152テスト全パス。

---

### X-6. 収集済みEvidenceの安全なJSON監査概要

**重要度**: Major
**箇所**: `models.py` / `orchestrator.py` / `cli.py` / `tests/unit/test_orchestrator.py` / `tests/unit/test_cli.py`
**回答**: 確定。`RunResult`へ`evidence: tuple[dict, ...] = ()`を末尾フィールドとして追加し、OrchestratorのRun終了時に`state.evidence`のdeepcopy snapshotを渡すようにした。正常完了、withheld、audit保留、Agent失敗、Budget失敗、Storage失敗のRunResult生成経路を対象にし、Evidence収集前の終了では空tupleになる。

`output_run_result(..., use_json=True)`では`result.evidence`を直接出さず、許可リスト方式の`evidence_summary()`を通す。JSONへ出す項目は`evidence_id`、`claim_id`、`url`、`title`、`source`、`rank`、`content_type`、`retrieved_at`、`excerpt`のみ。`excerpt`はJSON表示時だけ最大400文字へ制限する。許可キーでもdict/list等のネスト値は直接出さない。`content`、`body`、`raw_content`、`prompt`、`stdout`、`stderr`、`environment`、`headers`、`cookies`、`tokens`、`diagnostics`、`notes`、未知キーは出力しない。

Storage契約は変更しない。JSONLへEvidence本文や概要を新規保存せず、`history show`や`--store-content`の境界も変更しない。今回の変更は実行直後のJSON監査性改善に限定する。

**テスト**: RunResult保持、収集前失敗は空、収集後の後続失敗・withheldでも保持、Evidence snapshot化、Fake/Manual/Web相当のJSON出力、不足フィールド耐性、400文字制限、禁止キー非出力、ネスト値の非出力、Evidenceなし空配列、非JSON表示不変を追加。163テスト全パス。

---

### X-7. Evidence収集フェーズの計測とエラー観測

**重要度**: Major
**箇所**: `models.py` / `orchestrator.py` / `evidence.py` / `cli.py` / `scripts/collect_metrics.py`
**回答**: 確定。`PhaseRecord`へ`metrics: dict[str, Any] = field(default_factory=dict)`を追加し、`evidence_collect`では検索回数、候補件数、fetch試行/成功/失敗件数、Evidence件数、対象Claim件数、Evidence取得済みClaim件数、SearchError/EvidenceFetchErrorのコード別件数を記録する。全PhaseのJSONに`metrics`を出し、metricsなしPhaseは`{}`とする。

`EvidenceCollectionResult`を追加し、`WebEvidenceProvider.collect_with_metrics()`でEvidenceとmetricsを同時に返す。既存`collect()`は後方互換のため維持し、`collect_with_metrics()`のEvidenceだけを返す。Orchestratorは`collect_with_metrics()`があるProviderでは詳細metricsを使い、Fake/Manual等のfallback Providerでは従来どおりEvidence有無だけで`outcome`を決める。`last_metrics`のようなProvider内部可変状態は使わない。

`evidence_collect.success_count`はEvidence件数ではなく収集処理の正常完了回数とし、正常終了ならEvidence 0件でも`1`、SearchError等でPhase失敗なら`0`とする。`outcome`は`PhaseRecord.outcome`を正本とし、metrics内へ重複保存しない。詳細metricsがある場合は、Evidence 0件なら`no_evidence`、fetch失敗またはEvidenceなし対象Claimがあれば`partial_evidence`、全対象ClaimにEvidenceがありfetch失敗なしなら`evidence_found`とする。

Run開始後の`SearchError`は`evidence_collect`を`failed`にし、`error_code=<SearchError.code>`、`metrics.search_error_codes`、`finished_at`を記録してRunを`failed`/exit 3にする。CLI JSONの外部statusはX-5互換で`verification_unavailable`とし、messageは`web evidence unavailable: <code>`だけを出す。個別URLの`EvidenceFetchError`はRunを失敗させず、fetch失敗件数とコード別件数へ集計して次候補へ進む。

Storage契約は変更しない。Phase metricsはin-memory `PhaseRecord`、RunResult、実行直後のCLI JSON、`collect_metrics.py`の安全なフラット項目に限定し、JSONL保存や`history show`、`--store-content`、Evidence本文保存は拡張しない。

**テスト**: metrics既定値独立、EvidenceCollectionResultのdeepcopy snapshot、fake clockによるevidence_collect計測、正常/0件/SearchErrorのsuccess_count、途中SearchErrorの部分Evidence/metrics保持、outcome規則、WebEvidenceProvider metrics、SearchErrorのPhase/Run/CLI JSON記録、fetch失敗集計、metrics sanitize、collect_metrics.pyの新旧JSON互換を追加。182テスト全パス。

---

### X-7.1. Unicode/IRIエンコード障害の切り分けと堅牢化

**重要度**: Major
**箇所**: `evidence.py` / `tests/unit/test_evidence.py` / `tests/unit/test_cli.py` / `tests/unit/test_adapter_unicode.py`
**回答**: 確定。c572303の実Web E2Eで発生した`'ascii' codec can't encode characters...`は、日本語質問そのものではなく、WebSearch候補URL/IRIを`urllib.request.Request`へ渡す境界で非ASCII URLがHTTP URIへ正規化されていない可能性が高いと切り分けた。Claude/Codex Adapterは既に`subprocess.run(..., text=True, encoding="utf-8", errors="replace")`で日本語質問を扱えることをモックテストで確認した。

`SafeHttpFetcher`はHTTPリクエスト前にIRIをURIへ正規化する。hostnameはIDNA化し、path/query/fragmentの非ASCII文字はpercent-encodeする。既存percent-encodeは二重変換しない。正規化不能なURLは`EvidenceFetchError("INVALID_URL_ENCODING")`へ変換し、個別候補のfetch失敗としてmetricsへ集計して次候補へ進む。URL全文、検索語、prompt、stdout/stderr、環境変数、例外全文はmetricsへ入れない。

表示用Evidence URLは、実際にfetchへ使用した正規化済みURIを保持する。全候補がURL正規化で失敗した場合も、収集処理自体は`succeeded`、`success_count=1`、`outcome=no_evidence`、`fetch_error_codes.INVALID_URL_ENCODING`として記録し、CLI最外層の`internal_error`へ漏らさない。Storage契約は変更しない。実E2Eは再実行していない。

**テスト**: 日本語質問のClaude/Codex Adapterモック実行、日本語path/query、国際化ドメイン、既存percent-encode、ASCII URL、不正IRIの`EvidenceFetchError`化、不正IRI候補後の継続、全候補不正時の`no_evidence`、CLI JSONが`internal_error`にならないことを追加。

---

### X-8. 固定評価セット準備

**重要度**: Major
**箇所**: `evaluation/x8/` / `scripts/run_x8_evaluation.py`
**回答**: 準備完了。実AI・実Web Evidence付きMVPの信頼性測定用に、8問の固定評価セット`eval-set-v1.json`を作成した。カテゴリは単純事実、安定法令事実、最新/近年情報、誤った前提、競合資料、用語訂正、Evidence不足、日時指定の現在情報に分けた。質問文・順序・期待挙動・受入確認・許容classification・`max_external_runs=1`はJSONを正本にする。

runnerは、worktree clean、HEAD一致、ローカル`refs/remotes/origin/main`一致、リポジトリ外output、同一question-id再実行禁止を確認する。最初のlive実行前に`manifest.json`を原子的に作成し、eval-set SHA-256、HEAD、question_idsを固定する。外部コマンド直前に`attempted.json`を原子的に作成し、失敗しても解除しない。stdout/stderrは別ファイルに保存し、`record.json`と`summary.jsonl`/`summary.csv`にはrun_id、status、classification、Phase概要、Evidence metricsなどの監査用抽出値だけを保存する。回答全文、生prompt、生stdout/stderr、本文全文はsummaryへ入れない。

`--dry-run`は外部AIや`oracle ask`を起動せず、`attempted.json`や`manifest.json`も作らない。開発中の未コミット差分がある状態でも、dirty状態を安全確認結果として表示する。本番評価実行ではdirty worktreeを拒否する。`--all`は通常のwithheld/no_evidence/partial_evidenceでは継続するが、timeout、不正JSON、`internal_error`、`configuration_error`、`verification_unavailable`、`run_id=null`、subprocess起動失敗では残り質問へattemptedを作らず停止する。`--rebuild-summary`で既存のattempted/stdout/stderr/recordからrecordとsummaryを再構築できる。

**テスト**: 質問順、manifest作成と不一致拒否、1問1回制限、attempted後の再実行拒否、失敗後の再実行拒否、`--all`の継続/停止規則、HEAD/origin/dirty/output-dir拒否、stdout/stderr分離、不正JSON耐性、metrics抽出、欠落フィールド耐性、timeout、spawn失敗、summary再構築、CSV formula injection防止、dry-runでsubprocess未実行、日本語質問の引数渡し、UTF-8環境、`shell=False`を確認する。

---

### X-8.1. criticize INVALID_OUTPUTの安全な診断

**重要度**: Major
**箇所**: `models.py` / `adapters/base.py` / `orchestrator.py` / `cli.py` / `scripts/run_x8_evaluation.py`
**回答**: q01の保存済みX-8結果だけでは、`criticize`の`INVALID_OUTPUT`がJSON構文不正、必須フィールド欠落、型不正、コードフェンス等のどれだったかは特定不能だった。保存JSONにはphase/executionの`INVALID_OUTPUT`と所要時間はあるが、schema検証の失敗理由や生critic出力は保存されていない。したがって、q01原因を推測してparserを緩める変更は行わない。

将来の同種障害に備え、`AgentFailure`へ安全な`public_summary`を追加した。Adapterのschema検証は、必須フィールド欠落や型不正などの構造的理由だけを固定形式で`public_summary`へ入れる。raw stdout/stderr、prompt、モデル出力全文、任意値、未知フィールド名は入れない。Orchestratorはallowlist検証済みの`public_summary`がある場合だけPhase/Executionの`error_summary`へ反映し、CLI JSONとX-8 runnerの`phase_summary`へ安全な`error_summary`を追加で出す。CLIとrunnerは共通のallowlist検証を使い、許可形式外、改行/制御文字、不正surrogate、200文字超は出力しない。`raw_diagnostic`は従来どおり`store_content=True`時だけ。

**テスト**: INVALID_OUTPUTの安全な構造診断、任意値や未知フィールドをpublic_summaryへ入れないこと、allowlist外・改行/制御文字・200文字超の拒否、public_summaryなしで生例外へfallbackしないこと、OrchestratorがPhase/Executionへ反映すること、CLI JSONがphase/execution双方で安全なsummaryだけを出すこと、X-8 runnerのrecord用phase_summaryに安全な`error_summary`だけが残ることを追加。

---

### X-8.2. 誤前提訂正と回答保留の判定分離

**重要度**: Major
**箇所**: `models.py` / `classification.py` / `orchestrator.py` / `adapters/`
**回答**: q04の保存済み結果では、Claimは全て`verified`/`supported`で、`criticize`/`synthesize`/`audit`は成功しているが、最終的に`withheld`だった。verify後の安全判定ではなく、初回auditが`approved`以外を返した経路が直接原因である。ただし`--no-store`のためaudit理由やsynthesize本文は保存されておらず、auditがなぜ未承認だったかは特定不能。

ローカル解析で再現可能な実装問題として、Real Adapterがphase payloadの`responses`/`claims`/`evidence`をpromptへ渡しておらず、verify後にClaimを丸ごと置換してClaim本文やIDが失われることを確認した。これでは誤前提、訂正Claim、補足Claim、Evidence対応を後続phaseが安定して区別できない。

最小修正として、Real Adapterのphase入力へrun contextをJSONデータとして渡し、`criticize`/`synthesize`/`audit`には「ユーザー前提の反証は訂正材料であり、支持済み訂正Claimがある場合はそれだけでwithheldにしない」旨を明記した。verify結果は既存Claimへmergeし、Claim ID、本文、`claim_role`を保持する。新たに`claim_role`（`user_premise` / `proposed_answer` / `contextual`）を追加し、既定値は`proposed_answer`で後方互換にした。`user_premise`が`contradicted`でも、支持済み訂正Claimがあれば分類上は公開可能にするが、訂正Claimが不足・未確認・競合ならwithheld/慎重分類を維持する。

**テスト**: 誤前提contradicted＋訂正Claim verified/supportedでwithheldしないこと、訂正Claimがunverifiedならwithheld維持、user_premiseだけならwithheld維持、q05相当の断定Claim contradictedはwithheld維持、verify mergeがClaim本文/ID/roleを保持すること、Adapter promptがclaims/evidence/final_answerと誤前提訂正指示を含むことを追加。

---

*最終更新: 2026-07-13 — W-1〜W-10、K-2、X-1、X-2、X-3、X-4、X-5、X-6、X-7、X-7.1確定。X-8固定評価セット準備完了。X-8.1でINVALID_OUTPUTの安全な構造診断を追加。X-8.2で誤前提訂正と回答保留の判定を分離。実機2 Agent完走達成、metrics成功条件4点クリア、CliSearchProviderのCLI実験接続、Evidence監査概要JSON出力、Evidence収集Phase計測、非ASCII URL/IRI正規化を完了。既回答77問、未回答23問。*
