"""KEYS に並べたレポート（RUN_ALL なら全部）を取得して、件数を比べ、CSV に書き出す。"""

import traceback
from pathlib import Path

from comken.core.encoding import UTF8_SIG
from comken.core.table.model import Table
from comken.toolbox.csv import CSV
from comken.toolbox.salesforce.client import SalesforceBase
from comken.toolbox.salesforce.sites import SolutionSandbox

from reports import REPORTS_BY_KEY
from src.soql_reports.base import SoqlReport

# True にすると KEYS を無視して、reports/ にある全レポートを実行する
RUN_ALL: bool = False

KEYS: list[str] = [
    # "1001",
]

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _select_reports() -> list[type[SoqlReport]]:
    """実行するレポートのクラスを選ぶ。RUN_ALL なら全部、なければ KEYS の順。"""
    if RUN_ALL:
        # 管理番号は数値順で実行する
        return [REPORTS_BY_KEY[key] for key in sorted(REPORTS_BY_KEY, key=_report_sort_key)]
    # 番号を書き間違えたときに、Salesforce へ接続する前に止める
    return [REPORTS_BY_KEY[key] for key in KEYS]


def _report_sort_key(key: str) -> tuple[int, int, str]:
    """管理番号を数値順に並べるためのキーを返す。数字以外は後ろに回して文字列順で並べる。"""
    # isdecimal() なら int に変換できるので、"²" のような数字扱いではない文字で止まらない
    if key.isdecimal():
        return (0, int(key), "")
    return (1, 0, key)


def main() -> None:
    """選んだレポートを順に取得して、件数を表示し、CSV に書き出す。

    1 つのレポートが失敗しても止めず、残りも続けて実行する。
    """
    reports = _select_reports()
    if not reports:
        print("実行するレポートがないため、Salesforce には接続しません。")
        return
    failed_keys: list[str] = []
    with SolutionSandbox() as sf:
        for report in reports:
            try:
                _run_report(sf, report)
            except Exception as exc:
                traceback.print_exc()
                print(f"{report.__name__}: 失敗 → {type(exc).__name__}: {exc}")
                failed_keys.append(report.KEY)
                _remove_stale_csv(report)
    if failed_keys:
        print(f"失敗 {len(failed_keys)} 件: {', '.join(failed_keys)}")


def _run_report(sf: SalesforceBase, report: type[SoqlReport]) -> None:
    """レポート 1 件を取得して、件数を表示し、CSV に書き出す。"""
    instance = report()
    soql = instance.soql()
    # 取り方はレポートごとの USE_BULK で選ぶ（False なら REST の query() になる）
    if report.USE_BULK:
        table = sf.bulk_query(soql)
        method = "Bulk"
    else:
        table = sf.query(soql)
        method = "REST"
    # 件数の比較は加工前の件数で行う（レポートの総件数と比べられるのは加工前の件数のため）
    soql_count = len(table)
    comparison = _compare_count(sf, report, soql_count)
    table = instance.transform(table)
    if not isinstance(table, Table):
        raise TypeError(f"transform() の戻り値が Table ではありません: {type(table).__name__}")
    names = report.COLUMN_NAMES
    columns = [names.get(column, column) for column in table.columns]
    aliases = {names[column]: column for column in table.columns if column in names}
    path = _csv_path(report)
    # 件数が合わなくても、中身を見て確かめられるように CSV は書く
    with CSV(path, encoding=UTF8_SIG) as csv_file:
        csv_file.replace(table.select(*columns, aliases=aliases))
    # 加工で件数が変わったときだけ、加工後の件数も表示する
    counts = f"SOQL {soql_count} 件"
    if len(table) != soql_count:
        counts += f" → 加工後 {len(table)} 件"
    print(f"{report.__name__}[{method}]: {counts} / {comparison} → {path}")


def _csv_path(report: type[SoqlReport]) -> Path:
    """レポートの CSV のパスを返す。"""
    return OUTPUT_DIR / f"{report.__name__}.csv"


def _remove_stale_csv(report: type[SoqlReport]) -> None:
    """失敗したレポートの CSV を消す。前回の成功した結果を取り違えないようにするため。"""
    path = _csv_path(report)
    if not path.exists():
        return
    # 書き込みの途中で失敗して中途半端な CSV ができた場合も、同じく消す
    path.unlink(missing_ok=True)
    print(f"古い CSV を消しました → {path}")


def _compare_count(sf: SalesforceBase, report: type[SoqlReport], soql_count: int) -> str:
    """SOQL の件数とレポートの総件数を比べて、表示する文字列を返す。"""
    if not report.REPORT_ID:
        return "比較なし"
    report_count = _report_row_count(sf, report.REPORT_ID)
    if report_count is None:
        return "比較なし"
    status = "一致" if report_count == soql_count else "不一致"
    return f"レポート {report_count} 件（{status}）"


def _report_row_count(sf: SalesforceBase, report_id: str) -> int | None:
    """レポートの総件数を返す。集計に RowCount が無いレポートは None を返す。"""
    # includeDetails=false なら明細が返らないので、2000 件を超えるレポートでも総件数が取れる
    path = f"{sf.data_path('/analytics/reports')}/{report_id}?includeDetails=false"
    result, _ = sf.request("GET", path, component="report")
    names = result["reportMetadata"]["aggregates"]
    if "RowCount" not in names:
        return None
    value = result["factMap"]["T!T"]["aggregates"][names.index("RowCount")]
    # API は数値か {"label": ..., "value": 数値} の形で返す
    return value["value"] if isinstance(value, dict) else value
