"""biz_main.py — 业务系统独立入口（研发费用管理系统，纯业务，不含 Agent）

用途：让业务系统脱离 Agent系统 / 连接系统独立运行（一键启动 / 独立打包 EXE）。
与融合模式（连接系统/main.py）并存：融合模式提供 Agent 对话增强，独立模式专注业务。

运行：
    python biz_main.py            # pywebview 桌面窗口
    RD_NO_GUI=1 python biz_main.py  # headless 纯 HTTP（调试/CI）
    RD_BIZ_STANDALONE=1 python biz_main.py  # 强制独立模式（默认即独立）
"""
import os
import sys
import threading
import socket
from pathlib import Path

# ── 独立模式：强制自建 app，不依赖连接系统 ─────────────────────
os.environ.setdefault("RD_BIZ_STANDALONE", "1")

# 把业务系统目录加入 sys.path，使 `import rdapp` 可用
_BASE = Path(__file__).resolve().parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

# 数据目录：独立部署时数据库与配置放到业务系统/data（可与融合模式共用 RD_DB_DIR 覆盖）
os.environ.setdefault("RD_DB_DIR", str(_BASE))


def find_free_port(start=8800):
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def wait_for_server(url, timeout=10):
    import time
    import urllib.request
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def start():
    import uvicorn
    from rdapp.app import app

    PORT = int(os.environ.get("PORT", 0)) or find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, reload=False)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    if not wait_for_server(f"http://127.0.0.1:{PORT}/dashboard"):
        print(f"[WARN] 服务启动超时: http://127.0.0.1:{PORT}")

    if os.environ.get("RD_NO_GUI"):
        print(f"[headless] 研发费用管理系统（独立模式）已运行: http://127.0.0.1:{PORT}/dashboard")
        try:
            while True:
                import time
                time.sleep(3600)
        except KeyboardInterrupt:
            server.should_exit = True
            return

    import webview
    webview.create_window("研发费用管理系统", f"http://127.0.0.1:{PORT}/dashboard")
    webview.start()


if __name__ == "__main__":
    start()
