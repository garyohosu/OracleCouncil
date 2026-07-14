---
protocol_version: 1
task_id: X-8.20
task_revision: 1
status: completed
previous_task_id: X-8.19
expected_base_commit: f13b043
preferred_executor: antigravity
session_policy: resume
allow_source_edit: true
allow_test_execution: true
allow_commit: true
allow_push: true
allow_live: false
allow_external_ai: false
allow_web_search: false
max_resume_count: 3
max_wall_minutes: 90
commit_message: "fix: contain DNS resolution failures in SafeHttpFetcher"
required_tests:
  - "py -m pytest"
allowed_paths:
  - "src/oracle_council/**"
  - "tests/**"
  - "QandA.md"
  - "SPEC.md"
  - "CLASS.md"
  - "TESTCASE.md"
  - "FIX_PLAN.md"
  - "hikitsugi.md"
  - "instructions/result.md"
---
# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分や未追跡ファイルがある場合は、勝手にreset・stash・削除・移動せず、差分を保護して状況を報告してください。

## X-8.20: q03 DNS failure-boundaryの修正

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.14のholdout評価では、q03がOracle Councilの構造化JSONとして次の状態で停止した。

```text
status: internal_error
oracle exit: 1
run_id: null
message: [Errno 11001] getaddrinfo failed
```

これはAgentExecutionの失敗ではなく、Evidence取得中のDNS解決例外が型付き境界へ変換されず、CLI最上位のgeneric exception handlerまで漏れたものと判断されている。ただし、正確な漏出箇所はまだコードとテストで確定していない。

X-8.20では、実装を先に決めつけず、まずFake DNS失敗で漏出経路を再現する。そのうえで最小のネットワーク境界修正を行い、`socket.gaierror`やDNS起因の`URLError`がraw例外のまま`internal_error`へ漏れないようにする。

X-8.19完了コミット:

```text
cd8422e5255447f6e298126cfeb394f97af66411
```

baseline:

```text
292 passed, 6 deselected
```

今回は実Claude、実Codex、WebSearch、実HTTP、live評価、q03再実行を行わない。

## 優先順位

q03のfailure-boundaryをS-9/S-10より先に修正する。

理由:

- 実holdoutで発生した具体的なsystemic failureである
- 評価runnerではなくOracle Council CLI自身が`internal_error`を返した
- 以後のlive評価の信頼性へ直接影響する
- S-9/S-10はAgent選定・probe snapshotの設計課題であり、DNS例外の漏出とは独立している

## 並行作業禁止

X-8.20と次を並行で進めない。

```text
S-9 / S-10
L-3 INVALID_OUTPUT回復
J-3 quick実行グラフ
S-4 Clarifier Agent経路
S-6 / T-2 cancel
T-3 DNS rebindingのpinned transport設計
Responder並列化
X-8 live評価
```

特に、X-8.20は**通常のDNS解決失敗を型付きEvidenceエラーへ収容する作業**である。T-3のDNS rebinding対策、resolver pinning、接続先IP固定を同時実装しない。

## 作業前確認

最初に次を読む。

```text
hikitsugi.md                 X-8.14 q03結果、X-8.19結果
instructions/result.md       X-8.14 q03結果、X-8.19結果
FIX_PLAN.md                  q03 failure-boundary、T-3
QandA.md                     S-1、T-3、S-8
SPEC.md                      EvidenceProvider、SafeHttpFetcher、Evidenceエラー、CLI終了コード
CLASS.md                     WebEvidenceProvider、SafeHttpFetcher、EvidenceFetchError、SearchError
SEQUENCE.md                  Evidence検索・取得の異常系
TESTCASE.md                  SafeHttpFetcher Security/Contract、EvidenceProvider、CLI JSON
src/oracle_council/http_fetch.py またはSafeHttpFetcher実装ファイル
src/oracle_council/evidence.py またはWebEvidenceProvider実装ファイル
src/oracle_council/models.py
src/oracle_council/orchestrator.py
src/oracle_council/cli.py
既存のSafeHttpFetcher / WebEvidenceProvider / CLIテスト
```

実際のファイル名が異なる場合は、定義元を検索して読む。

## Git前提確認

```powershell
cd C:\PROJECT\OracleCouncil

git status --short
git pull --ff-only
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git rev-parse refs/remotes/origin/main

git merge-base --is-ancestor cd8422e HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.19 commit cd8422e." }

git merge-base --is-ancestor 8bbc076 HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.18 commit 8bbc076." }
```

合格条件:

- branchが`main`
- `git status --short`が完全に空
- HEADと`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.20`
- HEADに`cd8422e`と`8bbc076`が含まれる

`dream.md`を含む未追跡ファイルが表示された場合は実装を開始しない。勝手に`git stash -u`、削除、移動、`.gitignore`追加をせず、ユーザーへ報告する。

## 変更前baseline

```powershell
py -m pytest
git diff --check
git status --short
```

基準:

```text
292 passed, 6 deselected
```

件数が変わっていても通常テストが全件passし、live/expensiveが除外されていればよい。

## 1. まず漏出経路をFakeで再現する

実装変更前に、既存コードで失敗する最小テストを追加する。

最低限、次を個別に確認する。

### 1.1 resolverの直接失敗

SafeHttpFetcherが利用するresolverまたは`socket.getaddrinfo`へ、次を注入する。

```python
socket.gaierror(11001, "getaddrinfo failed")
```

期待:

- raw `socket.gaierror`が呼び出し元へそのまま漏れる現状を再現できること、または既に変換されるなら別の漏出経路を特定すること
- Windows固有errno文字列に依存せず、`socket.gaierror`型でテストすること

### 1.2 opener/HTTP層に包まれたDNS失敗

次のような形もテストする。

```python
urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
```

実装がurllib以外なら、そのHTTP層がDNS失敗を包む実際の例外形をFakeで再現する。

### 1.3 providerからCLIまでの回帰

Fake resolver/openerを使い、少なくとも次の経路を通す。

```text
SafeHttpFetcher
→ WebEvidenceProvider
→ Orchestrator evidence_collect
→ CLI JSON
```

期待:

- `status=internal_error`にならない
- rawメッセージ`getaddrinfo failed`を公開JSONの`message`、`error_summary`、metadataへ出さない
- `oracle_exit_code=1`のgeneric internal error終端へ落ちない
- 既存のEvidence fetch failure契約に従って、失敗件数・error codeが記録される

## 2. 修正する境界

例外を最も狭いネットワーク境界で型付きエラーへ変換する。

優先順:

1. SafeHttpFetcherのDNS解決・HTTP open境界
2. WebEvidenceProviderの個別candidate fetch境界
3. Orchestrator / CLIは型付きエラーを既存規則どおり処理するだけ

CLIへ`except socket.gaierror`や広い`except OSError`を足して問題を隠すだけの修正は禁止する。

## 3. エラーコード

既存の`EvidenceFetchError`、SafeHttpFetcher、SPEC、TESTCASEに定義済みの公開error codeを正本とする。

- DNS失敗に対応する既存codeがある場合はそれを使用する
- 既存codeが一般的なnetwork failureを表している場合は、新しいcodeを増やさずそのcodeを使用する
- 新しい公開codeが本当に必要な場合は、先にQandA/SPEC/TESTCASEで一意に定義し、既存利用者との互換性を確認する
- errno、hostname、URL、IP、例外本文をerror codeやpublic summaryへ埋め込まない

最終報告には、採用したcodeと、そのcodeを選んだ既存契約上の根拠を記録する。

## 4. SafeHttpFetcher要件

DNS起因例外を、既存Contractに従う`EvidenceFetchError`または同等の型付きfetch例外へ変換する。

対象例:

```text
socket.gaierror
URLError.reasonがsocket.gaierror
resolverが投げるDNS/OSErrorのうち、DNS解決失敗と判定できるもの
```

要件:

- public codeと固定summaryだけを外へ出す
- raw例外本文はmetadataへ保存しない
- store-content時のraw診断方針が既にある場合だけ、その既存境界を維持する
- timeout、TLS、redirect、private IP、size limitなど既存分類を壊さない
- SSRF防止、redirect再検証、scheme制限を弱めない
- `except Exception`で全てをnetwork error化しない

## 5. WebEvidenceProvider要件

個別URLのfetch失敗は、既存のpartial-evidence規則に従う。

- 1候補のDNS失敗で、他候補の取得を不必要に中断しない
- `fetch_attempt_count`を維持する
- `fetch_failure_count`を加算する
- `fetch_error_codes`へ型付きcodeを加算する
- 他候補からEvidenceを取得できた場合は、そのEvidenceを保持する
- Evidenceが0件の場合の扱いは、既存SPEC/実装の正本に従う。X-8.20だけの都合で新しいRun classificationを作らない
- `SearchError`と`EvidenceFetchError`を混同しない

## 6. Orchestrator / CLI要件

- 型付きEvidenceエラーは既存の`evidence_collect` PhaseとCLI出力規則へ従わせる
- generic `internal_error`へ漏らさない
- Runが既に生成されている経路では、可能な限りそのRun記録を維持する
- `oracle_exit_code`と互換`exit_code`の同値を維持する
- `process_exit_code`との分離を壊さない
- q03のDNS失敗をAgent retry/substitutionへ流さない
- raw DNS例外本文をstdout/stderrの公開契約や保存metadataへ出さない

## 7. 必須テスト

最低限、次を追加・更新する。

### SafeHttpFetcher単体

- `socket.gaierror(11001, ...)`が型付きfetch errorになる
- `URLError(socket.gaierror(...))`が同じ公開分類になる
- public code/summaryにhost、URL、errno本文が含まれない
- timeout、blocked address、redirect等の既存テストが回帰しない

### WebEvidenceProvider

- 1件DNS失敗＋1件成功でpartial evidenceを返す
- metricsがattempt 2、success 1、failure 1になる
- `fetch_error_codes`へ採用codeが1件記録される
- DNS失敗後も次candidateを試す

### Orchestrator / CLI

- Fake DNS失敗が`internal_error`にならない
- JSONがvalid
- `oracle_exit_code == exit_code`
- raw `getaddrinfo failed`、errno、テスト用host/URLを公開summaryへ含めない
- q03型失敗でAgent retry/substitution counterを消費しない

### 非対象回帰

- X-8.19の25件を含むexit-code separationテスト
- L-5 phase schemaテスト
- M-5/S-5 substitutionテスト

## 8. 変更可能範囲

漏出経路に必要な最小範囲だけ変更する。

想定:

```text
SafeHttpFetcher実装ファイル
WebEvidenceProvider実装ファイル
models.py（既存Evidence error型の最小変更が必要な場合のみ）
orchestrator.py（既存型付きエラー処理の最小補強が必要な場合のみ）
cli.py（JSON回帰テスト上必要な最小変更のみ。広域catch追加は禁止）
関連unit/contract/CLI tests
QandA.md
SPEC.md
CLASS.md / SEQUENCE.md / TESTCASE.md（実際の契約変更がある場合）
FIX_PLAN.md
hikitsugi.md
instructions/result.md
```

変更禁止:

```text
config/
evaluation/
scripts/
phase schemas
Agent assignment / retry / substitution仕様
oracle/process exit-code契約
protected eval artifact directories
```

## 9. 実行禁止

```text
claude
codex
WebSearch
実HTTP
ORACLE_COUNCIL_LIVE=1
live / expensive pytest
X-8評価
q01〜q08
```

Claude Codeを実装担当として使用すること自体はよい。Oracle Councilから実Claude/Codexを呼び出してはならない。

## 10. 検証

対象テストを先に実行し、その後通常テストを全件実行する。

```powershell
py -m pytest <追加・更新したDNS/SafeHttpFetcher/WebEvidenceProvider/CLIテスト>
py -m pytest
git diff --check
git status --short
```

期待baseline:

```text
292 passed, 6 deselected
```

テスト追加により件数が増えてよい。通常テスト全件pass、live/expensive除外が条件。

## 11. 文書更新

### FIX_PLAN.md

- q03 failure-boundaryを、Fakeで原因経路を確定し通常実装・テスト完了した場合だけ解消済みへ移す
- 実live q03再確認は未実施と明記する
- T-3、S-9/S-10を解消済みにしない

### hikitsugi.md / instructions/result.md

X-8.20として次を記録する。

- 実際の漏出箇所
- 再現した例外形
- 採用した型付きerror code
- SafeHttpFetcherでの変換境界
- WebEvidenceProviderの継続・metrics挙動
- CLIで`internal_error`へ漏れないFake結果
- raw情報非公開確認
- 変更ファイル
- targeted/full pytest
- live未実行
- q03再評価には別の明示承認が必要
- 次候補がS-9/S-10であること

## 12. commit前確認

```powershell
git status --short
git diff --check
git diff --stat
git diff -- <変更ファイル>
```

次が混入していないことを確認する。

```text
実評価artifact
dream.md
raw DNS例外本文
host/IP/URLを含むfixture外の実データ
CLI認証情報
```

## 13. commitとpush

コミット例:

```powershell
git add <変更ファイル>
git commit -m "fix: contain DNS resolution failures"
git push origin main

git status --short
git rev-parse HEAD
git rev-parse refs/remotes/origin/main
```

完了条件:

- Fakeでq03型DNS例外の漏出経路を再現・特定
- DNS失敗が型付きEvidenceエラーへ変換される
- generic `internal_error`へ漏れない
- raw DNS例外本文が公開・metadataへ混入しない
- partial evidenceとmetrics規則が維持される
- q03をlive再実行していない
- 通常テスト全件pass
- `git diff --check`成功
- commit/push成功
- tracked/untrackedを含め`git status --short`が完全に空
- HEADとorigin/main一致

## 最終報告

次を簡潔に報告する。

1. 実行前HEADと結果commit SHA
2. q03漏出の正確な原因箇所
3. 再現した例外形
4. 採用した型付きerror codeと根拠
5. SafeHttpFetcher/WebEvidenceProvider/Orchestrator/CLIの変更内容
6. partial evidenceとmetricsのテスト結果
7. raw情報非混入の確認
8. targeted/full pytest件数
9. `git diff --check`
10. 実CLI/live/q03再評価を行っていないこと
11. 変更ファイル一覧
12. push/clean/HEAD一致
13. 未解決のS-9/S-10、T-3、その他設計ゲート
14. 次はその場で進めず、次指示を待つこと
