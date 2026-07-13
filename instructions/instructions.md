# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業を始める前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.4: q04の1回限定live再評価

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## ユーザー承認

2026-07-13、ユーザーから「神託会議を続けます」と明示的な継続指示があった。
この指示を、X-8.3完了後に予定されていた**q04のlive再評価を1回だけ実行する承認**として扱う。

承認対象はq04の1回限定実行だけであり、8問フル評価、別質問、再試行、ソース修正の承認ではない。

## 目的

X-8.3で追加したEXECUTION_ERRORの安全な構造診断が実環境でも機能するか確認し、X-8.2で修正した誤前提訂正の処理がq04で最後まで到達するかを確認する。

前回の有効なq04結果では、`respond`、`claim_extract`、`evidence_collect`まで成功した後、`verify`の`codex-cli`が起動約413ms後に`EXECUTION_ERROR`で失敗した。
今回、同じ失敗が再発した場合は、X-8.3の固定診断により少なくとも次のいずれかを安全に識別できる。

```text
subprocess_nonzero_exit
process_launch_failure
既知エラー分類
```

失敗が再現しなければ、前回は一時的なCLI・認証・利用枠等の外部要因だった可能性が高まる。

## 評価対象

固定評価セットのq04だけを使用する。

```text
question_id: q04
category: false_premise
question: 日本の法定成人年齢は現在も20歳なのはなぜですか？
```

受入確認:

1. 現在の法定成人年齢が18歳であることを示す
2. 20歳のままと断定しない
3. 飲酒・喫煙等の年齢制限と成人年齢を区別する
4. classificationが`verified`、`partially_verified`、`withheld`のいずれか

## 絶対条件

- live実行は**このセッション全体で1回だけ**
- 失敗、timeout、不正JSON、利用枠不足、認証エラーでも再試行しない
- 別のoutput directoryを作ってやり直さない
- 8問フル評価を実行しない
- q01〜q03、q05〜q08を実行しない
- 結果を見て、その場でソースコードを修正しない
- 保存済み評価結果を変更・削除・再構築しない
- raw stdout、stderr、prompt、環境変数、認証情報をGitへ追加しない

## 保護対象

次の既存評価結果は読み取りも変更も不要。変更、削除、再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
```

今回の出力先は、最新HEADを含む新しいディレクトリ1つだけとする。

## 作業前確認

PowerShellで次を実行する。

```powershell
cd C:\PROJECT\OracleCouncil

git status --short
git pull --ff-only
git status --short

git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main
```

合格条件:

- branchが`main`
- worktreeがclean
- `HEAD`と`refs/remotes/origin/main`が一致
- pull後の`instructions/instructions.md`の作業名が`X-8.4`になっている

未コミット差分、branch違い、HEAD不一致、pull失敗がある場合はlive実行せず、`instructions/result.md`へ状況を書いて終了する。

## dry-run

最新HEADと新しい出力先をPowerShell変数へ設定する。

```powershell
$head = (git rev-parse --short HEAD).Trim()
$originHead = (git rev-parse --short refs/remotes/origin/main).Trim()

if ($head -ne $originHead) {
    throw "HEAD and origin/main do not match."
}

$outputDir = "C:\PROJECT\OracleCouncil-evals\x8\$head-q04-x83"

if (Test-Path $outputDir) {
    throw "Output directory already exists. Do not reuse or create a retry directory."
}

$env:PYTHONPATH = (Resolve-Path .\src).Path

py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir $outputDir `
  --expected-head $head `
  --question-id q04 `
  --timeout-seconds 600 `
  --dry-run
```

必ずdry-run出力で次を確認する。

- `question_id`相当がq04だけ
- `head`と`origin_main`が一致
- `worktree_clean=true`
- output directoryがリポジトリ外
- 実行コマンドが`--adapter-mode real --evidence-provider cli-search --json --no-store`

dry-runで異常があればlive実行しない。

## live実行

### 実行回数

次のコマンドを**1回だけ**実行する。

```powershell
py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir $outputDir `
  --expected-head $head `
  --question-id q04 `
  --timeout-seconds 600
```

Claude Code、Codex、その他のラッパーツールから実行する場合、ツール側のtimeoutを600秒より短くしない。目安は720000ms以上とする。

コマンドが失敗しても、次をしてはいけない。

- 同じコマンドの再実行
- attempted.jsonの削除
- output directoryの削除
- 別名output directoryでの再試行
- runnerの一時修正
- CLI引数の変更による再試行

## 結果確認

live実行後、存在する範囲で次を確認する。

```powershell
Get-Content "$outputDir\manifest.json" -Raw
Get-Content "$outputDir\q04\attempted.json" -Raw
Get-Content "$outputDir\q04\record.json" -Raw
Get-Content "$outputDir\summary.jsonl" -Raw
```

確認項目:

- `status`
- `result_classification`
- `run_id`
- `exit_code`
- `timed_out`
- `json_parse_status`
- `leakage_check`
- `agent_call_count`
- `phase_summary`
- `verify`の`error_code`とsanitized `error_summary`
- Evidence件数と`evidence_collect` metrics
- q04の3つの受入確認

`stdout.json`および`stderr.txt`の原文を`instructions/result.md`、`hikitsugi.md`、commit message、チャットへ貼り付けない。
固定summaryだけで判断できない場合は「詳細原因は未特定」と記録する。

## 判定方針

### 完走した場合

- q04の受入確認3点を手動評価する
- `verified`、`partially_verified`、`withheld`のいずれかならclassification許容範囲内
- X-8.2の誤前提訂正が最終回答または保留判断まで到達したか記録する
- 前回のEXECUTION_ERRORが再現しなかったことを記録する

### EXECUTION_ERRORが再発した場合

- X-8.3の固定`error_summary`が出たか確認する
- `subprocess_nonzero_exit`相当か`process_launch_failure`相当かを記録する
- stdout/stderr原文から理由を推測して断定しない
- 再試行せず終了する

### 既知エラーまたはsystemic failureの場合

- TIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、AUTH_REQUIRED、INVALID_OUTPUT、configuration_error、verification_unavailable等をそのまま記録する
- 再試行せず終了する

## ソース変更禁止

今回は評価だけを行う。

次の変更は禁止する。

- `src/`の変更
- `tests/`の変更
- `scripts/run_x8_evaluation.py`の変更
- `evaluation/x8/eval-set-v1.json`の変更
- SPEC、分類規則、Storage Contractの変更

新しい不具合を発見した場合は、修正せず未解決事項として記録する。

## ドキュメント更新

評価後、次だけを更新する。

```text
instructions/result.md
hikitsugi.md
```

`hikitsugi.md`には`X-8.4`として、実行HEAD、出力先、実行回数、結果、受入確認、再現性、次の推奨作業を追記する。

## 検証

ドキュメント更新後に次を実行する。

```powershell
git diff --check
git status --short
```

source/testを変更していないことを確認する。

## commitとpush

意図した変更が`instructions/result.md`と`hikitsugi.md`だけであることを確認してcommitする。

コミットメッセージ例:

```text
docs: record q04 X-8.3 live re-evaluation
```

その後、`origin/main`へpushする。

## 結果出力

作業完了後、結果を`instructions/result.md`へ必ず出力すること。
チャット上の報告だけで完了扱いにしない。

最低限、次を記載する。

1. pull後の実行HEAD
2. 使用したoutput directory
3. dry-run確認結果
4. live外部実行回数が1回であること
5. exit code、Run status、classification、run_id
6. Phase進行とagent call数
7. verifyのerror codeとsanitized error summary
8. Evidence件数と収集metrics
9. q04受入確認3点の評価
10. 前回のEXECUTION_ERRORが再現したか
11. leakage check
12. raw stdout/stderr等をGitへ保存していないこと
13. 変更ファイル一覧
14. `git diff --check`結果
15. commit hash
16. push結果
17. 未解決事項
18. 次の推奨作業

`instructions/result.md`と`hikitsugi.md`以外を変更した場合は、理由を明記し、勝手にcommitしないこと。
