"""conftest.py — 业务系统 pytest 共享夹具。

在 import rdapp 之前把 RD_DB_DIR 指向临时目录，实现数据库隔离，
避免测试污染真实业务数据（业务系统/data/rd_expense.db）。
"""
import os
import sys
import tempfile
from pathlib import Path

# 业务系统目录加入 sys.path，使 `import rdapp` 可用
_BIZ = Path(__file__).resolve().parent.parent
if str(_BIZ) not in sys.path:
    sys.path.insert(0, str(_BIZ))

# 测试隔离数据库：必须在任何 rdapp 模块 import 之前设置
_TMP = tempfile.mkdtemp(prefix="rd_importer_test_")
os.environ["RD_DB_DIR"] = _TMP
