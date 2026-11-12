"""reports/ の .py を全部 import して、管理番号（KEY）からレポートを引けるようにする。"""

from importlib import import_module
from pkgutil import iter_modules

from src.reports.base import SoqlReport

REPORTS_BY_KEY: dict[str, type[SoqlReport]] = {}

for module_info in iter_modules(__path__):
    module = import_module(f"{__name__}.{module_info.name}")
    for value in vars(module).values():
        if isinstance(value, type) and issubclass(value, SoqlReport) and value is not SoqlReport:
            REPORTS_BY_KEY[value.KEY] = value
