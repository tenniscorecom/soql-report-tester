"""``tester/reports.py`` のテスト。

レポート定義の読み込み（``importlib``）・管理番号の重複・未完成の印の判定を確かめる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tester.reports import (
    find_report_by_key,
    is_incomplete,
    load_report_file,
    load_reports,
)
from tests.conftest import write_report_file

REPORT_BODY = '''
class SampleReport(SoqlReport):
    """テスト用のレポート定義。"""

    KEY = "1001"

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''

INCOMPLETE_BODY = '''
class DraftReport(SoqlReport):
    """未完成のレポート定義。"""

    KEY = "1002"

    def soql(self) -> str:
        """未完成の SOQL。"""
        return "【未完成】SELECT Id FROM Sample__c"
'''


def test_loads_one_report_class(reports_dir: Path) -> None:
    """1 ファイルに 1 つだけ定義があれば読み込める。"""
    path = write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    definition = load_report_file(path)

    assert definition.key == "1001"
    assert definition.class_name == "SampleReport"
    assert definition.path == path
    assert definition.report_cls().soql() == "SELECT Id, SampleName FROM Sample__c"


def test_raises_when_subclass_is_missing(reports_dir: Path) -> None:
    """SoqlReport のサブクラスが 1 つでなければエラー。"""
    path = write_report_file(reports_dir, "no_report.py", "VALUE = 1\n")

    with pytest.raises(ValueError, match="SoqlReport のサブクラスを1つだけ"):
        load_report_file(path)


def test_raises_when_two_subclasses(reports_dir: Path) -> None:
    """SoqlReport のサブクラスが 2 つあればエラー。"""
    body = REPORT_BODY + '\n\nclass SecondReport(SoqlReport):\n    KEY = "1003"\n'
    path = write_report_file(reports_dir, "two_reports.py", body)

    with pytest.raises(ValueError, match="SoqlReport のサブクラスを1つだけ"):
        load_report_file(path)


def test_raises_when_key_is_empty(reports_dir: Path) -> None:
    """管理番号が空ならエラー。"""
    path = write_report_file(
        reports_dir, "no_key.py", 'class NoKeyReport(SoqlReport):\n    KEY = ""\n'
    )

    with pytest.raises(ValueError, match="管理番号（KEY）が空です"):
        load_report_file(path)


def test_raises_when_file_is_missing(reports_dir: Path) -> None:
    """ファイルが無ければエラー。"""
    with pytest.raises(ValueError, match="レポート定義が見つかりません"):
        load_report_file(reports_dir / "ない.py")


def test_raises_when_key_is_duplicated(reports_dir: Path) -> None:
    """管理番号が重複したらエラー。"""
    write_report_file(reports_dir, "first.py", REPORT_BODY)
    write_report_file(reports_dir, "second.py", REPORT_BODY)

    with pytest.raises(ValueError, match="管理番号が重複しています"):
        load_reports(reports_dir)


def test_skips_underscore_files(reports_dir: Path) -> None:
    """``_`` で始まるファイル（雛形）は読み飛ばす。"""
    write_report_file(reports_dir, "_template.py", REPORT_BODY)

    assert load_reports(reports_dir) == []


def test_finds_report_by_key(reports_dir: Path) -> None:
    """管理番号からレポート定義を引ける。"""
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    definition = find_report_by_key(reports_dir, "1001")

    assert definition.key == "1001"


def test_raises_when_key_is_not_found(reports_dir: Path) -> None:
    """管理番号が見つからなければエラー（ある管理番号を添える）。"""
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    with pytest.raises(ValueError, match="管理番号 9999 のレポート定義が"):
        find_report_by_key(reports_dir, "9999")


def test_detects_incomplete_soql(reports_dir: Path) -> None:
    """未完成の印で始まる SOQL は未完成と分かる。"""
    path = write_report_file(reports_dir, "draft_report.py", INCOMPLETE_BODY)

    definition = load_report_file(path)

    assert is_incomplete(definition.report_cls().soql()) is True
    assert is_incomplete("SELECT Id FROM Sample__c") is False
