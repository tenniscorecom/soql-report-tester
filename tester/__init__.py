"""soql-report-tester — SoqlReport を 1 本だけ試す道具。

soql-collector が作ったレポート定義（``SoqlReport`` のサブクラスを書いた ``.py``）を、
ダウンローダーの ``reports/`` に入れる**前**に、1 本だけ実行して確かめるための道具。

- 対象は読み取り専用。Salesforce への書き込み、管理表の書き換え、
  ダウンローダーへのファイル配置はしない
- レポート本体（``SoqlReport`` / ``apply_column_names`` / 件数取得 /
  未完成の印）は **ダウンローダーのものをそのまま使う**（コピーしない）
"""
