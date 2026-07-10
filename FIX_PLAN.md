# FIX_PLAN — SPEC v0.3.2 時点の残件計画

> 2026-07-10 v0.3.0レビュー → レビュアー回答反映（v0.3.1: J-5・O-5・L-4） → ユースケースQ-1〜Q-3反映（v0.3.2） → USECASE.md承認・SEQUENCE.md作成後の状態。

## 0. v0.3.1で解消済み

| # | 内容 | SPEC反映箇所 |
|---|---|---|
| J-5 | Critic入力の予算超過 → 上限を上げず入力を削る。回答3,000字、Evidence 500字×最大8件（重複除去後・Run全体）、critical/majorのみCriticへ、入力12,000目標/16,000絶対上限、超過時はEvidenceから先に削る | §8.6、§9.4 |
| O-5 | RunRuntime（実行時）とRunMetadataRecord（永続化）を分離。既定保存はRunMetadataRecordのみ、contentは`--store-content`時のみ | §15.1、§15.8 |
| L-4 | 実装前spikeで公式2 CLIのcapability（非対話・ツール無効・読み取り専用・出力安定性・seed）を確認し`docs/adapter-spike.md`へ記録 | §21 Phase 0前spike |

v0.3.0レビュー時の編集修正（§12.2投票削除、§13.3進捗例、§8.1設定例、§14 votes予約）も反映済み。

## 1. 合意した処理順（設計書ルート）

1. ~~J-5を修正~~ 済（v0.3.1）
2. ~~O-5を修正~~ 済（v0.3.1）
3. ~~Q-1〜Q-3を回答してUSECASE.mdを確定~~ 済（v0.3.2、Codexレビュー APPROVED）
4. ~~通常系と異常系のSEQUENCE.md~~ 済（Codexレビュー実施）
5. 状態遷移図（M-1の状態機械をMermaid `stateDiagram`へ）
6. CLASS.md（O-5のRunRuntime / RunMetadataRecord分離を反映）
7. TESTCASE.md
8. 全文書の横断レビュー
9. L-4 Adapter spike（実装開始のゲート）
10. Phase 0実装開始

## 2. 実装開始前に確定（ブロッカー）

| # | 項目 | 一言で |
|---|---|---|
| J-3 | `quick`の実行グラフ | フェーズ一覧・呼び出し数・出力の確定（v0.2.0から継続） |
| L-5 | フェーズ別の構造化出力スキーマ | 6フェーズ分のJSON Schema。Phase 0のfixture・Contract Testの前提 |
| M-5 | 代替Agent選定と再試行・12回上限 | 修正込み10回＋再試行2＋代替1=13回の矛盾を解消 |
| M-4 | Evidence収集フェーズの状態モデル | Phase enumにない。全断時のRun状態と失敗理由の置き場所 |
| O-6 | stdin限定と一時ファイル許可の矛盾 | §16.1を「Execution専用一時ディレクトリ内・終了時削除」の条件付き許可へ修正見込み |
| R-1 | CLI終了コード一覧 | `strict_required`、`verification_unavailable`、`failed`、`withheld`等の終了コード。非対話クライアントの分岐契約 |

## 3. 該当Phase開始時に確定

| # | 項目 | 決めるPhase |
|---|---|---|
| J-4 | Clarifier 2ラウンドと上限8回の整合 | Phase 1（質問整理） |
| M-3 | JSONL破損・同時実行・ディスクフル | Phase 0〜1（Storage実装時） |
| L-3 | 構造化出力失敗時の回復 | Phase 2（Adapter実装） |
| O-2 | 認証情報マスキングの境界 | Phase 2（Adapter実装） |
| N-3 | 障害注入テストの契約（仮想時計・遅延・SSRF再現） | Phase 2〜3 |
| K-2 | Web取得で扱える資料範囲 | Phase 3（Evidence実装） |
| K-4 | Claim分割とEvidence多対多 | Phase 3 |
| K-5 | `critical` Claim 6件以上で必然的`withheld` | Phase 3（処理順5で先行検討） |
| K-6 | `freshness`判定の決定的手順と既定値 | Phase 3（K-1決定表fixtureと同時、処理順5で先行検討） |
| K-7 | Evidence処理90秒とfetch並列度 | Phase 3（処理順5で先行検討） |
| N-2 | 非決定的AI判定のgolden dataset | Phase 5（品質）だが設計はPhase 3から |
| R-2 | `--json`時の進捗表示の出力先 | Phase 5（UX）。stdout汚染回避 |
| R-3 | ユーザー応答待ちと全体タイムアウトの関係 | Phase 1（対話実装時） |
| R-4 | `probe()`の実行方式とAI呼び出しカウント | Phase 2（Adapter実装） |

## 4. 実験・記事用（仕様ではなく実験計画）

P-1（多数決との比較）、P-2（保留率の評価）、P-3（匿名化効果）、P-4（Agent数と費用対効果）はMVP実装後の実験計画としてQandA.mdに保持する。note記事の有料部の骨子候補:

- 最大23回→通常7回への呼び出し削減の意思決定過程（J-1）
- 「AIに真偽を決めさせない」決定表設計（K-1）
- 「Criticへ全部載せる」をやめたトークン予算設計（J-5）— 保守的すぎる推定式が自分の首を絞めた話
- SafeHttpFetcherのSSRF対策をローカルツールでやる理由（O-3）
- 既定metadata保存というログ設計（O-1、O-5）

## 5. 次のアクション

1. 状態遷移図（Run / Phase / AgentExecutionのMermaid `stateDiagram`）を作成する。M-4（Evidence収集の状態モデル）の回答が前提になるため、先に確定するのが望ましい
2. M-4、M-5、O-6、R-1の回答を確定してSPEC v0.3.3へ反映する
3. CLASS.md、TESTCASE.md、全文書の横断レビュー
4. L-4 spike: Claude Code / Codex CLIを手元で「非対話・ツール無効・読み取り専用・JSON出力」で起動し、フラグ列・バージョン・安定性を`docs/adapter-spike.md`へ記録する
5. K-5〜K-7、J-3、L-5の確定をもってPhase 0実装へ着手する
