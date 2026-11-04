"""レポート定義の基底クラス。

soql-collector が生成する .py が `from src.soql_reports.base import SoqlReport` と書くので、
この場所に置く。
"""

from typing import ClassVar


class SoqlReport:
    """レポート 1 本の定義。サブクラスで soql() を実装する。"""

    KEY: ClassVar[str] = ""
    REPORT_ID: ClassVar[str] = ""
    COLUMN_NAMES: ClassVar[dict[str, str]] = {}

    def soql(self) -> str:
        """実行する SOQL を返す。"""
        raise NotImplementedError
