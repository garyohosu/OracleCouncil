# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業を始める前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.9: AUTH_REQUIRED分類修正後のq04再評価（明示承認ゲート付き）

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.7では、Codex入力をstdin化した後のq04で、以前の短時間`EXECUTION_ERROR`は再現せず、`verify`が`AUTH_REQUIRED`で停止した。

X-8.8では、自由文エラー分類に存在した次の危険な部分一致を廃止した。

```python
"auth" in lowered
"login" in lowered
```

代わりに、構造化401/403、構造化`unauthorized`、および明示的な認証失敗表現だけを`AUTH_REQUIRED`とする境界付きallowlistへ変更した。

X-8.9では、新しいHEADでq04を1回だけ再評価し、次を確認する。

1. `verify`が再び`AUTH_REQUIRED`になるか
2. 明示パターンに一致しない失敗が`EXECUTION_ERROR`として識別されるか
3. `verify`を通過して`criticize`、`synthesize`、`audit`へ到達するか
4. q04の誤前提訂正が最終回答まで到達するか

成功・失敗のどちらでも、X-8.7の`AUTH_REQUIRED`が誤分類だったと直ちに断定しない。今回の条件での再現有無として記録する。

## X-8.8の確定状態

実装コミット:

```text
bc3b99f fix: tighten auth error classification
```

追加回帰テストコミット:

```text
67c8f3c test: cover structured auth error classification
```

最終検証結果:

```text
257 passed, 6 deselected
```

`instructions/result.md`と`hikitsugi.md`には、X-8.8実装コミット時点の`255 passed, 6 deselected`が残っている可能性がある。X-8.9で文書を更新する場合は、X-8.8の最終テスト数を`257 passed, 6 deselected`へ訂正し、追加回帰テストコミット`67c8f3c`を記録する。

## 重要: live実行の承認ゲート

この指示書を読んで実行するという一般的な依頼だけでは、live実行の承認とはみなさない。

live実行前に、現在のローカル実行セッション内で、ユーザーから次と同等の明示的承認を確認すること。

```text
X-8.9のq04 live実行を1回だけ承認します
```

- X-8.7の承認は既に消費済みであり、X-8.9へ流用しない
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
- 結果を見て、その場でソースコードを修正しない
- `codex login`、`codex logout`、認証情報の変更を行わない
- `codex login status`は今回実行しない
- raw stdout、stderr、prompt、環境変数、認証情報をGitへ追加しない
- 保存済み評価結果を変更・削除・再構築しない

## 保護対象

次の既存評価結果は変更、削除、再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
C:\PROJECT\OracleCouncil-evals\x8\177abc4-q04-stdin
```

今回の出力先は、pull後の最新HEADを含む新しいディレクトリ1つだけとする。

```text
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>-q04-authfix
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
git merge-base --is-ancestor bc3b99f HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain bc3b99f." }
git merge-base --is-ancestor 67c8f3c HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain 67c8f3c." }
```

合格条件:

- branchが`main`
- worktreeがclean
- `HEAD`と`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.9`
- HEADに`bc3b99f`と`67c8f3c`が含まれる

不一致がある場合はlive実行しない。

## 通常テスト

```powershell
py -m pytest
git diff --check
```

期待値:

```text
257 passed, 6 deselected
```

テスト件数が増減していても、全通常テストがpassし、live・expensiveが除外されていればよい。失敗した場合はlive実行しない。

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

$outputDir = "C:\PROJECT\OracleCouncil-evals\x8\$head-q04-authfix"

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
        throw "X-8.9 dry-run failed with exit code $LASTEXITCODE."
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
    if ([string]::IsNullOrEmpty($oldLive)) {
        Remove-Item Env:ORACLE_COUNCIL_LIVE -ErrorAction SilentlyContinue
    } else {
        $env:ORACLE_COUNCIL_LIVE = $oldLive
    }

    if ([string]::IsNullOrEmpty($oldPythonPath)) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $oldPythonPath
    }
}

Write-Host "X-8.9 live exit code: $liveExit"
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

### A. verifyを通過した場合

- X-8.8後の今回条件では`AUTH_REQUIRED`が再現しなかったと記録する
- X-8.7が誤分類だった、またはstdin化が根本原因を解決したと断定しない
- `criticize`、`synthesize`、`audit`まで到達したか確認する
- q04の受入条件を確認する

### B. AUTH_REQUIREDが再現した場合

- X-8.8の明示的allowlistでも認証失敗として分類されたと記録する
- 真の認証問題である可能性がX-8.7時点より強まったとする
- ただしraw出力を引用せず、認証状態やtoken失効を断定しない
- 再試行、login、logout、認証変更を行わない

### C. EXECUTION_ERRORになった場合

- X-8.7の`AUTH_REQUIRED`が旧部分一致による誤分類だった可能性と整合すると記録する
- ただし今回と前回で外部条件が異なるため断定しない
- summaryが安全な固定形式であることを確認する
- raw出力から原因を推測して仕様変更しない

### D. QUOTA_EXCEEDED、RATE_LIMITED、TIMEOUT等の場合

- 既知分類とsanitized summaryだけを記録する
- 再試行しない

## ドキュメント更新

live実行した場合だけ、次を更新する。

```text
instructions/result.md
hikitsugi.md
```

先頭へX-8.9の節を追加し、最低限次を記録する。

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
11. X-8.7のAUTH_REQUIREDが再現したか
12. X-8.8後に言えること・言えないこと
13. JSON parseとleakage check
14. raw情報を保存・公開していないこと
15. 未解決事項と次の推奨作業

同時に、X-8.8節に残っている場合は次を訂正する。

```text
pytest: 255 passed, 6 deselected
```

を

```text
pytest: 257 passed, 6 deselected
```

へ変更し、追加回帰テストコミット`67c8f3c`を記録する。

既存の過去結果は削除しない。

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
docs: record q04 auth classification re-evaluation
```

`origin/main`へpushし、commit hashとpush結果を`instructions/result.md`へ記録する。

## 明示承認がない場合

次を報告して停止する。

- pull後HEAD
- worktree・origin同期状況
- 通常テスト結果
- import確認
- dry-run結果
- 想定出力先
- live未実行
- X-8.9の明示承認待ち

この場合はcommit・pushしない。
