# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業を始める前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.6: Codexの長いPhase入力をstdinへ移す

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

q04のlive評価では、2回とも次の流れで失敗した。

- `respond` 2回成功
- `claim_extract`成功
- `evidence_collect`成功
- Evidence 14〜15件取得
- `verify`のCodex CLIが起動直後の短時間で非ゼロ終了
- `EXECUTION_ERROR`

X-8.3〜X-8.5により、失敗を安全な固定summaryとして記録する経路は整備できたが、実Codexが非ゼロ終了する根本原因は未特定である。

現在の`CodexAdapter.execute()`は、`build_phase_input()`が生成した質問、Claim、Evidence等の長い入力全文を、`codex exec`の位置引数としてコマンドラインへ直接追加している。

```python
cmd = [
    "codex.cmd" if os.name == "nt" else "codex",
    "exec",
    question,
    ...
]
```

`verify`は質問だけでなくClaimとEvidenceを含むため、先行Phaseより大幅に長くなる。Windows上で`codex.cmd`へ長い引数を渡す構成は、コマンドライン長制限や引数解釈の影響を受ける可能性がある。

これは現時点では**有力仮説であり確定原因ではない**。今回の目的は、原因と断定することではなく、Codex CLIが公式に対応するstdin入力へ切り替え、プロンプト長をコマンドラインから除去することで、この失敗要因を安全に排除することである。

## O-6に関する今回の設計判断

`FIX_PLAN.md`のO-6「stdin限定と一時ファイル許可の矛盾」について、CodexAdapterでは次の境界を採用する。

### stdinへ渡す情報

次のユーザー由来・実行由来データはコマンドライン引数や一時ファイルへ書かず、stdinで渡す。

```text
question
responses
claims
evidence
critique
final_answer
build_phase_input()が生成するPhase入力全文
```

### 一時ファイルを許可する情報

Codex CLIの`--output-schema`で必要な、プログラムが生成したJSON Schemaだけは一時ファイルを許可する。

条件:

- ユーザー質問を含めない
- Claim本文、Evidence、回答、promptを含めない
- 環境変数や認証情報を含めない
- subprocess終了後、成功・失敗を問わず`finally`で削除する
- 既存の安全な一時ファイル処理を維持する

今回、ClaudeAdapterやCliSearchProviderの入力方式は変更しない。O-6全体を完了扱いにせず、**CodexAdapter側のprompt transportを解消した**と記録する。

## 作業前確認

最初に次を確認する。

```text
src/oracle_council/adapters/codex.py
src/oracle_council/adapters/base.py
tests/unit/test_adapter_error_classification.py
tests/unit/test_adapter_schema.py
FIX_PLAN.md
hikitsugi.md
instructions/result.md
```

確認事項:

- `build_phase_input()`がPhase別に含めるデータ
- CodexAdapterの`probe()`と本実行の`subprocess.run()`の違い
- temp schemaの作成・削除経路
- `classify_cli_error()`の順序
- X-8.3のEXECUTION_ERROR固定summary
- X-8.5のOrchestrator summary規則
- Codex CLIのprompt `-`によるstdin入力契約

## 実装要件

### 1. promptをargvから除去する

Codex本実行のコマンドラインに、`question`または`build_phase_input()`の戻り値を直接含めない。

期待する構造例:

```python
cmd = [
    "codex.cmd" if os.name == "nt" else "codex",
    "exec",
    "-s",
    "read-only",
    "--ephemeral",
    "--output-schema",
    temp_schema_path,
]

if self.model:
    cmd.extend(["--model", self.model])

cmd.append("-")
```

実際の並び順はCodex CLIの現行契約に合わせること。

次を満たすこと。

- promptを示す位置引数にはstdin指定の`-`だけを使う
- `question`全文を`cmd`へ追加しない
- schema path以外の実行時データをargvへ追加しない
- Windowsでは従来どおり`codex.cmd`を使う
- read-only、ephemeral、output-schema、model指定を維持する

### 2. subprocess.runへstdinデータを渡す

本実行では`subprocess.run()`へPhase入力を文字列として渡す。

期待例:

```python
res = subprocess.run(
    cmd,
    input=question,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=self.timeout_s,
    env=env,
    shell=False,
)
```

次を満たすこと。

- `input=question`を使用する
- 本実行で`stdin=subprocess.DEVNULL`を併用しない
- probeは従来どおり`stdin=subprocess.DEVNULL`でよい
- prompt内容をログ、例外summary、コマンド表示へ追加しない

### 3. 既存の処理を変更しない

次を維持する。

- probeの動作
- `--output-schema`による構造化出力
- `_strict_schema()`
- temp schemaの削除
- stdoutからのJSON抽出
- `validate_phase_output()`
- TIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、AUTH_REQUIRED分類
- EXECUTION_ERROR固定summary
- INVALID_OUTPUT構造診断
- Usageの現行扱い
- Storage Contract
- Run、Phase、Executionのclassificationと終了コード

### 4. 仮説を事実化しない

ドキュメントでは次のように区別する。

- 確認済み: Codex prompt全文がargvへ入っていた
- 確認済み: verifyはClaimとEvidenceを含み、前段より長い
- 確認済み: q04のverifyで短時間の非ゼロ終了が2回再現した
- 仮説: Windowsのコマンドライン長または引数受け渡しが原因
- 今回の修正: promptをstdinへ移し、この原因候補を除去
- 未確認: stdin化で実liveが成功するか

「根本原因を特定した」「Windows長制限が原因だった」とは、live再確認前に断定しない。

## テスト要件

実Codexを呼ばず、`subprocess.run`をFakeまたはmonkeypatchして通常テストを追加する。

最低限、次を確認する。

### コマンドとstdin

1. probe呼び出しは従来どおり成功する
2. 本実行の`cmd`に`codex exec`が含まれる
3. 本実行の`cmd`にstdin指定の`-`が含まれる
4. 本実行の`cmd`に質問本文が含まれない
5. 本実行の`cmd`にClaim本文が含まれない
6. 本実行の`cmd`にEvidence本文が含まれない
7. `subprocess.run(input=...)`へ`build_phase_input()`相当の全文が渡される
8. 本実行で`stdin=subprocess.DEVNULL`が指定されない
9. `shell=False`を維持する
10. Windows分岐では`codex.cmd`を維持する

### 長い入力

11. 50,000文字以上のsyntheticなverify入力を作る
12. 長い入力全文が`input`へ渡される
13. `cmd`の長さは入力本文の長さに比例して増えない
14. 長い質問、Claim、Evidenceの識別文字列がargvへ一切入らない
15. Fake成功応答を正常にparse・validateできる

### 一時schema

16. subprocess呼び出し時点でschemaファイルが存在する
17. schemaに質問、Claim、Evidence、秘密文字列が含まれない
18. 成功後にschemaファイルが削除される
19. 非ゼロ終了や例外後にもschemaファイルが削除される

### エラー回帰

20. 非ゼロ終了は`EXECUTION_ERROR`になる
21. fixed summaryは`<phase> process exited with a non-zero status.`になる
22. stdout、stderr、prompt、秘密文字列はpublic summaryへ混入しない
23. timeout、quota、rate limit、authの既存分類を壊さない
24. INVALID_OUTPUTの既存構造診断を壊さない

テストの追加先は、既存構成に合わせて次のいずれかを使用する。

```text
tests/unit/test_adapter_error_classification.py
tests/unit/test_adapter_schema.py
```

必要ならCodex transport専用の単体テストファイルを新設してよい。

## 実行禁止事項

今回は次を実行しない。

```text
codex execによる生成呼び出し
claude -pによる生成呼び出し
WebSearch
実HTTP取得
ORACLE_COUNCIL_LIVE=1
liveテスト
expensiveテスト
q04再実行
8問フル評価
scripts/run_x8_evaluation.pyのlive実行
```

`codex --version`や`codex exec --help`も、実装とテストに不要なら実行しない。

保存済み評価結果を変更・削除・再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
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
- live / expensiveは既定設定で除外
- `git diff --check`成功
- 意図しないファイル変更なし
- prompt本文がCodex実行argvへ入らない
- 長いPhase入力がstdinへ渡される
- temp schemaのcleanupが維持される
- 既存エラー分類とsummaryを壊さない

## ドキュメント更新

`hikitsugi.md`へX-8.6として次を記録する。

- q04のverify非ゼロ終了が2回再現したこと
- promptをargvへ直接渡していた現行構造
- Windowsコマンドライン長は未確認の原因仮説であること
- Codex promptをstdinへ移したこと
- temp fileはschemaだけに限定したこと
- O-6はCodexAdapter側のみ前進し、全体完了ではないこと
- 追加した長文入力テスト
- pytest結果
- live再実行をしていないこと
- 次の作業が「ユーザー承認後のq04 1回限定再評価」であること

`FIX_PLAN.md`のO-6には、完了扱いにせず次の趣旨を追記する。

```text
CodexAdapter: promptはstdin、temp fileは非機密schemaだけに限定して実装済み。
ClaudeAdapter/CliSearchProviderを含む全体方針の完了確認は未実施。
```

SPEC変更が不要ならバージョンは上げない。

## コミットとpush

全テスト通過後、意図したsource、test、documentだけをコミットし、`origin/main`へpushする。

コミットメッセージ例:

```text
fix: pass Codex phase input through stdin
```

`instructions/result.md`も今回のコミット対象に含める。

## 結果出力

作業完了後、結果を次へ必ず出力すること。

```text
instructions/result.md
```

チャット上の報告だけで完了扱いにしない。

最低限、次を記載する。

1. 現行Codex commandの確認結果
2. stdin化した実装内容
3. 最終的な`cmd`の構造（prompt本文は記載しない）
4. `subprocess.run()`へ渡すstdin方式
5. 長文入力テストの文字数と結果
6. argvへprompt、Claim、Evidenceが入らないこと
7. temp schemaの内容境界とcleanup結果
8. 既存エラー分類の回帰結果
9. 変更ファイル一覧
10. pytest結果
11. `git diff --check`結果
12. live、q04、実CLIを実行していないこと
13. commit hash
14. push結果
15. Windowsコマンドライン長は未確認仮説であること
16. 未解決事項
17. 次の推奨作業
