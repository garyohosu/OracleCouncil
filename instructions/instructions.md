# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.11: Claude stdin化後のq04再評価（明示承認ゲート付き）

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.9のq04 liveでは、次のPhaseまで成功した。

```text
respond
claim_extract
evidence_collect
verify
criticize
```

その後、Claude担当の`synthesize`が`COMMAND_NOT_FOUND`で停止した。

X-8.10では、ClaudeAdapterの長いPhase入力をargvから除去し、stdin経由へ変更した。

```text
実装コミット: 1152bcf fix: pass Claude phase input through stdin
通常テスト: 258 passed, 6 deselected
git diff --check: success
live / q04 / 実Claude / 実Codex: 未実行
```

X-8.11では新しいHEADでq04を1回だけ再評価し、次を確認する。

1. `synthesize`の`COMMAND_NOT_FOUND`が今回も再現するか
2. `synthesize`が成功して`audit`へ到達するか
3. `audit`後にRunが完了し、最終回答が生成されるか
4. q04の誤前提訂正が受入条件を満たすか
5. CodexとClaude双方のstdin transportが実Phaseで機能するか

成功・失敗のどちらでも、X-8.9の根本原因がWindows argv長だったとは断定しない。今回の条件での再現有無として記録する。

## 重要: live実行の承認ゲート

この指示書を読んで実行するという一般的な依頼だけでは、live承認とはみなさない。

live実行前に、現在のローカル実行セッション内で、ユーザーから次と同等の明示承認を確認すること。

```text
X-8.11のq04 live実行を1回だけ承認します
```

- X-8.9以前の承認はすべて消費済みであり、X-8.11へ流用しない
- 承認を推測・継承しない
- 明示承認がない場合は、作業前確認、通常テスト、import確認、dry-runまで実施して停止する
- 承認なしで`ORACLE_COUNCIL_LIVE=1`、実Codex、実Claude、WebSearch、実HTTPを実行しない
- 承認なしで停止した場合はsource、test、`hikitsugi.md`を変更せず、commit・pushしない

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

- live実行は明示承認後に、このセッション全体で**1回だけ**
- q04だけを実行する
- 失敗、timeout、不正JSON、認証・利用枠エラーでも再試行しない
- 別のoutput directoryを作ってやり直さない
- q01〜q03、q05〜q08を実行しない
- 8問フル評価を実行しない
- 結果を見て、その場でsource/testを修正しない
- `claude auth`、`codex login`、`codex logout`等の認証変更を行わない
- raw stdout、stderr、prompt、環境変数、認証情報をGitへ追加しない
- 保存済み評価結果を変更、削除、再構築しない

## 保護対象

少なくとも次の既存評価結果は変更、削除、再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
C:\PROJECT\OracleCouncil-evals\x8\177abc4-q04-stdin
C:\PROJECT\OracleCouncil-evals\x8\0bdf5ca-q04-authfix
```

今回の出力先は、pull後の最新HEADを含む新しいディレクトリ1つだけとする。

```text
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>-q04-claude-stdin
```

既に存在する場合はlive実行せず停止する。retry用の別名ディレクトリを作らない。

## 作業前確認

```powershell
cd C:\PROJECT\OracleCouncil

git status --short
git pull --ff-only
git status --short

git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main
git merge-base --is-ancestor 1152bcf HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.10 implementation commit 1152bcf." }
```

合格条件:

- branchが`main`
- worktreeがclean
- `HEAD`と`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.11`
- HEADに`1152bcf`が含まれる

不一致がある場合はlive実行しない。

## 通常テスト

```powershell
py -m pytest
git diff --check
```

期待値:

```text
258 passed, 6 deselected
```

件数が増減していても、全通常テストがpassし、live・expensiveが除外されていればよい。失敗した場合はlive実行しない。

## 評価セットとimportの事前確認

```powershell
$evalSet = (Resolve-Path ".\evaluation\x8\eval-set-v1.json").Path
$repoSrc = (Resolve-Path ".\src").Path
$oldPythonPath = $env:PYTHONPATH

if (-not (Test-Path $evalSet -PathType Leaf)) {
    throw "Evaluation set not found: $evalSet"
}

try {
    $env:PYTHONPATH = if ([string]::IsNullOrEmpty($oldPythonPath)) {
        $repoSrc
    } else {
        "$repoSrc$([IO.Path]::PathSeparator)$oldPythonPath"
    }

    py -c "import oracle_council; print('oracle_council import OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "oracle_council import smoke test failed."
    }
}
finally {
    if ([string]::IsNullOrEmpty($oldPythonPath)) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $oldPythonPath
    }
}
```

評価セットの内容を変更しない。

## dry-run

```powershell
$head = (git rev-parse --short HEAD).Trim()
$originHead = (git rev-parse --short refs/remotes/origin/main).Trim()

if ($head -ne $originHead) {
    throw "HEAD and origin/main do not match."
}

$outputDir = "C:\PROJECT\OracleCouncil-evals\x8\$head-q04-claude-stdin"

if (Test-Path $outputDir) {
    throw "Output directory already exists. Do not reuse it and do not create a retry directory."
}

$evalSet = (Resolve-Path ".\evaluation\x8\eval-set-v1.json").Path
$repoSrc = (Resolve-Path ".\src").Path
$oldPythonPath = $env:PYTHONPATH

try {
    $env:PYTHONPATH = if ([string]::IsNullOrEmpty($oldPythonPath)) {
        $repoSrc
    } else {
        "$repoSrc$([IO.Path]::PathSeparator)$oldPythonPath"
    }

    py scripts/run_x8_evaluation.py `
      --eval-set $evalSet `
      --output-dir $outputDir `
      --expected-head $head `
      --question-id q04 `
      --timeout-seconds 600 `
      --dry-run

    if ($LASTEXITCODE -ne 0) {
        throw "X-8.11 dry-run failed with exit code $LASTEXITCODE."
    }
}
finally {
    if ([string]::IsNullOrEmpty($oldPythonPath)) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $oldPythonPath
    }
}
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

明示承認が確認できた場合だけ、dry-run成功後に次を1回だけ実行する。

実行担当Agentやラッパーのtool timeoutは、Oracle Council側の600秒より長い**720000ms以上**にする。

```powershell
$evalSet = (Resolve-Path ".\evaluation\x8\eval-set-v1.json").Path
$repoSrc = (Resolve-Path ".\src").Path
$oldPythonPath = $env:PYTHONPATH
$oldLive = $env:ORACLE_COUNCIL_LIVE
$liveExit = $null

try {
    $env:PYTHONPATH = if ([string]::IsNullOrEmpty($oldPythonPath)) {
        $repoSrc
    } else {
        "$repoSrc$([IO.Path]::PathSeparator)$oldPythonPath"
    }
    $env:ORACLE_COUNCIL_LIVE = "1"

    py scripts/run_x8_evaluation.py `
      --eval-set $evalSet `
      --output-dir $outputDir `
      --expected-head $head `
      --question-id q04 `
      --timeout-seconds 600

    $liveExit = $LASTEXITCODE
}
finally {
    if ([string]::IsNullOrEmpty($oldPythonPath)) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $oldPythonPath
    }

    if ([string]::IsNullOrEmpty($oldLive)) {
        Remove-Item Env:ORACLE_COUNCIL_LIVE -ErrorAction SilentlyContinue
    } else {
        $env:ORACLE_COUNCIL_LIVE = $oldLive
    }
}

Write-Host "X-8.11 live exit code: $liveExit"
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

raw `stderr.txt`やstdout本文をチャット、`instructions/result.md`、`hikitsugi.md`、Gitへ転記しない。

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

### A. `synthesize`を通過し`audit`へ到達した場合

- Claude stdin化後にX-8.9の`synthesize COMMAND_NOT_FOUND`が今回の条件では再現しなかったと記録する
- ただしstdin化が根本原因を解決したと断定しない
- `audit`のstatusと、必要ならrevision cycleの有無を確認する
- final answerとclassificationが生成されたか確認する
- q04の受入条件を確認する

### B. `synthesize COMMAND_NOT_FOUND`が再現した場合

- stdin化だけでは今回の失敗を除去できなかったと記録する
- raw出力から原因を推測してsourceを変更しない
- sanitized summaryが`synthesize execution ended with COMMAND_NOT_FOUND.`であることを確認する
- 再試行しない

### C. 別の既知エラーになった場合

AUTH_REQUIRED、QUOTA_EXCEEDED、RATE_LIMITED、TIMEOUT、EXECUTION_ERROR、INVALID_OUTPUT等の分類とsanitized summaryだけを記録する。再試行しない。

## ドキュメント更新

live実行した場合だけ、次を更新する。

```text
instructions/result.md
hikitsugi.md
```

記載内容:

1. 実行HEAD
2. 出力先
3. X-8.11の明示承認を確認したこと
4. dry-run結果
5. live外部実行回数が1回で、再試行なしであること
6. process exit、status、classification
7. 参加Agentとcall count
8. Phase結果とsanitized summary
9. `synthesize`のX-8.9結果が再現したか
10. `audit`到達とrevision cycleの有無
11. Evidence件数・metrics
12. q04受入条件の判定
13. stdin化について言えること・言えないこと
14. JSON parseとleakage check
15. raw情報を保存・公開していないこと
16. 未解決事項と次の推奨作業

既存の過去結果は削除せず、X-8.11の節を追加する。

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
docs: record q04 Claude stdin live re-evaluation
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
- import確認
- dry-run結果
- 想定出力先
- live未実行
- X-8.11の明示承認待ち

承認なしで停止した場合はcommit・pushしない。
