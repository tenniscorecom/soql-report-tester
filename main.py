"""レポートをまとめて bulk_query で取得して、CSV に書き出す。

試すレポートは src/run.py の REPORTS に並べる。
"""

from comken import comken_logger

from src.run import main

if __name__ == "__main__":
    comken_logger.setup_local_logging()
    main()
