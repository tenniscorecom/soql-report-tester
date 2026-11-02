"""``tester/cli.py`` のテスト（一覧・表示・引数の誤り・サブプロセス起動）。

``if __name__ == "__main__"`` を抜けていないことを確かめるため、
``python main.py`` を **実際に起動する** テストも含める。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tester.cli import main as cli_main
from tests.conftest import (
    _COMKEN_FALLBACK,
    _DOWNLOADER_ROOT,
    _PROJECT_ROOT,
    FakeSalesforce,
    make_site_for,
    write_report_file,
)

REPORT_BODY = '''
class SampleReport(SoqlReport):
    """テスト用のレポート定義。"""

    KEY = "1001"

    def soql(self) -> str:
        """テスト用の SOQL。"""
        return "SELECT Id, SampleName FROM Sample__c"
'''


def test_list_does_not_connect(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--list`` はつながらずに一覧を出す。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    exit_code = cli_main(["--list"])

    assert exit_code == 0
    assert calls == []
    output = capsys.readouterr().out
    assert "1001" in output
    assert "SampleReport" in output
    assert "sample_report.py" in output


def test_show_does_not_connect(
    monkeypatch: pytest.MonkeyPatch,
    fake_config: SimpleNamespace,
    reports_dir: Path,
    fake_salesforce: tuple[FakeSalesforce, list[tuple[Any, ...]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--show`` はつながらずに SOQL を表示する。"""
    salesforce, calls = fake_salesforce
    monkeypatch.setattr("tester.run.site_for", make_site_for(salesforce, calls))
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    exit_code = cli_main(["1001", "--show"])

    assert exit_code == 0
    assert calls == []
    assert capsys.readouterr().out.strip() == "SELECT Id, SampleName FROM Sample__c"


def test_returns_two_when_key_is_unknown(
    fake_config: SimpleNamespace,
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """知らない管理番号なら終了コード 2。"""
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    exit_code = cli_main(["9999"])

    assert exit_code == 2
    assert "管理番号 9999" in capsys.readouterr().err


def test_returns_two_when_key_is_duplicated(
    fake_config: SimpleNamespace,
    reports_dir: Path,
) -> None:
    """管理番号が重複したら終了コード 2。"""
    write_report_file(reports_dir, "first.py", REPORT_BODY)
    write_report_file(reports_dir, "second.py", REPORT_BODY)

    exit_code = cli_main(["--list"])

    assert exit_code == 2


def test_exits_with_two_when_list_and_target_are_given(
    fake_config: SimpleNamespace,
    reports_dir: Path,
) -> None:
    """``--list`` と管理番号を同時に渡したら 2 で終わる（argparse）。"""
    write_report_file(reports_dir, "sample_report.py", REPORT_BODY)

    with pytest.raises(SystemExit) as error:
        cli_main(["--list", "1001"])

    assert error.value.code == 2


def _write_config(directory: Path, downloader_root: Path) -> None:
    """``config.ini`` を書く（サブプロセス用）。"""
    (directory / "config.ini").write_text(
        "[FILES]\n"
        f"DOWNLOADER_ROOT = {downloader_root}\n"
        "REPORTS_DIR = ./reports\n"
        "MASTER_XLSX_PATH = ./input/レポート管理表.xlsx\n"
        "OUTPUT_DIR = ./output\n",
        encoding="utf-8",
    )


def _make_subprocess_env() -> dict[str, str]:
    """サブプロセス用の環境変数（``tester`` と comken  gefundenられるようにする）。"""
    env = os.environ.copy()
    parts = [str(_PROJECT_ROOT)]
    for key in ("purelib", "platlib"):
        path = sysconfig.get_paths().get(key)
        if path:
            parts.append(path)
    if _COMKEN_FALLBACK.is_dir():
        parts.append(str(_COMKEN_FALLBACK))
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    # 標準出力の文字コードが環境依存で変わらないようにする
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _prepare_subprocess_workspace(tmp_path: Path) -> Path:
    """サブプロセス用に、``main.py`` と ``config.ini`` とレポート定義を並べる。"""
    shutil.copy2(_PROJECT_ROOT / "main.py", tmp_path / "main.py")
    _write_config(tmp_path, _DOWNLOADER_ROOT)
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_report_file(reports, "sample_report.py", REPORT_BODY)
    return tmp_path


def _run_subprocess(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """``python main.py ...`` を実際に起動する。

    ``main.py`` をカレント（tmp）へ置いて相対パスで起動することで、
    comken の ``project_dir()`` が tmp を指すようにしている
    （``project_dir()`` は相対の ``sys.argv[0]`` を見たときカレントを返す）。

    **``stdin`` は明示的に DEVNULL にする。** 既定の ``None`` だと Windows の
    標準入力ハンドルをそのまま引き継ぎ、pytest が標準入力を差し替えた
    状態では ``WinError 6``（ハンドルが無効）でパイプを作れなくなることが
    あるため。
    """
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=workspace,
        env=_make_subprocess_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.skipif(
    not (_DOWNLOADER_ROOT / "src" / "soql_reports" / "base.py").is_file(),
    reason=f"ダウンローダーが見つかりません: {_DOWNLOADER_ROOT}",
)
def test_subprocess_list_returns_zero(tmp_path: Path) -> None:
    """``python main.py --list`` を起動して、終了コード 0 を確認する。"""
    workspace = _prepare_subprocess_workspace(tmp_path)

    result = _run_subprocess(workspace, "--list")

    assert result.returncode == 0, result.stderr
    assert "1001" in result.stdout


@pytest.mark.skipif(
    not (_DOWNLOADER_ROOT / "src" / "soql_reports" / "base.py").is_file(),
    reason=f"ダウンローダーが見つかりません: {_DOWNLOADER_ROOT}",
)
def test_subprocess_unknown_key_returns_two(tmp_path: Path) -> None:
    """``python main.py 9999`` を起動して、終了コード 2 を確認する。"""
    workspace = _prepare_subprocess_workspace(tmp_path)

    result = _run_subprocess(workspace, "9999")

    assert result.returncode == 2, result.stderr
