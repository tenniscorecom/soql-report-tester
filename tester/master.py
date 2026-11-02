"""tester/master.py — レポート管理表から Salesforce の URL を探す。

管理表（Excel）の ``管理表`` シートから、**この道具が本当に必要な 2 列**
（``ID`` と ``Salesforce URL``）だけを読む。 読み方は soql-collector の
``src/master.py`` に合わせている（comken の ``Excel`` 経由で読む）。

- ``ID`` … 管理番号（社内で決める論理的な番号。Salesforce のレポート ID ではない）
- ``Salesforce URL`` … Salesforce でレポートを開いたときのアドレス

``--url`` を指定したときは管理表を開かない（このモジュールは呼ばれない）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from comken.exceptions import ComkenError
from comken.toolbox.excel import Excel

logger = logging.getLogger(__name__)

# 管理表のシート名（comken の規約で実ファイルは ``PY_管理表``）
SHEET_NAME = "管理表"

# 読む列（この道具に必要な 2 つだけ）
COL_KEY = "ID"
COL_URL = "Salesforce URL"


def load_urls(path: Path) -> dict[str, str]:
    """管理表を読んで ``{管理番号: Salesforce URL}`` を返す。

    ``ID`` が空の行は読み飛ばす（管理番号が特定できない行は対象外のため）。
    同じ管理番号が複数行あるときは **先に見つけた行**を返す
    （どれか 1 つを選んでも同じ管理番号を持つため）。

    Raises:
        ValueError: 管理表が無い・読めない・必要な列が無いとき。
    """
    if not path.is_file():
        raise ValueError(
            f"レポート管理表が見つかりません: {path}\n"
            "config.ini の [FILES] MASTER_XLSX_PATH を確認してください。"
        )
    try:
        with Excel(path, read_only=True) as excel:
            table = excel.data_sheet(SHEET_NAME).table().read()
    except ComkenError as exc:
        raise ValueError(f"レポート管理表を読めませんでした: {path}（{exc}）") from exc
    try:
        needed = table.select(COL_KEY, COL_URL)
    except ComkenError as exc:
        raise ValueError(
            f"レポート管理表に「{COL_KEY}」列と「{COL_URL}」列がありません: {path}"
        ) from exc
    urls: dict[str, str] = {}
    for row in needed:
        key = str(row.get(COL_KEY) or "").strip()
        if not key:
            continue
        urls.setdefault(key, str(row.get(COL_URL) or "").strip())
    logger.info("レポート管理表を読込ました: path=%s, 件数=%d", path, len(urls))
    return urls


def find_url(path: Path, key: str) -> str:
    """管理番号に対応する Salesforce の URL を返す。

    Raises:
        ValueError: 管理表に管理番号が無い、または URL が空のとき。
    """
    urls = load_urls(path)
    if key not in urls:
        raise ValueError(
            f"レポート管理表に管理番号 {key} がありません: {path}\n"
            "管理表の「ID」列に同じ番号があるか確認してください。"
        )
    url = urls[key]
    if not url:
        raise ValueError(
            f"レポート管理表の管理番号 {key} の「{COL_URL}」が空です: {path}\n"
            "Salesforce でレポートを開いたときのアドレスをそのまま貼り付けてください。"
        )
    return url
