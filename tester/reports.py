"""tester/reports.py — レポート定義（``.py`` ファイル）を読み込む。

soql-collector が作るレポート定義は、1 レポート 1 ファイルの ``.py`` で、
``SoqlReport`` のサブクラスを 1 つだけ持つ（例: ``class HogeReport(SoqlReport)``）。

読み込みは ``importlib.util.spec_from_file_location`` で行う（``import`` 文では
動かないため）。 1 ファイルから定義された ``SoqlReport`` サブクラスが
**ちょうど 1 つ**でなければエラーにする。 管理番号（``KEY``）が空 ·
管理番号が重複などの設定ミスもエラーにする（黙って片方を選ぶと、
違うレポートを試してしまう）。

フォルダを 1 つのパッケージとしてまとめて読み込む ``load_package()`` もある。
``reports/`` のようなフォルダの中のレポート定義を全部読み込んで公開する
（``from reports import *``）ためのもの。
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tester.downloader import incomplete_marker, soql_report_base
from tester.paths import prepare_downloader_imports

if TYPE_CHECKING:  # 実行時は import しない（config.ini を読む前に失敗させないため）
    from src.soql_reports.base import SoqlReport

logger = logging.getLogger(__name__)

# ファイル名が ``_`` で始まるものは雛形として読み飛ばす
# （ダウンローダーの自動登録と同じ規則。KEY が空の雛形を誤って読まないため）
TEMPLATE_PREFIX = "_"

# 読み込むときのモジュール名。レポートの ``.py`` 同士で名前が被らないように接頭辞を付ける
MODULE_PREFIX = "_soql_report_tester_"


@dataclass(frozen=True)
class ReportDefinition:
    """レポート定義 1 件（``.py`` ファイル 1 個）の読み取り結果。"""

    #: 管理番号（``SoqlReport.KEY``）
    key: str
    #: クラス名（一覧の表示に使う）
    class_name: str
    #: 定義が置いてあるファイル
    path: Path
    #: ``SoqlReport`` のサブクラス
    report_cls: type[SoqlReport]
    #: Salesforce のレポート ID（``SoqlReport.REPORT_ID``。無いときは空文字）
    report_id: str


def load_report_file(path: Path) -> ReportDefinition:
    """``.py`` ファイルを読み込んで、レポート定義 1 件を返す。

    Raises:
        ValueError: ファイルが無い、Python として読めない、定義された
            ``SoqlReport`` サブクラスが 1 つでない、``KEY`` が空のとき。
    """
    if not path.is_file():
        raise ValueError(f"レポート定義が見つかりません: {path}")
    # 先にダウンローダーの場所を ``sys.path`` に入れておく。レポート定義は
    # ``from src.soql_reports.base import SoqlReport`` と書いてあるため、
    # 読み込む前に ``src`` が見つかるようにしておかないと import で失敗する
    prepare_downloader_imports()
    module_name = f"{MODULE_PREFIX}{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Python のファイルとして読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    # ``definition_of_class()`` が ``sys.modules`` を見てファイル位置を確かめるため、
    # 実行前に登録する（読み込みに失敗したら登録を取り消す）
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        # 例外のメッセージには行の値が入ることがあるため、型名だけを出す
        raise ValueError(
            f"レポート定義を読み込めませんでした: {path}（{type(exc).__name__}）"
        ) from exc
    return definition_of_class(pick_report_class(module))


def definition_of_class(report_cls: type) -> ReportDefinition:
    """レポートのクラスから、レポート定義 1 件を返す。

    ファイル位置は ``sys.modules`` にあるクラスの居場所から確かめる
    （``sys.modules[report_cls.__module__].__file__``）。

    Raises:
        ValueError: クラスが属するモジュールが ``sys.modules`` に無い、
            管理番号（``KEY``）が空のとき。
    """
    module = sys.modules.get(report_cls.__module__)
    file_path = getattr(module, "__file__", None)
    if not file_path:
        raise ValueError(
            f"レポートのクラスの居場所が分かりません: {report_cls.__module__}.{report_cls.__name__}"
        )
    key = str(getattr(report_cls, "KEY", "") or "").strip()
    if not key:
        raise ValueError(
            f"管理番号（KEY）が空です: {file_path}\n"
            'SoqlReport.KEY に管理番号を書いてください（例: KEY = "1001"）。'
        )
    # レポート ID は基底クラスに無いので ``getattr`` で読む
    # （ダウンローダーの ``SoqlReport`` は変更しない）
    report_id = str(getattr(report_cls, "REPORT_ID", "") or "").strip()
    return ReportDefinition(
        key=key,
        class_name=report_cls.__name__,
        path=Path(file_path),
        report_cls=report_cls,
        report_id=report_id,
    )


def load_package(package_name: str, folder: str) -> list[str]:
    """フォルダ内のレポート定義を全部読み込んで、レポート名のリストを返す。

    戻り値は **パッケージの中の名前**（``report_1001`` など）のリストで、
    ``from reports import *`` の ``__all__`` に使える形。

    - ファイル名が ``_`` で始まるもの（``__init__.py`` や雛形）は読み飛ばす
    - Python の名前として書けないファイル名（``1001.py`` など）も読み飛ばす
      （``import`` できないため。警告を出す）
    - 管理番号（``KEY``）の検査と重複検査は **しない**
      （使うとき＝``to_csv()`` と CLI で検査する）

    Raises:
        ValueError: レポート定義が読み込めないとき。
    """
    prepare_downloader_imports()
    names: list[str] = []
    for path in sorted(Path(folder).glob("*.py")):
        stem = path.stem
        if stem.startswith(TEMPLATE_PREFIX):
            continue
        if not stem.isidentifier():
            logger.warning(
                "Python の名前として書けないファイル名なので読み飛ばします: %s", path.name
            )
            continue
        try:
            importlib.import_module(f"{package_name}.{stem}")
        except Exception as exc:
            # 例外のメッセージには行の値が入ることがあるため、型名だけを出す
            raise ValueError(
                f"レポート定義を読み込めませんでした: {path}（{type(exc).__name__}）"
            ) from exc
        names.append(stem)
    return names


def load_reports(reports_root: Path) -> list[ReportDefinition]:
    """フォルダ内のレポート定義を全部読み込む。

    ファイル名が ``_`` で始まるものは読み飛ばす。 管理番号が重複したらエラー。

    Raises:
        ValueError: フォルダが無い、定義が読めない、管理番号が重複しているとき。
    """
    if not reports_root.is_dir():
        raise ValueError(
            f"レポート定義のフォルダが見つかりません: {reports_root}\n"
            "config.ini の [FILES] REPORTS_DIR を確認してください。"
        )
    definitions = [
        load_report_file(path)
        for path in sorted(reports_root.glob("*.py"))
        if not path.name.startswith(TEMPLATE_PREFIX)
    ]
    _reject_duplicate_keys(definitions)
    return definitions


def find_report_by_key(reports_root: Path, key: str) -> ReportDefinition:
    """管理番号が一致するレポート定義を 1 件返す。

    Raises:
        ValueError: 管理番号に対応する定義が無いとき（ある管理番号を
            メッセージに添えて、選び方が分かるようにする）。
    """
    definitions = load_reports(reports_root)
    for definition in definitions:
        if definition.key == key:
            return definition
    available = "、".join(definition.key for definition in definitions) or "（なし）"
    raise ValueError(
        f"管理番号 {key} のレポート定義が {reports_root} にありません。\nある管理番号: {available}"
    )


def is_incomplete(soql_text: str) -> bool:
    """SOQL が未完成の印で始まっているか（``True`` なら Salesforce には問い合わせない）。"""
    return soql_text.lstrip().startswith(incomplete_marker())


def pick_report_class(module: object) -> type:
    """モジュールから、定義された ``SoqlReport`` サブクラスを 1 つ選んで返す。

    ``import`` しただけのクラス（``from ... import SomeReport``）は数えない。
    対象は、そのファイルの中で定義されたクラスだけ。

    Raises:
        ValueError: サブクラスがちょうど 1 つでないとき。
    """
    base = soql_report_base()
    module_name = getattr(module, "__name__", "")
    path = Path(getattr(module, "__file__", "") or "")
    candidates = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, base)
        and obj is not base
        and obj.__module__ == module_name
    ]
    if len(candidates) != 1:
        names = [obj.__name__ for obj in candidates] or "（なし）"
        raise ValueError(
            "レポート定義のファイルには SoqlReport のサブクラスを1つだけ書いてください: "
            f"{path}（見つかったクラス: {names}）"
        )
    return candidates[0]


def _reject_duplicate_keys(definitions: list[ReportDefinition]) -> None:
    """管理番号が重複していたらエラーにする（1 つの管理番号に 1 つのファイル）。"""
    by_key: dict[str, list[str]] = {}
    for definition in definitions:
        by_key.setdefault(definition.key, []).append(definition.path.name)
    duplicates = {key: names for key, names in by_key.items() if len(names) >= 2}
    if not duplicates:
        return
    details = "、".join(f"{key}（{', '.join(names)}）" for key, names in sorted(duplicates.items()))
    raise ValueError(
        f"管理番号が重複しています: {details}\n1 つの管理番号に 1 つのファイルを置いてください。"
    )
