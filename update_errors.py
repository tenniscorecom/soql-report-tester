"""
update_errors.py — docs/ERRORS.md のエラー名の表を作り直す

`エラー一覧の更新.bat` か `python update_errors.py` で実行する。

tester/ で定義した ComkenError のサブクラスと comken のエラーを、docstring から表にする。
エラーを足したり docstring を直したりしたら実行する（手で表を直すと、すぐ古くなるため）。
"""

import logging

from comken import comken_logger
from comken.core.files import project_dir
from comken.exceptions import ComkenError
from comken.tools.errors_doc import ERRORS_DOC_PATH, update_errors_doc

import tester

logger = logging.getLogger(__name__)


def main() -> None:
    """docs/ERRORS.md の自動生成部分を作り直す。"""
    root = project_dir()
    if update_errors_doc(root, project_package=tester):
        logger.info("エラー一覧を更新しました: %s", root / ERRORS_DOC_PATH)
    else:
        logger.info("エラー一覧は最新です: %s", root / ERRORS_DOC_PATH)


if __name__ == "__main__":
    comken_logger.setup_local_logging()
    try:
        main()
    except ComkenError as e:
        logger.error("処理を中断しました: %s", e)
        raise
