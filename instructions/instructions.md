# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業を始める前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.8: AUTH_REQUIRED分類の部分一致を廃止する

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.7のq04再評価では、CodexAdapterのstdin化後、以前の短時間`EXECUTION_ERROR`は再現せず、`verify`が`AUTH_REQUIRED`で停止した。

```text
status: failed
exit: 1
classification: unverified
verify error_code: AUTH_REQUIRED
verify summary: verify execution ended with AUTH_REQUIRED.
```

ただし、現在の`classify_cli_error()`は自由文のfallback判定で次を使用している。

```python
if "auth" in lowered or "login" in lowered:
    return "AUTH_REQUIRED"
```

この判定は、明示的な認証失敗だけでなく、次のような無関係な文字列にも一致する。

```text
author
authority
authoritative
authentic
authentication-related explanatory text that is not an error
```

したがって、X-8.7の`AUTH_REQUIRED`が本当の認証切れだったか、部分一致による誤分類だったかは、保存されたsanitized情報だけでは確定できない。

今回はlive再実行を行わず、AUTH_REQUIREDの自由文判定を明示的な認証失敗表現のallowlistへ変更し、誤分類を通常テストで防ぐ。

## 確認済み事項

### 1. 構造化エラーは維持する

Claude Code等の構造化JSONに次がある場合は、従来どおり`AUTH_REQUIRED`としてよい。

```text
api_error_status: 401
api_error_status: 403
result内の明示的なunauthorized
```

### 2. Codex CLIにはlogin statusがある

公式Codex CLIには`codex login status`があり、保存済み認証情報がある場合は終了0、認証情報がない場合は終了1となる。

ただし、このコマンドはローカル認証ストレージの存在確認を主目的としており、実API呼び出し時のトークン有効性やrefresh成功まで保証するものとして扱わない。

今回は`CodexAdapter.probe()`への組込みや実`codex login status`実行は行わない。まず分類器だけを修正する。

### 3. X-8.7の結果

- 実行HEAD: `177abc4`
- q04 live: 1回のみ
- CodexとClaudeが参加
- respond、claim_extract、evidence_collect成功
- Evidence 14件
- verifyで`AUTH_REQUIRED`
- JSON parse valid
- leakage check passed
- raw stdout/stderrは保存・公開していない
- 実行結果コミット: `9165f2c docs: record q04 stdin live re-evaluation`

## 作業前確認

最初に次を確認する。

```text
src/oracle_council/adapters/base.py
src/oracle_council/adapters/codex.py
src/oracle_council/adapters/claude.py
tests/unit/test_adapter_error_classification.py
tests/unit/test_adapter_schema.py
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
```

合格条件:

- branchが`main`
- worktreeがclean
- `HEAD`と`origin/main`が一致
- pull後の作業名が`X-8.8`
- HEADに`9165f2c`が含まれる

不一致がある場合は実装せず、状況を報告する。

## 実装要件

### 1. 裸の`"auth" in lowered`判定を削除する

次のような単純な部分一致を使用しない。

```python
"auth" in lowered
```

`login`についても、単独の単語が現れただけで認証失敗と断定しない。文脈を伴う明示的な失敗表現に限定する。

### 2. AUTH_REQUIREDの自由文allowlistを定義する

実装方法は既存コードの命名規則に合わせてよいが、自由文fallbackは最低限、次のような明示的表現だけを認証失敗として扱う。

```text
unauthorized
not logged in
login required
log in required
please login
please log in
please sign in
sign in again
authentication required
auth required
invalid api key
missing api key
api key is missing
access token expired
refresh token has expired
refresh token was revoked
refresh token was already used
```

大文字小文字、句読点、複数空白は安全に正規化してよい。

完全な自然言語解析は不要。固定フレーズまたは境界付き正規表現を使用し、任意のCLI文字列を外部へ出さない。

### 3. 明示的でない語はAUTH_REQUIREDにしない

少なくとも次は`AUTH_REQUIRED`へ分類しない。

```text
author
authoritative source
authority
authentic response
authenticity check
authorization policy
login page documentation
OAuth documentation
```

`authorization denied`のように権限拒否を意味する表現は、仕様上AUTH_REQUIREDへ含めるか慎重に判断すること。単に`authorization`という単語があるだけでは認証失敗としない。

明示的な既知パターンに一致しない非ゼロ終了は、Adapter側で従来どおり`EXECUTION_ERROR`へフォールバックさせる。

### 4. 既存分類の優先順位を維持する

次の優先順位と既存挙動を壊さない。

- 構造化401/403 → `AUTH_REQUIRED`
- 構造化429でrate limit文言 → `RATE_LIMITED`
- その他の構造化429 → `QUOTA_EXCEEDED`
- quota、usage credit、session limit → `QUOTA_EXCEEDED`
- 明示的rate limit → `RATE_LIMITED`
- 明示的認証失敗 → `AUTH_REQUIRED`
- それ以外 → `None`、呼出側で`EXECUTION_ERROR`

TIMEOUT、COMMAND_NOT_FOUND、INVALID_OUTPUT等のAdapter側処理は変更しない。

### 5. 公開境界を変更しない

次をsummary、CLI JSON、Phase metrics、X-8 summaryへ出さない。

```text
stdout
stderr
prompt
質問本文
Claim本文
Evidence本文
モデル出力
コマンド全文
ファイルパス
環境変数
APIキー
access token
refresh token
Cookie
HTTP header
例外本文
任意のCLI出力文字列
```

Storage Contract、JSONL形式、Run分類、終了コード、retry条件は変更しない。

### 6. probeやlogin処理は変更しない

今回は次を変更しない。

- `CodexAdapter.probe()`
- `ClaudeAdapter.probe()`
- `codex login status`の自動実行
- 認証情報の読取り・更新・削除
- ログイン操作
- token refresh処理
- Adapterのコマンドライン引数
- stdin transport
- phase schema
- prompt内容

## テスト要件

Fakeまたは純粋関数テストだけで実施する。

### AUTH_REQUIREDになるケース

最低限、次を追加または維持する。

1. 構造化401
2. 構造化403
3. 構造化`unauthorized`
4. `Not logged in`
5. `Please log in again`
6. `Authentication required`
7. `Invalid API key`
8. `refresh token has expired. Please log out and sign in again.`

### AUTH_REQUIREDにならないケース

最低限、次を追加する。

1. `authoritative source unavailable`
2. `authority lookup failed`
3. `authentic response could not be parsed`
4. `author field was missing`
5. `OAuth documentation was not found`
6. `login page documentation could not be fetched`
7. `authorization policy rejected the request`のみで、認証資格情報の不足を明示しないケース

これらは`classify_cli_error()`で`None`となり、Adapterの非ゼロ終了経路では`EXECUTION_ERROR`になることを確認する。

### 回帰

- QUOTA_EXCEEDEDを維持
- RATE_LIMITEDを維持
- AUTH_REQUIREDの明示的ケースを維持
- 非ゼロ終了時の固定EXECUTION_ERROR summaryを維持
- raw文字列や秘密情報がpublic summaryへ混入しない
- Claude/Codex双方が共通分類器を使用しても既存テストが通る

## 実行禁止事項

今回は次を実行しない。

```text
codex
claude
codex login
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

保存済み評価結果を変更・削除・再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
C:\PROJECT\OracleCouncil-evals\x8\177abc4-q04-stdin
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
- 意図しないファイル変更なし
- 裸の`"auth" in lowered`が残っていない
- 明示的認証エラーはAUTH_REQUIRED
- `author`、`authority`、`authentic`等はAUTH_REQUIREDにならない

## ドキュメント更新

`hikitsugi.md`へX-8.8として次を追記する。

- X-8.7のAUTH_REQUIREDは真の認証切れか誤分類か未確定であること
- 旧判定が`auth`部分一致だったこと
- 新しい明示的認証失敗allowlist
- AUTH_REQUIREDにならない負例
- 構造化401/403の扱いは維持したこと
- probe、login status、認証情報を変更していないこと
- liveを実行していないこと
- pytest結果
- 次の作業候補

次の作業候補は、ユーザー承認後にローカルで`codex login status`を安全に確認するか、別HEADでq04を1回限定再評価すること。ただしX-8.8完了時点では実施しない。

## 結果出力

作業結果を必ず次へ出力する。

```text
instructions/result.md
```

先頭へX-8.8の節を追加し、最低限次を記録する。

1. 旧AUTH_REQUIRED判定の問題
2. 実装した明示的パターン
3. AUTH_REQUIREDにならない負例
4. 既存分類の回帰結果
5. 変更ファイル一覧
6. pytest結果
7. `git diff --check`結果
8. live・実CLIを実行していないこと
9. Storage Contractと公開境界が不変であること
10. 未解決事項と次の推奨作業

## commit・push

全通常テスト通過後、意図したsource、test、documentだけをコミットし、`origin/main`へpushする。

コミットメッセージ例:

```text
fix: tighten auth error classification
```

commit hashとpush結果を`instructions/result.md`へ記録する。