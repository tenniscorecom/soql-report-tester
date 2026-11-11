# soql-report-tester

Salesforce の SOQL レポート定義（`SoqlReport` のサブクラスを書いた `.py`）を
まとめて bulk_query で取得して、CSV に書き出す道具です。

## 準備（初回だけ）

`認証情報の登録.bat` を実行して、認証情報（client_secret など）を登録する。

## レポートを並べる

`reports/` にレポート定義（`SoqlReport` のサブクラスを1つだけ書いた `.py`）を置く。
`.py` には実データ（SOQL・列名）が入るので git には入りません。

置いた `.py` は自動で読み込まれるので、import は書かない。`src/run.py` の `KEYS` に管理番号を並べる。

```python
KEYS: list[str] = [
    "1001",  # 例（管理番号は架空の値）
]
```

`src/run.py` の `RUN_ALL` を `True` にすると、`KEYS` を無視して `reports/` にある全レポートを実行する（管理番号の昇順）。

読み込めない `.py` が 1 つでもあると、実行が止まる。

## 実行する

`python main.py` または `実行.bat` を実行する。CSV は `output/` に **クラス名.csv** で書き出され、実行のたびに上書きされる。

`REPORT_ID` があるレポートは、SOQL の件数とレポートの総件数を比べて表示する。一致しなくても CSV は書き出す。

1 つのレポートが失敗しても止まらず、残りのレポートを続けて実行し、最後に失敗した管理番号を一覧表示する。失敗したレポートの CSV は書かない。
