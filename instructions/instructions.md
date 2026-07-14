# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分や未追跡ファイルがある場合は、勝手にreset・stash・削除・移動せず、差分を保護して状況を報告してください。

## X-8.14: q04を除く残り7問のholdout評価（明示承認ゲート付き）

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.13では、CodexAdapter、ClaudeAdapter、CliSearchProviderの3系統すべてがstdin transportとなった状態でq04を1回実行し、次を確認した。

```text
実行HEAD: 8fcdeaf
結果記録コミット: 1212c67
exit_code: 0
status: completed
classification: verified
respond〜audit: 全7Phase成功
q04受入条件: 3点すべて充足
```

q04はtransport障害の診断過程で複数回使用されており、もはやclean holdoutではない。

X-8.14では、まだlive実行していない次の7問だけを、現在の実装を固定した状態で評価する。

```text
q01
q02
q03
q05
q06
q07
q08
```

この評価をM-5の代替Agent・再試行設計より先に行い、M-5導入前の基準線として保存する。X-8.14中はsource、test、評価ロジック、固定8問セットを変更しない。

## 並行作業禁止

X-8.14とM-5、L-5、S-8を並行で進めない。

- holdout実行前から結果記録完了まで、実装変更を入れない
- 別ブランチの変更をmergeしない
- Agent設定、role priority、timeout、モデル、検索Providerを変更しない
- q04を再実行しない
- holdout結果の確定後にM-5へ進む

## 重要: live実行の承認ゲート

この指示書を読んで実行するという一般的な依頼だけでは、live承認とはみなさない。

live実行前に、現在のローカル実行セッション内で、ユーザーから次と同等の明示的承認を確認すること。

```text
X-8.14の残り7問holdout live実行を、q01〜q03・q05〜q08各1回、合計最大7回だけ承認します
```

承認の意味:

- q01、q02、q03、q05、q06、q07、q08を各最大1回
- 外部`oracle ask`実行は合計最大7回
- q04は0回
- timeout、失敗、不正JSON、認証、利用枠、CLI障害が発生しても同じ質問を再試行しない
- systemic stopで途中終了した場合、そのセッション内で再開しない
- 未実行問題の再開には、別タスクと新しい明示承認が必要

過去のq04承認、X-8.11、X-8.13の承認を流用しない。

明示承認がない場合は、作業前確認、通常テスト、holdout subset生成、整合性検証、dry-runまで実施して停止する。承認なしで`ORACLE_COUNCIL_LIVE=1`、実Claude、実Codex、WebSearch、実HTTPを実行しない。

## 評価対象

正本は次の固定評価セットである。

```text
evaluation/x8/eval-set-v1.json
```

正本自体は変更しない。

runnerは現時点で`--all`または単一`--question-id`だけを受け付けるため、q04を除外した派生subset JSONを**リポジトリ外**へ機械的に生成し、そのsubsetに対して`--all`を1回実行する。

派生subsetは次を満たすこと。

- 質問順は`q01,q02,q03,q05,q06,q07,q08`
- 各question objectは正本の同一IDとdeep-equal
- q04を含まない
- 7問ちょうど
- 正本のSHA-256を派生subset内に記録
- 派生処理で質問文、expected_behavior、acceptance_checks、allowed_classifications、max_external_runsを変更しない

## 絶対条件

- live実行は明示承認後に1セッションだけ
- 対象はq01、q02、q03、q05、q06、q07、q08のみ
- 各問題は最大1回
- 合計外部実行は最大7回
- q04は実行しない
- 8問正本を変更しない
- runner、source、test、configを変更しない
- 実行結果を見てその場で修正しない
- retry用output directoryを作らない
- `--resume`相当の独自処理を作らない
- `attempted.json`、manifest、record、stdout、stderrを削除・改変しない
- `claude auth`、`codex login`、`codex logout`等の認証変更を行わない
- raw stdout/stderr、prompt、環境変数、認証情報をGitへ追加しない
- `git stash`、`git stash -u`を使用しない
- `dream.md`を評価前または評価中に作成・変更しない

## 保護対象

既存の全評価結果を変更、削除、再構築しない。少なくとも次を保護する。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
C:\PROJECT\OracleCouncil-evals\x8\177abc4-q04-stdin
C:\PROJECT\OracleCouncil-evals\x8\0bdf5ca-q04-authfix
C:\PROJECT\OracleCouncil-evals\x8\05714b7-q04-claude-stdin
C:\PROJECT\OracleCouncil-evals\x8\8fcdeaf-q04-clisearch-stdin
```

今回の出力先と派生subsetはpull後のHEADを含む新規パスとする。

```text
出力ディレクトリ:
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>-holdout7

派生subset:
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>-holdout7-eval-set.json
```

どちらかが既に存在する場合はlive実行しない。別名やretry用パスを作らない。

## 作業前確認

```powershell
cd C:\PROJECT\OracleCouncil

git status --short
git pull --ff-only
git status --short

git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main

git merge-base --is-ancestor 1212c67 HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.13 result commit 1212c67." }

git merge-base --is-ancestor 8fcdeaf HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain full stdin implementation commit 8fcdeaf." }
```

合格条件:

- branchが`main`
- worktreeが完全にclean
- 未追跡ファイルもない
- `HEAD`と`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.14`
- HEADに`1212c67`と`8fcdeaf`が含まれる

未追跡`dream.md`等がある場合、executorはstash、削除、移動を行わず停止し、ユーザーへclean化を依頼する。

## 通常テスト

```powershell
py -m pytest
git diff --check
git status --short
```

期待値:

```text
259 passed, 6 deselected
```

件数が増減していても、通常テストが全件passし、live・expensiveが除外されていればよい。失敗またはworktree差分がある場合はlive実行しない。

## 派生holdout subsetの生成

正本を変更せず、リポジトリ外へsubsetを生成する。

```powershell
$head = (git rev-parse --short HEAD).Trim()
$originHead = (git rev-parse --short refs/remotes/origin/main).Trim()

if ($head -ne $originHead) {
    throw "HEAD and origin/main do not match."
}

$sourceEval = (Resolve-Path ".\evaluation\x8\eval-set-v1.json").Path
$evalRoot = "C:\PROJECT\OracleCouncil-evals\x8"
$outputDir = Join-Path $evalRoot "$head-holdout7"
$subsetEval = Join-Path $evalRoot "$head-holdout7-eval-set.json"

if (Test-Path $outputDir) {
    throw "Holdout output directory already exists. Do not reuse it."
}
if (Test-Path $subsetEval) {
    throw "Holdout subset already exists. Do not overwrite or create a retry copy."
}

$env:ORACLE_SOURCE_EVAL = $sourceEval
$env:ORACLE_SUBSET_EVAL = $subsetEval

try {
    @'
import hashlib
import json
import os
from pathlib import Path

source_path = Path(os.environ["ORACLE_SOURCE_EVAL"])
subset_path = Path(os.environ["ORACLE_SUBSET_EVAL"])
source_bytes = source_path.read_bytes()
source = json.loads(source_bytes.decode("utf-8"))
ids = ["q01", "q02", "q03", "q05", "q06", "q07", "q08"]
by_id = {item["id"]: item for item in source["questions"]}

assert [item["id"] for item in source["questions"]] == [
    "q01", "q02", "q03", "q04", "q05", "q06", "q07", "q08"
]
assert set(by_id) == {"q01", "q02", "q03", "q04", "q05", "q06", "q07", "q08"}

subset = {
    "evaluation_version": "x8-eval-set-v1-holdout7-no-q04",
    "derived_from_sha256": hashlib.sha256(source_bytes).hexdigest(),
    "excluded_question_ids": ["q04"],
    "questions": [by_id[qid] for qid in ids],
}

subset_path.parent.mkdir(parents=True, exist_ok=True)
with subset_path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(subset, stream, ensure_ascii=False, indent=2)
    stream.write("\n")

loaded = json.loads(subset_path.read_text(encoding="utf-8"))
assert [item["id"] for item in loaded["questions"]] == ids
assert len(loaded["questions"]) == 7
assert all(item == by_id[item["id"]] for item in loaded["questions"])
assert "q04" not in {item["id"] for item in loaded["questions"]}
print("holdout subset verified")
print("source_sha256=" + subset["derived_from_sha256"])
print("subset_sha256=" + hashlib.sha256(subset_path.read_bytes()).hexdigest())
'@ | py -

    if ($LASTEXITCODE -ne 0) {
        throw "Holdout subset generation or verification failed."
    }
}
finally {
    Remove-Item Env:ORACLE_SOURCE_EVAL -ErrorAction SilentlyContinue
    Remove-Item Env:ORACLE_SUBSET_EVAL -ErrorAction SilentlyContinue
}
```

生成後に次を確認する。

```powershell
py -c "import json,sys; p=json.load(open(sys.argv[1],encoding='utf-8')); print([q['id'] for q in p['questions']]); assert [q['id'] for q in p['questions']] == ['q01','q02','q03','q05','q06','q07','q08']" $subsetEval
```

subset生成後もGit worktreeがcleanであること。

```powershell
git status --short
```

## import確認

```powershell
$repoSrc = (Resolve-Path ".\src").Path
$oldPythonPath = $env:PYTHONPATH

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

## dry-run

```powershell
$repoSrc = (Resolve-Path ".\src").Path
$oldPythonPath = $env:PYTHONPATH

try {
    $env:PYTHONPATH = if ([string]::IsNullOrEmpty($oldPythonPath)) {
        $repoSrc
    } else {
        "$repoSrc$([IO.Path]::PathSeparator)$oldPythonPath"
    }

    py scripts/run_x8_evaluation.py `
      --eval-set $subsetEval `
      --output-dir $outputDir `
      --expected-head $head `
      --all `
      --timeout-seconds 600 `
      --dry-run

    if ($LASTEXITCODE -ne 0) {
        throw "X-8.14 dry-run failed with exit code $LASTEXITCODE."
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

- question orderが`q01,q02,q03,q05,q06,q07,q08`
- q04が含まれない
- question_countが7
- `adapter-mode real`
- `evidence-provider cli-search`
- JSON出力
- `--no-store`
- 各問timeout 600秒
- 出力先がリポジトリ外
- HEADとorigin/mainが一致
- worktree clean

## live実行

明示承認が確認できた場合だけ、dry-run成功後に次を**1回だけ**実行する。

runnerは内部で最大7回の`oracle ask`を順番に起動する。実行担当Agentや外部ラッパーのtimeoutは、7問×600秒と処理余裕を考慮し、少なくとも**5,400,000ms**にする。

```powershell
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
      --eval-set $subsetEval `
      --output-dir $outputDir `
      --expected-head $head `
      --all `
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

Write-Host "X-8.14 holdout runner exit code: $liveExit"
```

終了コードが0以外でも、同じコマンドや個別問題を再実行しない。systemic stopで7問未満になっても、その場でresumeしない。

## 結果確認

確認対象は今回の派生subsetとoutput directoryだけとする。

優先して読むもの:

```text
<outputDir>\manifest.json
<outputDir>\summary.jsonl
<outputDir>\summary.csv
<outputDir>\qXX\record.json
```

`stdout.json`はCLIの設計済みJSON境界にある構造化フィールドを用いてacceptanceを手動確認する場合だけ読む。全文をresult.mdやhikitsugi.mdへコピーしない。`stderr.txt`の原文は読まず、記録・公開しない。

各問題について次を記録する。

- attemptedか未実行か
- exit_code
- status
- result_classification
- run_id
- timed_out
- agent_call_count
- participants
- 各Phaseのstatus、success_count、error_code、固定summary
- Evidence件数、search/candidate/fetch成功失敗数、outcome
- retry_count
- JSON parse
- leakage check
- allowed_classificationsに含まれるか
- acceptance_checksの手動判定: met / not_met / not_assessable

質問別acceptance:

- q01: 3776m、Evidence、矛盾値なし
- q02: 2022-04-01、成人年齢引下げ、成立日との混同なし
- q03: 2024年受賞者、業績、別年との混同なし
- q05: Nile/Amazon競合、定義差、過度な断定なし
- q06: 富士山は活火山、休火山は旧表現、Evidence矛盾なし
- q07: 根拠なしなら捏造しない、Evidence不足明示、保留または未確認
- q08: 2026-07-13基準、公式・信頼できるEvidence、pre-releaseとstableの区別

全体集計:

- attempted count / 7
- completed count
- verified / partially_verified / withheld / unverified件数
- allowed classification適合数 / attempted数
- acceptance met数 / assessable数
- systemic stopの有無と停止位置
- Phase別失敗数
- エラーコード別件数
- Evidence fetch success率
- 総agent_call_count
- retry総数
- q04を実行していないこと

非決定的な品質評価なので、結果が悪くても再実行して改善しない。

## 解釈上の注意

- 7問はM-5導入前baselineである
- 一度の成功は再現性の証明ではない
- 一度の失敗は恒常的障害の証明ではない
- `partial_evidence`でも最終classificationが許容される場合がある
- q07の`unverified`、`partially_verified`、`withheld`は評価セット上すべて許容
- q04の既存結果を7問holdoutの分母へ含めない
- X-8.13のq04 verifiedは参考結果として別枠で扱う

## 公開境界

次をGitへ追加しない。

```text
派生subset以外の外部評価artifact
stdout.json
stderr.txt
raw stdout
raw stderr
prompt全文
質問・回答・Claim・Evidenceの全文
モデル出力全文
コマンド全文
環境変数
認証情報
APIキー
token
Cookie
HTTP header
任意のCLI診断原文
```

派生subsetとoutput directoryはリポジトリ外に残し、Gitへ追加しない。

## 実行後の変更範囲

結果を見た後もsource、test、config、runner、評価セットを変更しない。

更新を許可するのは次だけ。

```text
instructions/result.md
hikitsugi.md
```

`dream.md`は今回変更しない。

## ドキュメント更新

`instructions/result.md`と`hikitsugi.md`へX-8.14としてsanitized結果を追記する。

必須記録:

- 実行HEAD
- 指示書コミット
- 正本eval setのSHA-256
- 派生subsetのSHA-256
- subsetがq04除外のみで、7 question objectが正本とdeep-equalだったこと
- 明示承認文を確認したこと
- runner実行回数1回
- 外部question実行数
- q04実行数0
- 各問のsanitized結果
- 全体集計
- acceptance手動判定
- systemic stopの有無
- retryなし
- JSON/leakage結果
- raw情報をGitへ追加していないこと
- source/test/config/runner/eval-set未変更
- 次がM-5仕様確定であること

結果が途中終了でも、実行済み結果だけを記録し、未実行問題を明示する。

## コミット前確認

```powershell
git status --short
git diff --check
git diff -- instructions/result.md hikitsugi.md
```

許可される変更は次だけ。

```text
instructions/result.md
hikitsugi.md
```

それ以外の変更があればcommitせず報告する。

## commitとpush

```powershell
git add instructions/result.md hikitsugi.md
git commit -m "docs: record seven-question X-8 holdout evaluation"
git push origin main

git status --short
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main
```

完了条件:

- commit成功
- push成功
- worktree clean
- HEADとorigin/main一致
- 評価artifact、subset、raw出力をGitへ追加していない

## 最終報告

次を簡潔に報告する。

1. 実行HEADと結果コミット
2. 明示承認確認
3. 正本/subset SHA-256
4. attempted count
5. 各問のclassificationとacceptance
6. 全体集計
7. systemic stop、timeout、retryの有無
8. q04未実行
9. JSON/leakage
10. 変更ファイル
11. commit/push/clean状態
12. 次作業がM-5仕様確定であること

## 次の作業

X-8.14の結果記録が完了してから、次の順で進める。

```text
M-5: 代替Agent選定と再試行・12回上限
L-5: Phase別構造化出力スキーマ
S-8: processExitCodeとoracleExitCodeの分離
```
