"""server.py — FastHTML app 创建与挂载 + 路由注册触发 + 服务入口

按 example01 独立性/耦合度批判报告建议：把原 `routes/__init__.py` 中的 **app 创建与挂载**
（fast_app、静态资源目录、no-cache middleware、js-errors、热重载、serve_only）抽到独立模块。
路由子模块需要 `app` 时显式 `from server import app`，不再经由 `routes` 命名空间总线拉取。

**关键导入顺序（循环依赖处理）**：
    main.py → `from server import app`
    server.py 先创建 `app`，再 `import routes` 触发各路由子模块注册；
    routes/__init__.py → `from server import app`（此时 app 已存在）+ `from . import pages, ...`。
    依赖「先建 app、后导路由」的严格顺序，勿调整。

SSE 契约（与 agent_runtime.stream_agent_chat 一致）见 routes/__init__.py 头部说明。
"""
from __future__ import annotations

import os
import sys
import time as _hr_time
from pathlib import Path

# 冻结态（PyInstaller）：HERMES_HOME 必须在任何 hermes 导入前指向可写路径
if getattr(sys, "frozen", False):
    os.environ.setdefault(
        "HERMES_HOME",
        os.path.join(os.path.dirname(sys.executable), "hermes_data"),
    )

from fasthtml.common import fast_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

APP_TITLE = "Hermes Desktop"


# ---------------------------------------------------------------------------
# 静态资源目录（开发态 = ./static；冻结态 = _MEIPASS/static）
# ---------------------------------------------------------------------------
def _static_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / "static"
        if p.is_dir():
            return str(p)
    return str(Path(__file__).resolve().parent / "static")


STATIC_DIR = _static_dir()

app, rt = fast_app(
    pico=False, htmx=False, live=False,          # 全手写前端，不引入 pico/htmx
    title=APP_TITLE,
    static_path=STATIC_DIR,                       # 见 routes/__init__.py 头部约束 1
    default_hdrs=False,                           # 页面结构完全自定义
)

# ── 开发态：前端源码模块禁用浏览器缓存 ─────────────────────────────────────
# FastHTML 静态服务不设 Cache-Control，浏览器会对 /src/*.js 做启发式缓存，
# 导致升级后仍加载旧版 ES module（界面不更新）。这里对前端脚本/样式加
# no-cache：浏览器每次向服务端重新验证，etag 变化即重新下载。
class _NoCacheStatic(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/src/") or path.endswith((".js", ".mjs", ".css")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.add_middleware(_NoCacheStatic)

# ── 前端 JS 错误捕获（调试用）────────────────────────────────
_JS_ERRORS = []


@app.post('/api/js-errors')
def _recv_js_error(req: dict):
    _JS_ERRORS.append(req)
    return {'ok': True}


@app.get('/api/js-errors')
def _get_js_errors():
    return {'errors': _JS_ERRORS, 'count': len(_JS_ERRORS)}


# ── 触发路由子模块注册（app 创建后导入；路由定义在 routes/ 包）─────────────
import routes  # noqa: E402

# ── P1：首轮 Agent 预热（后台线程预构造默认模型实例，首轮对话直接命中缓存）──
# 仅当已配置有效 api_key 才预热；无 key / 构造失败均静默跳过（best-effort，
# 不阻塞服务启动，不产生日志噪音）。
def _start_agent_warmup() -> None:
    import threading

    def _warmup() -> None:
        try:
            import hermes_config as _hc
            cfg = _hc.get_active_model_cfg()
            if not cfg or not cfg.get("api_key"):
                return  # 未配置有效 Key → 不预热
            from agent_runtime._cache import prewarm_agent
            prewarm_agent(cfg)
        except Exception as _e:  # noqa: BLE001
            print(f"[warmup] skip: {type(_e).__name__}: {_e}", file=sys.stderr)

    threading.Thread(target=_warmup, daemon=True, name="agent-warmup").start()


_start_agent_warmup()

# ── 热重载（开发调试用：前端代码修改后自动刷新页面）────────────────────
_HR_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_HR_SNAPSHOT: dict[str, float] = {}


def _hr_take_snapshot() -> dict[str, float]:
    """扫描 static/ 下所有文件的修改时间。"""
    snap: dict[str, float] = {}
    base = _HR_STATIC_DIR
    if not os.path.isdir(base):
        return snap
    for root, _dirs, files in os.walk(base):
        for f in files:
            fp = os.path.join(root, f)
            try:
                snap[fp] = os.path.getmtime(fp)
            except OSError:
                pass
    return snap


@app.get('/api/hot-reload')
async def _hot_reload_sse():
    """SSE 端点：前端代码变更时推送 'reload' 事件。
    浏览器连接后每 1s 轮询文件修改时间，检测到变化时推送信号。
    """
    global _HR_SNAPSHOT
    if not _HR_SNAPSHOT:
        _HR_SNAPSHOT = _hr_take_snapshot()

    import asyncio

    async def _event_stream():
        global _HR_SNAPSHOT
        # 先发一个 connected 事件确认连接成功
        yield f"event: connected\ndata: {_hr_time.time()}\n\n"
        while True:
            await asyncio.sleep(1.0)
            curr = _hr_take_snapshot()
            if curr != _HR_SNAPSHOT:
                _HR_SNAPSHOT = curr
                yield f"event: reload\ndata: {_hr_time.time()}\n\n"
                # 发完即停，浏览器收到后刷新页面，会重新连接
                return

    return StreamingResponse(_event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


def serve_only() -> None:
    """纯服务模式：不开窗口，只起 HTTP（调试 / 冒烟 / 远程访问用）。"""
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "5001")), log_level="warning")


# 注意：这里**必须**用 `__name__` 守卫而不是 FastHTML 惯用的模块级 `serve()`。
# launcher.py 会 `from main import app` 再自己起 uvicorn；模块级 serve() 一旦被
# 求值就可能在导入期阻塞或触发 reload 子进程，在冻结态尤其危险。
if __name__ == "__main__":
    serve_only()
