"""bridge.py — 连接系统桥接/装配层（纯桥接，不作为独立应用）

职责
====
在融合模式下，把「业务系统」接入「Agent系统（example01 纯净底座）」：

1. **注册 rd 领域工具**：Agent系统纯净版 app_tools 只含演示工具（sogou_weixin），
   不会自动加载连接系统的 rd_biz。本模块在装配时显式调用 `rd_biz.register_into(registry)`
   把 db_operation / analyze_* 等 rd 领域工具注册进 Hermes 全局 registry（toolset=rd_db），
   使 Agent 对话能调用业务领域工具。

2. **装配 app**：提供 `get_fused_app()`，从 Agent系统（example01）server 导入 app/rt，
   业务系统在此基础上挂载业务路由（由 rdapp.app 的融合分支完成）。

设计约束
========
- 连接系统**不创建自己的 app / 不起独立服务**，仅作为装配与桥接层被 main 调用。
- 惰性导入 + try/except，Agent 底座或业务系统任一不可用时优雅降级。
"""
from __future__ import annotations

import sys
import shutil
from pathlib import Path


def _project_root() -> Path:
    """返回三系统根目录（连接系统 main.py 的 parent.parent）。"""
    return Path(__file__).resolve().parent.parent


def ensure_syspath() -> None:
    """把三系统目录加入 sys.path（顺序 Agent→业务→连接，Agent 最前）。"""
    base = _project_root()
    for _d in (base / "Agent系统", base / "业务系统", base / "连接系统"):
        _s = str(_d)
        if _s not in sys.path:
            sys.path.insert(0, _s)


def install_rd_skills() -> list[str]:
    """融合装配时把连接系统 skills/* 安装到 Agent 系统 HERMES_HOME/skills。

    Agent 系统技能机制：扫描 <HERMES_HOME>/skills/*/SKILL.md 加载专家技能。
    连接系统 /skills 是随包分发的 rd 业务技能（rd-governor / rd-policy-builder），
    融合装配时同步到 Agent 底座技能区，使 Agent 对话能加载 rd 业务专家技能
    （业务系统已回归纯业务，不含 SKILL）。

    连接系统 /skills 为权威源，同名技能目录会完整覆盖同步到 Agent 端，
    保证 Agent 加载的是随包分发的最新版。返回本次同步的技能名列表。
    """
    installed = []
    try:
        src = _project_root() / "连接系统" / "skills"
        if not src.exists():
            return []
        try:
            from hermes_config import _paths as _hp  # type: ignore
            home = _hp.get_hermes_home()
        except Exception:
            from agent_runtime import get_hermes_home as _gh  # type: ignore
            home = _gh()
        skills_dir = Path(home) / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        def _cp(s, d):
            d.mkdir(parents=True, exist_ok=True)
            for e in s.iterdir():
                dd = d / e.name
                if e.is_dir():
                    _cp(e, dd)
                else:
                    shutil.copy2(e, dd)

        for item in sorted(src.iterdir()):
            if not item.is_dir():
                continue
            target = skills_dir / item.name
            # 连接系统 /skills 为权威源：完整同步覆盖到 Agent 技能区
            if target.exists():
                shutil.rmtree(target)
            _cp(item, target)
            installed.append(item.name)
        if installed:
            print(f"[bridge] 已安装 rd 业务技能到 Agent 技能区：{', '.join(installed)}")
        return installed
    except Exception as _e:  # noqa: BLE001
        print(f"[bridge] 技能安装失败（降级）：{type(_e).__name__}: {_e}")
        return []


def register_rd_tools() -> list[str]:
    """把 rd 领域工具注册进 Hermes 全局 registry；返回注册的工具名列表。

    Agent系统纯净版 `agent_runtime.register_pure_python_tools()` 只会 `import app_tools`
    （命中 Agent系统/app_tools，仅含演示工具），不会加载连接系统的 rd_biz。
    因此这里显式调用连接系统 `rd_biz.register_into(registry)`。
    """
    try:
        from tools.registry import registry  # type: ignore
        from rd_biz import register_into
        names = list(register_into(registry) or [])
        if names:
            print(f"[bridge] 已注册 rd 领域工具：{', '.join(names)}")
        return names
    except Exception as _e:  # noqa: BLE001
        print(f"[bridge] rd 领域工具注册失败（降级，不影响启动）：{type(_e).__name__}: {_e}")
        return []


def inject_business_context() -> None:
    """包装 Agent系统 agent_runtime.stream_agent_chat，注入 rd 业务数据快照。

    业务系统 app.py 融合分支会把 `BUSINESS_CONTEXT_HOOK` 设置到 Agent系统
    routes.chat 模块（含业务数据快照生成函数）。但 Agent系统纯净版 chat.py
    自身不读取该属性。这里在**更底层**包装 stream_agent_chat：调用前把 hook
    生成的业务数据快照追加到 system 消息，使 Agent 对话能感知业务数据。
    （技术可颠覆：不修改 Agent系统任何文件。）
    """
    try:
        import agent_runtime
        from routes import chat as _chat
        _orig = agent_runtime.stream_agent_chat
        if getattr(_orig, "_rd_bridge_wrapped", False):
            return

        def _wrapped(messages, model_cfg, **kw):
            hook = getattr(_chat, "BUSINESS_CONTEXT_HOOK", None)
            if callable(hook):
                try:
                    biz = hook()
                except Exception as _e:  # noqa: BLE001
                    biz = f"（业务数据快照不可用：{_e}）"
                if biz:
                    msgs = list(messages or [])
                    block = "\n\n[业务数据快照]\n" + biz
                    if msgs and isinstance(msgs[0], dict) and msgs[0].get("role") == "system":
                        msgs[0] = dict(msgs[0], content=str(msgs[0].get("content", "")) + block)
                    else:
                        msgs.insert(0, {"role": "system", "content": "以下为本系统当前业务数据快照：" + block})
                    messages = msgs
            return _orig(messages, model_cfg, **kw)

        _wrapped._rd_bridge_wrapped = True
        agent_runtime.stream_agent_chat = _wrapped
        print("[bridge] 已注入业务数据快照（Agent 对话可感知 rd 业务数据）")
    except Exception as _e:  # noqa: BLE001
        print(f"[bridge] 业务上下文注入失败（降级）：{type(_e).__name__}: {_e}")


def _install_download_bridge(app):

    """给融合 app 挂「下载桥接」中间件：桌面 pywebview 下载适配。



    仅在批量导入页（路径含 /import/）且响应为 HTML 时，在 </body> 前注入一段脚本，

    把「下载模板」锚点（<a href="/import/{entity}/template">）点击劫持为调用

    window.pywebview.api.download_template(entity)（由原生保存对话框落盘）。

    pywebview/WebView2 会拦截普通 attachment 锚点下载（点击无反应），故此桥接仅服务

    于桌面窗口；普通浏览器无 window.pywebview，锚点走浏览器默认下载，不受影响。

    本中间件为纯 ASGI 包装：非 /import/ 路径或非 HTML 响应完全透传（不缓冲），

    因此 SSE（/api/chat，路径不含 /import/）流式输出不受破坏。

    """

    _SNIPPET = (
        "<script>\n"
        "(function(){\n"
        "function _bind(){\n"
        "if(!window.pywebview||!window.pywebview.api||!window.pywebview.api.download_template)return false;\n"
        "document.addEventListener('click',function(e){\n"
        "var a=e.target&&e.target.closest?e.target.closest('a[href*=\"/import/\"][href$=\"/template\"]'):null;\n"
        "if(!a)return;e.preventDefault();\n"
        "var m=a.getAttribute('href').match(/\\/import\\/([^\\/]+)\\/template/);\n"
        "if(m&&m[1])window.pywebview.api.download_template(m[1]);\n"
        "});\n"
        "return true;\n"
        "}\n"
        "if(_bind())return;\n"
        "window.addEventListener('pywebviewready',_bind);\n"
        "window.addEventListener('DOMContentLoaded',_bind);\n"
        "setTimeout(_bind,500);\n"
        "})();\n"
        "</script>"
    ).encode("utf-8")



    async def _wrapper(scope, receive, send):

        if scope["type"] != "http":

            await app(scope, receive, send)

            return

        path = scope.get("path", "")

        if "/import/" not in path:

            await app(scope, receive, send)

            return

        status = None

        headers = None

        is_html = False

        started = False

        body = bytearray()



        async def _send(message):

            nonlocal status, headers, is_html, started, body

            if message["type"] == "http.response.start":

                status = message["status"]

                headers = message["headers"]

                ctype = b""

                for k, v in headers:

                    if k == b"content-type":

                        ctype = v.lower()

                        break

                is_html = b"text/html" in ctype

                if not is_html:

                    await send(message)

                    started = True

                return

            if message["type"] == "http.response.body":

                if not started:

                    body += message.get("body", b"")

                    if message.get("more_body"):

                        return

                    final = bytes(body)

                    if "下载模板".encode("utf-8") in final:

                        final = final.replace(b"</body>", _SNIPPET + b"</body>", 1)

                    new_headers = []
                    for _k, _v in headers:
                        if _k == b"content-length":
                            new_headers.append((_k, str(len(final)).encode("latin-1")))
                        else:
                            new_headers.append((_k, _v))
                    await send({"type": "http.response.start", "status": status, "headers": new_headers})

                    await send({"type": "http.response.body", "body": final, "more_body": False})

                else:

                    await send(message)



        await app(scope, receive, _send)



    return _wrapper





def fuse_business_into_agent():
    """融合装配：把 rd 业务路由挂载到 Agent 底座 app，注入业务快照，返回融合 app。

    流程：
      1. ensure_syspath + install_rd_skills + register_rd_tools
      2. 从 Agent 底座 server 导入 app/rt
      3. 用业务系统 mount_rd_routes 把 16 个业务路由 + dashboard 挂到 Agent app
      4. 把业务 get_business_snapshot 设为 Agent 底座 routes.chat 的 BUSINESS_CONTEXT_HOOK
      5. inject_business_context 包装 stream_agent_chat 读取快照
      返回挂好业务路由的 Agent app（含 Agent 对话）。
    Agent 底座不可用则回退业务系统自建纯业务 app（无 Agent 对话）。
    """
    ensure_syspath()
    install_rd_skills()
    register_rd_tools()
    try:
        from server import app as _agent_app, rt as _agent_rt
        from rdapp.app import mount_rd_routes, get_business_snapshot
        mount_rd_routes(_agent_app, _agent_rt)
        try:
            from routes import chat as _chat  # type: ignore
            _chat.BUSINESS_CONTEXT_HOOK = get_business_snapshot
        except Exception as _e:  # noqa: BLE001
            print(f"[bridge] 业务快照 HOOK 设置失败（降级）：{type(_e).__name__}: {_e}")
        inject_business_context()
        print("[bridge] 已把 rd 业务路由挂载到 Agent 底座 app（融合 app 就绪）")
        return _install_download_bridge(_agent_app)
    except Exception as _e:  # noqa: BLE001
        print(f"[bridge] 融合装配失败，回退业务自建 app：{type(_e).__name__}: {_e}")
        try:
            from rdapp import app as _biz_app
            return _install_download_bridge(_biz_app)
        except Exception:
            try:
                from server import app as _a2
                return _a2
            except Exception:
                return None