"""业务系统根级独立入口（三系统架构门禁 biz_independent_entry 识别）。

统一从 rdapp.app 暴露 FastHTML 应用 app 与路由对象 rt，作为业务系统的根级入口。
业务系统保持纯净：本文件不 import 任何 Agent 模块，可独立运行（脱离 Agent/连接系统）：

    python biz_main.py                 # 桌面窗口 / headless 见 biz_main.py
    RD_NO_GUI=1 python 业务系统/app.py  # 经本入口启动

与融合模式（连接系统/main.py）并存：融合模式由 bridge.fuse_business_into_agent 装配，
此处提供业务独立入口。
"""
from rdapp.app import app, rt  # noqa: F401
