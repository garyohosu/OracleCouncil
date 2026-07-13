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
3. ~~再試行~~ 済（2026-07-12、W-3確定）。対象はSPEC正本どおりTIMEOUT/RATE_LIMITEDのみ。同一Execution 1回・Run全体2回・retry_of・別予約・失敗履歴保持・起動後失敗は安全側commit。代替Agent選定はM-5確定待ちで未実装（非一時エラーは決定的にfailed）
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
