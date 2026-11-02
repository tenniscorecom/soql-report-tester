"""reports — 試すレポート定義（``.py``）をまとめて公開するパッケージ。

このフォルダに置いたレポート定義（``.py``）を全部読み込んで、名前
（``report_1001`` など）を ``__all__`` に載せる。 呼び出し側は::

    from reports import *

    report_1001              # モジュール
    report_1001.Report1001   # クラスそのもの

と書ける。 ``import reports`` して ``reports.report_1001.Report1001`` と
書くこともできる。

**``config.ini`` の ``[FILES] REPORTS_DIR`` は使わない。** 公開するのは
このパッケージのあるフォルダ（``__path__``）の中のファイルだけ。
"""

from tester.reports import load_package

__all__ = load_package(__name__, __path__[0])
