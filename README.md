# Oracle Council

Oracle Council は、複数のAI CLIと外部Evidenceを使って回答を検証する、実験的な監査可能CLIです。

複数Agentに独立回答させ、検証可能なClaimを抽出し、外部Evidenceを収集し、Claimを検証し、統合回答を作り、最後に別Agentで監査してから公開します。通常開発では外部AIやネットワークを使わないFake modeを使い、明示した場合だけClaude Code、Codex CLI、Claude Code WebSearch、HTTP取得を使う実経路を通します。

## 現在の到達点

MVPとして次の縦断動作まで確認済みです。

- 実Claude + 実Codex + 実Web EvidenceのE2Eが完走済み
- `CliSearchProvider`を`oracle ask --evidence-provider cli-search`で明示選択可能
- `WebEvidenceProvider.collect()`はPhase 0互換経路として接続済み
- JSON出力にsanitized Evidence概要を表示
- `evidence_collect`で所要時間、検索/fetch件数、outcome、エラーコード別metricsを記録
- 非ASCII Evidence URL/IRIをHTTP取得前に正規化
- Adapterの`INVALID_OUTPUT`は固定形式allowlistの安全な構造診断だけを外部JSONへ出力
- 誤前提Claimと回答Claimを`claim_role`で分離
- X-8固定評価セットと安全ガード付きrunnerを用意

まだMVPです。完全なSPEC §10.2 Evidence収集エンジン、反証検索、authority分類、Viewer対応、大規模な自動評価は未実装です。

## 必要環境

- Python 3.11以上
- Windowsでは`py` launcherを使用
- 開発依存は`.[dev]`

初回セットアップ:

```powershell
py -m pip install -e ".[dev]"
```

通常テスト:

```powershell
py -m pytest
```

pytest設定では、既定で`live`マーカー付きテストを除外します。

## 基本実行

Fake modeは決定的で、外部AIやネットワークを起動しません。

```powershell
py -m oracle_council.cli ask "富士山の標高は何メートルですか？" `
  --adapter-mode fake `
  --json `
  --no-store
```

手動Evidenceは`--evidence-file`で指定できます。`--evidence-file`も`--evidence-provider`も省略した場合は、後方互換のため`FakeEvidenceProvider`を使います。

**注意（X-9）**: `FakeEvidenceProvider`は固定の1件（実質空）のEvidenceしか返さず、実Web検索は一切行いません。事実確認が必要なcritical/majorのClaimは、根拠不足でほぼ確実に`unverified`となり、回答が保留（`withheld`、exit 4）になりやすくなります。`--adapter-mode real`で実Agentを使い、かつEvidence Providerを省略した場合はstderrへ警告を表示します（`--json`指定時は表示しません。stdoutのJSONを汚さないためです）。プログラムから検知するには、`phases[].metrics.provider_type`（`fake` / `manual` / `cli_search`）と`phases[].metrics.real_search_performed`（真偽値）を見てください。`search_count`や`fetch_attempt_count`が0でも`Phase.status`は「収集処理として正常終了した」ことしか意味せず、「実検索で何も見つからなかった」わけではない点に注意してください（この区別は`real_search_performed`が担います）。

## 実験的Web Evidence

Web Evidence経路は明示指定時だけ有効です。

```powershell
py -m oracle_council.cli ask "富士山の標高は何メートルですか？" `
  --adapter-mode fake `
  --evidence-provider cli-search `
  --json `
  --no-store
```

`cli-search`指定時は次を構築します。

```python
WebEvidenceProvider(
    fetcher=SafeHttpFetcher(),
    searcher=CliSearchProvider(),
)
```

この経路はClaude Code WebSearchと外部HTTP取得を実行し得ます。通常のunit testでは使わず、subprocessとHTTP取得をFakeまたはMockに差し替えてください。

## 実Agent実行

本番構成の実行は外部AI利用枠とネットワークを消費します。

```powershell
py -m oracle_council.cli ask "富士山の標高は何メートルですか？" `
  --adapter-mode real `
  --evidence-provider cli-search `
  --json `
  --no-store
```

live確認として明示された場合だけ実行してください。失敗時も、実行した事実を記録せずに再試行しないでください。

## JSON出力の境界

トップレベル`evidence`に出すのは、次のsanitized概要だけです。

- `evidence_id`
- `claim_id`
- `url`
- `title`
- `source`
- `rank`
- `content_type`
- `retrieved_at`
- `excerpt`

Evidence本文全体、prompt、生stdout/stderr、headers、cookies、tokens、環境変数、diagnostics、未知キーは出力しません。

`phases[].metrics`は、件数カウンターとエラーコード別件数だけを保持します。URL、検索クエリ、excerpt、title、生例外本文はmetricsに入れません。`evidence_collect`のmetricsには`provider_type`（`fake`/`manual`/`cli_search`）と`real_search_performed`（真偽値）も含まれます。

## Claimの性質（claim_nature、X-9）

Claimは`importance`（critical/major/minor）、`status`（verified/supported/contradicted/conflicting/unverified/not_applicable）に加え、`claim_nature`（factual/reasoning/opinion/normative/hedge/structural）を持ちます。`claim_nature`が未設定の場合は`factual`扱いです（既存データ・既存Adapter出力との後方互換）。

意見・価値判断・留保表現・回答構成上の補助的表現（opinion/normative/hedge/structural）は、SPEC §10.5が定義する`not_applicable`（事実検証の対象外）に該当します。verify Phaseはこれらを`not_applicable`とするよう指示されますが、AIがなお`unverified`を返した場合はOrchestratorが決定的に`not_applicable`へ正規化します（`contradicted`/`conflicting`は正規化しません。より具体的な指摘とみなし、既存の判定規則をそのまま適用します）。これにより、事実確認の対象外である価値判断的なClaimだけを理由に、回答全体が不必要に保留（withheld）になることを防ぎます。critical/majorな**事実**Claimが未検証の場合に安全側（withheld）へ倒す既存の挙動は変更していません。

## 各Phaseの生出力を確認する（--trace、X-9）

通常実行では、各AIの生の応答（raw response）はCLI JSON・保存・履歴表示のいずれにも出力されません（SPEC §11.5 / §15.8）。デバッグ目的で明示的に確認したい場合は次を使います。

```powershell
py -m oracle_council.cli ask "質問" --adapter-mode fake --no-store --trace
py -m oracle_council.cli ask "質問" --adapter-mode fake --no-store --trace-output trace.json
```

- `--trace`: 各Phase・各Agentの生出力（best-effort redaction適用済み）をstderrへ表示します。
- `--trace-output PATH`: 同内容をJSONファイルへ書き込みます（`--trace`と併用時はstderrにも表示します）。
- どちらも`data/`配下のStorage Contract（`--store-content` / `--no-store`）とは完全に独立しています。trace出力はメモリ上に保持されるだけで、明示的に`--trace-output`を指定しない限りディスクへは書き込みません。
- redactionはbest-effortです（APIキー・Bearerトークン・ホームディレクトリパスらしき文字列などをパターンで除去します）。完全性は保証しないため、機密情報を含み得る環境でtrace出力を共有する際は内容を確認してください。

## X-8固定評価runner

固定評価セットは次にあります。

```text
evaluation/x8/eval-set-v1.json
```

dry-run例:

```powershell
py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir C:\PROJECT\OracleCouncil-evals\x8\<HEAD> `
  --expected-head <HEAD> `
  --all `
  --dry-run
```

live評価結果はリポジトリ外に保存します。慣例は次です。

```text
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>\
```

各質問は、同一output directory内で1回だけ実行できます。runnerは外部コマンド起動直前に`attempted.json`を書きます。失敗、不正JSON、timeoutでもattemptedを削除せず、同じ質問を再実行しないでください。生成された評価結果をGitへ追加しないでください。

## 開発メモ

- このWindows環境では`python`ではなく`py`を使います。
- Storage形式の変更は明示的にレビューしてください。
- 明示依頼がない限り、`claude`、`codex`、WebSearch、live/expensive testは実行しません。
- 保存済みX-8評価結果は基準値として扱い、編集しません。
- commit対象は、意図したsource、test、document変更だけに限定します。
