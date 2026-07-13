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

`phases[].metrics`は、件数カウンターとエラーコード別件数だけを保持します。URL、検索クエリ、excerpt、title、生例外本文はmetricsに入れません。

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
