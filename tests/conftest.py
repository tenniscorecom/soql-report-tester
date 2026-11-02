"""``tests/`` 共通の fixture / ヘルパー。

**パス設定:** comken の場所を ``PYTHON_LIBRARY`` 環境変数 → 無ければ
隣接フォルダ ``../comken`` の順で ``sys.path`` の末尾に足す。
``pyproject.toml`` に pythonpath を直書きしないのは、CI／社内 BO 環境ごとに
参照場所が違うため。

comken を **末尾** に置くのは、comken 側の ``tests/`` が通常のパッケージとして
``import tests`` を横取りするのを避けるため。

**設定の差し替え:** 本体は ``from comken import config`` で読む（config.ini を
書かずに済ませたい）。 そのため ``tester.paths.config`` を偽の物に差し替えて、
``config.ini`` を作らずに一時フォルダだけで動かす。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from comken.core.table.model import Table
from comken.toolbox.excel import Excel

# プロジェクトルート（``tester/`` の親）と comken の場所を ``sys.path`` に足す。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_COMKEN_FALLBACK = _PROJECT_ROOT.parent / "comken"

# ダウンローダーの場所（config.ini.example の既定値と同じ隣フォルダ）。
# 本体はここを ``sys.path`` の先頭に足して ``src.soql_reports`` を import する。
_DOWNLOADER_ROOT = _PROJECT_ROOT.parent / "Salesforceレポートダウンローダー"

# レポート API の返り値（実物の形）。
# ``reportMetadata.aggregates`` の "RowCount" の位置が、
# ``factMap["T!T"]["aggregates"]`` の同じ位置の値になる。
REPORT_PAYLOAD_ROW_COUNT_3: dict[str, Any] = {
    "reportMetadata": {"aggregates": ["RowCount"]},
    "factMap": {"T!T": {"aggregates": [{"label": "3", "value": 3}]}},
}

# レポート API の返り値（RowCount が無い形。=件数を比較できない）
REPORT_PAYLOAD_WITHOUT_ROW_COUNT: dict[str, Any] = {
    "reportMetadata": {"aggregates": []},
    "factMap": {"T!T": {"aggregates": []}},
}


def _append_sys_path(path: Path) -> None:
    """``sys.path`` の末尾に ``path`` を足す（既にあれば何もしない）。"""
    text = str(path)
    if text not in sys.path:
        sys.path.append(text)


# comken を import できるようにする（末尾に足す理由はモジュール docstring 参照）
_python_library = os.environ.get("PYTHON_LIBRARY", "")
if _python_library:
    _append_sys_path(Path(_python_library))
elif _COMKEN_FALLBACK.is_dir():
    _append_sys_path(_COMKEN_FALLBACK)


@pytest.fixture(scope="session")
def downloader_root() -> Path:
    """ダウンローダーの場所（無ければ skip する）。"""
    if not (_DOWNLOADER_ROOT / "src" / "soql_reports" / "base.py").is_file():
        pytest.skip(f"ダウンローダーが見つかりません: {_DOWNLOADER_ROOT}")
    return _DOWNLOADER_ROOT


@pytest.fixture
def fake_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """``tester.paths.config`` を差し替えて、config.ini なしで動かせるようにする。"""
    stub = SimpleNamespace(
        FILES=SimpleNamespace(
            DOWNLOADER_ROOT=_DOWNLOADER_ROOT,
            REPORTS_DIR=tmp_path / "reports",
            MASTER_XLSX_PATH=tmp_path / "input" / "レポート管理表.xlsx",
            OUTPUT_DIR=tmp_path / "output",
        )
    )
    monkeypatch.setattr("tester.paths.config", stub)
    return stub


@pytest.fixture
def reports_dir(fake_config: SimpleNamespace) -> Path:
    """試すレポート定義を置くフォルダ（作っておく）。"""
    path = fake_config.FILES.REPORTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_report_file(directory: Path, file_name: str, body: str) -> Path:
    """レポート定義（``.py``）を 1 つ書き出す。

    ``body`` はクラス定義の部分（import は自動で足す）。 足す import は
    ダウンローダーの雛形（``src/soql_reports/reports/_template.py``）と同じ形。
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / file_name
    header = (
        "from comken.core.table.model import Table\n"
        "from src.soql_reports.base import SoqlReport\n"
        "\n"
        "\n"
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def write_master_xlsx(path: Path, rows: list[dict[str, str]]) -> Path:
    """レポート管理表（Excel）をテスト用に作る。"""
    table = Table(["ID", "Salesforce URL"], rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with Excel(path) as excel:
        excel.create_data_sheet("管理表").create_table("管理表", table)
    return path


class FakeSalesforce:
    """偽の Salesforce 接続。``bulk_query`` とレポート API だけを持つ。"""

    def __init__(
        self,
        table: Table,
        report_payload: dict[str, Any],
        calls: list[tuple[Any, ...]],
    ) -> None:
        self._table = table
        self._report_payload = report_payload
        self.calls = calls

    def bulk_query(self, soql: str) -> Table:
        """SOQL を実行して結果を返す（返り値は偽の物）。"""
        self.calls.append(("bulk_query", soql))
        return self._table

    def data_path(self, path: str) -> str:
        """REST API のパスを作る（実物と同じ形）。"""
        return f"/services/data/v62.0{path}"

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        component: str = "other",
        headers: dict[str, str] | None = None,
        data: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """レポート API の返り値を返す（実物と同じ形）。"""
        self.calls.append(("request", method, path))
        return self._report_payload, {}


class FakeSite:
    """偽の組織クラス。インスタンスが context manager になる。"""

    def __init__(self, salesforce: FakeSalesforce) -> None:
        self._salesforce = salesforce

    def __enter__(self) -> FakeSalesforce:
        return self._salesforce

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


def make_site_for(salesforce: FakeSalesforce, calls: list[tuple[Any, ...]]):
    """``site_for`` の代用品を作る。つないだ URL は ``calls`` に記録する。"""

    def site_for(url: str):
        calls.append(("site_for", url))
        return lambda: FakeSite(salesforce)

    return site_for


@pytest.fixture
def fake_salesforce() -> tuple[FakeSalesforce, list[tuple[Any, ...]]]:
    """偽の接続と、呼び出しの記録リストを返す。"""
    table = Table(
        ["Id", "SampleName"],
        [
            {"Id": "001", "SampleName": "あ行"},
            {"Id": "002", "SampleName": "い行"},
            {"Id": "003", "SampleName": "う行"},
        ],
    )
    calls: list[tuple[Any, ...]] = []
    return FakeSalesforce(table, REPORT_PAYLOAD_ROW_COUNT_3, calls), calls
