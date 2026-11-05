<img src="assets/icon.svg" width="64" height="64" alt="">

# apple-container-validation

Apple Container 上に再現可能な技術検証環境を構築し、コンテキストから論点・反証条件・オラクル・ケース行列を定義して、独立ケースを安全な上限内で並列実行し、ログと来歴を伴う Markdown レポートへ集約するエージェントスキル。

[vercel-labs/skills](https://github.com/vercel-labs/skills) CLI（`npx skills`）に対応する。

## 仕組み

![仮説と棄却条件を結果より先に固定し、各ケースに support・falsify・neutral を割り当て、Apple Container でジョブごとに隔離して並列実行し、仮説を FALSIFIED・SUPPORTED・UNVERIFIED などに評価して、ログと来歴付きの Markdown レポートにまとめる。](docs/how-it-works.png)

仮説評価は、ジョブの結果を上の行から順に照合して決まる。前提条件を含む規則の全体は `skills/apple-container-validation/SKILL.md` の手順7にある。

![falsify ケースに oracle-pass が1件でもあれば FALSIFIED。support が全件 pass で falsify が全件 fail なら SUPPORTED WITHIN TESTED SCOPE。falsify が全件 fail で support は一部だけ pass なら PARTIALLY SUPPORTED WITHIN TESTED SCOPE。それ以外は timeout や欠損を含めて UNVERIFIED。neutral ケースは判定に入らない。](docs/claim-outcome.png)

実行時は次の順で成果物ができる。信頼する結果は `summary.json` と世代別 report の組である。

![manifest.json を run-matrix.py が検証してジョブを起動し、Apple Container がジョブごとに隔離して実行する。各ジョブの判定とログは result.json に記録され、summary.json と世代別 report に集約される。この2つが SHA-256 で結ばれた権威ある結果で、利用者向けレポートはそのパスと SHA-256 を引用する。](docs/execution-artifacts.png)

## 由来

[53able/skills](https://github.com/53able/skills) の `skills/apple-container-validation`（コミット `f17a12d` 時点）を、該当パスのコミット履歴を保持したまま切り出したもの。

## 要件

- Apple silicon Mac / macOS 26 以降
- Apple Container CLI
- Python 3.10 以上
- 依存のある Python ハーネスでは uv、TypeScript ハーネスでは Node.js・npm・TypeScript 7・tsx・pino

## 構成

```
skills/apple-container-validation/
├── SKILL.md        # スキル本体
├── references/     # コマンド・マニフェスト仕様・ケース設計・実行規約
├── assets/         # マニフェスト/レポートのテンプレート、agent-cli 用 Containerfile
├── scripts/        # validate-manifest.py, run-matrix.py
├── tests/          # 標準ライブラリのみのユニットテスト
└── evals/          # skill-creator / claude plugin eval 形式の実機評価ケース
```

## インストール

```bash
npx skills add 53able/apple-container-validation -g
```

`-g` はユーザー単位（全プロジェクト共通）でインストールする。特定のプロジェクトだけで使う場合は、そのプロジェクトのルートで `-g` を付けずに実行する。

スキルを開発・変更する場合は、クローンしたリポジトリのルートから入れる。

```bash
git clone https://github.com/53able/apple-container-validation.git
cd apple-container-validation
npx skills add ./ -g
```

## テスト

リポジトリルートで実行する。Apple Container は起動しない。

```bash
python3 -m unittest discover -s skills/apple-container-validation/tests -p 'test_*.py'
```

## ライセンス

MIT（[LICENSE](LICENSE)）。
