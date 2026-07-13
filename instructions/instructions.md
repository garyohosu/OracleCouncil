# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業を始める前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.7: Codex stdin化後のq04再評価（明示承認ゲート付き）

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.6でCodexAdapterのPhase入力をargvから除去し、stdin経由へ変更した。

これまでq04は2回とも、`respond`、`claim_extract`、`evidence_collect`まで成功した後、長いClaim・Evidenceを受け取る`verify`のCodex CLIが短時間で非ゼロ終了していた。

今回の目的は、新しいHEADでq04を1回だけ再評価し、次を確認することである。

1. stdin化後も`verify`の非ゼロ終了が再現するか
2. `verify`を通過し、後続の`criticize`、`synthesize`、`audit`へ到達するか
3. 失敗時のEXECUTION_ERROR summaryがX-8.5修正後の正しい形式か
4. q04の誤前提訂正が最終回答まで到達するか

ただし、Windowsコマンドライン長が過去の根本原因だったとはまだ断定しない。

## 重要: live実行の承認ゲート

この指示書を読んで実行するという一般的な依頼だけでは、live実行の承認とはみなさない。

live実行前に、ユーザーから現在のローカルセッションで、次と同等の明示的な承認を得ること。

```text
X-8.7のq04 live実行を1回だけ承認します
```

- 明示承認が確認できない場合は、作業前確認とdry-runまで実施して停止する
- 承認を推測・継承しない
- X-8.4で与えられた1回限定承認は既に消費済みであり、今回へ流用しない
- 承認なしで`ORACLE_COUNCIL_LIVE=1`、実Codex、実Claude、WebSearch、実HTTPを実行しない

承認なしで停止した場合も、`instructions/result.md`へ「dry-run完了・live承認待ち」と記録する。ただしsource、test、`hikitsugi.md`は変更せず、commit・pushもしない。

## 現在地

X-8.6では次を完了している。

- CodexのPhase入力をargvから除去
- `codex exec ... -`でstdin入力を指定
- `subprocess.run(input=question, ...)`で本文を渡す
- 50,000文字超の質問・Claim・Evidenceでテスト
- argvへ本文が入らないことを確認
- JSON Schema一時ファイルの成功・失敗時cleanupを確認
- 既存エラー分類を維持
- `238 passed, 6 deselected`
- live、q04、実CLIは未実行

実装HEAD:

```text
55044cc fix: pass Codex phase input through stdin
```

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

- live実行は明示承認後に**このセッション全体で1回だけ**
- q04だけを実行する
- 失敗、timeout、不正JSON、認証・利用枠エラーでも再試行しない
- 別のoutput directoryを作ってやり直さない
- q01〜q03、q05〜q08を実行しない
- 8問フル評価を実行しない
- 結果を見て、その場でソースコードを修正しない
- raw stdout、stderr、prompt、環境変数、認証情報をGitへ追加しない
- 保存済み評価結果を変更・削除・再構築しない

## 保護対象

次の既存評価結果は変更、削除、再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
```

今回の出力先は、pull後の最新HEADを含む新しいディレクトリ1つだけとする。

```text
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>-q04-stdin
```

既に存在する場合はlive実行せず停止する。retry用の別名ディレクトリを作らない。

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
- pull後の`instructions/instructions.md`の作業名が`X-8.7`
- HEADに`55044cc`が含まれている

未コミット差分、branch違い、HEAD不一致、pull失敗がある場合はlive実行しない。

## 通常テスト

live実行前に既定テストを実行する。

```powershell
py -m pytest
git diff --check
```

期待値:

```text
238 passed, 6 deselected
```

テスト件数が増減していても全通常テストがpassし、live・expensiveが除外されていればよい。失敗した場合はlive実行しない。

## dry-run

```powershell
$head = (git rev-parse --short HEAD).Trim()
$originHead = (git rev-parse --short refs/remotes/origin/main).Trim()

if ($head -ne $originHead) {
    throw "HEAD and origin/main do not match."
}

$outputDir = "C:\PROJECT\OracleCouncil-evals\x8\$head-q04-stdin"

if (Test-Path $outputDir) {
    throw "Output directory already exists. Do not reuse it and do not create a retry directory."
}

py scripts/run_x8_evaluation.py `
  --eval-set tests/evals/x8_eval_set.json `
  --output-dir $outputDir `
  --expected-head $head `
  --question-id q04 `
  --timeout-seconds 600 `
  --dry-run
```

確認項目:

- q04だけが選択されている
- `adapter-mode real`
- `evidence-provider cli-search`
- JSON出力
- `--no-store`
- timeout 600秒
- 出力先がリポジトリ外
- HEADとorigin/mainが一致
- worktree clean

## live実行

**明示承認が確認できた場合だけ**、dry-runと同じPowerShellセッションで次を1回だけ実行する。

```powershell
$env:ORACLE_COUNCIL_LIVE = "1"

try {
    py scripts/run_x8_evaluation.py `
      --eval-set tests/evals/x8_eval_set.json `
      --output-dir $outputDir `
      --expected-head $head `
      --question-id q04 `
      --timeout-seconds 600
}
finally {
    Remove-Item Env:ORACLE_COUNCIL_LIVE -ErrorAction SilentlyContinue
}
```

終了コードが0以外でも再実行しない。

## 結果確認

リポジトリ外の今回出力だけを確認する。

```text
manifest.json
summary.jsonl
summary.csv
q04/attempted.json
q04/record.json
q04/stdout.json
q04/stderr.txt
```

raw `stderr.txt`やstdout本文をチャット、`result.md`、`hikitsugi.md`、Gitへ転記しない。

記録してよいのは、構造化・sanitizedされた次の情報だけ。

- process exit code
- Run status
- result classification
- run_id
- agent_call_count
- participants
- Phaseごとのstatus、elapsed_ms、error_code、sanitized error_summary
- Evidence件数と収集metrics
- JSON parse status
- leakage check
- acceptance status

## 判定

### A. verifyを通過した場合

- stdin化後に過去の即時非ゼロ終了が再現しなかったと記録する
- ただしstdin化が根本原因を解決したと断定せず、「今回の条件では再現しなかった」とする
- criticize、synthesize、auditまで到達したか確認する
- q04の3つの受入条件を確認する

### B. 同じ非ゼロ終了が再現した場合

- Windows argv長だけが原因という仮説は弱まったと記録する
- X-8.5修正後のsummaryが正確に次の形式か確認する

```text
verify process exited with a non-zero status.
```

- `invalid output`や二重ピリオドが復活していないことを確認する
- raw出力から原因を推測して仕様変更しない

### C. 既知エラーへ分類された場合

AUTH_REQUIRED、QUOTA_EXCEEDED、RATE_LIMITED、TIMEOUT等の分類とsanitized summaryだけを記録する。再試行しない。

## ドキュメント更新

live実行した場合だけ、次を更新する。

```text
instructions/result.md
hikitsugi.md
```

記載内容:

1. 実行HEAD
2. 出力先
3. 明示承認を確認したこと
4. dry-run結果
5. live外部実行回数が1回であること
6. process exit、status、classification
7. 参加Agentとcall count
8. Phase結果とsanitized summary
9. Evidence件数・metrics
10. q04受入条件の判定
11. 過去の非ゼロ終了が再現したか
12. stdin化について言えること・言えないこと
13. JSON parseとleakage check
14. raw情報を保存・公開していないこと
15. 未解決事項と次の推奨作業

既存の過去結果は削除せず、X-8.7の節を先頭へ追加する。

## commit・push

live実行後、変更対象は原則として次の2ファイルだけとする。

```text
instructions/result.md
hikitsugi.md
```

確認:

```powershell
git diff --check
git status --short
```

評価ディレクトリ、raw stdout/stderr、秘密情報をcommitしない。

コミットメッセージ例:

```text
docs: record q04 stdin live re-evaluation
```

`origin/main`へpushし、commit hashとpush結果を`instructions/result.md`へ記録する。

## 結果出力

作業結果は必ず次へ出力する。

```text
instructions/result.md
```

チャット上の報告だけで完了扱いにしない。

明示承認がない場合は、次だけを記録して停止する。

- pull後HEAD
- worktree・origin同期状況
- 通常テスト結果
- dry-run結果
- 想定出力先
- live未実行
- 明示承認待ち

承認なしで停止した場合はcommit・pushしない。