# hikitsugi.md — 引き継ぎ（Phase 0実装）

> 最終更新: 2026-07-13。前セッションがトークン切れで中断したため、現在地と残作業をここに集約する。
> 正本はFIX_PLAN.md（残ブロッカー）とTESTCASE.md（期待値）。本書は「次に何をするか」の作業指示書。

## 1. 現在地

- 設計: SPEC v0.3.6で確定済み。USECASE / SEQUENCE / CLASS / STATE / TESTCASE(151件)すべてCodexレビュー済み
- 確定済みの主要契約: 終了コード表(§13.4)、Run分類の二段判定(§15.3)、evidence_collect 2軸モデル(§15.7)、withheld開示境界(§11.5)、Storage Contract(§15.1)、TokenBudget Contract(§8.7)
- 実装: `src/oracle_council/` にPhase 0骨格あり（未コミット）。**テストは未作成**
- git: `af079fa` まではpush済み。`pyproject.toml`と`src/`が未追跡

## 2. src/ の実装状況

| ファイル | 状態 |
|---|---|
| `models.py` | 済: Budget系DTO、RunEvent、StorageLoadResult、RunResult。**Claim/ClaimImportance/ClaimStatus等は今回追加** |
| `budget.py` | 済: S-7契約どおり（原子的reserve、commit/release、call上限12、assert_settled） |
| `storage.py` | 済: S-3/M-3/T-4契約どおり（Storage採番、fsync、lockfile、TRUNCATED_TAIL警告、破損検出） |
| `fakes.py` | 済: ScriptedAgentAdapter、FakeEvidenceProvider |
| `orchestrator.py` | 済: T-5二段判定・withheld短絡・exit 4、複数Agent対応（V-1準拠のpreflight） |
| `classification.py` | 済: §15.3の二段判定（W-1でv0.3.6と整合済み） |
| `assignment.py` | 済: §6.2〜§6.4の決定的Agent割当（Responder 2分離、Synthesizer≠Auditor、insufficient_agents） |
| `tests/` | 済: budget / storage / classification / assignment / orchestrator、47ケース全パス |

## 3. 今回のセッションで完了したこと（2026-07-12）

1. `classification.py`: §15.3二段判定を実装（第1段: withheld安全判定、第2段: 分類表、優先順位つき）
2. `orchestrator.py`: verify後にclassifyを適用。withheldなら`criticize/synthesize/audit`を`phase_skipped`イベント付きでskip（AI呼び出し4回で終端）、Run=`completed`、exit 4。公開時は二段判定の分類を反映。`RunResult.claims`でU-1開示用のClaim検証結果を返す
3. `models.py`: ClaimImportance / ClaimStatus / Claim を追加
4. `tests/unit/` 4ファイル・38ケース、**全パス**
   - test_budget.py: 予約・解放・排他（20スレッド競合）・12回上限・retry別予約・assert_settled
   - test_storage.py: InMemory/JSONLの採番・round-trip・TRUNCATED_TAIL・破損・sequence gap・run_idエスケープ拒否
   - test_classification.py: 二段判定の決定表（withheld 3系・分類9系・優先順位）
   - test_orchestrator.py: 7回フェーズ順・withheld 4回exit 4・conflicting exit 0・監査未承認failed・予算切れ・no-store・例外時のbudget精算
5. E2E動作確認済み: JSONLストレージで正常系（7回・exit 0・イベント9件連番）とwithheld系（4回・exit 4）を実走

## 4. 次セッション以降の残タスク（優先順）

1. ~~Responder 2 Agent分離~~ 済（2026-07-12、`assignment.py`）。確認ポイント7点（2 Agent必須・insufficient_agents・Synthesizer≠Auditor・role_priority＋設定順・同一入力同一割当・脱落後の再選定も決定的・暗黙の自己監査なし）をテストで固定済み。insufficient_agentsはV-1準拠でRun生成前に停止（exit 3）
2. ~~修正・再監査1回~~ 済（2026-07-12、W-2確定・SPEC v0.3.7）。changes_required→同一Synthesizer修正→同一Auditor再監査1回（7→9回）。再監査不承認と初回blockedは`failed`ではなく`withheld`（completed・exit 4・final_answer非公開）。AuditIssueはopen→resolved追跡、revision系4イベント記録。「修正込み10回」の10はClarifier込みの数と照合済み
3. ~~再試行~~ 済（2026-07-12、W-3確定）。対象はSPEC正本どおりTIMEOUT/RATE_LIMITEDのみ。同一slot 1回・Run全体2回・retry_of・別予約・失敗履歴保持・起動後失敗は安全側commit。代替Agent選定はX-8.16で仕様確定済み・未実装（非一時エラーは現行実装では決定的にfailed）
4. ~~Phase/AgentExecutionレコードの正式化~~ 済（2026-07-12、W-4確定）。PhaseRecord（min/success_count、skipped/failed、evidence_collectのoutcome）、AgentExecutionRecord（試行ごと、retry_of、error_summary定型200字、raw_diagnosticはstore-contentのみ）、RunMetadataRecordスナップショット（run_*イベントへ埋め込み、再集計しない）。再監査は同一PhaseへのExecution追加。STATE.mdのW-2前の残骸も修正
5. ~~CLI骨格~~ 済（並行セッション: argparse実装、exit code全表、--json純化、real/fake adapter切替、Windows UTF-8）。W-5でpre-flight probeフィルタとlive test 4分割を追加。**2 Agent実機完走テストはClaude利用上限の解除後に `$env:ORACLE_COUNCIL_LIVE="1"; python -m pytest -m "live and expensive" -vv` で再実行**
6. **Clarification Engine**（Phase 1）: 決定的ルール→§7.2ステータス。J-4（2ラウンド目のClarifier）が未回答
7. ~~L-4 spike~~ 実質完了（実Adapter接続と実機テストで代替。probe/execute乖離等の知見はW-5に記録）

## 4-2. 実機接続後の優先順（2026-07-12レビュー合意）

1. ~~Claude復活後に2 Agent実機E2E完走~~ **達成**（2026-07-12、W-6）。`test_real_two_agent_council`が実機PASS（7フェーズ、約180秒）。過程で見つけた5件のAdapterバグ（quota誤分類、Claude封筒未展開、Claim enum未検証、Codex verify schema enum欠落、Codex audit schema OpenAI厳格モード違反）はすべて修正済み・回帰テスト追加済み
2. ~~Manual Evidence付きE2E~~ 済（`--evidence-file`＋ManualEvidenceProvider、既定スイートで検証）
3. ~~SearchProvider Contract確定~~ 済（2026-07-12、X-1・K-2確定、SPEC v0.3.8）。`SearchResult`/`SearchProvider`/`SearchError`実装済み、`FakeSearchProvider`でテスト可能。次は実検索サービス選定（未選定、条件6点はSPEC §10.2参照）
4. SafeHttpFetcher経由の実Web Evidence（実検索サービス選定待ち、下記参照）
5. ~~評価指標ハーネス~~ 済（2026-07-12）。`scripts/collect_metrics.py`：CLIのJSON出力（`phases[].elapsed_ms`をこのセッションで追加済み）から総所要時間・Phase別所要時間・呼び出し回数・分類割合・quota/failure発生数を集計しJSONLへ保存。単体テストあり（`test_collect_metrics.py`）。**実行はしていない**（liveでAPI費用が発生するため、対象問い数と実行タイミングはユーザー判断待ち）。サンプル質問は`scripts/sample_questions.txt`
   - 実行例: `ORACLE_COUNCIL_LIVE=1 python scripts/collect_metrics.py scripts/sample_questions.txt --out metrics.jsonl`（`ORACLE_COUNCIL_LIVE`はこのスクリプト自体は見ないが、live実行の合図として揃えている）
   - 「単独AI回答との差」はまだ未実装。単一Agentだけを有効にした設定ファイルが必要（現状のbaselineは`--mode quick`の粗い代替に留まる）

## 4-3. metrics初回実行の結果とW-7

指示どおり1問だけ実行（`--limit 1`）。結果: `run_status: failed`、`TIMEOUT`×2、`agent_call_count: 4`（respond×2, claim_extract止まり）。

原因はAdapterのバグだった（W-7、修正済み・push待ち）: `claude.py`/`codex.py`の`execute()`が`timeout=45`/`timeout=60`にハードコードされており、SPEC §8.4の`verify`モード規定（1呼び出し180秒）を守っていなかった。W-6完走時はたまたま速かっただけ。両Adapterに`timeout_s: int = 180`のコンストラクタ引数を追加し既定値をSPECへ合わせた。`quick`/`strict`のmode別配線はOrchestrator未実装（J-3）のため保留。

**タイムアウト修正後の再実行（2026-07-13）**: `QUOTA_EXCEEDED`で3.7秒即失敗（Claude quota再枯渇）。バグではなく外部要因——むしろW-5の分類修正（`QUOTA_EXCEEDED`を正しく検出、`EXECUTION_ERROR`に誤分類しない）と非再試行ルールが正しく機能していることを確認できた。ただしW-7の180秒タイムアウト自体はまだ実効性を検証できていない（API側が即座に拒否したため）。metrics JSONLのスキーマは正常（`participants`/`executions[]`/`phases[].elapsed_ms`/`metadata`すべて期待どおり）。

**W-8（2026-07-13）**: 上記JSONLで`participants: ["fake-claude"]`と、実Adapter実行なのにFake時代の識別子が残っていることが判明。`config/agents.yaml`の`id`を`claude-code`/`codex-cli`へ修正済み（124テスト全パス確認）。次回のmetrics実行ではこの識別子が反映される。

**quota回復後の再実行（2026-07-13、成功）**: `scripts/collect_metrics.py`を再実行し、4条件すべて確認できた——`participants: ["claude-code", "codex-cli"]`（W-8修正が反映）、`agent_call_count: 7`（7フェーズ完走）、全呼び出しが180秒設定内（最長22,105ms、W-7が効いている）、metrics JSONLは期待スキーマどおり。**metricsの検証条件は達成**。

**W-9（同じ実行結果から発見）**: `phases[].elapsed_ms`が開始順に単調減少する異常値だった（respond: 89734ms、audit: 8546ms）。`_execute_phase`の成功パスで`record.finished_at`を設定しておらず、`_finish()`のフォールバックでRun全体の終了時刻が全成功Phaseへ埋まっていたのが原因。修正済み（`record.finished_at = utc_now()`を成功のたびに更新）、決定的な擬似時計での回帰テストを追加、125テスト全パス。`executions[].elapsed_ms`（個別呼び出し）は元から正常だった。

## 4-4. CliSearchProvider Spike（X-2、レビュアー方針転換）— 次はこれ

外部検索API契約より先に、Claude/CodexのCLI内蔵検索能力を`CliSearchProvider`として使えるかSpikeする方針にレビュアーが転換。ヘルプ出力調査（API呼び出しなし）の結果:

- **Codex**: `codex features list`でWeb検索系フィーチャーがすべて`removed`/`under development(false)`/`deprecated(false)`。**候補外**
- **Claude**: `--tools`は実在し個別ツール名を許可できるが、`WebSearch`という名前がヘルプの例に載っておらず**live呼び出しでの実在確認が未実施**

**Spike実行結果（2026-07-13、成功）**: `scripts/spike_claude_websearch.py`で5項目すべて確認できた——`WebSearch`ツール名は受理される、空cwdはファイル変更後も空のまま、`{"sources":[{"url","title","snippet"}]}`形式の構造化JSONを返す、返された3URLは全てSafeHttpFetcherで再取得成功（docs.python.org等）。取得不能URL側（否定ケース）は今回3件とも成功したため未検証だが、判定ロジック自体は実装済み。**結論: Claude WebSearchは`CliSearchProvider`の実用候補**（X-3）。

**途中で発見・修正したバグ（W-10）**: `SafeHttpFetcher()`を既定引数で構築するとTypeErrorでクラッシュしていた（`_NoRedirect`が`BaseHandler`を継承していなかった）。既存テストが全て`opener`をモック注入していたため、既定経路（実運用の唯一の経路）が一度もテストを通っていなかった。修正済み、回帰テスト追加、126テスト全パス。このバグにより2回のlive呼び出しを空振り（結果を確認する前にクラッシュ）し、計3回のlive呼び出しでSpikeを完了した。

## 4-5. 次: CliSearchProvider本実装

Spike成功により候補確定。残作業:
~~1〜3~~ 済（2026-07-13、X-4確定）。`CliSearchProvider`は`evidence.py`ではなく`adapters/claude.py`へ追加した（`claude`バイナリを呼ぶ他のロジックと同居させ、Protocolの構造的型付けだけで`SearchProvider`を満たす。`evidence.py`→`adapters`の依存は作らない）。Spikeのプロンプト・envelope展開ロジックをそのまま引き継ぎ、`classify_cli_error`のerror_code語彙を`SearchError` Enum（X-1）へ写像する`_SEARCH_ERROR_MAP`を追加。取得不能URL（否定ケース）はFakeで検証済み（`test_evidence.py`の`fetch_error`系）——live再実行での否定ケース確認はまだ。137テスト全パス。

`WebEvidenceProvider`への接続例:
```python
from oracle_council.adapters.claude import CliSearchProvider
from oracle_council.evidence import SafeHttpFetcher, WebEvidenceProvider

provider = WebEvidenceProvider(fetcher=SafeHttpFetcher(), searcher=CliSearchProvider())
```
X-5でCLIから実験的に選択可能になった。既定動作は引き続きFakeで、明示指定時だけ`CliSearchProvider`を使う。

## 4-6. CliSearchProviderのCLI実験接続（X-5）

実装済み（2026-07-13、X-5確定）。`oracle ask`に`--evidence-provider {fake,cli-search}`を追加し、`cli-search`明示時だけ次を構築する。

```python
WebEvidenceProvider(fetcher=SafeHttpFetcher(), searcher=CliSearchProvider())
```

後方互換性は維持済み: オプション省略は`FakeEvidenceProvider`、`--evidence-file`単独は`ManualEvidenceProvider`、`--evidence-file`と`--evidence-provider`同時指定は`configuration_error`/exit 3。

`WebEvidenceProvider.collect()`はPhase 0互換レイヤーとして最小実装した。`critical`/`major`のみ最大5 Claim、検索はClaimごと1回`limit=5`、fetch成功はClaimごと最大3件、抜粋は1,200文字まで。`EvidenceFetchError`はURL単位でスキップ、`SearchError`はCLIで`verification_unavailable`/exit 3へ変換する。Evidence品質値は保守的に`authority=other`、`directness=indirect`、`stance=neutral`、`freshness=unknown`固定。

未実施・未実装:

- Fake Agent＋実Claude WebSearch＋実HTTP取得の1回限定スモークは成功済み（2026-07-13）。`metadata.evidence_count=2`、`evidence_collect=succeeded`、全7フェーズ完走、作業ツリーcleanを確認
- 反証検索、authority判定、registrable domain独立性判定、90秒制限、24MB制限などの完全なSPEC §10.2収集処理は未実装
- 否定ケースのlive確認と外部検索サービス選定は引き続き未実施

## 4-7. Evidence監査概要のJSON出力（X-6）

実装済み（2026-07-13、X-6確定）。`RunResult`へ収集済みEvidenceのdeepcopy snapshotを保持し、`oracle ask --json`のトップレベル`evidence`へ安全な概要だけを出力する。

出力許可項目は次の9項目のみ:

```text
evidence_id, claim_id, url, title, source, rank, content_type, retrieved_at, excerpt
```

`excerpt`はJSON表示時だけ最大400文字。許可キーでもdict/list等のネスト値は直接出さない。`content`、`body`、`raw_content`、`prompt`、`stdout`、`stderr`、`environment`、`headers`、`cookies`、`tokens`、`diagnostics`、`notes`、未知キーは出力しない。Storage契約は変更していないため、JSONL保存や`history show`のEvidence表示は未対応のまま。

次の優先作業:

- 実Claude＋実Codex＋実WebSearchの1回限定E2Eを実行し、回答、Claim抽出、Web Evidence、検証、統合回答を1つのJSONで監査する
- その前提として`PYTHONPATH=(Resolve-Path .\src).Path`を設定し、このcloneのsrcを読むことを確認する
- live実行はClaude/Codex利用枠と外部HTTPを消費するため、再試行なしの1回限定で行う

## 4-8. Evidence収集Phaseの計測（X-7）

実装済み（2026-07-13、X-7確定）。`evidence_collect`のPhaseRecordを収集前に作成し、`started_at`/`finished_at`/`elapsed_ms`が実際の収集処理を囲むようにした。`success_count`はEvidence件数ではなく収集処理の正常完了回数で、正常終了ならEvidence 0件でも`1`、SearchError等のPhase失敗なら`0`。

`PhaseRecord.metrics`を追加し、`evidence_collect`では次を記録する:

```text
search_count, candidate_count, fetch_attempt_count, fetch_success_count,
fetch_failure_count, evidence_count, target_claim_count,
claims_with_evidence_count, search_error_codes, fetch_error_codes
```

metricsにはURL、title、excerpt、本文、検索語、prompt、stdout/stderr、環境変数を入れない。CLI JSONの`phases[]`には全Phaseで`metrics`を出し、metricsなしPhaseは`{}`。Storage契約は変更しておらず、JSONL保存や`history show`にはPhase metricsを新規保存しない。

`WebEvidenceProvider.collect_with_metrics()`を追加し、既存`collect()`は後方互換でEvidenceだけを返す。Run開始後のSearchErrorは内部的に`evidence_collect failed`/Run failed/exit 3へ記録し、外部CLI JSONではX-5互換の`verification_unavailable`を返す。個別URLのEvidenceFetchErrorはRunを失敗させず、件数とコード別件数を記録して継続する。

次の優先作業:

- 代表質問5〜10問を1回ずつ実行し、完走率、classification、Evidence件数、フェーズ別所要時間、検索/fetch失敗率を測る
- `collect_metrics.py`のフラットEvidence metricsを使い、検索が遅いのか、fetchが失敗しているのか、AI処理が遅いのかを切り分ける

## 4-9. Unicode/IRIエンコード障害の堅牢化（X-7.1）

実装済み（2026-07-13、X-7.1確定）。c572303の実Web E2Eで`urllib`境界由来とみられるASCII encode failureが出たため、実E2Eは再実行せず、モックテストで境界を切り分けた。Claude/Codex Adapterは日本語質問をUTF-8 text modeでsubprocessへ渡せることを確認済み。

`SafeHttpFetcher`はfetch前に検索結果URL/IRIをHTTP URIへ正規化する。hostnameはIDNA化し、path/query/fragmentの非ASCII文字はpercent-encodeする。既存percent-encodeは二重変換しない。正規化できないURLは`EvidenceFetchError("INVALID_URL_ENCODING")`として個別候補のfetch失敗にし、Run全体の`internal_error`へ漏らさない。metricsにはコード別件数だけを残し、URL全文、検索語、prompt、stdout/stderr、環境変数、例外全文は入れない。

Storage契約は変更していない。次の実Web E2Eでは、`evidence_collect.metrics.fetch_error_codes.INVALID_URL_ENCODING`の有無と、`internal_error`ではなく通常のPhase記録に収まることを確認する。

## 4-10. X-8固定評価セット準備

準備済み（2026-07-13）。`evaluation/x8/eval-set-v1.json`に8問の固定評価セットを定義した。質問文・順序・カテゴリ・期待挙動・受入確認・許容classification・`max_external_runs=1`はJSONを正本にする。

`scripts/run_x8_evaluation.py`は、実行前にHEAD、ローカル`refs/remotes/origin/main`、worktree、output-dirを検査する。本番実行ではdirty worktreeを拒否し、output-dirがリポジトリ内なら拒否する。最初のlive実行前に`manifest.json`を作成し、eval-set SHA-256、HEAD、question_idsを固定する。各質問は`attempted.json`を外部コマンド直前に原子的に作成して1回制限をかける。失敗してもattemptedは解除しない。stdout/stderrは質問ごとのディレクトリへ分離保存し、`record.json`と`summary.jsonl`/`summary.csv`には監査用の抽出値だけを保存する。

dry-runは外部AI、WebSearch、実HTTPを起動せず、attemptedやmanifestも作成しない。未コミット差分がある開発中でもdirty状態を安全確認結果として表示する。本番実行コマンドはREADME参照。生成された評価結果は`C:\PROJECT\OracleCouncil-evals\x8\<HEAD>\`配下に置き、Gitへ追加しない。timeout、不正JSON、`internal_error`、`configuration_error`、`verification_unavailable`、`run_id=null`などのsystemic failureでは`--all`を停止し、未実行質問のattemptedを作らない。`--rebuild-summary`で既存record群からsummaryを再構築できる。

## 4-11. criticize INVALID_OUTPUTの診断改善（X-8.1）

q01の保存済みX-8結果は読み取り専用で確認した。`criticize` phaseが`INVALID_OUTPUT`で失敗したことは分かるが、生critic出力やschema検証詳細は保存されていないため、原因分類は「保存情報不足により特定不能」。q01評価結果は再実行・改変していない。

推測でparserを緩める代わりに、将来のINVALID_OUTPUTへ安全な構造診断を残す経路を追加した。`AgentFailure.public_summary`は必須フィールド欠落、型不正、JSON抽出不能などの構造的理由だけを固定形式で保持する。Orchestratorはallowlist検証済みの値だけをPhase/Executionの`error_summary`へ入れ、CLI JSONとX-8 runnerの`phase_summary`へ出す。raw stdout/stderr、prompt、モデル出力全文、任意のモデル値、未知フィールド名は出さない。許可形式外、改行/制御文字、不正surrogate、200文字超は出力しない。Storage契約は変更していない。

## 4-12. 誤前提訂正と回答保留の分離（X-8.2）

q04の保存済みX-8結果は読み取り専用で確認した。Claimは全て`verified`/`supported`、publish phaseは全て成功していたため、早期のClaim安全判定ではなくaudit未承認によるwithheldだった。ただしaudit出力理由は保存されておらず、直接の判断理由は特定不能。

実装上の再現可能な問題として、Real Adapterがphase payloadの`claims`/`evidence`/`final_answer`をpromptへ渡していなかったこと、verify後にClaimを丸ごと置換してClaim本文・ID・roleを失っていたことを修正した。`claim_role`を追加し、省略時は`proposed_answer`。`user_premise`が反証されても、支持済みの訂正Claimがある場合はそれだけで公開ブロックにしない。訂正Claimが未確認、競合、反証、または存在しない場合は保留を維持する。Storage契約は変更していない。

追加した回帰観点:

- 誤前提Claim（`user_premise`）が`contradicted`でも、訂正Claimが`verified`/`supported`なら公開可能分類へ進める
- 訂正Claimが`unverified`、`conflicting`、`contradicted`、または存在しない場合は保留・慎重分類を維持する
- q05相当の「断定Claim自体が反証される」ケースと、q07相当のEvidence 0件はwithheldを維持する
- verify mergeでClaim本文、ID、`claim_role`を保持する
- Real Adapterの後続phase promptへclaims、evidence、critique、final_answerなどのrun contextを渡す

検証済み: `py -m pytest` は224 passed / 6 deselected / 460 warnings、`git diff --check`成功。X-8評価結果は読み取りのみで、q04やrunnerは再実行していない。次に実機で確認する場合は、この差分をコミット・pushした後、新しいHEAD用の別評価ディレクトリでX-8再評価を行う。既存`C:\PROJECT\OracleCouncil-evals\x8\6a55ede`は基準値として変更しない。

## 4-13. X-8.2後のlive再評価（q04）で新しい未解決の失敗を発見 — 次はこれ

X-8.2（誤前提と回答保留の分離）コミット・push後、新HEAD（`9dd2407`）で`scripts/run_x8_evaluation.py --dry-run`を実行し安全確認（worktree clean・origin一致・出力先`x8/9dd2407`が既存`x8/6a55ede`と非衝突）。8問フルの本番live実行はコストが大きいため、ユーザー判断でq04（false_premise、X-8.2の直接対象）1問だけに絞ってlive再実行した。

**運用ミス**: live 1問の所要時間（実測約280秒）を見積もらず、最初の試行をBashツール既定の2分タイムアウトで強制終了してしまった。`attempted.json`は外部コマンド起動直前に原子的作成されるため、この試行でq04の1回限定ロックは無結果のまま消費された（`C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live\`、`record.json`なし、`stdout.json`/`stderr.txt`とも空）。別出力ディレクトリ（`9dd2407-q04-live2`、タイムアウトを10分へ延長）で再度実行し完走。**結果としてq04の外部呼び出しをこのセッションで実質2回消費した**（eval-set側の`max_external_runs=1`は出力ディレクトリ単位のロックであり、別ディレクトリを跨いだ多重実行そのものは防げない）。次にlive評価を回す際は、SPEC §8.4のverifyモード上限（1呼び出し180秒）×フェーズ数から逆算し、最初からBashのtimeoutを600000ms付近に設定すること。

**完走した方（`9dd2407-q04-live2`）の結果**: `status: failed`、`result_classification: unverified`（q04の`allowed_classifications`は`verified`/`partially_verified`/`withheld`のいずれかで、これに該当しない）。フェーズ進行は`respond`（2件成功）→`claim_extract`→`evidence_collect`（Evidence 15件収集、`outcome: partial_evidence`）までは正常。`verify` phaseで`codex-cli`が起動から413ms後に`error_code: EXECUTION_ERROR`（`error_summary: "verify execution ended with EXECUTION_ERROR."`のみ、allowlist経由の定型文）で失敗し、Run全体が`failed`で終端した。

X-8.2で修正した「誤前提Claimが反証されても訂正Claimがverified/supportedなら公開可能」ロジックは、audit以降のRun分類判定の話であり、そこに到達する前の`verify`実行自体が失敗しているため**今回の失敗はX-8.2の修正対象とは無関係**。X-8.1で追加した構造診断（`AgentFailure.public_summary`）は主に`INVALID_OUTPUT`（必須フィールド欠落・型不正・JSON抽出不能）向けで、`EXECUTION_ERROR`（`classify_cli_error`の一般フォールバック、CLIサブプロセス自体の異常終了系）には粒度の粗い定型文しか残らない。`--no-store`実行だったため生stdout/stderrは保存されておらず、根本原因は**q01（X-8.1）と同様「保存情報不足により特定不能」**。413msという速さから、タイムアウトよりもCLI起動直後の即時拒否（引数不正、認証/quota、コンテキスト長超過など）を疑うが未確認。

**次にやること（未着手）**:

1. EXECUTION_ERROR系にもX-8.1相当の粗い構造診断（subprocess非ゼロ終了か／タイムアウトか／既知パターン不一致か程度)を残せないか検討・実装する。再現性のない一発の失敗から仕様を変えない（X-8.1の教訓と同じ）
2. 再現性確認のため、ユーザーの追加承認を得た上でq04をもう一度live実行する（別出力ディレクトリ、timeoutは600000ms前提）。1回で再現しなければ外部要因（レート制限等）の可能性が高い
3. 8問フル評価はまだ未実施。1問実行するたびに数分かかる前提でスケジュールし、`--all`はBashの`run_in_background`＋Monitor監視、またはtimeoutを600000ms超で分割実行することを検討する
4. 既存の基準値`C:\PROJECT\OracleCouncil-evals\x8\6a55ede`と、今回のq04単発結果（`9dd2407-q04-live`は無結果につき無視、`9dd2407-q04-live2`が有効）はどちらも変更・削除していない

## 5. 決定表fall-throughの顛末（QandA W-1で確定済み）

実装中に「仕様の穴」と見えた3件は、検証の結果、SPEC v0.3.5/v0.3.6の改訂で既に解消されていた（criticalのconflicting→row1、minorのcontradicted→row4、row5の拡張により表は網羅的）。逆に実装側がv0.3.4の表を前提にした齟齬（minorのみ全て確認済み→仕様は`verified`、実装は`partially_verified`）があり、修正済み。防御的既定値`partially_verified`は到達不能だが残している。

**教訓**: 実装は必ずSPECの最新版を参照する。本書のような中間メモを仕様の代わりにしない。

## 6. 未回答ブロッカー（FIX_PLAN §2-3の要約）

- 実装前: J-3（quick）、L-5（フェーズ別出力schema）、M-5（代替Agentと12回）、O-6（stdin/一時ファイル）、S-4〜S-6、S-8〜S-10、T-2（cancel基準）、T-3（DNS pinning試験境界）
- L-5はFakeのoutput契約にも影響するため、Phase 0のfixture固定前に確定するのが望ましい

## 7. 環境・実行方法

```bash
# セットアップ（初回）
pip install -e .[dev]
# テスト
python -m pytest
```

- Python 3.11+、依存はMVPコアでは標準ライブラリのみ（pytestはdev）
- コミット時は5点セット（QandA/FIX_PLAN/SPEC等）と実装を分けること。実装コミットは `feat: implement phase0 core (budget, storage, verify flow)` 系
- コミットメッセージ末尾に `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` を付ける運用

## 8. 参照

- 終了コード: SPEC §13.4 / 分類: §15.3 / Budget: §8.7 / Storage: §15.1 / withheld開示: §11.5
- 状態遷移: STATE.md / テスト期待値: TESTCASE.md（BLOCKED解除済みのものから実装）
- note記事素材: docs/note-draft.md（「23回→7回」「AIに真偽を決めさせない」「保留は失敗ではない」が柱）

## 4-14. EXECUTION_ERRORの安全な構造診断（X-8.3）

実装済み（2026-07-13）。既知のTIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、AUTH_REQUIRED、INVALID_OUTPUT分類は維持したまま、認識不能なCLI失敗にもプログラム側で確定した固定診断を付けるようにした。

外部へ出せる診断は次のallowlistだけで、CLI出力から文字列を連結しない:

```text
<phase> process exited with a non-zero status.
<phase> process could not be started.
<phase> execution failed without a recognized error pattern.
<phase> execution failed unexpectedly.
```

現在のAdapter経路では、既知パターンに一致しない非ゼロ終了を`subprocess_nonzero_exit`、起動時の`OSError`を`process_launch_failure`として記録する。`AgentFailure.public_summary`、CLI JSONのExecution/Phase、X-8 runnerの`phase_summary`はいずれもallowlist検証を通す。stdout、stderr、prompt、モデル出力、コマンド全文、パス、環境変数、認証情報、Cookie、HTTP header、検索語、例外本文は外部出力へ出さない。Storage Contract、新しいJSONL項目、Runの終了コード・classification・PhaseStatus、`--no-store`の意味は変更していない。

追加テストは、Claude/Codex双方の非ゼロ終了・起動失敗、固定summary、診断情報の混入拒否、既存分類の回帰、CLI/X-8 summaryのallowlist経路を対象とした。`py -m pytest`は234 passed / 6 deselected。q04 live、実CLI、実WebSearch、実HTTP、expensive評価は指示どおり再実行していない。次の作業は、ユーザー承認後に新しい評価ディレクトリでq04を1回限定再評価すること。今回の診断により、同様の失敗が再発した場合でも少なくとも「非ゼロ終了」か「起動失敗」か、既知エラー分類かを外部へ安全に識別できる。

## 4-15. q04 1回限定live再評価（X-8.4）

2026-07-13、HEAD `bca0c90`でq04だけを新規出力先`C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83`へ1回実行した。dry-runでmain、worktree clean、origin/main一致、real Adapter、CLI search、JSON、`--no-store`を確認し、live外部実行は1回で終了した。失敗後の再試行、別ディレクトリ、他の質問、保存済み評価結果の変更は行っていない。

結果は`status=failed`、`exit_code=1`、`result_classification=unverified`、`run_id=7e891cbe-12f3-4568-bf3f-ea829dc0f962`、`agent_call_count=4`。Claude/Codex双方が参加し、respond、claim_extract、evidence_collect（Evidence 14件、search 5、fetch成功14/18）まで成功したが、verifyが254msで`EXECUTION_ERROR`となった。sanitized summaryには`verify process exited with a non-zero status`相当が現れ、前回のEXECUTION_ERRORは再現した。ただしOrchestrator既存ラップにより外部文言は`verify invalid output: ...`となっており、根本原因は未特定。`json_parse_status=valid`、`leakage_check=passed_structural_check`で、raw stdout/stderr等はGitへ保存していない。

q04の受入確認（18歳への訂正、20歳との混同回避、飲酒・喫煙等との区別）はverify失敗により最終回答へ到達せず未評価。次は実CLIを再実行せず、固定FakeでEXECUTION_ERROR summaryのラップを修正し、通常テストで回帰を防ぐ。

## 4-16. EXECUTION_ERROR summary誤ラップ修正（X-8.5）

X-8.4のq04で、`EXECUTION_ERROR`の固定診断が`verify invalid output: ...`へ誤ラップされ、末尾ピリオドも二重になる問題を確認した。原因はOrchestratorの`_failure_summary()`が`error_code`を見ず、`public_summary`を常にINVALID_OUTPUT形式へ変換していたこと。

`EXECUTION_ERROR`は`safe_error_summary()`で検証し、現在のphaseと一致する固定summaryをそのまま返す。phase不一致、不正形式、任意文字列は`<phase> execution ended with EXECUTION_ERROR.`へフォールバックする。`INVALID_OUTPUT`だけは従来どおり`safe_public_summary()`で構造診断を検証して`<phase> invalid output: ...`へ整形する。Storage Contract、JSONL形式、Adapter分類、retry、timeout、Evidence処理は変更していない。

Fakeベースの回帰テストを追加し、PhaseRecord/AgentExecutionRecordのsummary、秘密情報非混入、ラップ除去、二重ピリオド除去、phase不一致フォールバック、既存INVALID_OUTPUT互換性を確認した。`py -m pytest`は236 passed / 6 deselected。live、expensive、q04再実行、実CLI、WebSearch、HTTPは実行していない。

## 4-17. Codexの長いPhase入力をstdinへ移行（X-8.6）

q04で2回再現したverify非ゼロ終了に対し、CodexAdapterが`build_phase_input()`全文を位置引数へ渡していたことを確認した。verifyはClaimとEvidenceを含むため前段より長い。Windowsコマンドライン長または引数受け渡しが原因というのは未確認の仮説であり、今回の変更で原因候補を除去しただけである。

Codex本実行のargvからprompt本文を削除し、末尾の`-`でstdin入力を指定した。`subprocess.run(input=question, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)`を使用し、本実行で`stdin=DEVNULL`は併用しない。probe、read-only、ephemeral、output-schema、model指定、JSON抽出、既存エラー分類は維持した。temp fileは非機密のJSON Schemaだけで、成功・失敗後とも削除する。

50,000文字超の質問・Claim・Evidenceを使うtransportテストを追加し、全文がstdinへ渡り、argvに本文識別子が入らず、schemaに入力本文が含まれないことを確認した。`py -m pytest`は238 passed / 6 deselected。live、expensive、q04、実CLI、WebSearch、HTTPは実行していない。O-6はCodexAdapter側のみ前進し、ClaudeAdapter/CliSearchProviderを含む全体完了ではない。次はユーザー承認後の新HEAD q04 1回限定live再評価。

## 4-18. Codex stdin化後のq04再評価（X-8.7）

ユーザー明示承認後、HEAD `177abc4`でq04を新規出力先`C:\PROJECT\OracleCouncil-evals\x8\177abc4-q04-stdin`へ1回だけ実行した。評価セットは`evaluation/x8/eval-set-v1.json`、実行中のみ`src`を`PYTHONPATH`へ追加し、dry-runでq04のみ・real adapter・CLI search・JSON・`--no-store`・HEAD一致・cleanを確認した。

結果は`exit_code=1`、`status=failed`、`classification=unverified`、`agent_call_count=4`。CodexとClaudeが参加し、respond、claim_extract、evidence_collect（Evidence 14件、search 5、fetch成功14/23）までは成功したが、verifyが`AUTH_REQUIRED`（`verify execution ended with AUTH_REQUIRED.`）で失敗した。以前の短時間`EXECUTION_ERROR`は今回の条件では再現しなかったが、認証要求で停止したためstdin化が根本原因を解決したとは断定しない。criticize、synthesize、auditには到達せず、q04の受入条件は未評価。JSON parseはvalid、leakage checkはpassedで、raw stdout/stderr等はGitへ保存していない。

追加liveは承認なしに実行せず、次はFake/Contractで認証切れ時の停止と、verify以降のstdin transportを確認する。

## 4-19. AUTH_REQUIRED部分一致の廃止（X-8.8）

X-8.7の`AUTH_REQUIRED`は真の認証切れか、旧分類器の部分一致による誤分類かをsanitized結果だけでは確定できない。旧実装は`"auth" in lowered`と`"login" in lowered`を使っていたため、`authoritative`、`authentic`、説明文の`login`にも一致し得た。

自由文fallbackを境界付きallowlistへ変更した。`unauthorized`、`not logged in`、`login required`、`please log in`、`authentication required`、`invalid api key`、`missing api key`、`access token expired`、refresh tokenのexpired/revoked/already usedを認証失敗とする。構造化401/403と構造化`unauthorized`は従来どおり維持する。

`authoritative source`、`authority lookup`、`authentic response`、`author field`、`OAuth documentation`、`login page documentation`、単独の`authorization policy`はAUTH_REQUIREDにしない。明示パターンに一致しない非ゼロ終了はEXECUTION_ERRORへ戻る。認証情報・probe・login status・Adapter引数・stdin transport・Storage Contract・公開境界は変更していない。

明示的認証失敗と誤分類防止の通常テストを追加し、`py -m pytest`は255 passed / 6 deselected。live、expensive、q04、実CLI、`codex login status`、WebSearch、HTTPは実行していない。次は承認後のローカル認証状態確認またはq04 1回限定再評価。
## 4-20. X-8.9 q04 live re-evaluation

User approval was obtained for exactly one live run. On HEAD `0bdf5ca`, the q04 run completed once in `C:\\PROJECT\\OracleCouncil-evals\\x8\\0bdf5ca-q04-authfix`.

Sanitized result: `exit_code=1`, `status=failed`, `classification=unverified`, `run_id=d462fda2-85f6-4702-80d0-0d8ae560989e`, `agent_call_count=6`, participants `codex-cli` and `claude-code`. `respond`, `claim_extract`, `evidence_collect`, `verify`, and `criticize` succeeded. `synthesize` failed with `COMMAND_NOT_FOUND` and summary `synthesize execution ended with COMMAND_NOT_FOUND.`; `audit` was not reached.

Evidence metrics were 15 evidence items, 5 searches, 25 candidates, 20 fetch attempts, 15 fetch successes, and 5 fetch failures. JSON parsing was valid and leakage checking passed. The run did not reproduce `AUTH_REQUIRED`, but this cannot establish whether X-8.7 was a genuine authentication failure or a prior partial-match misclassification. Raw stdout/stderr and other sensitive artifacts were not read into the report or committed. No source/test changes were made; the remaining issue is external CLI availability during `synthesize`.
## 4-21. X-8.10 Claude Phase input stdin transport

X-8.9 ended after `criticize` because Claude-assigned `synthesize` returned sanitized `COMMAND_NOT_FOUND`. X-8.10 did not infer the root cause and did not run live or real Claude/Codex.

`ClaudeAdapter.execute()` now keeps only fixed CLI flags in argv and passes the complete `_build_prompt(..., build_phase_input(...))` result through `input=prompt`. The production Phase call no longer supplies `stdin=DEVNULL`; `probe()` and `CliSearchProvider` remain unchanged. JSON envelope extraction, Phase validation, usage accounting, error classification, retry behavior, and storage contracts were preserved.

Added a Fake subprocess transport test with a 50,000-character `synthesize` input, asserting sensitive input is absent from argv and present in stdin, and that the Claude JSON envelope still becomes a validated `AgentResult`. Updated the Unicode transport regression test to the same stdin contract.

`py -m pytest` passed: **258 passed, 6 deselected**. `git diff --check` passed. Live, q04, real Claude, real Codex, WebSearch, HTTP, and expensive evaluation were not executed.
## 4-22. X-8.11 q04 Claude stdin live re-evaluation

After explicit approval, exactly one q04 live run was executed on HEAD `05714b7` in `C:\\PROJECT\\OracleCouncil-evals\\x8\\05714b7-q04-claude-stdin`.

Sanitized result: `exit_code=4`, `status=completed`, `classification=withheld`, `timed_out=false`, run ID `7d42b9c7-a0c5-4df3-9ad8-92f5340b7e31`, and `agent_call_count=9`. Participants were `claude-code` and `codex-cli`. All phases from `respond` through `audit` succeeded. `synthesize` completed with `success_count=2`, `audit` completed with `success_count=2`, and the X-8.9 `synthesize COMMAND_NOT_FOUND` did not recur. This confirms the stdin transport worked through the later phases under these conditions, without proving a root cause for X-8.9.

Evidence metrics: 14 evidence items, 5 searches, 25 candidates, 23 fetch attempts, 14 fetch successes, and 9 fetch failures; outcome `partial_evidence`. JSON parsing was valid, leakage checking passed, and no error codes were reported. The q04 acceptance status was `not_assessed`; raw stdout/stderr and other sensitive artifacts were not read into the report or committed.
## 4-23. X-8.12 CliSearchProvider search prompt stdin transport

X-8.11 was already completed on HEAD `05714b7`; X-8.12 does not rerun q04 or any live capability. The remaining O-6 gap was `CliSearchProvider.search()`, which passed the user-derived search prompt as the `claude -p` argv value and used `stdin=DEVNULL`.

The search prompt now travels through `input=prompt`; argv contains only fixed Claude/WebSearch flags. Search result parsing, validation, limit handling, malformed-entry skipping, timestamps, error mapping, timeout handling, and SafeHttpFetcher responsibility were preserved. A Fake test covers a 50,000-character Japanese query and asserts the query is absent from argv and present in stdin.

`FIX_PLAN.md` O-6 progress now records Codex, Claude Phase, and CliSearchProvider stdin transport as implemented and Fake-tested. `py -m pytest` passed: **259 passed, 6 deselected**. `git diff --check` passed. Real Claude, WebSearch, q04, live, HTTP, and expensive evaluation were not executed.

## 4-24. X-8.13 q04 live re-evaluation after full stdin transport (O-6 confirmed)

After explicit user approval, exactly one q04 live run was executed on HEAD `8fcdeaf` in `C:\PROJECT\OracleCouncil-evals\x8\8fcdeaf-q04-clisearch-stdin`. `dream.md` (untracked, unrelated to this change) was the only worktree diff; it was set aside with `git stash -u` before the dry-run/live run and restored with `git stash pop` immediately after, so the eval script's dirty-worktree safety check ran against the real repo state. Dry-run confirmed HEAD/origin match, clean worktree, and a non-colliding output directory before the live command executed. `PYTHONPATH` was set to `src` for the run.

**Result: first `verified` completion with all three stdin transports in place.** `exit_code=0`, `status=completed`, `result_classification=verified`, `run_id=18a25201-780e-419c-be72-fd412fb433aa`, `agent_call_count=7`, participants `claude-code` and `codex-cli`. All seven phases (`respond` through `audit`) succeeded; none of the earlier failure modes (X-8.4 `EXECUTION_ERROR`, X-8.7 `AUTH_REQUIRED`, X-8.9 `synthesize COMMAND_NOT_FOUND`) recurred. Note: X-8.11 (Claude Phase stdin only, before X-8.12's CliSearchProvider fix) had already completed all seven phases once, with `synthesize` and `audit` each succeeding twice — but ended `status=completed`/`classification=withheld`. What is new here is that with Codex, Claude Phase, *and* CliSearchProvider all on stdin transport, q04 reached `verified`/`exit_code=0` and its acceptance criteria were met, which no prior live attempt achieved.

Evidence metrics: 12 evidence items, 4 searches, 20 candidates, 16 fetch attempts, 12 fetch successes, 4 fetch failures (`FETCH_FAILED`×3, `UNSUPPORTED_CONTENT_TYPE`×1); outcome `partial_evidence`. `json_parse_status=valid`, `leakage_check=passed_structural_check`.

Acceptance criteria assessed directly from the CLI's own `--json` output (not raw stdout/stderr — the sanitized structured fields already present in the tool's designed output boundary), since this run's purpose was specifically to validate false-premise correction and prior runs never reached a `final_answer` to check: all three q04 acceptance points are met. The premise claim (`c1`, "法定成人年齢は現在も20歳") is `contradicted`; the correction claim (`c2`, 2022-04-01 18歳への引き下げ) is `verified`; and the answer explicitly distinguishes the lowered contractual-adulthood age (18) from the still-20 drinking/smoking/public-gambling age limits, explaining why "20歳" persists in public perception. `acceptance_status` in `record.json` remains the runner's static `not_assessed` (the script does not auto-grade); the assessment above is a manual read of this run only.

This closes out O-6's "real Claude/WebSearch/q04/live confirmation" gap; O-6 is now confirmed by both Fake tests and one live q04 run covering all three transports. No source or test changes were made this session. `py -m pytest` still passes (259 passed, 6 deselected, exit 0).

Process note: `git stash -u` was used to set the untracked `dream.md` aside for the dry-run/live safety check, then restored immediately after. This worked without incident, but should not become standard practice — before future live evaluation runs, either write `dream.md` after the live run finishes, or commit it deliberately beforehand, so the worktree is clean without needing to stash anything.

Remaining open items are unchanged except that X-8.16 now resolves M-5/S-5: J-3, L-5, S-4, S-6–S-10, T-2, T-3 (design-gated FIX_PLAN blockers), J-4 (Clarifier second round), and evaluation of the remaining 7 X-8 questions (q01–q03, q05–q08 — none run live yet; q04 has been exercised repeatedly during transport debugging and is no longer a clean holdout). A full `--all` pass, if attempted, needs `run_in_background`+Monitor or a timeout budget well over 600s per question.

## X-8.16. M-5 / S-5 代替Agent・ExecutionPlan仕様確定（2026-07-14）

X-8.15のq08でClaudeの`synthesize`が`QUOTA_EXCEEDED`となった事実を具体例として、M-5とS-5を同時確定した。これは文書による仕様確定のみで、live、実CLI、HTTP、評価、source/test/config/runner変更は行っていない。

- retryは同一Agent・同一論理slot・同一phaseの新Execution（`retry_of`）で、slotあたり最大1回、Run全体最大2回。
- substitutionは異なるAgentが同じslot/phaseを引き継ぐ新Execution（`substitute_for`）で、Run全体最大1回。retryとは別枠で、各々別BudgetReservation。13回目は`TokenBudget.reserve()`前に拒否する。
- retry対象は`TIMEOUT`と`RATE_LIMITED`のみ。`AUTH_REQUIRED`、`QUOTA_EXCEEDED`、`COMMAND_NOT_FOUND`、`UNSUPPORTED_VERSION`、`UNSAFE_CAPABILITY`はRun全体unavailableとして同一Agent retryなしで候補探索、`EXECUTION_ERROR`はslot-local substitution。`INVALID_OUTPUT`、`CONTEXT_OVERFLOW`、`BUDGET_EXCEEDED`、`CANCELLED`、Evidence障害、Run生成前CLI/DNS/設定例外は対象外。
- Run開始時に`ExecutionPlan`を決定的に構築し、phase/slot/必要成功数/候補順/制約、retry=2、substitution=1、AI call=12を保持する。候補順はprobe/capability、`role_priority`降順、設定順tie-break、失敗・hard unavailable除外、独立性制約の順。
- Responderは異なる2 Agentを維持し、成功済みのもう一方を代替に使わない。SynthesizerとAuditorは常に別Agentで、Synthesizer候補選定時に別Auditor候補をlook-ahead確保する。
- 既定2 AgentでSynthesizerがquota切れになり、Codexを代替するとAuditorが残らない場合は、分離要件を破らずRunをfailedにする。q03のDNS失敗は別failure-boundary課題として維持する。

更新文書: `QandA.md`、`SPEC.md` v0.3.9、`CLASS.md`、`SEQUENCE.md`、`STATE.md`、`TESTCASE.md`、`FIX_PLAN.md`、本書、`instructions/result.md`。次はM-5/S-5実装、その後L-5、S-8。

## 4-25. X-8.14 seven-question holdout evaluation (q04 excluded) — partial, systemic stop at q03

Executed per a dedicated instructions.md gate, under explicit approval matching the required text exactly ("X-8.14の残り7問holdout live実行を、q01〜q03・q05〜q08各1回、合計最大7回だけ承認します"). Pre-checks passed: HEAD `e707d9e` (branch `main`), worktree clean (the untracked `dream.md` was moved outside the repo, not stashed, before starting, and restored after), `origin/main` matched, both `1212c67` and `8fcdeaf` confirmed as ancestors, `py -m pytest` passed (259 passed, 6 deselected, exit 0).

A q04-excluded holdout subset was generated outside the repo at `C:\PROJECT\OracleCouncil-evals\x8\e707d9e-holdout7-eval-set.json`: question order `q01,q02,q03,q05,q06,q07,q08`, 7 questions, each deep-equal to the corresponding object in the canonical `evaluation/x8/eval-set-v1.json` (SHA-256 `35af8d4ba22fcfa7e828986ea5bc1b2f374d85258c56bdc9dcbaaf16eb6c41d5`), with that source hash recorded inside the subset (subset SHA-256 `0511956bc1c6dace85740e0e59ec4f3faed678044f35ed39eaadee70251e7182`). The canonical eval set itself was not modified. Dry-run confirmed the runner would invoke `--adapter-mode real --evidence-provider cli-search --json --no-store` per question with a 600s per-question timeout, output outside the repo, and no q04.

The runner was invoked once (`--all`, 7-question subset) with `ORACLE_COUNCIL_LIVE=1`, in the background given the long expected runtime. **Result: systemic stop after q03; the runner never reached q05–q08.** External `oracle ask` invocations: 3 total (q01, q02, q03); q04: 0; q05–q08: 0 (no `attempted.json` created for any of them, confirming the stop was clean and nothing was silently retried). Per instructions, this systemic stop was not resumed or retried within the session.

- **q01** (stable_fact, 富士山標高): `exit_code=0`, `status=completed`, `classification=verified` (within `[verified, partially_verified]`), `run_id=0d376b4f-5574-4d81-b032-e7cf8876d531`, `agent_call_count=7`, all 7 phases succeeded, evidence 3 items (fetch 3/5, `UNSUPPORTED_CONTENT_TYPE`×2), `partial_evidence`. Acceptance (3776m, no conflicting values) manually confirmed **met** from the CLI's sanitized answer/claims fields: answer states 3,776m, sole claim `c1` is `supported`.
- **q02** (stable_legal_fact, 成年年齢18歳への引き下げ): `exit_code=0`, `status=completed`, `classification=verified` (within allowed set), `run_id=18e73ed9-51e2-4acc-b327-334be89222a2`, `agent_call_count=7`, all 7 phases succeeded, evidence 6 items (fetch 6/8), `partial_evidence`. Acceptance (2022-04-01 施行日、成立日との混同なし) manually confirmed **met**: answer states 2022-04-01 施行 without conflating it with the law's separate 2018 passage date; claims verified.
- **q03** (recent_award_fact, 2024年ノーベル物理学賞): `exit_code=1`, `status=internal_error`, `classification=null`, `run_id=null`, no participants/phases recorded (failure occurred before Run creation). The CLI's own structured JSON envelope reported `message: "[Errno 11001] getaddrinfo failed"` — a Windows DNS-resolution failure, not an application-level Phase or classification failure, and not one of the previously catalogued Adapter error codes. `json_parse_status=valid`, `leakage_check=passed_structural_check`. Acceptance: **not assessable** (no final answer reached). This is the systemic-failure trigger the runner correctly stopped on.

Aggregate: attempted 3/7, completed 2 (both `verified`, both within `allowed_classifications`, both acceptance-met), 1 `internal_error` (q03, not attempted count toward classification stats), 0 retries, 0 timeouts, 0 phase-level failures among attempted questions, q04 executed 0 times. Evidence fetch success: q01 60% (3/5), q02 75% (6/8). Total `agent_call_count` across attempted questions: 14 (q01: 7, q02: 7, q03: 0).

No source, test, config, runner, or eval-set changes were made. Raw `stdout.json`/`stderr.txt` were read locally only to extract the sanitized answer/claims text (for acceptance) and the CLI's own structured error message (for q03); none of that raw content, nor the evaluation artifacts or subset file, were added to Git. `dream.md` was intentionally left unmodified this session per the X-8.14 instructions.

**Per instructions, this systemic stop is not resumed automatically.** Resuming q05–q08 requires a separate task and a new explicit approval. Next planned work after this is recorded is M-5 (alternate-agent selection and retry design), then L-5, then S-8, per the agreed non-parallel ordering — unless the user instead wants q05–q08 attempted first.

## 4-26. X-8.15 q05–q08 holdout continuation — all four attempted, 3/4 within allowed classifications

Executed per the gated instructions.md (commit `78ae55c`), under explicit approval matching the required text exactly ("X-8.15のq05〜q08 holdout live実行を、各1回、合計最大4回だけ承認します"). `dream.md` was moved outside the repo before starting (no `git stash`), leaving `git status --short` completely empty. Pre-checks passed: HEAD `78ae55c` = origin/main, branch `main`, ancestors `0ec758a`/`1212c67`/`8fcdeaf` confirmed, `py -m pytest` 259 passed / 6 deselected, `git diff --check` clean.

Holdout subset generated outside the repo at `C:\PROJECT\OracleCouncil-evals\x8\78ae55c-holdout4-eval-set.json` (SHA-256 `e3e6e993efc686ea3e4837648cffba3e8bfa9e5266edaf522df81c12d7bba90b`): exactly q05–q08 in order, each deep-equal to the canonical set (source SHA-256 `35af8d4b...` asserted inside the generator). Dry-run verified real adapter, cli-search, `--no-store`, 600s/question, output outside the repo. Runner invoked exactly once (`--all`); **all 4 questions attempted, no systemic stop, 0 retries, 0 timeouts, q01–q04 executed 0 times**. Runner process exit code was 4 — by design it propagates the first non-zero question exit code (q07's withheld exit 4), not an evaluation failure.

- **q05** (contested_fact, ナイル川最長断定): `exit_code=0`, `completed`, `verified` (allowed), `run_id=24f08a2a-16dc-4cd2-b128-d8c3a736bea8`, 7 calls, all 7 phases succeeded, evidence 15 (fetch 15/16). The user-premise claim ("断定できる") is `contradicted` while correction claims are verified — the X-8.2 false-premise logic again produced a publishable corrected answer. Acceptance **met**: Nile/Amazon competition explained, measurement/definition dependence explained (USGS vs Guinness figures), no over-assertion ("断定はできません").
- **q06** (terminology_correction, 休火山/活火山): `exit_code=0`, `completed`, `partially_verified` (allowed), `run_id=fe61e115-a6ee-4335-99b9-21a369bb3a42`, 7 calls, all 7 phases succeeded, evidence 15 (fetch 15/17, JMA sources). Two minor claims stayed `unverified` (2003年改定の年次、かつて休火山と呼ばれた), hence partially_verified. Acceptance **met**: 活火山と明示、休火山が現行分類にない旧表現と説明、Evidence矛盾なし。
- **q07** (likely_no_evidence, 架空企業の売上高): `exit_code=4`, `completed`, `withheld` (allowed), `run_id=75201974-8879-4689-a037-498c1ebcdebf`, 4 calls — the designed withheld short-circuit: respond×2 → claim_extract → evidence_collect (12 items, none confirming the company exists) → verify left critical claims `unverified` → criticize/synthesize/audit skipped, `final_answer` withheld (text null per U-1). Acceptance **met**: no sales figure fabricated, evidence insufficiency visible via disclosed claim statuses, outcome is 保留.
- **q08** (current_fact, Python最新安定版): `exit_code=1`, `status=failed`, `classification=unverified` (**not** in allowed set `[verified, partially_verified, withheld]`), `run_id=5439873d-547d-4ee8-a1cd-48d31b87d255`, 6 calls. respond through criticize succeeded (evidence 14, fetch 14/23), then `synthesize` failed in 3.2s with `QUOTA_EXCEEDED` (fixed sanitized summary; correctly non-retried per W-3/W-5 rules). Acceptance **not assessable** (no final answer). This is an external quota exhaustion at the 4th question of a long session, not a logic defect — and it is precisely the scenario M-5 (alternate-agent selection) is meant to address, since codex-cli was available while claude-code's quota ran out.

Aggregate (X-8.15): attempted 4/4; completed 3; verified 1 / partially_verified 1 / withheld 1 / unverified(failed) 1; allowed-classification compliance 3/4; acceptance met 3/3 assessable; evidence fetch success 56/71 (~79%); total agent calls 24; `json_parse_status=valid` and `leakage_check=passed_structural_check` on all 4.

**Combined M-5-pre baseline (X-8.14 q01–q02 + X-8.15 q05–q08)**: 6 questions reached a Run; 5/6 within allowed classifications; 5/5 assessable acceptance checks met; failures are one pre-Run DNS failure (q03, separate systemic bucket) and one mid-Run quota exhaustion (q08). No incorrect published answer occurred in any baseline question.

No source, test, config, runner, or eval-set changes. Raw stdout was read only for sanitized structured fields; stderr was not read. Nothing from the evaluation output was added to Git. Next work: **M-5 spec confirmation** (the q08 quota failure directly motivates it), then L-5, then S-8. q03's `getaddrinfo failed` remains a separate pre-Run failure-boundary task and must not be assumed solved by M-5 alone.

## X-8.17. M-5 / S-5 ExecutionPlan・Agent substitution実装（2026-07-14）

実行前HEADは`d59be6a`（X-8.17指示書）で、X-8.16仕様コミット`554602d`とX-8.15結果`599d3d0`を含む。実装は通常経路とFakeテストだけを対象とし、実Claude/Codex、WebSearch、実HTTP、live/expensive評価、q01〜q08再実行は行っていない。

- `assignment.py`に不変の`ExecutionPlan`、`PhaseAssignment`、`RunAgentAvailability`、`build_execution_plan(run_id, agents)`を追加。Run開始時に渡された適格Agent snapshotを`configured_agent_ids`として固定し、`role_priority`降順・設定順tie-breakで7 logical slotの候補順を確定する。旧`AssignmentPlan`/`plan_assignments()`は互換wrapperとして維持。
- `orchestrator.py`はRun開始後同じPlanを実行正本として使用し、Run全体のretry=2、substitution=1をstateで管理。`TIMEOUT`/`RATE_LIMITED`は同一Agent retry、hard unavailable（AUTH_REQUIRED/QUOTA_EXCEEDED/COMMAND_NOT_FOUND/UNSUPPORTED_VERSION/UNSAFE_CAPABILITY）はRun全体除外、`EXECUTION_ERROR`はslot-local除外とした。M-5対象外は代替せず既存終端を維持。
- `AgentExecutionRecord.substitute_for`を追加し、`retry_of`との同時設定を拒否。retry/substitutionは別Execution・別BudgetReservationで、CLI JSON `executions[]`にも`substitute_for`を出力する。
- substitution成功・候補なしを`agent_substitute_selected`/`agent_substitution_unavailable`で記録。eventはphase、slot、execution/agent ID、固定reasonだけで、raw診断、prompt、質問、回答、Claim/Evidence本文、path、env、secretを含めない。
- Responderはplanned distinct slotを維持し、成功済みResponderを代替候補にしない。Synthesizer候補は別Auditor候補をlook-aheadで確保し、Auditorはcurrent Synthesizerを除外する。revisionはcurrent担当をpreferredにする。
- Fakeテストで、TIMEOUT retry→3 Agent目 substitution成功、2 Agent synthesize quota failureの救済不能、3 Agent synthesize substitutionと別Auditor、metadata-only event、決定的Planを確認。12回のTokenBudget境界と既存retry回帰も維持。

検証: targeted tests `55 passed`、通常pytest `264 passed, 6 deselected`、`git diff --check`成功。q03 DNS failure-boundary、S-9/S-10、L-5、S-8は未解決。次はL-5、その後S-8。

## X-8.18 L-5 phase schema実装（2026-07-14）

6フェーズの正式JSON Schema resource、共通validator、AgentRequestへのdeep-copy注入、Claude/Codex共有、Fake/Contract/Unitテストを実装した。全objectをclosedとし、必須項目、Enum、文字数・件数上限、固定安全summaryを確定した。実Claude/Codex、WebSearch、実HTTP、live評価は未実行。S-8、q03 DNS、S-9/S-10は未解決として維持する。

## X-8.19 S-8 process/Oracle exit code分離（2026-07-14）

変更前は`AgentExecutionRecord.exit_code`（子CLI process想定・ほぼ未使用）と`RunResult.exit_code`／CLI JSONトップレベル`exit_code`（Oracle自身）が同名で、Adapter・Orchestrator・保存記録・CLI利用者が混同でき、AgentResult/AgentFailureから子process return codeを伝える正式経路もなかった。

S-8を確定し通常実装した（QandA回答確定、SPEC v0.3.10）。子CLI processのOS終了コードは`process_exit_code`：`AgentResult`（既定None）と`AgentFailure`に追加し、`AgentExecutionRecord.exit_code`を`process_exit_code`へ正式rename。成功0、非0は実値、command not found・timeout・起動失敗・Fake AgentはNone、process 0後のparse/schema失敗は`INVALID_OUTPUT`かつprocess 0。Claude/Codex両Adapterが`res.returncode`を成功・分類済みエラー・非0終了・INVALID_OUTPUTの全経路で伝播する（base.pyのschema検証が投げるAgentFailureにはAdapter側でprocess 0を付与）。

Oracle全体は`oracle_exit_code`：`RunResult`の保存フィールドを正式renameし（読み取り専用compatibility property `exit_code`を残す。新規コードは`.oracle_exit_code`）、`RunMetadataRecord`へ追加して`to_dict()`とterminal Run eventのmetadataに含めた。Orchestratorの`_finish()`引数もrename。`agent_execution_succeeded`／`agent_execution_failed` eventは`process_exit_code`フィールドを常に持つ（取得不能はnull）。raw stderr・prompt等は従来どおりevent・summaryへ入れない。

CLI JSONはトップレベル`oracle_exit_code`を正式フィールドとし、schema 1.x互換エイリアスとして旧`exit_code`を同値で残す（`exit_stop`のRun未生成経路も同様）。`executions[]`には`process_exit_code`だけを出力し、曖昧な`exit_code`は出力しない。R-1の0/1/2/3/4/130対応表・実際の終了値は不変（130はS-6/T-2待ちの文書上の契約のまま）。

テスト: `tests/unit/test_exit_code_separation.py`（25件）を追加。モデル既定値・保持・compat property・metadata to_dict、Claude/Codex monkeypatched transportで成功0／非0=17保持／returncode 0+malformed・schema不正→INVALID_OUTPUTかつprocess 0／FileNotFound→COMMAND_NOT_FOUNDでNone／Timeout→TIMEOUTでNone、OrchestratorでFake成功=None記録・失敗コード保持と意味的status非上書き・retry/substitution個別コード・metadata event安全性、CLI JSONで成功/failed/withheld/exit_stopの`oracle_exit_code == exit_code`・戻り値一致・`executions[].process_exit_code`存在・`executions[]`に`exit_code`なし、を検証。`py -m pytest`は**292 passed, 6 deselected**（baseline 267から+25）、`git diff --check`成功。

`assignment.py`の`InsufficientAgentsError.exit_code = 3`はOracle側の値でありcli.pyからも読まれていないが、今回の許可変更範囲外のため未変更。実Claude、実Codex、WebSearch、実HTTP、live評価、q01〜q08は実行していない。ドキュメントはQandA（S-8回答確定）、SPEC v0.3.10（§8.5/§13.4/§14/§15.8）、CLASS（processExitCode/oracleExitCode、曖昧なexitCode除去）、TESTCASE（S-8 BLOCKED解除3箇所）、FIX_PLAN（0-9追加、§2からL-5/S-8行を解消済みへ）を更新。未解決はq03 DNS failure-boundary、S-9/S-10、L-3、J-3、S-4、S-6、T-2、T-3、J-4。次作業は別の指示書で決める。

## X-8.20 q03 DNS failure-boundaryの修正（2026-07-14）

実行前HEADは`f13b043`（X-8.19コミット`f13b043`到達、`cd8422e`/`8bbc076`祖先確認済み、`git status --short`完全に空、`origin/main`一致）。実Claude/Codex、WebSearch、実HTTP、live評価、q03再実行は行っていない。

**q03漏出の正確な原因箇所**: `SafeHttpFetcher.fetch()`のリダイレクトループは各hopの先頭で`self._validate_url(current)`を呼ぶが、この呼び出しは`fetch()`内のどのtry/exceptブロックの外にもあった。`_validate_url()`はSSRF事前チェックのため`self._resolver(parsed.hostname)`（既定は`socket.getaddrinfo`）を直接呼んでおり、DNS解決に失敗すると`socket.gaierror`がそのまま`_validate_url()`→`fetch()`外へ漏れていた。この生例外は`WebEvidenceProvider.fetch()`（個別fetch、無catch）、`WebEvidenceProvider.collect_with_metrics()`（`except EvidenceFetchError`のみ）、`Orchestrator._collect_evidence()`／`_apply_output()`／`_execute_phase()`（いずれも`except SearchError`のみ）のどの型付きハンドラにも一致せず、`run_verify()`全体を素通りしてCLIの`except Exception as e: return exit_stop("internal_error", 1, str(e), args.json)`まで到達し、`message`に`str(socket.gaierror(...))`＝`"[Errno 11001] getaddrinfo failed"`が生のまま出ていた。これがX-8.14 q03の直接原因であることをFakeで確定した。なお`opener.open()`側で発生する`URLError(socket.gaierror(...))`は、既存の`except (URLError, TimeoutError, OSError)`で従来から正しく`EvidenceFetchError("FETCH_FAILED", ...)`へ変換されており、この経路は漏出していなかった（回帰テストで契約を明示的に固定した）。

**再現した例外形**: `socket.gaierror(11001, "getaddrinfo failed")`（resolver直接失敗）と`urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))`（HTTP層に包まれた形）の両方をFakeで再現した。前者は修正前に生のまま`SafeHttpFetcher.fetch()`外へ漏れることを確認し、後者は修正前から既に正しく変換されていることを確認した。

**修正した境界**: `SafeHttpFetcher._validate_url()`内の`self._resolver(parsed.hostname)`呼び出しを`try/except socket.gaierror`で囲み、`EvidenceFetchError("FETCH_FAILED", "DNS resolution failed")`へ変換する1箇所だけを変更した。`WebEvidenceProvider`・`Orchestrator`・`cli.py`は無変更（型付きエラーを既存契約どおり処理するだけで済んだ）。CLIへの`except socket.gaierror`や広い`except OSError`の追加は行っていない。

**採用した公開error codeと根拠**: 新規codeは追加せず、既存の`FETCH_FAILED`を使用した。理由は次の2点。(1) 同じ`SafeHttpFetcher.fetch()`内で`URLError`/`TimeoutError`/`OSError`（`socket.gaierror`のスーパークラスを含む）を捕捉する既存の`opener.open()`失敗パスが既に`FETCH_FAILED`を使っており、DNS解決失敗は同種の「一般的network/connectivity failure」であるため。(2) SPEC §10.8は非UTF-8デコード失敗など他の接続時例外も`FETCH_FAILED`に分類しており、DNS専用の別codeは定義されていない。指示書の「既存codeが一般的なnetwork failureを表している場合は、新しいcodeを増やさずそのcodeを使用する」に従った。

**partial-evidence・metrics挙動**: `EvidenceFetchError`へ変換された後は、`WebEvidenceProvider.collect_with_metrics()`の既存per-candidate loopがそのまま処理する（変更不要）。1候補DNS失敗＋他候補成功で`fetch_attempt_count`加算・`fetch_failure_count`加算・`fetch_error_codes.FETCH_FAILED`加算・次候補へ継続・成功分のEvidenceを保持することをテストで確認した。全候補がDNS失敗の場合は既存のno-evidence契約（`evidence_collect`は`succeeded`・`success_count=1`・`outcome=no_evidence`）に従うことをCLI JSONレベルで確認した（新しいRun classificationは作成していない）。

**CLIでのFake結果**: `--evidence-provider cli-search`で`CliSearchProvider`をFakeに差し替え、`socket.getaddrinfo`だけを`gaierror(11001, "getaddrinfo failed")`側で常に失敗させるFake（`SafeHttpFetcher`自体は実クラスをそのまま使用、実HTTP・実DNSは発生しない）で確認した。結果は`status="completed"`・`exit_code=0`・`oracle_exit_code==exit_code`・`run_id`が有効値・`evidence=[]`・`evidence_collect`フェーズが`succeeded`/`success_count=1`/`outcome="no_evidence"`/`fetch_error_codes={"FETCH_FAILED":1}`で、`internal_error`にもgeneric `exit_code=1`にもならないことを確認した。

**raw情報非公開確認**: 上記CLIテストの出力JSON全体を`json.dumps`でシリアライズし、`"getaddrinfo"`、`"11001"`、`"gaierror"`、テスト用hostname`"dns-fail.example.com"`のいずれも含まれないことをassertした。`EvidenceFetchError`側の`str()`にもこれらが含まれないことを別途unit testで確認済み。`oracle_exit_code`・互換`exit_code`・`process_exit_code`の分離は無変更で、この修正では触れていない。

**変更ファイル**: `src/oracle_council/evidence.py`（`SafeHttpFetcher._validate_url`、resolver呼び出しの1箇所）、`tests/unit/test_evidence.py`（DNS単体3件追加）、`tests/unit/test_cli.py`（DNS CLI回帰1件追加）、`FIX_PLAN.md`（§0-10追加）、`hikitsugi.md`（本節）、`instructions/result.md`。`orchestrator.py`・`cli.py`・`models.py`は変更不要だった（既存の型付きエラー処理経路がそのまま機能したため）。

**追加テスト**: `test_dns_resolution_failure_from_resolver_becomes_typed_fetch_error`（resolver直接失敗→`FETCH_FAILED`、raw情報非混入）、`test_dns_resolution_failure_wrapped_in_urlerror_becomes_typed_fetch_error`（`URLError(gaierror)`→既存契約の回帰固定）、`test_collect_with_metrics_continues_after_raw_dns_failure_and_records_typed_code`（WebEvidenceProvider: 1件DNS失敗＋1件成功でpartial evidence、metrics確認）、`test_cli_ask_dns_resolution_failure_does_not_become_internal_error`（CLI JSON全体でinternal_errorにならないこと、raw情報非混入、`oracle_exit_code==exit_code`）。

**対象テスト・全テスト結果**: 修正前に4件のDNSテストのうち3件が失敗し漏出を再現した（`test_dns_resolution_failure_wrapped_in_urlerror_becomes_typed_fetch_error`のみ修正前から成功、既存契約の健全性を確認）。修正後は`tests/unit/test_evidence.py`と`tests/unit/test_cli.py`の対象テストが全件成功（72 passed）。全体`py -m pytest`は**296 passed, 6 deselected**（baseline 292から+4）、`git diff --check`成功、`git status --short`は変更ファイルのみ。

**残っている課題**: T-3（DNS rebinding対策、resolver pinning、redirect hop個別再検証の専用境界）とS-9/S-10は本作業の対象外で未解決のまま。q03の実live再評価は未実施（別途明示承認が必要）。

**次の推奨作業**: ユーザー承認を得た上でのq03 1回限定live再評価、またはS-9/S-10の設計確定。並行作業禁止のとおり、この場では次へ進まない。
