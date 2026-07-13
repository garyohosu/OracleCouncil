# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.12: CliSearchProviderの検索promptをstdinへ移す

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.11はHEAD `05714b7`でq04を1回だけ実行済みであり、再実行しない。
結果はコミット`193706d docs: record q04 Claude stdin live re-evaluation`へ記録済み。

確定結果:

```text
status: completed
exit_code: 4
classification: withheld
agent_call_count: 9
respond〜audit: 全Phase成功
synthesize success_count: 2
audit success_count: 2
COMMAND_NOT_FOUND: 再現せず
JSON parse: valid
leakage check: passed
```

`acceptance_status=not_assessed`は異常ではない。`evaluation/x8/README.md`にあるとおり、`acceptance_checks`は自動採点せず、runnerは`not_assessed`を記録する設計である。既存評価結果を書き換えない。

CodexAdapterとClaudeAdapterのPhase入力はstdin化済みだが、`CliSearchProvider.search()`は検索queryを含むprompt全文を、現在も`claude -p <prompt>`のargvへ直接追加し、本実行で`stdin=DEVNULL`を使用している。

X-8.12では、`CliSearchProvider`の検索promptもstdinへ移し、user-derived queryをargvから除去する。通常実装とFakeテストだけを行い、live・実Claude・WebSearch・q04は実行しない。

## 作業前確認

最初に次を確認する。

```text
src/oracle_council/adapters/claude.py
tests/unit/test_claude_transport.py
tests/unit/test_adapter_unicode.py
CliSearchProvider関連テスト
evaluation/x8/README.md
FIX_PLAN.md
hikitsugi.md
instructions/result.md
```

PowerShell:

```powershell
cd C:\PROJECT\OracleCouncil

git status --short
git pull --ff-only
git status --short

git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main

git merge-base --is-ancestor 193706d HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.11 result commit 193706d." }

git merge-base --is-ancestor 1152bcf HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain Claude stdin commit 1152bcf." }
```

合格条件:

- branchが`main`
- worktreeがclean
- `HEAD`と`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.12`
- HEADに`193706d`と`1152bcf`が含まれる

不一致がある場合は実装せず状況を報告する。

## 現行問題

現在の`CliSearchProvider.search()`は概ね次の構造になっている。

```python
prompt = _SEARCH_PROMPT_TEMPLATE.format(query=query, limit=limit)
cmd = [
    "claude",
    "-p",
    prompt,
    "--tools",
    "WebSearch",
    "--output-format",
    "json",
    "--no-session-persistence",
    "--safe-mode",
]

subprocess.run(
    cmd,
    ...,
    stdin=subprocess.DEVNULL,
    shell=False,
)
```

この構造では検索queryとpromptがargvへ入る。X-8.6/X-8.10でPhase入力に採用したstdin transportと方針が一致していない。

## 実装要件

### 1. 検索promptをargvから除去する

期待する基本形:

```python
cmd = [
    "claude",
    "-p",
    "--tools",
    "WebSearch",
    "--output-format",
    "json",
    "--no-session-persistence",
    "--safe-mode",
]

subprocess.run(
    cmd,
    input=prompt,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=self.timeout_s,
    env=env,
    shell=False,
)
```

要件:

- user-derivedな`query`を含む完全な検索promptを`input=prompt`で渡す
- 本実行では`stdin=subprocess.DEVNULL`を併用しない
- query、prompt、識別文字列をargvへ入れない
- `-p`、`--tools WebSearch`、`--output-format json`、`--no-session-persistence`、`--safe-mode`を維持する
- `shell=False`、timeout、環境変数の既存挙動を維持する
- 一時promptファイルを作らない
- queryの切断・要約・文字コード変換をしない

### 2. 検索結果処理を変更しない

次を維持する。

- Claude JSON envelope解析
- `envelope["result"]`からのJSON抽出
- `sources`配列の検証
- `limit`件への切り詰め
- malformed itemのskip
- `retrieved_at`
- `source="claude-code-websearch"`
- `classify_cli_error()`と`_SEARCH_ERROR_MAP`
- `SEARCH_TIMEOUT`、`SEARCH_UNAVAILABLE`、`SEARCH_AUTH_REQUIRED`、`SEARCH_QUOTA_EXCEEDED`、`SEARCH_RATE_LIMITED`
- `INVALID_SEARCH_RESPONSE`
- SafeHttpFetcherだけがURLを実取得する境界

### 3. Phase Adapterを壊さない

`ClaudeAdapter.execute()`のstdin transport、`ClaudeAdapter.probe()`、`CodexAdapter`は変更しない。

## テスト要件

Fake subprocessだけで通常テストを追加または更新する。実ClaudeやWebSearchは呼び出さない。

最低限、次を確認する。

### A. 長い検索query

- 50,000文字を超えるqueryを作る
- 完全な検索promptが`subprocess.run(input=...)`へ渡る
- query識別文字列がargvのどの要素にも存在しない
- argv長がquery長に比例しない
- 本実行kwargsに`stdin`がない
- `input`にquery全文、limit、JSON出力指示が含まれる

### B. Unicode

- 日本語queryをstdinで完全に渡す
- argvに日本語queryがない
- `encoding="utf-8"`と`errors="replace"`を維持する

### C. 成功経路

Fake subprocessが有効なClaude JSON envelopeを返す場合に、従来どおり`SearchResult`へ変換されることを確認する。

- URL
- title
- snippet
- rank
- source
- retrieved_at
- limit超過時の切り詰め

### D. エラー回帰

既存または追加テストで次を維持する。

- FileNotFoundError → `SEARCH_UNAVAILABLE`
- TimeoutExpired → `SEARCH_TIMEOUT`
- 明示的認証失敗 → `SEARCH_AUTH_REQUIRED`
- quota → `SEARCH_QUOTA_EXCEEDED`
- rate limit → `SEARCH_RATE_LIMITED`
- 未知の非ゼロ終了 → `SEARCH_UNAVAILABLE`
- malformed envelope/JSON/sources → `INVALID_SEARCH_RESPONSE`
- raw queryや秘密文字列が公開summaryへ追加されない

## O-6の整理

`FIX_PLAN.md`のO-6進捗を更新する。

確認対象:

- Codex Phase prompt: stdin化済み
- Claude Phase prompt: stdin化済み
- CliSearchProvider query prompt: 今回stdin化
- Codexの一時ファイル: user contentを含まないJSON Schemaのみ
- prompt本文用一時ファイル: 使用しない

上記が通常テストで確認できた場合、O-6はMVPのtransport方針として解消済みと記録してよい。未解決条件が残る場合は、解消済みと断定せず具体的に残件を書く。

## 公開境界

次をsummary、CLI JSON、Phase metrics、result.md、hikitsugi.mdへ出さない。

```text
stdout原文
stderr原文
検索prompt全文
検索query全文
質問本文
Claim本文
Evidence本文
モデル出力本文
コマンド全文
環境変数
APIキー
access token
refresh token
Cookie
HTTP header
例外本文
任意のCLI診断文字列
```

## 実行禁止事項

今回は次を実行しない。

```text
claude
codex
WebSearch
実HTTP取得
ORACLE_COUNCIL_LIVE=1
liveテスト
expensiveテスト
q04再実行
8問フル評価
scripts/run_x8_evaluation.pyのlive実行
```

保存済み評価結果を変更、削除、再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
C:\PROJECT\OracleCouncil-evals\x8\177abc4-q04-stdin
C:\PROJECT\OracleCouncil-evals\x8\0bdf5ca-q04-authfix
C:\PROJECT\OracleCouncil-evals\x8\05714b7-q04-claude-stdin
```

## 検証

```powershell
py -m pytest
git diff --check
git status --short
```

合格条件:

- 通常テスト全件pass
- live、expensiveは既定設定で除外
- `git diff --check`成功
- user-derived検索queryがargvへ入らない
- 完全な検索promptがstdinへ渡る
- 既存検索結果処理とエラー分類が維持される
- 意図しないファイル変更がない

## ドキュメント更新

`hikitsugi.md`へX-8.12として次を追記する。

- X-8.11は完了済みで再実行しないこと
- X-8.11の全Phase成功とwithheld結果
- `acceptance_status=not_assessed`はrunner仕様であること
- CliSearchProviderの旧argv transport
- stdin化後のcommand contract
- 追加・更新テスト
- O-6の最終状態
- live・実CLIを実行していないこと
- pytestと`git diff --check`結果

`instructions/result.md`の先頭へX-8.12の節を追加し、最低限次を記録する。

1. 旧CliSearchProvider transport
2. stdin化した内容
3. argv非混入テスト
4. Unicode/長文/成功/エラー回帰結果
5. O-6の状態
6. 変更ファイル一覧
7. pytest結果
8. `git diff --check`結果
9. live・q04・実CLI未実行
10. 未解決事項

## commit・push

全通常テスト通過後、意図したsource、test、documentだけをコミットし、`origin/main`へpushする。

コミットメッセージ例:

```text
fix: pass search prompt through stdin
```

commit hash、push結果、最終working tree状態を`instructions/result.md`へ記録する。
