# 検証マニフェスト仕様

## ルート

```json
{
  "version": 1,
  "slug": "short-experiment-name",
  "claim": "検証する技術的主張",
  "hypothesis": "条件付きで反証可能な仮説",
  "falsificationCriteria": [{"id": "criterion-main", "description": "棄却条件1"}],
  "image": {},
  "defaults": {},
  "mounts": [],
  "cases": []
}
```

- `slug`: 小文字英数字とハイフンだけを使う。
- `claim`: 元の主張を短く保つ。
- `hypothesis`: 対象、条件、期待結果を含める。
- `falsificationCriteria`: 一意なIDと説明を実行前に定義する。結果を見て変更しない。

## image

既存イメージを使う場合:

```json
{"tag": "python:3.13-slim"}
```

ローカルでビルドする場合:

```json
{
  "tag": "validation-example:20260815",
  "context": "image",
  "file": "image/Containerfile",
  "pull": false
}
```

`context` と `file` はマニフェストの親ディレクトリ配下にある、dot/`..`・絶対指定・制御文字・symlink componentを含まない相対パスにする。`context`は実ディレクトリ、`file`はそのcontext配下の通常ファイルに限定する。再現性を優先し、ベースイメージと依存バージョンを固定する。

検証ハーネスのランタイム規約は`references/runtime-conventions.md`に従う。Pythonに外部依存がある場合は`uv`、JavaScript系ではTypeScript 7、`tsx`、`pino`を使用する。対応するlockfileと設定ファイルをbuild contextへ含める。

## defaults

```json
{
  "network": "none",
  "cpus": 1,
  "memory": "2G",
  "timeoutSeconds": 120,
  "retries": 0,
  "repeats": 1,
  "maxConcurrency": 8,
  "readOnlyRoot": true,
  "allowWritableMounts": false
}
```

- `network`: 通信不要なら `none`、必要な場合だけ `default` または明示したネットワーク名を使う。
- `cpus` / `memory`: 1ケース当たりの上限。ホスト容量を超える並列度を指定しない。
- `retries`: ハーネスまたは外部依存の一時失敗を観察するための再試行回数。結果の見栄えを良くする目的で増やさない。
- `repeats`: 非決定性または性能分布を測る反復数。
- `readOnlyRoot`: 原則 `true`。一時ファイルは `/tmp`、証跡は `/evidence` を使う。
- `allowWritableMounts`: 原則 `false`。明示的に有効化した場合、root-level mountは全ケースで共有されるためランナーが全ジョブを直列化する。並列性が必要なら書き込みを各ジョブ固有の `/evidence` に限定する。

## mounts

```json
[
  {
    "source": "./fixture",
    "target": "/workspace",
    "readonly": true
  }
]
```

- `source`はmanifest配下のsymlinkでない通常ファイルまたは実ディレクトリに限定する。FIFO、socket、deviceなどの特殊ファイルは拒否する。
- 入力は読み取り専用にする。
- `/evidence` はランナーが予約するため指定しない。
- 書き込み可能マウントはケース間で共有しない。

## cases

```json
{
  "id": "timeout-negative",
  "group": "failure",
  "description": "応答が停止した場合に制限時間内で終了するか",
  "relation": "support",
  "agentCli": "claude-code-subscription",
  "criterionIds": [],
  "exclusiveGroup": "upstream-api",
  "command": ["sh", "-lc", "run-test --mode timeout > /evidence/measurement.json"],
  "env": {"MODE": "strict"},
  "inheritEnv": ["CLAUDE_CODE_OAUTH_TOKEN"],
  "network": "none",
  "cpus": 1,
  "memory": "1G",
  "timeoutSeconds": 30,
  "retries": 0,
  "repeats": 3,
  "readOnlyRoot": true,
  "oracle": {
    "exitCode": 0,
    "stdoutContains": ["timeout handled"],
    "stdoutNotContains": ["secret"],
    "stderrContains": [],
    "stderrNotContains": ["panic"],
    "artifacts": [
      {"path": "measurement.json", "exists": true, "contains": "elapsed_ms"}
    ]
  }
}
```

- `id`、`group`、`exclusiveGroup`、`criterionIds`の各ID、`slug`: 小文字英数字とハイフンだけ、先頭は英数字、80文字以内（`^[a-z0-9][a-z0-9-]{0,79}$`）。大文字やアンダースコアを含むと拒否される。`slug`以外のIDエラーは「idが不正」などと理由を示さない。
- `relation`: オラクル成立時に仮説を `support`、`falsify`、または `neutral` のどれへ動かすかを指定する。`falsify` は `criterionIds` を必須にし、宣言した各棄却条件は最低1件の有効な`relation: falsify`ケースから参照する。`support`/`neutral`からの参照だけでは運用上の反証可能性を満たさない。`falsify`では、棄却条件が実際に観察されたとき成立するオラクルを定義する。健全な対象でその観察が生じなければ、ジョブは判定済みの`oracle-fail`になる。
- `agentCli`: CLIを使う場合だけ`claude-code-subscription`または`codex-subscription`を指定する。認証方式と安全条件は`references/agent-cli-subscriptions.md`に従う。
- `criterionIds`: 検証する棄却条件IDを指定する。
- `exclusiveGroup`: 同じ共有資源を使うケースへ同じ値を付け、その群だけ直列化する。
- `command`: argv配列にする。パイプ、リダイレクト、複合コマンドが必要な場合だけ `sh -lc` を明示する。
- `env`: 公開可能な固定値だけを置く。
- `inheritEnv`: ホストから渡す環境変数名だけを置く。値はマニフェストや来歴へ書かない。Claude Code subscriptionでは`CLAUDE_CODE_OAUTH_TOKEN`、Codex workspace access tokenでは`CODEX_ACCESS_TOKEN`だけを許可し、APIキーは渡さない。1ケースでも`inheritEnv`を使うrunは値の同一性を証明できないため`--resume`できない。リダクトの範囲と限界は`references/results-and-evidence.md`の「秘密値のリダクト」を読む。
- `oracle`: 最低1項目を定義する。既定の期待終了コードは0。stdout/stderr条件は生出力をメモリ内で評価するが、結果ファイルへ生出力や秘密値を含むfailure excerptは保存しない。claim-bearing caseではpayload由来の正の証拠として、空でない`stdoutContains`または`exists: true`を明示したartifactを含める。否定条件、stderr、存在しないartifactだけではpayload起動を証明しない。markerの一意性はvalidatorで証明できないため、stderrとApple Container system logも確認する。
- `artifacts.path`: `/evidence` からの相対パスにする。絶対パス、`..`、NUL/CR/LFを含む制御文字は禁止する。`exists: false`と`contains`は併用できない。`exists: true`が成立するのはevidence root内のsymlinkでない通常ファイルだけで、ディレクトリ、FIFO、socket、deviceなどは不成立とする。`contains`もこの通常ファイルだけを読む。`exists: false`はパスの不在だけを確認する。

出力側の仕様（証跡レイアウト、実行状態と仮説評価、resume、リダクト）は`references/results-and-evidence.md`にある。
