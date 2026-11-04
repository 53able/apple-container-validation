# runnerの操作詳細

スモーク検証の前に一度読む。runnerとvalidatorの実際の挙動のうち、ケース設計・時間予算・結果確認に影響するものをまとめる。出力ファイルの仕様と判定規則はスキル同梱の`references/results-and-evidence.md`にある。

## 引数

runnerの引数は`manifest`（位置引数）、`--run-id`（必須。英数字で始まり英数字・`_.-`のみ、80文字以内）、`--concurrency`（`auto`または正の整数。いずれも`maxConcurrency`とジョブ数で頭打ち）、`--dry-run`、`--resume`、`--results-dir`（既定は**カレントディレクトリ**の`results`。レポートに実行時のcwdを書く）だけである。validatorは`manifest`と`--json`だけを取る。どちらも引数の値を出力に反映しない設計のため、`--help`や誤った引数には`invalid arguments`とだけ返す。

## コンテナの起動条件

runnerは各ジョブを`container run --rm --init --name acv-...`で起動し、`readOnlyRoot`なら`--read-only --tmpfs /tmp`を付け、ジョブ固有の`/evidence`を書き込み可能でマウントする。`--init`によりハーネスはPID 1にならず、`--rm`により正常終了したコンテナは残らない（タイムアウト時はrunnerが名前を指定して`container delete --force`する）。コンテナ名は`acv-`＋results pathの先頭＋hashで、results pathが長いとrun-idは名前に現れない。自分のジョブのコンテナ名は`result.json`の`command`で確かめる。

コンテナ起動にはジョブごとに10〜30秒かかることがあり、`durationSeconds`と`timeoutSeconds`はこれを含む。`timeoutSeconds`には起動分の余裕を持たせ、payload自体の時間はハーネス内で測ってartifactに書く。プロセス木、シグナル、ゾンビ回収、ファイルシステム書き込みを扱う検証では、`--init`（ハーネスはPID 1にならない）と`--read-only`の条件を仮説の前提としてレポートに書く。

## 起動失敗の手作業確認

`launcherOriginVerification`が`NOT VERIFIED BY RUNNER`のとき、claim-bearing caseについて次を確認し、確認した範囲をレポートに書く。

1. payload markerまたは`exists: true`のartifactが実際に出ている。
2. stderrに起動・設定エラーがない。`[1/6] Fetching image`のようなApple Containerの進捗行は正常。
3. 実行直後に`container system logs --last 10m`（1.2.2で確認。構文は`container system logs --help`を正とする）を取り、該当時間帯に起動失敗がない。コンテナは`--rm`で消えるので、後からは取れない。
   - ログには他セッションの行も混ざる。`result.json`の`command`にあるコンテナ名と実行時間帯で絞る。
   - 実行前の時間帯にも出ている`xpc ... Connection invalid`や`ImagesHelper`の接続エラーは背景ノイズとして扱ってよい。
   - 保存したログはrun rootに置けない（runnerが未知のファイルを拒否する）ので、利用者向けレポートの隣に置く。
