# -*- coding: utf-8 -*-
"""native_bridge.py — 连接系统原生桥接层（pywebview js_api）

向桌面前端暴露原生能力（pywebview window.js_api）：技能文件夹安装、文件保存、
已批准命令执行、资源管理器打开、预览窗口、最大化切换。
独立成模块以提升 main.py 的内聚（main 仅负责启动装配）。
"""
from __future__ import annotations

import os
import subprocess


class AgentApi:
    """暴露给前端 JS 的原生桥接（window.pywebview.api）。

    技能文件夹安装走原生路径：直接弹出系统文件夹选择框，从真实文件系统路径
    安装，规避 WebView2 下 webkitdirectory 上传不稳定 / 超大负载导致失败的问题。
    """

    def pick_and_install_skill(self, name=""):
        import webview
        from pathlib import Path as _P
        try:
            from hermes_config import _paths as _hp
            _home = _P(_hp.get_hermes_home())
        except Exception:
            from agent_runtime import get_hermes_home as _gh
            _home = _P(_gh())
        def _install_skill_folder(name, files):
            skills_dir = _home / "skills" / (name or "unnamed")
            skills_dir.mkdir(parents=True, exist_ok=True)
            for rel, data in files:
                fp = skills_dir / rel
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(data)
            return {"ok": True, "path": str(skills_dir), "files": len(files)}

        try:
            folders = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "无法打开文件夹选择：" + str(e)}
        if not folders:
            return {"ok": False, "error": "未选择文件夹"}
        folder = folders[0]
        if not os.path.isdir(folder):
            return {"ok": False, "error": "所选路径不是文件夹"}
        sk = os.path.join(folder, "SKILL.md")
        if not os.path.isfile(sk):
            return {"ok": False, "error": "所选文件夹中未找到 SKILL.md，无法识别为技能"}
        files = []
        for dp, dns, fns in os.walk(folder):
            for f in fns:
                full = os.path.join(dp, f)
                rel = os.path.relpath(full, folder).replace("\\", "/")
                try:
                    data = open(full, "rb").read()
                except Exception:
                    continue
                files.append((rel, data))
        if not files:
            return {"ok": False, "error": "文件夹为空"}
        return _install_skill_folder(name or "", files)

    def save_file(self, filename, content, mimetype="text/plain"):
        """前端导出对话等内容时调用原生保存对话框，避免 WebView2 拦截程序化下载。"""
        import webview
        from pathlib import Path

        default_dir = str(Path.home() / "Documents")
        default_path = os.path.join(default_dir, filename)
        try:
            paths = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory=default_dir,
                save_filename=filename,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "无法打开保存对话框：" + str(e)}
        if not paths:
            return {"ok": False, "error": "用户取消保存"}
        path = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            # 确保扩展名与默认文件名一致
            if not Path(path).suffix and Path(filename).suffix:
                path = path + Path(filename).suffix
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"ok": True, "path": path}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "保存失败：" + str(e)}

    def run_command(self, cmd: str, timeout: int = 120):
        """审批弹窗「批准执行」后由前端（pywebview 原生窗口）调用：执行用户已批准的删除操作。

        委托 Agent系统（底座）的 `agent_runtime.execute_approved_command`——纯 Python 进程内删除，
        无 shell、无 Git Bash、无 PortableGit 依赖。详见该函数的文档说明。
        """
        from agent_runtime import execute_approved_command
        return execute_approved_command(cmd, timeout)

    def open_in_explorer(self, path: str):
        """在 Windows 资源管理器中打开文件所在文件夹（并选中文件）或打开文件夹本身。"""
        if not path or not os.path.exists(path):
            return {"ok": False, "error": "路径不存在"}
        try:
            if os.path.isdir(path):
                os.startfile(path)
            else:
                # /select 参数需要反斜杠路径
                target = os.path.normpath(path)
                subprocess.Popen(["explorer", "/select,", target], shell=False)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def open_preview_window(self, url: str):
        """预览工具（preview_fasthtml_app）启动本地服务后，由前端触发弹出原生预览窗口。

        由 pywebview 的 js_api 调用，运行在 pywebview 主线程（即 webview.start() 所在线程），
        因此可安全地在此创建新的原生窗口显示该 ASGI 应用的 URL。窗口沿用宿主运行时
        （Edge / WebView2），与桌面端一致。浏览器 / 无原生窗口场景前端会退化为 window.open。
        """
        import webview

        if not url:
            return {"ok": False, "error": "缺少预览 URL"}
        try:
            webview.create_window("预览", url, js_api=AgentApi())
            return {"ok": True, "url": url}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "打开预览窗口失败：" + str(e), "url": url}

    def toggle_maximize(self):
        """设置中心弹窗右上角「最大化」按钮：在最大化 / 还原之间切换。

        调用 pywebview 原生 Window 的 maximize()/restore()。用窗口自定义属性
        `_is_max` 记录当前状态，避免反复最大化导致无法还原。
        """
        import webview

        try:
            w = webview.windows[0]
            if getattr(w, "_is_max", False):
                w.restore()
                w._is_max = False
            else:
                w.maximize()
                w._is_max = True
            return {"ok": True, "maximized": bool(getattr(w, "_is_max", False))}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "切换最大化失败：" + str(e)}

    def download_template(self, entity: str = ""):
        """桌面窗口内下载批量导入模板：转发业务系统模板生成，弹原生保存对话框落盘。

        pywebview/WebView2 会拦截 <a href> 指向 Content-Disposition: attachment 的下载
        （点击无反应）。故前端注入脚本把导入页「下载模板」锚点劫持为调用本方法：
        连接系统仅转发业务系统 routes_import.import_template 的模板 bytes，不承载任何
        业务逻辑，保存交互交给原生保存对话框。
        """
        import re
        import webview
        from pathlib import Path
        from urllib.parse import unquote

        try:
            # 模板生成逻辑在业务系统，连接系统仅转发
            from rdapp.routes_import import import_template as _it
            resp = _it(entity)
            data = resp.body  # xlsx bytes
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "模板生成失败：" + str(e)}

        fname = "导入模板_" + (entity or "template") + ".xlsx"
        try:
            cdisp = resp.headers.get("content-disposition", "")
            m = re.search(r"filename\*=UTF-8''([^;]+)", cdisp)
            if m:
                fname = unquote(m.group(1))
        except Exception:  # noqa: BLE001
            pass

        try:
            default_dir = str(Path.home() / "Documents")
            paths = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG, directory=default_dir, save_filename=fname
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "无法打开保存对话框：" + str(e)}
        if not paths:
            return {"ok": False, "error": "用户取消保存"}
        path = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            if not Path(path).suffix and Path(fname).suffix:
                path = path + Path(fname).suffix
            with open(path, "wb") as f:
                f.write(data)
            return {"ok": True, "path": path, "size": len(data), "entity": entity}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "保存失败：" + str(e)}
