# -*- coding: utf-8 -*-
"""
rd_biz.py — 研发费用管理系统领域工具（业务扩展点，迁移自 rd 的 _register_domain_tools）

把 rd 的 `operations.AGENT_TOOLS`（7 个领域工具）注册进 Hermes registry 的
自定义 toolset `rd_db`。handler 直调 `operations.dispatch_tool`，返回 JSON 字符串
（registry 契约）。与 01 底座完全解耦：注册进自定义 toolset 后 registry 自动发现，
设置中心「工具与集成」面板自动列出。

命名铁律：不可把 app_tools/ 改名为 tools/（遮蔽 hermes-agent 顶层 tools 包）。

连接系统定位：仅作连接/装配/注册/交互，不承载任何具体业务功能。除遍历
`operations.AGENT_TOOLS` 注册业务系统已有工具外，另提供 `import_template`
桥接工具：其业务逻辑（模板生成）完全在业务系统 routes_import.import_template，
连接系统仅负责调用业务系统能力并落盘交付，不实现业务逻辑。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

MAX_TOOL_OUTPUT = 100_000

# 批量导入实体（与业务系统 importer.IMPORT_MAP 一致）
_IMPORT_ENTITIES = [
    "worktime", "personnel", "expenses", "equipment", "materials",
    "labor_cost", "projects", "outsourcing", "others",
    "special_income", "evidence",
]

_EMOJI = {
    "db_operation": "\U0001f5c3\ufe0f",          # 🗃️
    "analyze_project": "\U0001f4ca",             # 📊
    "analyze_metrics": "\U0001f4c8",             # 📈
    "analyze_capitalization": "\U0001f9ee",      # 🧮
    "dashboard_summary": "\U0001f4cb",           # 📋
    "analyze_expense_trend": "\U0001f4c9",       # 📉
    "generate_packages": "\U0001f4e6",
    "generate_rd_policy": "\U0001f9fe",           # 🧾
    "import_batch": "\U0001f4e5",             # 📥
    "import_template": "\U0001f4c4",           # 📄
}


def _load_ops():
    """惰性加载 rd 业务操作层；rdapp 不可用时返回 None（降级，不崩）。"""
    try:
        from rdapp import operations as _ops
        return _ops
    except Exception:
        return None


def register_into(registry) -> list[str]:
    """注册 rd 领域工具到 registry；返回注册的工具名列表。rdapp 缺失时返回空。"""
    _ops = _load_ops()
    if _ops is None:
        return []

    def _make_handler(tool_name: str):
        def _handler(args: dict, **kwargs) -> str:
            try:
                result = _ops.dispatch_tool(tool_name, args or {})
            except Exception as e:  # noqa: BLE001
                result = {"ok": False, "error": f"领域工具执行异常：{e}"}
            payload = json.dumps(result, ensure_ascii=False, default=str)
            if len(payload) > MAX_TOOL_OUTPUT:
                payload = payload[:MAX_TOOL_OUTPUT] + "…[truncated]"
            return payload
        return _handler

    names: list[str] = []
    for t in _ops.AGENT_TOOLS:
        fn = t["function"]
        name = fn["name"]
        schema = {
            "name": name,
            "description": fn["description"],
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        }
        registry.register(
            name=name, toolset="rd_db", schema=schema,
            handler=_make_handler(name), is_async=False,
            description=f"RD expense domain tool: {name}",
            emoji=_EMOJI.get(name, "\U0001f9f0"),
            max_result_size_chars=MAX_TOOL_OUTPUT, override=True,
        )
        names.append(name)

    # ── 批量导入模板下载（桥接工具）────────────────────────────
    # 业务逻辑（模板生成）完全在业务系统 routes_import.import_template；
    # 连接系统仅做桥接：调用业务系统能力 → 落盘交付 → 返回文件路径。
    # 连接系统不承载任何具体业务功能，仅承担连接/交互/装配。
    try:
        registry.register(
            name="import_template", toolset="rd_db", schema=_import_template_schema(),
            handler=_import_template_handler, is_async=False,
            description="RD expense import template bridge tool",
            emoji=_EMOJI.get("import_template", "\U0001f4c4"),
            max_result_size_chars=MAX_TOOL_OUTPUT, override=True,
        )
        names.append("import_template")
    except Exception as _e:  # noqa: BLE001
        print(f"[rd_biz] import_template 桥接注册失败（降级）：{type(_e).__name__}: {_e}")

    return names


def _import_template_schema():
    return {
        "name": "import_template",
        "description": (
            "生成某实体批量导入的 Excel 模板（含表头与示例行），落盘并返回文件路径，"
            "供用户按模板填写后上传。实体与 import_batch 一致（11 个）。\n"
            "当用户需要下载/获取批量导入模板、了解某实体导入列结构时调用本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "enum": _IMPORT_ENTITIES,
                            "description": "待生成模板的导入实体"},
                "out_dir": {"type": "string",
                             "description": "可选：模板输出目录，缺省为项目根/output/import_templates"},
            },
            "required": ["entity"],
        },
    }


def _import_template_handler(args: dict, **kwargs) -> str:
    """桥接业务系统 routes_import.import_template，落盘并返回文件路径。"""
    args = args or {}
    entity = str(args.get("entity") or "").strip()
    try:
        from rdapp.routes_import import import_template as _biz_import_template
        from rdapp import importer as _importer
    except Exception as _e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"业务系统不可用：{type(_e).__name__}: {_e}"},
                          ensure_ascii=False)
    if entity not in _importer.IMPORT_MAP:
        return json.dumps({"ok": False, "error": f"未知实体：{entity}",
                           "available": sorted(_importer.IMPORT_MAP.keys())},
                          ensure_ascii=False)
    try:
        resp = _biz_import_template(entity)
        data = getattr(resp, "body", None)
        if not isinstance(data, bytes):
            return json.dumps({"ok": False, "error": "模板生成失败：未取得二进制数据"},
                              ensure_ascii=False)
    except Exception as _e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"模板生成异常：{type(_e).__name__}: {_e}"},
                          ensure_ascii=False)
    out_dir = str(args.get("out_dir") or "")
    if not out_dir:
        out_dir = str(Path(__file__).resolve().parent.parent / "output" / "import_templates")
    try:
        os.makedirs(out_dir, exist_ok=True)
        fname = f"导入模板_{entity}.xlsx"
        path = os.path.join(out_dir, fname)
        with open(path, "wb") as f:
            f.write(data)
    except Exception as _e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"模板落盘失败：{type(_e).__name__}: {_e}"},
                          ensure_ascii=False)
    spec = _importer.IMPORT_MAP[entity]
    result = {
        "ok": True, "entity": entity, "label": spec.get("label"),
        "columns": spec.get("template", []), "file_path": path,
        "file_size": len(data),
    }
    return json.dumps(result, ensure_ascii=False, default=str)
