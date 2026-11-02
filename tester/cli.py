"""tester/cli.py — 引数の解釈と終了コード。

使い方:

    python main.py 1001                 # REPORTS_DIR から KEY=1001 を探す。URL は管理表から
    python main.py 1001 --url <URL>     # URL を直接指定
    python main.py path\\to\\report_1001.py --url <URL>
    python main.py --list               # 一覧を表示する（接続しない）
    python main.py 1001 --show          # SOQL 本文を表示するだけ（接続しない）

終了コード:

===========  =====================================================
0            成功（件数が一致した／比較できなかった／比較なし）
1            失敗（未完成・取得失敗・件数不一致）
2            使い方の誤り（引数が違う・見つからない・管理表に無い）
===========  =====================================================
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from comken.exceptions import ComkenError

from tester.master import find_url
from tester.paths import master_xlsx_path, reports_dir
from tester.reports import (
    ReportDefinition,
    find_report_by_key,
    is_incomplete,
    load_report_file,
    load_reports,
)
from tester.run import CountStatus, RunResult, run_report

logger = logging.getLogger(__name__)

# 終了コード
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    """コマンドを実行して終了コードを返す。

    Raises:
        SystemExit: 引数の書き方が間違っているとき（argparse が 2 で終了する）。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args, parser)
    except ValueError as exc:
        # 使い方の誤り（見つからない管理等）
        print(f"エラー: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except ComkenError as exc:
        # 取得失敗・加工失敗など
        print(f"エラー: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except Exception as exc:
        # 想定外の失敗。メッセージやトレースは出さない（行の値が混ざるため）。
        # どのファイルの何行で起きたかだけを出す（値が入らないため）
        logger.error("処理に失敗しました: %s", describe_failure(exc))
        print(f"エラー: {type(exc).__name__}", file=sys.stderr)
        return EXIT_FAILURE


def describe_failure(exc: Exception) -> str:
    """失敗した例外を「クラス名（ファイル名:行番号）」という形で表す。

    **例外のメッセージとトレースは含めない。** レポートの中身（行の値）が
    混ざったメッセージが画面やログに出るのは避けたい。 発生位置だけなら
    値は含まれず、どこで失敗したかを追える。
    """
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return f"{type(exc).__name__}（発生位置不明）"
    last = frames[-1]
    return f"{type(exc).__name__}（{Path(last.filename).name}:{last.lineno}）"


def _build_parser() -> argparse.ArgumentParser:
    """引数の定義を組み立てる。"""
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description=(
            "SoqlReport を 1 本だけ試す（管理表の「SOQL」列やスケジュールは通さない）。"
            "読み取り専用の道具で、Salesforce への書き込みはしない。"
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="管理番号（例: 1001）またはレポート定義の .py ファイルのパス",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Salesforce のレポート URL（省略時は管理表から管理番号で探す）",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="SOQL 本文を表示するだけ（Salesforce にはつながらない）",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="レポート定義の一覧を表示する（Salesforce にはつながらない）",
    )
    return parser


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """引数の組合せに合わせて処理を分岐する。"""
    if args.list:
        if args.target is not None:
            parser.error("--list のときは管理番号やファイルを指定できません")
        _print_report_list(load_reports(reports_dir()))
        return EXIT_OK
    if args.target is None:
        parser.error("管理番号（例: 1001）またはレポート定義の .py を指定してください")
    definition = _resolve_definition(args.target)
    soql_text = _read_soql(definition)
    if args.show:
        print(soql_text)
        return EXIT_OK
    if is_incomplete(soql_text):
        print(
            f"未完成です（{definition.path.name}）: "
            "SOQL の先頭に未完成の印があります。Salesforce には問い合わせません。"
        )
        return EXIT_FAILURE
    url = args.url or find_url(master_xlsx_path(), definition.key)
    result = run_report(definition, url, soql_text)
    _print_result(result)
    if result.count_status == CountStatus.MISMATCH:
        return EXIT_FAILURE
    return EXIT_OK


def _resolve_definition(target: str) -> ReportDefinition:
    """引数（管理番号または ``.py`` のパス）からレポート定義を 1 件取り出す。"""
    if target.lower().endswith(".py"):
        return load_report_file(Path(target))
    return find_report_by_key(reports_dir(), target)


def _read_soql(definition: ReportDefinition) -> str:
    """レポート定義の SOQL を読み取る。"""
    try:
        return str(definition.report_cls().soql())
    except Exception as exc:
        raise ComkenError(
            f"SOQL を取得できませんでした: クラス={definition.class_name}, "
            f"例外={type(exc).__name__}"
        ) from exc


def _print_report_list(definitions: list[ReportDefinition]) -> None:
    """レポート定義の一覧を表示する（接続しない）。"""
    if not definitions:
        print("レポート定義がありません。")
        return
    print("管理番号 | クラス名 | ファイル名 | 状態")
    for definition in definitions:
        print(
            f"{definition.key} | {definition.class_name} | "
            f"{definition.path.name} | {_state_of(definition)}"
        )


def _state_of(definition: ReportDefinition) -> str:
    """一覧に出す状態（実行可／未完成／SOQL が読めない）。"""
    try:
        soql_text = str(definition.report_cls().soql())
    except Exception as exc:
        return f"SOQL を読めません（{type(exc).__name__}）"
    if is_incomplete(soql_text):
        return "未完成"
    return "実行可"


def _print_result(result: RunResult) -> None:
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
