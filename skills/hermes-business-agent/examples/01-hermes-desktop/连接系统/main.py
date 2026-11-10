"""main.py — 入口文件（pywebview + uvicorn + 进程内 Hermes Library 运行时）

由 fasthtml-desktop 技能 bootstrap 生成，并集成 hermes-dev 的 Library 模式方案：
把 hermes-agent 内核以 Python 库形式烤进 EXE，在当前进程内直接运行 Agent
（run_agent.AIAgent），无需拉起网关子进程、无需内置 PortableGit。terminal 工具集
被禁用，文件/进程操作改由纯 Python 工具与进程内 run_python 完成。
窗口标题：研发费用管理系统
"""
import sys
import os
import subprocess
import time
from pathlib import Path

if getattr(sys, 'frozen', False):
    # onefile 冻结模式：业务代码解包到 _MEIPASS 根
    _src = str(Path(sys._MEIPASS) / "连接系统")
    _base = Path(sys._MEIPASS)
else:
    # 开发模式：main.py 位于「连接系统」目录内，_base 为项目根
    _base = Path(__file__).resolve().parent.parent
    _src = str(Path(__file__).parent)

if _src not in sys.path:
    sys.path.insert(0, _src)

# 三层解耦：把「连接系统 / 业务系统 / Agent系统」三个目录都加入 sys.path。
# Agent系统（底座）可整体替换（见 docs/替换底座.md）；业务/连接不动。
for _d in (_base / "连接系统", _base / "业务系统", _base / "Agent系统"):
    _s = str(_d)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# ── PyInstaller onefile SSL 证书兜底 ────────────────────────────────
# onefile 模式下 certifi 的 cacert.pem 若未被 --collect-data certifi 收集，
# 运行时 SSL_CERT_FILE 会指向 _MEI.../certifi/cacert.pem 但文件不存在，
# 导致 OpenAI/httpx 客户端初始化抛出 "SSL_CERT_FILE points to a missing CA bundle"。
# 这里先做运行时修复：若环境变量指向不存在的文件，改用 certifi.where() 或彻底取消。
def _ensure_ssl_certs() -> None:
    valid_path = ""
    try:
        import certifi
        valid_path = certifi.where()
        if not os.path.isfile(valid_path):
            valid_path = ""
    except Exception:
        valid_path = ""

    for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        val = os.environ.get(env_name)
        if val and not os.path.isfile(val):
            if valid_path:
                os.environ[env_name] = valid_path
            else:
                os.environ.pop(env_name, None)

    if valid_path and not os.environ.get("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = valid_path


_ensure_ssl_certs()

# ── 进程内 Library 模式：Hermes 运行时随主进程启动，无 --hermes-child 子进程 ──

# ── rd 领域能力由连接系统 rd_biz 直接注册进 Hermes registry（不再需要独立 MCP DB server）──

# ── onefile 冻结模式：代码执行沙箱子进程分流 + 递归防护 ──
# tools.code_execution_tool 用 ``subprocess.Popen([sys.executable, script.py])``
# 派生沙箱子进程；冻结后 sys.executable 就是这个 EXE 本身，若不加守卫，子进程会
# 重新走 start() 拉起第二个 HTTP 服务并卡死。此前曾实测 EXE 启动后进程 3→191
# 指数增长、内存耗尽致系统濒临崩溃，故在此统一拦截所有「把 EXE 当作 python
# 派生的 .py 子进程」以及「继承环境的递归子进程」。
#
# 1) 代码执行沙箱子进程（HERMES_RPC_SOCKET 场景）：在本进程内直接执行该脚本后
#    退出，让父进程的 execute_code 正常收回 stdout/stderr。脚本内的
#    ``from hermes_tools import *`` 通过子进程环境里的 PYTHONPATH（tmpdir 在前）
#    解析，并经 HERMES_RPC_SOCKET 回连父进程的 RPC 服务线程完成工具调用。
if getattr(sys, "frozen", False) and len(sys.argv) >= 2 and os.path.isfile(sys.argv[1]):
    if "HERMES_RPC_SOCKET" in os.environ:
        _sandbox_script = sys.argv[1]
        try:
            with open(_sandbox_script, "r", encoding="utf-8") as _f:
                _sandbox_code = _f.read()
            exec(compile(_sandbox_code, _sandbox_script, "exec"), {"__name__": "__main__"})
        except SystemExit:
            raise
        except BaseException:
            import traceback as _tb
            _tb.print_exc()
            sys.exit(1)
        sys.exit(0)
    # 2) 其他把 EXE 当作 python 派生的 .py 子进程：一律退出，防止递归
    else:
        print("[guard] 检测到 EXE 被派生为脚本子进程（argv=%s），退出" % sys.argv[1:], file=sys.stderr)
        sys.exit(0)

# ── onefile 冻结模式：递归/多实例熔断器 ───────────────────────────
# 若 EXE 在某条未识别链路中被当作解释器反复派生（进程指数增长的主因），这些
# 子进程会继承 RD_MAIN_PID 环境变量。此处识别「由主实例派生的非主进程」：
# RD_MAIN_PID 存在且不等于当前进程，说明本进程是递归/重复派生的子进程，直接
# 退出，避免再次进入 start() 造成进程爆炸。
# 注：execute_code 沙箱子进程的环境会被 _scrub_child_env 清掉 RD_MAIN_PID，
# 因此不会被本熔断器误伤（其已被上方守卫 1 拦截）。
if getattr(sys, "frozen", False):
    _rd_main = os.environ.get("RD_MAIN_PID")
    if _rd_main is not None and _rd_main != str(os.getpid()):
        print("[guard] 检测到递归子进程（主实例 pid=%s），本进程退出" % _rd_main, file=sys.stderr)
        sys.exit(0)
    os.environ["RD_MAIN_PID"] = str(os.getpid())

import uvicorn, webview, threading, socket, signal

from native_bridge import AgentApi


def wait_for_server(url: str, timeout: int = 30) -> bool:
    import time
    import urllib.request
    import urllib.error
    for _ in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except urllib.error.URLError:
            time.sleep(1)
    return False


def find_free_port(start: int = 5001, end: int = 6000) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("未找到可用端口")


def start() -> None:
    PORT = int(os.environ.get("PORT", 0)) or find_free_port()
    print(f"[OK] 研发费用管理系统启动：http://127.0.0.1:{PORT}")
    print("[INFO] 关闭窗口或按 Ctrl+C 退出")

    _server_instance = None

    # Hermes 运行时由 Agent系统（底座）提供，连接系统不再初始化旧的 rd 自研启动器。
    def _cleanup(*args):
        if _server_instance:
            _server_instance.should_exit = True
        print("[INFO] 正在退出...")
        os._exit(0)
    signal.signal(signal.SIGINT, _cleanup)

    # ── 连接系统融合装配：把 rd 业务路由挂载到 Agent 底座 app（含 Agent 对话）──
    # 业务系统已解耦（不 import Agent），融合装配全部由 bridge.fuse_business_into_agent 完成。
    try:
        from bridge import fuse_business_into_agent
        app = fuse_business_into_agent()
    except Exception as _be:  # noqa: BLE001
        print(f"[main] 融合装配失败（降级）：{_be}")
        try:
            from rdapp import app
        except ImportError:
            from app import app

    _config = uvicorn.Config(app, host="127.0.0.1", port=PORT, reload=False)
    _server_instance = uvicorn.Server(_config)
    threading.Thread(target=_server_instance.run, daemon=True).start()

    # （旧的技能市场 / 内容市场预热已废弃——被 Agent系统 新版替代）


    if not wait_for_server(f"http://127.0.0.1:{PORT}"):
        print("[WARN] 服务启动超时，仍尝试打开窗口")

    # 无界面模式（headless / 纯 HTTP 服务）：用于服务器部署、CI 冒烟测试、
    # 以及无显示环境下仅验证 API/静态资源。设置 RD_NO_GUI=1 即跳过 GUI 窗口，
    # 进程常驻运行 HTTP 服务，直到收到 SIGTERM/SIGINT。
    if os.environ.get("RD_NO_GUI"):
        print("[headless] RD_NO_GUI 已设置：跳过 webview 窗口，仅运行 HTTP 服务")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("[headless] 收到中断，退出")
        return

    webview.create_window("研发费用管理系统", f"http://127.0.0.1:{PORT}/dashboard", js_api=AgentApi())
    print("WEBVIEW_WINDOW_OPENED", flush=True)
    webview.start()  # 阻塞直到窗口关闭
    print("WEBVIEW_WINDOW_CLOSED", flush=True)


if __name__ == "__main__":
    start()
