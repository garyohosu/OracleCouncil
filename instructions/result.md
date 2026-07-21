# OracleCouncil v0.4試作版：4AI神託会議の実機E2E完走報告

## 1. 選択タスクと目的
- **タスク**: OracleCouncilの最終完成確認として、Claude／Codex／Grok／agyの4つの実CLIによる「神託会議」を、象徴的な質問「神は存在しますか？」で最初から最後まで実行する。
- **前提**: Grok/agy Adapter追加・4AI評議会化はecec8b6→0091446で完了済み。今回はその実機E2E検証であり、新機能開発ではない。

## 2. 実行して判明した問題と対応
1回目の実機実行（`result_classification: conflicting`のまま公開）は、複数の立場を並べるだけで利用者へ判断を委ねる回答だった。ユーザーはこれをOracle Councilの目的に反すると判断し、証拠評価（SPEC §2.2: verified/partially_verified/unverified/conflicting/withheld）は維持したまま、synthesize・auditの利用者向け最終回答の**構造**を追加する正式決定（SPEC §2.2.1新設）を下した。

修正後の実行で2件の副次的不具合が判明し、修正した。

1. **無関係なmeta-claimによる早期withheld**: claim_extract（Grok）が「AIは断定を避ける」という自己言及claimを抽出し、verify（Codex）が`contradicted`と判定して、質問内容と無関係にStage 1で早期withheldとなった。claim_extractへ、AI自身の回答姿勢についての記述を除外する指示（質問自体がAIの性質を問う場合は例外）を追加した。
2. **audit指摘がre-synthesizeへ伝わっていなかった**: コード調査により、修正サイクルの再synthesize呼び出しが最初のsynthesizeと全く同じcontextしか受け取っておらず、直前auditの指摘内容を一切知らないまま再生成していたことが判明した（2回連続changes_requiredの直接原因と推定）。`audit_issues`をsynthesizeのcontextへ追加し、修正1回で収束できるようにした。

加えて、`--store-content`指定時にwithheldとなった草稿・audit指摘が一切保存されていなかった問題（監査可能性の欠如）を修正し、内部監査証跡として保存されるようにした。

証拠評価規則そのもの（is_withheld等）、synthesize→auditの修正許容回数（1回）は変更していない。特定の宗教的結論を強制する分岐や、この質問専用の分岐も追加していない。

## 3. 最終E2E実行結果（無編集）
- **実行コマンド**: `python -m oracle_council.cli ask "神は存在しますか？" --mode verify --no-interactive --json --adapter-mode real --store-content`
- **結果**: `oracle_exit_code: 0`（公開）、`result_classification: conflicting`（証拠評価は維持）、call_count 7（修正サイクルなし、初回auditで承認）。
- **4AI参加**: claude-code（respond, synthesize）、codex-cli（respond, verify, audit）、grok-cli（claim_extract）、agy-cli（criticize）の4体全てが実際に起動・応答した。
- **最終回答（神託、無編集）**: 「現在の証拠ではこの問いに確定的な決着はついていない」という一文の結論で始まり、理由、有神論・無神論を検討した上で採用しなかった理由、残る不確実性の順で構成される4要素構造を満たした。

## 4. テスト・検証結果
- `py -m pytest`: **384 passed, 10 deselected**（既存378件は無傷、純増6件）。
- `git diff --check`: 成功。
- セキュリティ確認: 変更差分・最終E2E出力JSONともに、APIキー・認証情報・ローカルパス・ユーザー名の混入なし。
- `git status`: クリーン。HEADと`origin/main`は完全一致。

## 5. 変更ファイル
- 変更: `src/oracle_council/adapters/base.py`、`cli.py`、`models.py`、`orchestrator.py`
- テスト変更: `tests/unit/test_classification.py`、`test_claude_envelope.py`、`test_cli.py`、`test_orchestrator.py`
- 文書変更: `SPEC.md`（§2.2.1新設）、`QandA.md`（Y-4）、`FIX_PLAN.md`（§0-19）、`hikitsugi.md`（§0-22）、本ファイル

## 6. commit・push
- commit `01c2b3b`「fix: complete live four-agent oracle session」。通常push（amend/rebase/force-push なし）。

## 7. 未解決事項（今回の完成判定には含めない）
- J-4（対話モードでの2ラウンド質問整理）は未着手。
- claim_extractの除外ガイダンスは一般的なパターンを対象とし、全ての無関係meta-claimパターンを網羅しない。
- `instructions/instructions.md`のfront matterは引き続き人間が次タスクを書き込む必要がある。

## 8. 判定
**OracleCouncil v0.4試作版：完成。** Claude／Codex／Grok／agyの4実CLIが同一Runへ参加し、正式な会議フロー（clarify判定→respond×2→claim_extract→verify→criticize→synthesize→audit）が最後まで完走し、一つの結論（神託）を持つ最終回答が生成され、ログ・監査情報が保存され、致命的な不具合・機密情報の混入がなく、既存テストが全て成功した。
