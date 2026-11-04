"""reports/ の .py を全部 import して、レポートのクラスを reports.クラス名 で使えるようにする。"""

from importlib import import_module
from pkgutil import iter_modules

from src.soql_reports.base import SoqlReport

for module_info in iter_modules(__path__):
    module = import_module(f"{__name__}.{module_info.name}")
    for name, value in vars(module).items():
        if isinstance(value, type) and issubclass(value, SoqlReport) and value is not SoqlReport:
            globals()[name] = value
