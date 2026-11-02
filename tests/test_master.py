"""``tester/master.py`` のテスト。

レポート管理表から「ID」と「Salesforce URL」の 2 列だけを読めることを確かめる。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tester.master import find_url, load_urls
from tests.conftest import write_master_xlsx

URL_FIRST = "https://example.test/lightning/r/Report/00O000000000001AAA/view"
URL_SECOND = "https://example.test/lightning/r/Report/00O000000000002AAA/view"


def test_reads_id_and_url_only(fake_config: SimpleNamespace) -> None:
    """管理表から管理番号と URL の対応が読める。"""
    path = write_master_xlsx(
        fake_config.FILES.MASTER_XLSX_PATH,
        [
            {"ID": "1001", "Salesforce URL": URL_FIRST},
            {"ID": "1002", "Salesforce URL": URL_SECOND},
        ],
    )

    urls = load_urls(path)

    assert urls == {"1001": URL_FIRST, "1002": URL_SECOND}


def test_skips_rows_without_id(fake_config: SimpleNamespace) -> None:
    """管理番号が空の行は読み飛ばす。"""
    path = write_master_xlsx(
        fake_config.FILES.MASTER_XLSX_PATH,
        [
            {"ID": "1001", "Salesforce URL": URL_FIRST},
            {"ID": "", "Salesforce URL": URL_SECOND},
        ],
    )

    urls = load_urls(path)

    assert urls == {"1001": URL_FIRST}


def test_raises_when_file_is_missing(tmp_path: Path) -> None:
    """管理表が無ければエラー。"""
    with pytest.raises(ValueError, match="レポート管理表が見つかりません"):
        load_urls(tmp_path / "ない.xlsx")


def test_raises_when_key_is_not_in_master(fake_config: SimpleNamespace) -> None:
    """管理表に無い管理番号ならエラー。"""
    path = write_master_xlsx(
        fake_config.FILES.MASTER_XLSX_PATH,
        [{"ID": "1001", "Salesforce URL": URL_FIRST}],
    )

    with pytest.raises(ValueError, match="レポート管理表に管理番号 9999 がありません"):
        find_url(path, "9999")


def test_raises_when_url_is_empty(fake_config: SimpleNamespace) -> None:
    """URL が空ならエラー。"""
    path = write_master_xlsx(
        fake_config.FILES.MASTER_XLSX_PATH,
        [{"ID": "1001", "Salesforce URL": ""}],
    )

    with pytest.raises(ValueError, match="「Salesforce URL」が空です"):
        find_url(path, "1001")
