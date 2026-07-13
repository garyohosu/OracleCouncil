# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.10: Claudeの長いPhase入力をstdinへ移す

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.9のq04 live再評価では、次のPhaseまで成功した。

```text
respond
claim_extract
evidence_collect
verify
criticize
```

その後、`synthesize`が次で停止した。

```text
error_code: COMMAND_NOT_FOUND
summary: synthesize execution ended with COMMAND_NOT_FOUND.
```

同じRun内でClaude/Codexは前段のPhaseに参加しているため、単純にCLIが未インストールだったとは断定できない。

現在の`ClaudeAdapter.execute()`は、質問、回答、Claim、Evidence、批評を含むPhase入力全文を、`claude -p <prompt>`の位置引数としてargvへ直接追加している。`synthesize`は前段の情報を集約するため、Phase入力が特に長くなる。

Claude Codeの公式CLIはprint modeでパイプ入力を扱える。X-8.6でCodex入力をstdin化したのと同様に、ClaudeのPhase入力もargvから除去し、stdin経由へ変更する。

今回はtransportの通常実装とFakeテストだけを行う。live、実Claude、実Codex、q04再評価は実行しない。

## X-8.9の確定結果

```text
実行HEAD: 0bdf5ca
結果コミット: 25c29f4
外部実行: q04を1回のみ、再試行なし
status: failed
exit_code: 1
classification: unverified
agent_call_count: 6
Evidence: 15件
verify: success
criticize: success
synthesize: COMMAND_NOT_FOUND
audit: 未到達
AUTH_REQUIRED: 再現せず
JSON parse: valid
leakage check: passed
```

X-8.9ではsource/testを変更していない。

## 作業前確認

最初に次を確認する。

```text
src/oracle_council/adapters/claude.py
src/oracle_council/adapters/codex.py
src/oracle_council/assignment.py
config/agents.yaml
tests/unit/test_codex_transport.py
tests/unit/test_adapter_unicode.py
tests/unit/test_adapter_error_classification.py
tests/unit/test_adapter_schema.py
hikitsugi.md
instructions/result.md
```

特に次を確認する。

- `synthesize`担当が設定とAssignmentPlan上で`claude-code`になること
- `ClaudeAdapter.execute()`がprompt全文をargvへ入れていること
- `ClaudeAdapter.probe()`はPhase入力を扱わないこと
- `CliSearchProvider`は今回の修正対象外であること
- ClaudeのJSON envelope解析とPhase JSON抽出
- X-8.6のCodex stdin transportテスト方式

PowerShell:

```powershell
cd C:\PROJECT\OracleCouncil

git status --short
git pull --ff-only
git status --short

git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main
git merge-base --is-ancestor 25c29f4 HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.9 result commit 25c29f4." }
```

合格条件:

- branchが`main`
- worktreeがclean
- `HEAD`と`origin/main`が一致
- pull後の作業名が`X-8.10`
- HEADに`25c29f4`が含まれる

不一致がある場合は実装せず報告する。

## 実装要件

### 1. ClaudeAdapterのPhase入力をargvから除去する

現在の構造:

```python
cmd = [
    "claude",
    "-p",
    prompt,
    "--tools",
    "",
    "--output-format",
    "json",
    "--no-session-persistence",
    "--safe-mode",
]
```

`prompt`をargvへ入れない構造へ変更する。

期待する基本形:

```python
cmd = [
    "claude",
    "-p",
    "--tools",
    "",
    "--output-format",
    "json",
    "--no-session-persistence",
    "--safe-mode",
]
```

本実行は概ね次の形にする。

```python
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

- user-derivedなPhase入力全文を`input=prompt`で渡す
- 本実行では`stdin=subprocess.DEVNULL`を併用しない
- prompt、質問、Claim、Evidence、批評、秘密文字列をargvへ入れない
- `--tools ""`、`--output-format json`、`--no-session-persistence`、`--safe-mode`を維持する
- `--model`指定がある場合の既存挙動を維持する
- shellは`False`のままにする
- 一時promptファイルを作らない

Claude CLIの引数解析上、固定の非機密queryが必要と確認できる場合に限り、user-derived文字列を含まない短い固定文を位置引数に使用してよい。ただし、まずは`-p`とstdinのみの構造を優先し、Fakeテストでcommand contractを固定する。

### 2. probeは変更しない

`ClaudeAdapter.probe()`は従来どおり次を維持する。

```text
claude --version
stdin=DEVNULL
5秒timeout
```

probeへ長い入力を渡さない。認証確認、`claude auth status`、ログイン処理は追加しない。

### 3. 出力処理を維持する

次を変更しない。

- `--output-format json`のCLI envelope解析
- `envelope["result"]`からのPhase JSON抽出
- `_extract_json_object()`
- `validate_phase_output()`
- Usageの既存扱い
- TIMEOUT、AUTH_REQUIRED、QUOTA_EXCEEDED、RATE_LIMITED、INVALID_OUTPUT、EXECUTION_ERROR、COMMAND_NOT_FOUNDの既存分類
- retry条件
- Storage Contract
- CLI JSON schema

今回、X-8.9の`COMMAND_NOT_FOUND`がWindowsのargv長によるものだったとは断定しない。stdin化で原因候補を除去するだけとする。

### 4. CliSearchProviderは変更しない

今回変更するのは`ClaudeAdapter.execute()`のPhase入力transportだけである。

次は変更しない。

```text
CliSearchProvider
WebSearch prompt
SafeHttpFetcher
Evidence収集
検索クエリ生成
```

### 5. 公開境界を維持する

次をsummary、CLI JSON、Phase metrics、result.md、hikitsugi.mdへ出さない。

```text
stdout原文
stderr原文
prompt全文
質問本文
回答本文
Claim本文
Evidence本文
批評本文
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

## テスト要件

Fake subprocessだけで通常テストを追加する。実Claudeは呼び出さない。

最低限、次を固定する。

### A. 長いsynthesize入力

- 50,000文字を超える質問、回答、Claim、Evidence、批評を含む`synthesize`用`AgentRequest`を作る
- `build_phase_input()`と`_build_prompt()`を通した完全なpromptが`subprocess.run(input=...)`へ渡る
- prompt中の識別用文字列がargvのどの要素にも存在しない
- argv長がprompt長に比例しない
- 本実行のkwargsに`stdin=DEVNULL`がない
- `input`が省略、切断、変換されていない

### B. 成功経路

Fake subprocessは次を返す。

1. probe: returncode 0
2. 本実行: 有効なClaude JSON envelope

`synthesize`のPhase JSONが従来どおり解析され、`AgentResult`になることを確認する。

### C. 既存引数の維持

- `-p`
- `--tools`と空文字
- `--output-format json`
- `--no-session-persistence`
- `--safe-mode`
- 指定時の`--model`
- `shell=False`
- timeout
- environment

### D. エラー回帰

既存テストまたは追加テストで次を維持する。

- probeのFileNotFoundError → `COMMAND_NOT_FOUND`
- 本実行のFileNotFoundError → 既存の`COMMAND_NOT_FOUND`
- TimeoutExpired → `TIMEOUT`
- 明示的認証失敗 → `AUTH_REQUIRED`
- quota/rate limit分類
- 未知の非ゼロ終了 → `EXECUTION_ERROR`と固定summary
- malformed envelope/Phase JSON → `INVALID_OUTPUT`
- raw promptや秘密文字列がpublic summaryへ混入しない

### E. Assignment確認

設定とAssignmentPlanの通常テストまたは既存テスト確認により、現行構成では`synthesize`が`claude-code`へ割り当てられることを固定する。不要な本番コード変更は行わない。

必要に応じて次のようなテストファイルを追加する。

```text
tests/unit/test_claude_transport.py
```

Codex transportテストとの重複を避けつつ、Claude固有のJSON envelope処理も確認する。

## 実行禁止事項

今回は次を実行しない。

```text
claude
codex
claude auth status
codex login status
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
```

## 検証

実装後、次を実行する。

```powershell
py -m pytest
git diff --check
git status --short
```

合格条件:

- 通常テスト全件pass
- live、expensiveは既定設定で除外
- `git diff --check`成功
- 意図しないファイル変更なし
- ClaudeのPhase入力がargvに含まれない
- 50,000文字超のsynthesize入力がstdinへ完全に渡る
- 既存の出力解析、分類、公開境界が維持される

## ドキュメント更新

### instructions/result.md

先頭へX-8.10節を追加する。

最低限、次を記録する。

1. X-8.9のsanitized結果
2. `synthesize`担当がClaudeであること
3. ClaudeAdapterがpromptをargvへ渡していたこと
4. stdin化の実装内容
5. 長文synthesizeテスト
6. argv非混入確認
7. 既存引数・出力解析・エラー分類の回帰
8. 変更ファイル
9. pytest結果
10. `git diff --check`結果
11. live・実CLI未実行
12. 原因を断定していないこと
13. 次の推奨作業

また、X-8.8の最終テスト数を次へ訂正し、追加テストコミット`67c8f3c`を記録する。

```text
257 passed, 6 deselected
```

X-8.9節が古い節の内部へ入っている場合は、内容を変えず独立した見出しとして整理してよい。

### hikitsugi.md

X-8.10として次を追記する。

- X-8.9でverify/criticizeまで成功したこと
- synthesizeでCOMMAND_NOT_FOUNDになったこと
- 現行synthesize担当がClaudeであること
- ClaudeのPhase promptをargvからstdinへ移したこと
- 原因は未断定であること
- Fake長文テスト
- 公開境界不変
- live未実行
- pytest結果

## commit・push

全通常テスト通過後、意図したsource、test、documentだけをコミットし、`origin/main`へpushする。

コミットメッセージ例:

```text
fix: pass Claude phase input through stdin
```

作業完了時に次を確認する。

```powershell
git status --short
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main
```

working tree clean、HEADとorigin/main一致を確認し、commit hashとpush結果を`instructions/result.md`へ記録する。
