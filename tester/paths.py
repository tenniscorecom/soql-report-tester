"""tester/paths.py — 設定の読み取りとパスの解決。

``config.ini`` の ``[FILES]`` には 4 つのパスだけを書く（全部必須・既定値なし）。

============  ==========================================
キー          意味
============  ==========================================
DOWNLOADER_ROOT  ダウンローダーのフォルダ（import する場所）
REPORTS_DIR      試すレポート定義（``.py``）を置くフォルダ
MASTER_XLSX_PATH レポート管理表（Excel）
OUTPUT_DIR       試した CSV の書き出し先
============  ==========================================

**設定は ``from comken import config`` で直接読む**（``settings.py`` のような
自前の設定読み込みを作らない）。設定値が 1 つでも足りないと ``config.FILES.XXX`` を
参照した時点で comken の ``ConfigKeyNotFoundError`` が出るので、
ここで「足りているか」を検査しなくてよい。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from comken import config

logger = logging.getLogger(__name__)


def downloader_root() -> Path:
    """ダウンローダーのフォルダ（``src`` を含む場所）を返す。"""
    return Path(config.FILES.DOWNLOADER_ROOT)


def reports_dir() -> Path:
    """試すレポート定義（``.py``）を置くフォルダを返す。"""
    return Path(config.FILES.REPORTS_DIR)


def master_xlsx_path() -> Path:
    """レポート管理表（Excel）のパスを返す。"""
    return Path(config.FILES.MASTER_XLSX_PATH)


def output_dir() -> Path:
    """試した CSV の書き出し先を返す。"""
    return Path(config.FILES.OUTPUT_DIR)


def prepare_downloader_imports() -> Path:
    """ダウンローダーの場所を ``sys.path`` の先頭に足して、import できる状態にする。

    レポート定義の ``.py`` は ``from src.soql_reports.base import SoqlReport``
    と書いてあるため、ダウンローダーのフォルダ（``src`` の親）が ``sys.path`` に
    ないと読み込めない。**先頭に足す**のは、他の ``src`` パッケージ（この
    プロジェクト自身は ``src`` を作らないので該当しない）が先に来ると
    ダウンローダーの ``src`` を取り違えるのを避けるため。

    既に ``sys.path`` にある場合は動かさない（2 回目以降の呼び出しは何もしない）。

    Returns:
        ダウンローダーのフォルダ。
    """
    root = downloader_root()
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
        logger.debug("ダウンローダーの場所を sys.path の先頭に足しました: %s", root)
    return root
