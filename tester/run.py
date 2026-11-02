"""tester/run.py — レポート 1 本を実行して、結果を CSV にする。

やること（順番は変えない）:

1. SOQL を取る（``SoqlReport.soql()``）
2. 未完成の印で始まっているなら **Salesforce に問い合わせずに**止める
3. ``site_for(url)`` でつないで ``bulk_query(soql)`` を実行する
4. ``CHECK_COUNT`` が有効なら、**同じ接続のうち**にレポートの総件数を取って比べる
5. ``transform()`` → ``apply_column_names()``
6. CSV を書き出す（UTF-8 BOM）

**件数が不一致でも CSV は書く。** この道具は「中身を自分で見て確かめる」ための
もので、件数不一致のまま中身を捨てると何が起きているか分からなくなるため。

**行の値は画面にもログにも出さない。** 件数・列名・出力先だけを出す。

**接続の開き方:**

- コマンド（``main.py``）は ``site_for(url)`` でつなぐ
- Python のコードから呼ぶとき（``to_csv()``）は、**呼び出し側が開いた接続**を
  受け取る（ここでは開かない）。 そのため管理表もレポート URL も読まない
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from comken.core.dates import now
from comken.core.encoding import UTF8_SIG
from comken.core.table.model import Table
from comken.exceptions import ComkenError, SalesforceReportIDNotFoundError
from comken.toolbox.csv import CSV
from comken.toolbox.salesforce.report import report_id_from_url
from comken.toolbox.salesforce.sites import site_for

from tester.downloader import apply_column_names, fetch_report_total_count, soql_report_base
from tester.paths import output_dir
from tester.reports import ReportDefinition, definition_of_class, is_incomplete, pick_report_class

logger = logging.getLogger(__name__)

# Windows のファイル名に使えない文字（``KEY`` をファイル名に使うためだけ置き換える）
INVALID_FILENAME_CHARS = '\\/:*?"<>|'


class CountStatus:
    """件数の比較結果（画面に出す語）。"""

    MATCH = "一致"
    MISMATCH = "不一致"
    NOT_COMPARED = "比較できず"
    SKIPPED = "比較なし"


@dataclass(frozen=True)
class RunResult:
    """1 本のレポートを試した結果。"""

    #: 管理番号
    key: str
    #: クラス名
    class_name: str
    #: SOQL が返した件数（加工前。レポートの件数と比べる対象）
    soql_count: int
    #: レポートの総件数（取れなかったときは ``None``）
    report_count: int | None
    #: 比較結果（``CountStatus`` の値）
    count_status: str
    #: CSV に出る列名
    columns: list[str]
    #: CSV の書き出し先
    output_path: Path


def to_csv(target: object, salesforce: Any) -> RunResult:
    """レポート 1 本を実行して、CSV を書き出して結果を返す。

    **接続は呼び出し側が開いたものを使う**（ここでは開かないし閉じない）。
    そのため管理表もレポート URL も読まない。

    Args:
        target: レポートのクラス、または 1 つだけレポートのクラスを定義した
            モジュール（``reports.report_1001`` など）。
        salesforce: 開いている Salesforce 接続
            （``with SolutionSandbox() as sf:`` の中の ``sf``）。

    Returns:
        実行結果（件数・判定・列名・CSV の書き出し先）。件数が不一致でも
        例外にはしない（判定は戻り値と表示で分かる）。

    Raises:
        ValueError: ``target`` がレポートのクラスでもモジュールでもないとき。
        ComkenError: SOQL が未完成、取得に失敗、加工に失敗、CSV が書けなかったとき。
    """
    definition = definition_of_class(_report_class_of(target))
    soql_text = read_soql(definition)
    if is_incomplete(soql_text):
        raise ComkenError(
            f"未完成です（{definition.path.name}）: "
            "SOQL の先頭に未完成の印があります。Salesforce には問い合わせません。"
        )
    result = _run_on(salesforce, definition, soql_text, definition.report_id or None)
    print_result(result)
    return result


def run_report(definition: ReportDefinition, url: str, soql_text: str) -> RunResult:
    """レポート 1 本を実行して、CSV を書き出して結果を返す。

    Args:
        definition: 実行するレポート定義。
        url: つなぐ Salesforce のレポート URL。
        soql_text: 実行する SOQL（呼び出し側が ``soql()`` を取得済み）。

    Raises:
        ComkenError: 接続できない、加工に失敗した、CSV を書けなかったとき。
    """
    site = site_for(url)
    with site() as salesforce:
        return _run_on(salesforce, definition, soql_text, _report_id_of(definition.report_cls, url))


def read_soql(definition: ReportDefinition) -> str:
    """レポート定義の SOQL を読み取る。

    Raises:
        ComkenError: SOQL が取れなかったとき（メッセージに値は出さない）。
    """
    try:
        return str(definition.report_cls().soql())
    except Exception as exc:
        raise ComkenError(
            f"SOQL を取得できませんでした: クラス={definition.class_name}, "
            f"例外={type(exc).__name__}"
        ) from exc


def print_result(result: RunResult) -> None:
    """実行結果を表示する（件数と列名だけ。行の値は出さない）。"""
    print(f"クラス名: {result.class_name}")
    print(f"SOQL 件数: {result.soql_count}")
    if result.report_count is None:
        print("レポート件数: （取れませんでした）")
    else:
        print(f"レポート件数: {result.report_count}")
    print(f"判定: {result.count_status}")
    print(f"列数: {len(result.columns)}")
    print(f"列名: {', '.join(result.columns)}")
    print(f"出力先: {result.output_path}")


def _run_on(
    salesforce: Any,
    definition: ReportDefinition,
    soql_text: str,
    report_id: str | None,
) -> RunResult:
    """開いている接続で 1 本のレポートを実行する（CSV の書き出しまで）。

    Args:
        salesforce: 開いている Salesforce 接続。
        definition: 実行するレポート定義。
        soql_text: 実行する SOQL。
        report_id: 件数の比較に使う Salesforce のレポート ID
            （無いなら ``None``＝比較しない）。
    """
    report_cls = definition.report_cls
    instance = report_cls()
    table = salesforce.bulk_query(soql_text)
    soql_count = len(table)
    report_count, count_status = _compare_count(report_cls, salesforce, report_id, soql_count)
    transformed = _transform(instance, report_cls, table)
    named = apply_column_names(report_cls, transformed)
    output_path = _write_csv(definition.key, named)
    return RunResult(
        key=definition.key,
        class_name=definition.class_name,
        soql_count=soql_count,
        report_count=report_count,
        count_status=count_status,
        columns=list(named.columns),
        output_path=output_path,
    )


def _compare_count(
    report_cls: type,
    salesforce: Any,
    report_id: str | None,
    soql_count: int,
) -> tuple[int | None, str]:
    """SOQL の件数とレポートの総件数を比べる。

    比較は **加工前の生の件数** で行う（レポートの総件数と比べられるのは
    加工前の件数のため）。 戻り値は ``(レポート件数, 判定)`` 。

    ``report_id`` が ``None`` のときは、比較しない（``CHECK_COUNT`` が ``False``）
    か、比較する ID が無い（判定は「比較できず」）のどちらか。
    """
    if not report_cls.CHECK_COUNT:
        return None, CountStatus.SKIPPED
    if report_id is None:
        return None, CountStatus.NOT_COMPARED
    report_count = fetch_report_total_count(salesforce, report_id)
    if report_count is None:
        return None, CountStatus.NOT_COMPARED
    if report_count == soql_count:
        return report_count, CountStatus.MATCH
    return report_count, CountStatus.MISMATCH


def _report_id_of(report_cls: type, url: str) -> str | None:
    """URL から Salesforce のレポート ID を取り出す（取れなければ ``None``）。

    件数を比較しないレポート（``CHECK_COUNT`` が ``False``）は ID を取り出さない
    （取り出せなくても比較しないため。取り出せなかったときの警告も出さない）。
    """
    if not report_cls.CHECK_COUNT:
        return None
    try:
        return report_id_from_url(url)
    except SalesforceReportIDNotFoundError:
        logger.warning("URL からレポート ID を取り出せません（件数を比較できません）: %s", url)
        return None


def _report_class_of(target: object) -> type:
    """``to_csv()`` の対象から、レポートのクラスを 1 つ取り出す。

    モジュールは、その中で定義された ``SoqlReport`` サブクラスがちょうど 1 つ
    ならそのクラスにする（``pick_report_class()`` と同じ規則）。

    Raises:
        ValueError: レポートのクラスでもモジュールでもないとき。
    """
    if isinstance(target, type):
        base = soql_report_base()
        if issubclass(target, base) and target is not base:
            return target
        raise ValueError(f"SoqlReport のサブクラスを指定してください: {target.__name__}")
    if isinstance(target, ModuleType):
        return pick_report_class(target)
    raise ValueError(
        "レポートのクラスか、1 つだけレポートのクラスを定義したモジュールを指定してください: "
        f"{type(target).__name__}"
    )


def _transform(instance: Any, report_cls: type, table: Table) -> Table:
    """``transform()`` を呼んで、結果を ``Table`` にして返す。

    例外が起きても **行の値が出るメッセージにしない**（元の例外のメッセージには
    行の値が入ることがあるため）。 例外の名前だけを出して、原因として残す。
    """
    try:
        transformed = instance.transform(table)
    except Exception as exc:
        raise ComkenError(
            f"加工(transform)中にエラーが発生しました: "
            f"クラス={report_cls.__name__}, 例外={type(exc).__name__}"
        ) from exc
    if not isinstance(transformed, Table):
        raise ComkenError(
            f"transform() の戻り値が Table ではありません: "
            f"クラス={report_cls.__name__}, 戻り値={type(transformed).__name__}"
        )
    return transformed


def _safe_filename_part(key: str) -> str:
    """``KEY`` をファイル名に使える形にして返す。

    Windows のファイル名に使えない文字（``\\ / : * ? " < > |``）は
    すべて ``_`` に置き換える。 置き換えるのは **ファイル名だけ** で、
    管理番号そのもの（画面やログに出る値）は変えない。
    """
    return "".join("_" if char in INVALID_FILENAME_CHARS else char for char in key)


def _write_csv(key: str, table: Table) -> Path:
    """CSV を書き出して、パスを返す（UTF-8 BOM 付き）。"""
    folder = output_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(key)}_{now():%Y%m%d_%H%M%S}.csv"
    with CSV(path, encoding=UTF8_SIG) as csv_file:
        csv_file.replace(table)
    logger.info("CSV を書き出しました: %s", path)
    return path
