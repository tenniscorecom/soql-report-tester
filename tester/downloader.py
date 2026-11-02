"""tester/downloader.py — ダウンローダーの部品を「使うときに」取り込む。

この道具が Salesforce に対して使う以下の 4 つは、**ダウンローダーのものを
そのまま使う**（コピーしない）。

- ``SoqlReport``（``src.soql_reports.base``）— レポート定義の基底クラス
- ``apply_column_names()``（``src.soql_reports.runner``）— 見出しを人の読む名に換える
- ``_fetch_report_total_count()``（``src.service.soql``）— レポートの総件数を取る
- ``INCOMPLETE_SOQL_MARKER``（``src.service.soql``）— 未完成の印

**コピーしない理由:** ここへ写すと、ダウンローダーを直したときに
この道具だけ古くなり、同じ SOQL でも「試した時」と「本番で動く時」で
結果が変わってしまう（気づけない食い違いになる）。

**import を関数の中に置く理由:** ダウンローダーの場所は ``config.ini`` で
決まるので、``sys.path`` への追加と ``import`` は実行時に行う。
モジュール読み込み時に行うと、``config.ini`` が無い状態で
``import tester`` が失敗し、``--help`` やテストが動かなくなる。
"""

from __future__ import annotations

import logging
from typing import Any

from comken.core.table.model import Table

from tester.paths import prepare_downloader_imports

logger = logging.getLogger(__name__)


def soql_report_base() -> type:
    """ダウンローダーの ``SoqlReport`` 基底クラスを返す。

    戻り値の型は ``type[SoqlReport]`` だが、``SoqlReport`` 自体を実行時には
    import しない（``config.ini`` を読める前に import すると失敗するため）。
    """
    prepare_downloader_imports()
    from src.soql_reports.base import SoqlReport

    return SoqlReport


def apply_column_names(report_cls: type, table: Table) -> Table:
    """``COLUMN_NAMES`` を適用して、SOQL の結果列を人が読む見出しへ置き換える。

    置き換え後の見出しが 2 つ重なる場合は、ダウンローダー側の
    ``SoqlColumnNameConflictError`` がそのまま送出される（CSV は書かれない）。
    """
    prepare_downloader_imports()
    from src.soql_reports.runner import apply_column_names as apply_names

    return apply_names(report_cls, table)


def fetch_report_total_count(salesforce: Any, report_id: str) -> int | None:
    """レポート API から総件数（``RowCount``）を取り出す。

    取れない形だった場合は ``None``（=比較できない）。401 / 403 は
    ダウンロードの失敗扱いなので、そのまま送出される。
    """
    prepare_downloader_imports()
    from src.service.soql import _fetch_report_total_count as fetch_count

    return fetch_count(salesforce, report_id)


def incomplete_marker() -> str:
    """未完成の印（この文字列で始まる SOQL はそのままでは実行できない）。"""
    prepare_downloader_imports()
    from src.service.soql import INCOMPLETE_SOQL_MARKER

    return INCOMPLETE_SOQL_MARKER
