# AGENTS.md

このリポジトリは単一のエージェントスキル `apple-container-validation` を [vercel-labs/skills](https://github.com/vercel-labs/skills)（`npx skills`）向けに配布する。

## レイアウト

- スキル本体は `skills/apple-container-validation/` に置く。`npx skills add` は `skills/` を優先して走査するため、ルート直下にスキルファイルを置かない。
- スクリプトとテストはスキルディレクトリからの相対パス（`Path(__file__)`）で解決している。ディレクトリ構成を変える場合はテストを通して確認する。

## スキル記述規則

- スキル同梱のファイル（スクリプト・テンプレート・リファレンスなど）を prose で言及する場合は **`スキル同梱の`** を前置きする。コードブロック内のコマンドには不要。

## 変更時のチェック

```bash
python3 -m unittest discover -s skills/apple-container-validation/tests -p 'test_*.py'
```

- `README.md` のパス例がリポジトリ構造と一致しているか。
