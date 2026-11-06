"""KEYS に並べたレポートを bulk_query か query で取得して、件数を比べ、CSV に書き出す。"""

from pathlib import Path

from comken.core.encoding import UTF8_SIG
from comken.toolbox.csv import CSV
from comken.toolbox.salesforce.client import SalesforceBase
from comken.toolbox.salesforce.sites import SolutionSandbox

from reports import REPORTS_BY_KEY
from src.soql_reports.base import SoqlReport

KEYS: list[str] = [
    # "1001",
]

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def main() -> None:
    """KEYS のレポートを順に取得して、件数を表示し、CSV に書き出す。"""
    # 番号を書き間違えたときに、Salesforce へ接続する前に止める
    reports = [REPORTS_BY_KEY[key] for key in KEYS]
    with SolutionSandbox() as sf:
        for report in reports:
            soql = report().soql()
            # 取り方はレポートごとの USE_BULK で選ぶ（False なら REST の query() になる）
            if report.USE_BULK:
                table = sf.bulk_query(soql)
                method = "Bulk"
            else:
                table = sf.query(soql)
                method = "REST"
            comparison = _compare_count(sf, report, len(table))
            names = report.COLUMN_NAMES
            columns = [names.get(column, column) for column in table.columns]
            aliases = {names[column]: column for column in table.columns if column in names}
            path = OUTPUT_DIR / f"{report.__name__}.csv"
            # 件数が合わなくても、中身を見て確かめられるように CSV は書く
            with CSV(path, encoding=UTF8_SIG) as csv_file:
                csv_file.replace(table.select(*columns, aliases=aliases))
            print(f"{report.__name__}[{method}]: SOQL {len(table)} 件 / {comparison} → {path}")


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
