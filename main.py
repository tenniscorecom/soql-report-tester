"""レポートをまとめて bulk_query か query で取得して、CSV に書き出す。

試すレポートは src/run.py の KEYS に並べる。全部まとめて試すなら RUN_ALL を True にする。
"""

from comken import comken_logger

from src.run import main

if __name__ == "__main__":
    comken_logger.setup_local_logging()
    main()
