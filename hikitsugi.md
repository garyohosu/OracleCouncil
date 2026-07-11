# hikitsugi.md — 引き継ぎ（Phase 0実装）

> 最終更新: 2026-07-12。前セッションがトークン切れで中断したため、現在地と残作業をここに集約する。
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
| `orchestrator.py` | 骨格のみ→**今回T-5二段判定・withheld短絡・exit 4を統合** |
| `classification.py` | **今回新規**: §15.3の二段判定の実装 |
| `tests/` | **今回新規**: budget / storage / orchestrator の単体テスト |

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

1. **Responder 2 Agent分離**: 現orchestratorは単一adapterで7回呼んでいる。§6.3の「異なる2 AgentがResponder」「SynthesizerとAuditorは別agent_id」を満たすadapter割当（S-5確定前の暫定は設定順の決定的割当でよい）
2. **修正・再監査1回**: audit `changes_required`→synthesize修正→再audit（§11.1、AI呼び出し+2、上限10回）。現状はapproved以外を即failedにしている
3. **再試行**: 一時エラー（TIMEOUT等）の同一Execution 1回・Run全体2回・retry_of（§8.3）。予約はretry別予約（S-7）
4. **Phase/AgentExecutionレコードの正式化**: 現在イベントpayloadは簡易。§15.8のPhase（minimum_success_count等）とAgentExecutionのフィールドへ合わせ、RunMetadataRecordを`run_completed`スナップショットへ入れる（O-5）
5. **CLI骨格**（Typer）と`oracleExitCode`の全表結線（§13.4。invalid_arguments=2、insufficient_agents=3等）
6. **Clarification Engine**（Phase 1）: 決定的ルール→§7.2ステータス。J-4（2ラウンド目のClarifier）が未回答
7. **L-4 spike**: 実CLI接続前に`docs/adapter-spike.md`を作る（実装開始のゲート、未実施）

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
