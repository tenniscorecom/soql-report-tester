# soql-report-tester

soql-collector が作ったレポート定義（`SoqlReport` のサブクラスを書いた `.py`）を、
**ダウンローダーの `reports/` に入れる前に 1 本だけ実行して確かめる**ための道具です。

- 管理表の「SOQL」列もスケジュールも通らない（その行を動かさずに済む）
- 読み取り専用。Salesforce への書き込み・管理表の書き換え・ダウンローダーへの
  ファイル配置は **しない**
- 画面に出るのは「件数・列名・出力先」だけ。**レポートの中身（行の値）は出さない**

comken（社内共通ライブラリ）を使った業務自動化ツールです。

---

## ドキュメント（読む人で分かれています）

| 読む人 | ファイル |
|---|---|
| 実行する人（毎日使う） | [docs/使い方.md](docs/使い方.md) |
| 保守する人（中身を直す） | [docs/仕様書.md](docs/仕様書.md) |
| エラーが出た人 | [docs/ERRORS.md](docs/ERRORS.md) |

---

## セットアップ（初回だけ）

1. `実行.bat` を1度動かす（または `python main.py`）。`config.ini.example` から `config.ini` が作られるので、値を書き換える

`config.ini` の `[FILES]` に4つ書く（全部必須・既定値なし）。

| キー | 意味 | 既定の例 |
|---|---|---|
| `DOWNLOADER_ROOT` | ダウンローダーのフォルダ（`src` の親） | `../Salesforceレポートダウンローダー` |
| `REPORTS_DIR` | 試すレポート定義（`.py`）を置くフォルダ | `./reports` |
| `MASTER_XLSX_PATH` | レポート管理表（Excel） | `./input/レポート管理表.xlsx` |
| `OUTPUT_DIR` | 試した CSV の書き出し先 | `./output` |

comken の場所（`PYTHON_LIBRARY`）は作成時に入っているので、通常は触らなくてよい。
comken を別の場所へ移したときだけ、`実行.bat` と `.vscode/settings.json` の**2つ**を直す
（前者は実行用、後者は VS Code の補完・定義ジャンプ用。片方だけ直すと、動くのに補完が効かなくなる）。

---

## 実行

```
python main.py 1001                 # REPORTS_DIR から KEY=1001 を探す。URL は管理表から
python main.py 1001 --url <URL>     # URL を直接指定
python main.py path\to\report_1001.py --url <URL>
python main.py --list               # 一覧を表示する（つながらない）
python main.py 1001 --show          # SOQL 本文を表示するだけ（つながらない）
```

終了コードは **0=成功 / 1=失敗・未完成・件数不一致 / 2=使い方の誤り**。

`実行.bat` に続けて引数を渡しても同じ動きです（`実行.bat 1001`）。

実行例（管理番号・URL・列名はすべて架空の値）。

```
> python main.py 1001
クラス名: SampleReport
SOQL 件数: 3
レポート件数: 3
判定: 一致
列数: 2
列名: Id, SampleName
出力先: F:\dev\soql-report-tester\output\1001_20261102_101530.csv
```

---

## レポート定義を 1 本試す

1. soql-collector が出した `.py` を `reports/` に置く（ファイル名は `reports/` の中で
   重複しないこと。管理番号 `KEY` も重複させてはいけない）
2. `python main.py --list` で、その `.py` が読み込まれているか・未完成かを確認する
3. `python main.py <管理番号> --show` で SOQL の中身を目で確かめる
4. `python main.py <管理番号>` で実行する（CSV が `output/` に出る）

`.py` の書き方はダウンローダーの雛形
（`src/soql_reports/reports/_template.py`）と同じ。`SoqlReport` のサブクラスを
**1 ファイルに 1 つだけ**書く。

```python
from src.soql_reports.base import SoqlReport


class SampleReport(SoqlReport):
    """説明を書く。"""

    KEY = "1001"  # 社内で決める管理番号
    COLUMN_NAMES = {"SampleName": "サンプル名"}

    def soql(self) -> str:
        """実行する SOQL を返す。"""
        return "SELECT Id, SampleName FROM Sample__c"
```

---

## Python のコードから呼ぶ

コマンド（`main.py`）ではなく、**Python のコードの中から**レポートを実行できます。
管理表（Excel）も `config.ini` の接続設定も通しません。接続は呼び出し側が
comken の組織クラスで開きます。

```python
from comken.toolbox.salesforce.sites import SolutionSandbox
from reports import *
from tester import to_csv

report_1001                  # reports/report_1001.py（モジュール）
report_1001.Report1001       # クラスそのもの

with SolutionSandbox() as sf:
    to_csv(report_1001, sf)              # SOQL 実行・件数比較・CSV 出力
    to_csv(report_1002.Report1002, sf)   # クラスで。同じ接続のまま続けられる
```

- `to_csv()` は **接続を開かないし閉じない**（渡された接続を使うだけ）
- 件数を比較するのは、レポート定義に `REPORT_ID` があるときだけです
  （無いときは「比較せず」＝判定は「比較できず」）

  ```python
  class Report1001(SoqlReport):
      KEY = "1001"
      REPORT_ID = "00O000000000001AAA"   # Salesforce のレポート ID
  ```

- CSV の書き出し先は `config.ini` の `[FILES] OUTPUT_DIR`（管理表は不要）
- 画面に出るものは件数・列名・出力先だけ（行の値は出さない）

**スクリプトはこのリポジトリの直下に置いて実行する**（`python 試す.py`）。
`reports` パッケージと `tester` が見つかるのは、スクリプトのあるフォルダが
`sys.path` に入るため。

---

## ダウンローダーへ移す手順

確認が済んだら、**この道具では何も置かない**。次の2つを**手作業で**行います。

1. 試した `.py` をダウンローダーの `src/soql_reports/reports/` へコピーする
   （ファイル名が `_` で始まらないこと。始まると自動登録の対象外になる）
2. レポート管理表の、その管理番号の行の **「SOQL」列を「○」** にする
   （先にこれをすると、ダウンロードの定期実行が SOQL 経由に切り替わる）

これを守れば、ダウンローダーは自動でそのレポートを SOQL で取得する
（`src/soql_reports` は置いたファイルを走査して登録するため、明示的な一覧の
書き換えは不要）。

**「SOQL」列を「○」にするのは、上の2つを両方済ませてからにする。**
先に「○」にすると、定期実行が動かない SOQL を取得しに行く。

---

## エラー一覧を更新する

`tester/` にエラー（`ComkenError` のサブクラス）を足したり、その docstring を直したりしたら、
`エラー一覧の更新.bat` を叩く（または `python update_errors.py`）。
`docs/ERRORS.md` の自動生成部分（プロジェクト固有のエラーと comken のエラーの表）が作り直される。
comken を新しくしたときも、comken のエラーの説明を合わせるために叩く。
