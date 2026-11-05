---
name: apple-container-validation
description: Apple Container上に再現可能な技術検証環境を構築し、コンテキストから論点・反証条件・オラクル・ケース行列を定義して、独立ケースを安全な上限内で並列実行し、ログと来歴を伴うMarkdownレポートへ集約する。Use when macOS上で実装、設定、互換性、性能、障害系、エージェント挙動などの技術的主張を隔離環境で実測するとき。Don’t use for Apple Containerを利用できない環境、iOS/macOS GUI自動化、GPU学習、法務判断、または実行を伴わない机上レビュー。
compatibility: Requires an Apple silicon Mac running macOS 26 or later, Apple Container CLI, and Python 3.10 or later. Python harnesses with dependencies also require uv; TypeScript harnesses require Node.js, npm, TypeScript 7, tsx, and pino.
---

# Apple Container技術検証

コンテキスト中の技術的主張を、反証可能なケース行列へ変換する。各ケースをApple Containerで隔離して並列実行し、観察・推論・未検証事項を分けた再実行可能なMarkdownレポートを1つ残す。

このスキルの価値は「通った」ことではなく「何が確かめられ、何が確かめられていないか」を正確に残すことにある。都合の良い結果だけを集めた検証は、検証しないより有害になる。手順の多くはこの一点を守るためにある。

以下、`<skill-dir>`はこのSKILL.mdがあるディレクトリを指す。スキル同梱のスクリプトとテンプレートはこのパスで参照する。

## 参照ファイルの読み分け

| ファイル | 読むとき |
|---|---|
| スキル同梱の`references/case-design.md` | ケース行列を設計するとき（毎回） |
| スキル同梱の`references/manifest-spec.md` | `manifest.json`を書くとき（毎回） |
| スキル同梱の`references/runner-operations.md` | スモーク検証の前（runnerの引数、自動付与フラグ、時間予算、起動失敗の確認手順） |
| スキル同梱の`references/results-and-evidence.md` | 結果を判定・報告するとき、`--resume`や`inheritEnv`を使うとき、CIでgateするとき |
| スキル同梱の`references/runtime-conventions.md` | Python/TypeScriptで検証ハーネスを書くとき |
| スキル同梱の`references/agent-cli-subscriptions.md` | Claude Code CLIまたはCodex CLIをコンテナ内で使うとき |
| スキル同梱の`references/apple-container-commands.md` | `container`の構文が不明なとき（その後ローカルの`--help`を正とする） |

## 手順

### 1. 検証対象を固定する

結果を見る前に判定基準を決める。後から基準を動かすと、どんな結果も「支持」に読めてしまうためである。

1. 主張、対象実装、比較対象、前提条件、想定利用者を抽出し、主張を1文の条件付き仮説にする。
2. 仮説を棄却する条件を列挙し、一意なIDを付ける。
3. 各合否判定・定量値に最小オラクルを定義する。オラクルを定義できない論点は「観察的」「未検証」「環境外」に分類し、推測値を合格条件にしない。
4. 各ケースのオラクル成立が仮説に対して`support`・`falsify`・`neutral`のどれを意味するかを事前に固定する。オラクル成立は「期待観察との一致」であって仮説支持とは限らない。
5. 対象のリポジトリ、コミット、作業ツリーの汚れと差分の有無、依存バージョン、ホスト情報を記録する。

### 2. Apple Containerを事前確認する

1. `container --version`と`container system status`を実行する。
2. サービス停止時は、利用者の許可を得てから`container system start`を実行する。`status`自体が失敗した場合は、その出力全文と`container --help`で確かめた内容をレポートに残す。
3. 使うイメージは事前に`container image pull --platform linux/arm64 <image>`で取得する。1.2.2で`--platform`なしのpullが失敗し、既存イメージが一覧から消えた観察がある。
4. CLIが無い、または起動できない場合はインストールも実験の捏造もしない。レポートを`Preflight/report disposition: BLOCKED`、`Claim outcome: UNVERIFIED`、`Execution status: not emitted (runner not invoked)`で、手順8の要領（スキル同梱のレポートテンプレートと保存先）に沿って保存して止める。利用者の判断で実行しない場合は`BLOCKED`の代わりに`NOT RUN`を使う。`executionStatus`の値（`COMPLETE`/`INCOMPLETE`/`DRY RUN`）はランナーだけが出すもので、手で作らない。

### 3. ケース行列とマニフェストを作る

1. スキル同梱の`<skill-dir>/assets/manifest-template.json`を検証ワークスペースへコピーし、スキル同梱の`references/case-design.md`とスキル同梱の`references/manifest-spec.md`に沿って`manifest.json`を書く。
2. 少なくとも次の群を含める: 仮説が成立する代表ケース、成立しない負例、境界値・欠損値、失敗・タイムアウト・部分成功、バージョン/設定/資源の差、見かけは似ているが対象外のケース。
3. 宣言した棄却条件は、それぞれ最低1件の`relation: falsify`ケースから`criterionIds`で参照する。`support`/`neutral`からの参照だけでは、反証が起こり得ない検証になる。
4. ケース数を水増ししない。新しい失敗モードか交互作用を覆うケースだけを足す。非決定性が疑われるケースだけ`repeats`を増やす。
5. claim-bearing case（`relation`が`support`または`falsify`のケース）には、payloadだけが生成するstdout markerか`exists: true`のartifactをオラクルに含める。Apple Containerは起動失敗とpayloadの非ゼロ終了を区別して返さないため、終了コードだけでは「対象が動いて失敗した」のか「起動できなかった」のかを判別できない。
6. 前提条件もオラクルで確かめる。例えば「SIGTERMを無視するプロセス」を前提にするなら、ハーネスが前提成立を示すmarker（`TERM_IGNORED=yes`など）を出し、support/falsifyのオラクルに含める。前提が崩れたハーネスの結果が、そのまま主張の証拠として数えられるのを防ぐためである。
7. 1つの観察で複数の棄却条件を判定できるなら、ケースを複製せず1件の`falsify`ケースの`criterionIds`へ複数のIDを並べる。支持側と反証側で同じ観察を読む場合は、1つのハーネスが複数のmarkerを出し、ケースごとに引数や条件を変える（validatorは同一コマンドの複製を警告する）。「XはYしない」型の主張では、Yが起きたときに成立するオラクルを`falsify`ケースに置く。
   事前登録した仮説の範囲外で見つかった反例（例: 既定シグナル前提の主張に対する`-s KILL`）は、仮説を後から書き換えずに`neutral`ケースとして記録し、レポートの限界・追加観察に書く。
8. マニフェストはイメージを1つしか持てない。バージョンやイメージの比較は、同じケース集合のマニフェストをイメージごとに作り（生成スクリプトで書き出すと差分が混入しない）、別々のrun-idで実行する。全体の結論は、主張が全バージョンについてのものなら、1つでも`FALSIFIED`があれば反証、全runが`SUPPORTED WITHIN TESTED SCOPE`のときだけ支持とし、run別の結果を表で並べる。
9. 隔離を既定にする。通信不要なら`network: "none"`、入力は読み取り専用マウント、書き込み先は各ケース固有の`/evidence`だけにする。外部通信・秘密情報・書き込みマウントは必要なケースだけ明示する。
10. ハーネスを書く場合はスキル同梱の`references/runtime-conventions.md`に従う（Python依存は`uv`でロック、JS系はTypeScript 7 + `tsx` + `pino`）。
11. Claude Code/Codex CLIを使う場合はスキル同梱の`references/agent-cli-subscriptions.md`に従う。認証はsubscription（`CLAUDE_CODE_OAUTH_TOKEN`、ChatGPT認証または`CODEX_ACCESS_TOKEN`）に限り、APIキーを渡さない。ログインはホスト上で人間が行い、認証情報をイメージ・manifest・Git・ログ・成果物へ残さない。

### 4. マニフェストを検証する

```bash
python3 <skill-dir>/scripts/validate-manifest.py path/to/manifest.json
```

終了コード0になるまで修正して再実行する。検証を迂回しない。出力されたジョブ数、ケース群、反復数、推奨並列数を確認する。警告のうち同一コマンドの複製は、手順3-7の設計で解消する。エラーはtext modeではstderr、`--json`ではstdoutの`errors`に出る。

### 5. スモーク検証をする

壊れたハーネスを大量並列すると、大量の無意味な失敗と後片付けだけが残る。本実行の前に小さく通す。始める前にスキル同梱の`references/runner-operations.md`を一度読む（`--results-dir`の既定はcwd、`--help`は使えない）。

1. 代表ケース、負例、失敗系を各1件以上選んだ一時マニフェストを作る。抜き出したfalsifyケースが参照しない棄却条件は`falsificationCriteria`からも外す（外さないとvalidatorが未接続としてエラーにする）。ジョブ数やケース群が少ない警告はスモークでは無視してよい。スモークは`--results-dir results-smoke`など本実行と別の場所に出す。スモーク後にハーネスを直した場合は、入力hashが変わったことをレポートに書く。
2. ハーネスを`container run`で直接試すより、最初からrunnerの`--dry-run`で生成コマンドとマウントを確認し、続けてrunnerで実行する。runnerが付けるフラグ込みで試さないと、本実行で挙動が変わる。
3. 実行し、入力、出力、タイムアウト、終了コード、オラクル判定を確認する。ハーネス不良はここで直す。

### 6. 行列を並列実行する

```bash
python3 <skill-dir>/scripts/run-matrix.py path/to/manifest.json \
  --run-id YYYYMMDD-hhmmss \
  --concurrency auto
```

- 並列度は「可能な限り大きく」ではなく「証拠の独立性を壊さない範囲で最大」にする。`auto`はジョブ数、`maxConcurrency`、論理CPU数÷ケースの最大`cpus`だけを見るので、メモリ、APIレート制限、外部サービス制約が厳しい場合は`maxConcurrency`を下げる。
- 同じ外部API、固定ポート、書き込み先、レート制限を共有するケースには同じ`exclusiveGroup`を付け、その群だけ直列化する。
- 秘密値はイメージへ焼き込まず、`inheritEnv`で変数名だけ渡す。ランナーは保存物から完全一致値を除去するが、エンコード・分割された値は検出できない（詳細と限界はスキル同梱の`references/results-and-evidence.md`）。
- 中断後の再開:
  - `inheritEnv`を1件でも使うrunは`--resume`できない。値を来歴に残さないので同一性を証明できないためである。新しいrun-idで再実行する。
  - それ以外は、マニフェストとイメージが同一であることを確認して`--resume`を使う。拒否された場合の扱いはスキル同梱の`references/results-and-evidence.md`の「証跡レイアウト」にある。部分状態は削除・上書きしない。
- 残ったコンテナは名前を指定して削除する。`container delete --all`は使わない。
- 失敗ケースを削除しない。タイムアウトの再試行はattemptごとに証跡が分かれ、初回失敗も残る。オラクル不成立を都合よく再試行しない。ディスク・メモリ不足やレート制限で崩れたら並列度を下げて新しいrun-idで再実行し、失敗runは残す。

### 7. 結果を判定する

先にスキル同梱の`references/results-and-evidence.md`の「実行状態と仮説評価」を読む。要点は次のとおり。

- **実行状態と仮説評価は別の軸である。** `executionStatus`は「全ジョブを判定し終えたか」（`COMPLETE`/`INCOMPLETE`/`DRY RUN`）、`claimOutcome`は「判定済み証拠が仮説をどう動かすか」を示す。`COMPLETE`は全オラクル成立を意味しないし、`INCOMPLETE`でも判定済みの証拠は捨てない。
- **`claimOutcome`の優先順:**
  1. 一意な`falsify`ジョブの`oracle-pass`が1件でもあれば、他の欠損に関係なく`FALSIFIED`。
  2. `support`ジョブが1件以上あり、全`support`ジョブが一意に`oracle-pass`、全`falsify`ジョブが判定済み`oracle-fail`、重複・期待外・匿名結果なし、の全条件を満たすときだけ`SUPPORTED WITHIN TESTED SCOPE`。
  3. それ以外（`support`/`falsify`の欠損・timeout・基盤エラー、`support`の`oracle-fail`、支持証拠なし）は`UNVERIFIED`。`falsify`のtimeoutを「反証なし」と読み替えない。
  - `neutral`は仮説評価を直接動かさない。その欠損・未判定は支持を消さないが、重複は証拠整合性の異常として支持を止める。
- **自動判定は暫定である。** `launcherOriginVerification`が`NOT VERIFIED BY RUNNER`のとき`claimOutcome`は暫定で、CIはこれ単独で主張の真偽をgateしない。claim-bearing caseについて、payload markerがstdoutにあること、stderrに起動・設定エラーがないこと、実行直後のApple Container system logに該当時間帯の起動失敗がないことを確認し、確認した範囲をレポートに書く。確認手順とノイズの見分け方はスキル同梱の`references/runner-operations.md`の「起動失敗の手作業確認」にある。
- 秘密値の漏えいは、`stdoutNotContains`/`stderrNotContains`の否定条件で検出できる（判定はリダクト前の生出力に対して行われる）。
- イメージのdigestは`results/<run-id>/image-inspect.json`から取る（`run-manifest.json`の`image`はタグだけ）。
- 読むもの: `results/<run-id>/summary.json`、その`reportArtifact.path`が指す世代別report、各ジョブの`result.json`と`attempts/<n>/`のログ・evidence。`report.md`は更新失敗時に古い可能性がある写しなので、権威は`summary.json`とSHA-256で結ばれた世代別reportにある。
- 少なくとも合格1件、不合格または棄却1件、境界1件を、入力・コマンド・stdout/stderr・生成物・`result.json`の判定まで手作業で照合する。予想より整いすぎた結果ほど、入力ハッシュと負例を疑って再確認する。
- タイムアウト、コンテナ起動失敗、オラクル不備を、対象実装の失敗と区別する。
- 性能比較ではウォームアップ、反復、中央値とばらつき、ホスト負荷、並列干渉を確認し、単発値を一般化しない。

### 8. Markdownレポートを仕上げる

1. 利用者向けレポートはスキル同梱の`<skill-dir>/assets/report-template.md`から新しく書き、利用者が指定した場所（未指定なら`outputs/apple-container-validation-<slug>.md`）へ置く。runnerのreportはMarkdown記号を文字参照に置き換えた機械安全な証拠であり、人が読む文書の土台には向かない。利用者向けレポートには、根拠とした世代別reportのパスとSHA-256を記載する。run root内のreportは編集しない。
2. テンプレートの全節を埋める。
3. 実測していない値を書かない。`READY`はpreflightを通過してランナーがレポートを出したことだけを示し、`INCOMPLETE`と両立する。テンプレートに無いenum値を作らない。
4. 最後にファイルを再読し、参照した成果物が存在すること、仮値やTODOが残っていないことを確認する。

## 止めるべき状況

- Claude CodeまたはCodexでAPIキー認証が検出された: subscription検証として扱えないので実行を止める。
- Codexの書き込み可能`auth.json`方式: 認証キャッシュを並列ケースで共有せず、`--resume`も使わない。
