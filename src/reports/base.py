"""レポート定義の基底クラス。

soql-collector が生成する .py が `from src.reports.base import SoqlReport` と書くので、
この場所に置く。
"""

from typing import ClassVar

from comken.core.table.model import Table


class SoqlReport:
    """レポート 1 本の定義。サブクラスで soql() を実装する。"""

    KEY: ClassVar[str] = ""
    REPORT_ID: ClassVar[str] = ""
    COLUMN_NAMES: ClassVar[dict[str, str]] = {}
    # False なら query()（REST）で取る
    USE_BULK: ClassVar[bool] = True

    def soql(self) -> str:
        """実行する SOQL を返す。"""
        raise NotImplementedError

    def transform(self, table: Table) -> Table:
        """列名を置き換えた後の結果を、CSV に書く前に加工する。既定は何もしない。

        引数の table の列名は、COLUMN_NAMES で置き換えた表示名になっている。
        """
        return table
