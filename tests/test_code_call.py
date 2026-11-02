"""``reports`` パッケージと ``to_csv()`` のテスト。

Python のコードからレポートを呼ぶときの流れを確かめる。 実際に Salesforce に
はつながらない（偽の接続 ``FakeSalesforce`` を直接渡す）。

**パッケージのテストは本物の ``reports/__init__.py`` を使う。** 一時フォルダに
コピーして読み込むので、実装が ``__init__.py`` と合っていることが確かめられる。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from comken.core.table.model import Table
from comken.exceptions import ComkenError

from tester import to_csv
from tester.run import CountStatus
from tests.conftest import (
    _PROJECT_ROOT,
    REPORT_PAYLOAD_ROW_COUNT_3,
    FakeSalesforce,
    write_report_file,
)

# Salesforce のレポート ID（架空の値）
REPORT_ID = "00O000000000001AAA"

REPORT_BODY = '''
class Report1001(SoqlReport):
    """テスト用のレポート定義。"""

    KEY = "1001"
    COLUMN_NAMES = {"SampleName": "サンプル名"}

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''

REPORT_BODY_WITH_ID = '''
class Report1001(SoqlReport):
    """レポート ID を持つテスト用のレポート定義。"""

    KEY = "1001"
    REPORT_ID = "00O000000000001AAA"
    COLUMN_NAMES = {"SampleName": "サンプル名"}

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''

REPORT_BODY_1002 = '''
class Report1002(SoqlReport):
    """2 本目のテスト用レポート定義。"""

    KEY = "1002"

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''

TWO_CLASSES_BODY = '''
class ReportFirst(SoqlReport):
    """1 つ目のテスト用レポート定義。"""

    KEY = "1001"

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"


class ReportSecond(SoqlReport):
    """2 つ目のテスト用レポート定義。"""

    KEY = "1002"

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''

INCOMPLETE_BODY = '''
class Report1001(SoqlReport):
    """未完成のテスト用レポート定義。"""

    KEY = "1001"

    def soql(self) -> str:
        """未完成の SOQL。"""
        return "【未完成】SELECT Id, SampleName FROM Sample__c"
'''


def _drop_reports_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """``sys.modules`` から ``reports`` 系のモジュールを落とす（monkeypatch で元に戻す）。"""
    for name in [n for n in sys.modules if n == "reports" or n.startswith("reports.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture
def reports_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """一時フォルダに ``reports`` パッケージを作って、``sys.path`` の先頭に足す。"""
    folder = tmp_path / "reports"
    folder.mkdir()
    # 本物の ``reports/__init__.py`` をそのまま使う（実装が合っていることを確かめる）
    shutil.copy2(_PROJECT_ROOT / "reports" / "__init__.py", folder / "__init__.py")
    monkeypatch.syspath_prepend(str(tmp_path))
    _drop_reports_modules(monkeypatch)
    yield folder
    _drop_reports_modules(monkeypatch)


def _fail_if_called(*args: Any, **kwargs: Any) -> None:
    """呼ばれたら失敗する差し替え（管理表と ``site_for`` を使わないことの確認用）。"""
    raise AssertionError("管理表や site_for は使わない")


def _check_ignore(path: str) -> subprocess.CompletedProcess[str]:
    """``git check-ignore`` をリポジトリの中で実行する。

    **``stdin`` は DEVNULL にする。** Windows では pytest が標準入力を差し替えた
    状態だと ``WinError 6``（ハンドルが無効）でパイプを作れなくなるため。
    """
    return subprocess.run(
        ["git", "check-ignore", path],
        cwd=_PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_exposes_report_module_with_star_import(
    reports_package: Path,
    fake_config: SimpleNamespace,
) -> None:
    """``from reports import *`` でレポート定義のモジュールが取れる。"""
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)

    namespace: dict[str, Any] = {}
    exec("from reports import *", namespace)  # import * の動き自体を確かめるため

    module = namespace["report_1001"]
    assert module.Report1001().soql() == "SELECT Id, SampleName FROM Sample__c"


def test_exposes_report_module_with_import(
    reports_package: Path,
    fake_config: SimpleNamespace,
) -> None:
    """``import reports`` 経由でも同じものが取れる。"""
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)

    import reports

    assert reports.report_1001.Report1001().soql() == "SELECT Id, SampleName FROM Sample__c"


def test_exposes_every_report_file(
    reports_package: Path,
    fake_config: SimpleNamespace,
) -> None:
    """フォルダの中のレポート定義が全部見える（``_`` で始まるファイルは見えない）。"""
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)
    write_report_file(reports_package, "report_1002.py", REPORT_BODY_1002)
    write_report_file(reports_package, "_template.py", REPORT_BODY)
    write_report_file(reports_package, "1001.py", REPORT_BODY)

    namespace: dict[str, Any] = {}
    exec("from reports import *", namespace)  # import * の動き自体を確かめるため

    assert "report_1001" in namespace
    assert "report_1002" in namespace
    # 雛形（``_`` で始まる）と Python の名前として書けないファイルは見えない
    assert "_template" not in namespace
    assert "1001" not in namespace


def test_warns_when_file_name_is_not_a_python_name(
    reports_package: Path,
    fake_config: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``1001.py`` は Python の名前として書けないので、警告して読み飛ばす。"""
    write_report_file(reports_package, "1001.py", REPORT_BODY)

    with caplog.at_level(logging.WARNING):
        import reports  # noqa: F401  # 読み込んだだけ（警告の記録だけを見る）

    assert any("1001.py" in record.getMessage() for record in caplog.records)


def test_raises_value_error_when_report_file_is_broken(
    reports_package: Path,
    fake_config: SimpleNamespace,
) -> None:
    """壊れた ``.py`` はエラーになる（ファイル名と例外の型名だけを出す）。"""
    (reports_package / "broken.py").write_text("class Broken(:\n", encoding="utf-8")

    with pytest.raises(ValueError) as error:
        import reports  # noqa: F401  # 読み込みが失敗することだけを見る

    message = str(error.value)
    assert "broken.py" in message
    assert "SyntaxError" in message
    # 例外の中身（壊れたソース）は出さない
    assert "class Broken" not in message


def test_to_csv_writes_csv_from_module(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """モジュールを指定すると、CSV が書かれる（見出しと行数が正しい）。"""
    salesforce, _calls = fake_salesforce
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)

    import reports

    result = to_csv(reports.report_1001, salesforce)

    csv_files = list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))
    assert len(csv_files) == 1
    lines = csv_files[0].read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "Id,サンプル名"
    assert len(lines) == 4  # 見出し + 3 行
    assert result.soql_count == 3
    assert result.key == "1001"


def test_to_csv_writes_csv_from_class(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """クラスを指定しても同じように CSV が書かれる。"""
    salesforce, _calls = fake_salesforce
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)

    import reports

    result = to_csv(reports.report_1001.Report1001, salesforce)

    csv_files = list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))
    assert len(csv_files) == 1
    assert csv_files[0].read_text(encoding="utf-8-sig").splitlines()[0] == "Id,サンプル名"
    assert result.class_name == "Report1001"


def test_to_csv_runs_two_reports_with_one_connection(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """同じ接続のまま 2 本続けて呼べる（CSV が 2 つできる）。"""
    salesforce, calls = fake_salesforce
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)
    write_report_file(reports_package, "report_1002.py", REPORT_BODY_1002)

    import reports

    to_csv(reports.report_1001, salesforce)
    to_csv(reports.report_1002.Report1002, salesforce)

    csv_files = list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))
    assert len(csv_files) == 2
    assert [call[0] for call in calls] == ["bulk_query", "bulk_query"]


def test_to_csv_compares_count_with_report_id(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """``REPORT_ID`` があれば、その ID のレポート API を叩いて件数を比べる。"""
    salesforce, calls = fake_salesforce
    write_report_file(reports_package, "report_1001.py", REPORT_BODY_WITH_ID)

    import reports

    result = to_csv(reports.report_1001, salesforce)

    assert result.count_status == CountStatus.MATCH
    assert result.report_count == 3
    assert any(REPORT_ID in str(call) for call in calls)


def test_to_csv_does_not_call_report_api_without_report_id(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``REPORT_ID`` が無ければ比較できず（レポート API は叩かない）。"""
    salesforce, calls = fake_salesforce
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)

    import reports

    result = to_csv(reports.report_1001, salesforce)

    assert result.count_status == CountStatus.NOT_COMPARED
    assert not any(call[0] == "request" for call in calls)
    assert len(list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))) == 1
    assert "判定: 比較できず" in capsys.readouterr().out


def test_to_csv_works_without_master(
    monkeypatch: pytest.MonkeyPatch,
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """管理表がなくても、管理表も ``site_for`` も使わずに実行できる。"""
    salesforce, _calls = fake_salesforce
    monkeypatch.setattr("tester.master.load_urls", _fail_if_called)
    monkeypatch.setattr("tester.run.site_for", _fail_if_called)
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)

    import reports

    result = to_csv(reports.report_1001, salesforce)

    assert result.soql_count == 3
    assert len(list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))) == 1


def test_to_csv_writes_csv_when_count_differs(
    reports_package: Path,
    fake_config: SimpleNamespace,
) -> None:
    """件数が不一致でも例外にせず、CSV を書いて「不一致」と出す。"""
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
    write_report_file(reports_package, "report_1001.py", REPORT_BODY_WITH_ID)

    import reports

    result = to_csv(reports.report_1001, salesforce)

    assert result.count_status == CountStatus.MISMATCH
    csv_files = list(fake_config.FILES.OUTPUT_DIR.glob("*.csv"))
    assert len(csv_files) == 1
    assert len(csv_files[0].read_text(encoding="utf-8-sig").splitlines()) == 5


def test_to_csv_raises_when_soql_is_incomplete(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """未完成の SOQL は例外になる（Salesforce には問い合わせない）。"""
    salesforce, calls = fake_salesforce
    write_report_file(reports_package, "report_1001.py", INCOMPLETE_BODY)

    import reports

    with pytest.raises(ComkenError):
        to_csv(reports.report_1001, salesforce)

    assert calls == []


def test_to_csv_raises_when_module_has_two_classes(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """モジュールにクラスが 2 つあるときはエラー。"""
    salesforce, _calls = fake_salesforce
    write_report_file(reports_package, "two_reports.py", TWO_CLASSES_BODY)

    import reports

    with pytest.raises(ValueError):
        to_csv(reports.two_reports, salesforce)


def test_to_csv_raises_when_target_is_not_a_report(
    reports_package: Path,
    fake_config: SimpleNamespace,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
) -> None:
    """レポートでもなくモジュールでもないものを渡したらエラー。"""
    salesforce, _calls = fake_salesforce
    write_report_file(reports_package, "report_1001.py", REPORT_BODY)

    with pytest.raises(ValueError):
        to_csv("Sample__c", salesforce)


@pytest.mark.skipif(shutil.which("git") is None, reason="git が見つかりません")
def test_reports_init_is_not_ignored() -> None:
    """``reports/__init__.py`` は git に含める（無視されない）。"""
    assert _check_ignore("reports/__init__.py").returncode != 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git が見つかりません")
def test_report_files_are_ignored() -> None:
    """生成された ``reports/*.py`` は git に含めない（無視される）。"""
    assert _check_ignore("reports/report_1001.py").returncode == 0
