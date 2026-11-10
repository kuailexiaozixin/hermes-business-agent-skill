"""routes_import.py — 批量导入前端路由（工时登记打样）。

提供：导入页（模板下载 + 上传）、预检回执、确认落库。
人工上传路径：parse_upload → rows_from_sheet → import_batch（先预检后入库）。
"""
from __future__ import annotations

import json
import os

from fasthtml.common import *  # noqa: F403
from fasthtml.core import APIRouter
from starlette.datastructures import UploadFile
from starlette.responses import Response
from urllib.parse import quote

from . import importer
from .components import alert_box, data_table, empty_state, page_layout
from .routes_compliance import _build_xlsx  # 复用既有纯标准库 xlsx 生成器

ar = APIRouter()

# 实体 → 对应列表页（用于「返回」跳转）
_LIST_URL = {
    "worktime": "/worktime",
    "personnel": "/rd-personnel",
    "expenses": "/expenses",
    "equipment": "/equipment",
    "materials": "/materials",
    "labor_cost": "/labor-costs",
    "projects": "/projects",
    "outsourcing": "/outsourcing",
    "others": "/others",
    "special_income": "/special-income",
    "evidence": "/evidence",
}


# ── 导入页 ─────────────────────────────────────────────────
@ar("/import/{entity}")
def import_page(entity: str):
    if entity not in importer.IMPORT_MAP:
        return _entity_missing(entity)
    spec = importer.IMPORT_MAP[entity]
    return page_layout(
        f"批量导入·{spec['label']}",
        "首页 / 批量导入",
        _LIST_URL.get(entity, "/dashboard"),
        Div(
            alert_box(
                f"批量导入 {spec['label']}：请先下载模板并按要求填写，支持 xlsx / csv。"
                "上传后先「预检」，确认无误再提交入库。",
                "info",
            ),
            Form(
                Div(
                    Div(Label("模板文件", cls="form-label", for_="import_file"),
                        Input(type="file", name="file", id="import_file", accept=".xlsx,.csv",
                              cls="form-input", required=True, aria_label="选择要导入的模板文件"),
                        cls="form-group"),
                    cls="form-row",
                ),
                Div(
                    Button("预检", type="submit", cls="btn btn-primary"),
                    A("下载模板", href=f"/import/{entity}/template", cls="btn btn-outline"),
                    A("返回", href=_LIST_URL.get(entity, "/dashboard"), cls="btn btn-outline"),
                    style="display:flex;gap:10px;",
                ),
                method="post",
                action=f"/import/{entity}/preview",
                enctype="multipart/form-data",
            ),
            cls="card",
        ),
    )


# ── 模板下载 ───────────────────────────────────────────────
# 静态模板目录（离线预置 / 版本管理）：优先读 templates/，缺失回退动态生成（与 IMPORT_MAP 保持一致）
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

@ar("/import/{entity}/template")
def import_template(entity: str):
    if entity not in importer.IMPORT_MAP:
        return _entity_missing(entity)
    spec = importer.IMPORT_MAP[entity]
    fname = f"导入模板_{entity}.xlsx"
    path = os.path.join(_TEMPLATES_DIR, fname)
    if os.path.exists(path):
        # 静态模板：离线预置 / 版本管理
        with open(path, "rb") as f:
            data = f.read()
    else:
        # 回退：动态生成（保持模板与 IMPORT_MAP 一致）
        header = spec["template"]
        sample = spec.get("sample") or [""] * len(header)
        data = _build_xlsx([(spec["label"], [header, sample])])
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


# ── 预检（不落库）─────────────────────────────────────────
@ar("/import/{entity}/preview", methods=["POST"])
async def import_preview(entity: str, file: UploadFile):
    if entity not in importer.IMPORT_MAP:
        return _entity_missing(entity)
    raw = await file.read()
    filename = file.filename or ""
    try:
        sheet = importer.parse_upload(raw, filename)
        rows = importer.rows_from_sheet(sheet, entity)
    except Exception as e:  # noqa: BLE001
        return _result_page(entity, None, f"文件解析失败：{e}")
    if not rows:
        return _result_page(entity, None, "未解析到有效数据行（模板需含表头，首行不可为表头示例数据之外的占位）")
    result = importer.import_batch(entity, rows, dry_run=True)
    return _result_page(entity, result, None)


# ── 确认落库 ──────────────────────────────────────────────
@ar("/import/{entity}/commit", methods=["POST"])
def import_commit(entity: str, payload: str = ""):
    if entity not in importer.IMPORT_MAP:
        return _entity_missing(entity)
    try:
        rows = json.loads(payload or "[]")
    except Exception as e:  # noqa: BLE001
        return _result_page(entity, None, f"回执数据损坏，请重新上传：{e}")
    result = importer.import_batch(entity, rows, dry_run=False)
    return _result_page(entity, result, None)


# ── 回执渲染 ──────────────────────────────────────────────
def _entity_missing(entity: str):
    return page_layout(
        "批量导入", "首页 / 批量导入", _LIST_URL.get(entity, "/dashboard"),
        Div(alert_box(f"未知导入实体：{entity}", "danger"),
            A("← 返回列表", href=_LIST_URL.get(entity, "/dashboard"), cls="btn btn-outline"), cls="card"),
    )


def _result_page(entity: str, result: dict | None, error: str | None):
    spec = importer.IMPORT_MAP.get(entity, {})
    title = f"批量导入·{spec.get('label', entity)}"
    blocks = []

    if error:
        blocks.append(alert_box(error, "danger"))

    if result is None:
        blocks.append(A("← 重新上传", href=f"/import/{entity}", cls="btn btn-outline"))
        return page_layout(title, "首页 / 批量导入", _LIST_URL.get(entity, "/dashboard"), Div(*blocks, cls="card"))

    # 统计条
    blocks.append(alert_box(
        f"共 {result['total']} 行：成功 {result['success']} 行，失败 {result['failed']} 行。"
        + ("（当前为预检，未入库）" if result["dry_run"] else "（已入库）"),
        "info" if result["failed"] == 0 else "warning",
    ))

    # 失败行
    if result["errors"]:
        err_rows = [[e["row"], e["error"]] for e in result["errors"]]
        blocks.append(Div(
            Div(Span("失败明细（请修正后重新上传）", cls="card-title")),
            data_table(["行号", "错误原因"], err_rows) if err_rows else empty_state("⚠️", "无失败行"),
            cls="card",
        ))

    # 成功行 + 确认导入（仅预检阶段且存在成功行时）
    if result["dry_run"] and result["success"] > 0:
        ok_rows = [[r["row"], r["data"].get("person_name", ""), r["data"].get("project_code", ""),
                    r["data"].get("work_date", ""), r["data"].get("hours", "")] for r in result["rows"]]
        blocks.append(Div(
            Div(Span("预检通过（待确认）", cls="card-title")),
            data_table(["行号", "人员", "项目", "日期", "工时"], ok_rows),
            Form(
                Input(type="hidden", name="payload", value=json.dumps(
                    [r["data"] for r in result["rows"]], ensure_ascii=False)),
                Div(
                    Button("确认导入", type="submit", cls="btn btn-primary"),
                    A("放弃", href=f"/import/{entity}", cls="btn btn-outline"),
                    style="display:flex;gap:10px;",
                ),
                method="post",
                action=f"/import/{entity}/commit",
            ),
            cls="card",
        ))
    else:
        blocks.append(Div(
            Div(Span("导入结果", cls="card-title")),
            empty_state("✓", f"{spec.get('label', entity)} 处理完成") if result["success"] else empty_state("📋", "无成功行"),
            A("← 返回列表", href=_LIST_URL.get(entity, "/dashboard"), cls="btn btn-outline"),
            cls="card",
        ))

    return page_layout(title, "首页 / 批量导入", _LIST_URL.get(entity, "/dashboard"), *blocks)
