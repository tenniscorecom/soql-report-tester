"""``tester/run.py`` と ``tester/cli.py`` の実行フローのテスト。

実際に Salesforce にはつながらない。 偽の接続（``FakeSalesforce``）に差し替えて、
取得・件数比較・加工・CSV 書き出し・終了コードを確認する。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from comken.core.table.model import Table

from tester.cli import main as cli_main
from tester.run import CountStatus, _safe_filename_part
from tests.conftest import (
    REPORT_PAYLOAD_ROW_COUNT_3,
    REPORT_PAYLOAD_WITHOUT_ROW_COUNT,
    FakeSalesforce,
    make_site_for,
    write_master_xlsx,
    write_report_file,
)

REPORT_URL = "https://example.test/lightning/r/Report/00O000000000001AAA/view"

REPORT_BODY = '''
class SampleReport(SoqlReport):
    """テスト用のレポート定義。"""

    KEY = "1001"
    COLUMN_NAMES = {"SampleName": "サンプル名"}

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''

REPORT_BODY_NO_COUNT_CHECK = '''
class NoCountReport(SoqlReport):
    """件数を比較しないレポート定義。"""

    KEY = "1001"
    CHECK_COUNT = False

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''

INCOMPLETE_BODY = '''
class DraftReport(SoqlReport):
    """未完成のレポート定義。"""

    KEY = "1001"

    def soql(self) -> str:
        """未完成の SOQL。"""
        return "【未完成】SELECT Id FROM Sample__c"
'''


def _prepare_master(fake_config: SimpleNamespace) -> None:
    """管理表に 1 行だけ入れる。"""
    write_master_xlsx(
        fake_config.FILES.MASTER_XLSX_PATH,
        [{"ID": "1001", "Salesforce URL": REPORT_URL}],
    )


def test_writes_csv_and_returns_zero_when_count_matches(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """件数が一致したら終了コード 0 で、列名を置き換えた CSV が出る。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)
    _prepare_master(fake_config)

    exit_code = cli_main(["1001"])

    assert exit_code == 0
    csv_files = list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))
    assert len(csv_files) == 1
    # UTF-8 BOM 付き
    assert csv_files[0].read_bytes().startswith(b"\xef\xbb\xbf")
    lines = csv_files[0].read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "Id,サンプル名"
    assert len(lines) == 4  # 見出し + 3 行
    output = capsys.readouterr().out
    assert "判定: 一致" in output


def test_writes_csv_and_returns_one_when_count_differs(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
) -> None:
    """件数が一致しなくても CSV は書く（終了コードは 1）。"""
    table = Table(
        ["Id", "SampleName"],
        [
            {"Id": "001", "SampleName": "あ行"},
            {"Id": "002", "SampleName": "い行"},
            {"Id": "003", "SampleName": "う行"},
            {"Id": "004", "SampleName": "え行"},
        ],
    )
    calls: list[tuple[Any, ...]] = []
    salesforce = FakeSalesforce(table, REPORT_PAYLOAD_ROW_COUNT_3, calls)
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)
    _prepare_master(fake_config)

    exit_code = cli_main(["1001"])

    assert exit_code == 1
    csv_files = list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))
    assert len(csv_files) == 1
    assert csv_files[0].read_text(encoding="utf-8-sig").splitlines()[0] == "Id,サンプル名"


def test_does_not_connect_when_soql_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """未完成の印ならつながらずに終わる（終了コード 1）。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "draft_report.py", INCOMPLETE_BODY)
    _prepare_master(fake_config)

    exit_code = cli_main(["1001"])

    assert exit_code == 1
    assert calls == []
    assert "未完成" in capsys.readouterr().out


def test_does_not_call_report_api_when_check_count_is_false(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """``CHECK_COUNT = False`` ならレポート API を叩かない。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "no_count_report.py", REPORT_BODY_NO_COUNT_CHECK)
    _prepare_master(fake_config)

    exit_code = cli_main(["1001"])

    assert exit_code == 0
    assert [call[0] for call in calls] == ["site_for", "bulk_query"]


def test_shows_counts_and_columns_without_row_values(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """画面には件数と列名だけが出て、行の値は出ない。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)
    _prepare_master(fake_config)

    cli_main(["1001"])

    output = capsys.readouterr().out
    assert "SOQL 件数: 3" in output
    assert "レポート件数: 3" in output
    assert "列数: 2" in output
    assert "列名: Id, サンプル名" in output
    for row_value in ("あ行", "い行", "う行"):
        assert row_value not in output


def test_returns_two_when_key_is_not_in_master(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """管理表に無い管理番号なら終了コード 2。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    exit_code = cli_main(["1001"])

    assert exit_code == 2
    assert calls == []


def test_count_status_values_are_distinct() -> None:
    """判定の語が混ざっていない（画面の表示と終了コードの判定で使うため）。"""
    assert CountStatus.MATCH == "一致"
    assert CountStatus.MISMATCH == "不一致"
    assert CountStatus.NOT_COMPARED == "比較できず"
    assert CountStatus.SKIPPED == "比較なし"


def test_uses_url_option_without_opening_master(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """``--url`` を渡したら管理表を開かずに実行できる。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)
    # 管理表は作らない（作ると「管理表が無い」エラーになる）

    exit_code = cli_main(["1001", "--url", REPORT_URL])

    assert exit_code == 0
    assert ("site_for", REPORT_URL) in calls


def test_runs_report_from_file_path(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """``.py`` のパスを直接指定して実行できる。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    path = write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    exit_code = cli_main([str(path), "--url", REPORT_URL])

    assert exit_code == 0
    assert ("site_for", REPORT_URL) in calls


def test_applies_transform_before_column_names(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """``transform()`` で作った列にも ``COLUMN_NAMES`` が効く。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    body = '''
class SampleReport(SoqlReport):
    """加工するレポート定義。"""

    KEY = "1001"
    COLUMN_NAMES = {"SampleName": "サンプル名", "Total": "合計"}

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"

    def transform(self, table):
        """1 行にまとめる。"""
        rows = [{"Total": str(len(table))}]
        return Table(["Total"], rows)
'''
    write_report_file(reports_dir, "sample_report.py", body)

    exit_code = cli_main(["1001", "--url", REPORT_URL])

    assert exit_code == 0
    csv_files = list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))
    assert len(csv_files) == 1
    lines = csv_files[0].read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "合計"
    assert lines[1] == "3"


def test_returns_zero_when_count_cannot_be_compared(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
) -> None:
    """レポート総件数が取れなかったら「比較できず」で終了コード 0。"""
    table = Table(["Id", "SampleName"], [{"Id": "001", "SampleName": "あ行"}])
    calls: list[tuple[Any, ...]] = []
    salesforce = FakeSalesforce(table, REPORT_PAYLOAD_WITHOUT_ROW_COUNT, calls)
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    exit_code = cli_main(["1001", "--url", REPORT_URL])

    assert exit_code == 0
    assert any(call[0] == "request" for call in calls)


def test_writes_csv_directly_into_output_dir_when_key_has_invalid_filename_chars(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, Any]]],
) -> None:
    """管理番号にファイル名に使えない文字が入っていても、CSV は出力フォルダの直下に出る。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    body = '''
class PathKeyReport(SoqlReport):
    """ファイル名に使えない文字の管理番号を持つレポート定義。"""

    KEY = "A/1:2"

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''
    write_report_file(reports_dir, "path_key_report.py", body)

    exit_code = cli_main(["A/1:2", "--url", REPORT_URL])

    assert exit_code == 0
    output_dir = fake_config.FILES.OUTPUT_DIR
    csv_files = list(output_dir.glob("*.csv"))
    assert len(csv_files) == 1
    # 出力フォルダの直下に置かれる（サブフォルダに散らばらない）
    assert csv_files[0].parent == output_dir
    assert list(output_dir.iterdir()) == csv_files
    # ファイル名に使えない文字は ``_`` に置き換わる
    assert csv_files[0].name.startswith("A_1_2_")


@pytest.mark.parametrize("char", list('\\/:*?"<>|'))
def test_replaces_every_invalid_filename_character(char: str) -> None:
    """Windows のファイル名に使えない文字は、すべて ``_`` に置き換わる。"""
    assert _safe_filename_part(f"a{char}b") == "a_b"
