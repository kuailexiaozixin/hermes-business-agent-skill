"""routes_sharing.py — 共用设备分摊与多用途设备分摊比例（缺口⑫）

功能：
- 共用设备分摊登记：研发/生产/其他用途机时登记，计算研发用途占比，审批后回写折旧总账
- 多用途设备分摊比例：设备-项目级分摊比例（DeviceSharingRatio），支持按生效月份管理
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date

from .db import (
    equipment_tb, equipment_depreciation_tb,
    equipment_sharing_tb, device_sharing_ratios_tb,
    projects_tb, log_audit,
)
from .components import (
    page_layout, data_table, empty_state, alert_box,
    month_options,
)
from .routes_datacenter import log_data_change

ar = APIRouter()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _eq_options(selected=""):
    opts = [Option("— 请选择设备 —", value="")]
    for e in equipment_tb(order_by="code"):
        opts.append(Option(f"{e.code} {e.name}", value=e.id, selected=str(e.id) == str(selected)))
    return opts


def _proj_options(selected=""):
    opts = [Option("— 请选择项目 —", value="")]
    for p in projects_tb():
        opts.append(Option(f"{p.code} {p.name}", value=p.id, selected=str(p.id) == str(selected)))
    return opts


# ── 共用设备分摊登记 ──────────────────────────────────────

@ar("/equipment/sharing")
def equipment_sharing_index(month: str = ""):
    """共用设备分摊登记列表"""
    month = month or date.today().strftime("%Y-%m")
    rows = equipment_sharing_tb(order_by="-id")

    table_rows = []
    for r in rows:
        eq = equipment_tb[r.equipment_id] if r.equipment_id else None
        total_h = (r.rd_hours or 0) + (r.prod_hours or 0) + (r.other_hours or 0)
        ratio = (r.computed_ratio * 100) if r.computed_ratio is not None else (
            ((r.rd_hours or 0) / total_h * 100) if total_h else 0.0
        )
        actions = []
        if r.applied:
            actions.append(Span("已回写", cls="badge badge-green"))
        else:
            if not r.approver:
                actions.append(
                    Form(Button("审批", cls="btn btn-success btn-sm", type="submit"),
                         method="post",
                         action=f"/equipment/sharing/{r.id}/approve",
                         style="display:inline-block;margin-right:6px;"))
            actions.append(
                Form(Button("回写折旧", cls="btn btn-primary btn-sm", type="submit"),
                     method="post",
                     action=f"/equipment/sharing/{r.id}/apply",
                     style="display:inline-block;margin-right:6px;"))
            actions.append(
                Form(Button("删除", cls="btn btn-danger btn-sm", type="submit"),
                     method="post",
                     action=f"/equipment/sharing/{r.id}/delete",
                     style="display:inline-block;"))
        table_rows.append([
            eq.code if eq else "—", eq.name if eq else "—", r.cost_month,
            f"{r.rd_hours or 0:.0f}", f"{r.prod_hours or 0:.0f}", f"{r.other_hours or 0:.0f}",
            r.basis or "机时",
            f"{ratio:.1f}%",
            r.approver or "待审批",
            r.applied and "已回写" or "未回写",
            Div(*actions) if actions else "—",
        ])

    body = data_table(
        ["设备编码", "设备名称", "月份", "研发机时", "生产机时", "其他机时", "依据",
         "研发占比", "审批人", "回写状态", "操作"],
        table_rows) if table_rows else empty_state("tool", "暂无共用设备分摊登记")

    return page_layout(
        "共用设备分摊", "首页 / 研发资产 / 共用设备分摊", "/equipment",
        Div(
            Div(
                Span("共用设备分摊登记", style="font-size:15px;font-weight:600;"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("设备", cls="nat-label"), Select(*_eq_options(), name="equipment_id", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("月份", cls="nat-label"),
                        Select(*month_options(month), name="cost_month", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("研发机时", cls="nat-label"), Input(name="rd_hours", type="number", step="0.5", value="0", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("生产机时", cls="nat-label"), Input(name="prod_hours", type="number", step="0.5", value="0", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("其他机时", cls="nat-label"), Input(name="other_hours", type="number", step="0.5", value="0", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("分摊依据", cls="nat-label"),
                        Select(Option("机时", value="机时", selected=True),
                               Option("产量", value="产量"), Option("面积", value="面积"),
                               Option("人工工时", value="人工工时"),
                               name="basis", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("备注", cls="nat-label"), Input(name="note", cls="input", placeholder="可选"),
                        cls="nat-field", style="flex:1.5;"),
                    Div(Label("", cls="nat-label"), Button("保存登记", cls="btn btn-primary", type="submit", style="width:100%;"),
                        cls="nat-field", style="flex:0.8;"),
                    style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;"
                ),
                method="post", action="/equipment/sharing/save",
                cls="nat-form"
            ),
            cls="card"
        ),
        Div(
            Div("分摊登记列表", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            body,
            cls="card"
        ),
        Div(
            alert_box("共用设备须按合理依据（机时/产量/面积）拆分研发用途占比，经审批后回写当月折旧总账，避免全额计入研发费用被纳税调整。", "info"),
            cls="card"
        ),
    )


@ar("/equipment/sharing/save", methods=["POST"])
def equipment_sharing_save(equipment_id: str, cost_month: str, rd_hours: str = "0",
                           prod_hours: str = "0", other_hours: str = "0",
                           basis: str = "机时", note: str = ""):
    """保存共用设备分摊登记，自动计算研发占比"""
    if not equipment_id or not cost_month:
        return alert_box("设备与月份为必填项。", "danger")
    rd = float(rd_hours or 0)
    prod = float(prod_hours or 0)
    other = float(other_hours or 0)
    total = rd + prod + other
    ratio = round(rd / total, 4) if total > 0 else 0.0

    rec = equipment_sharing_tb.insert(
        equipment_id=int(equipment_id), cost_month=cost_month,
        rd_hours=rd, prod_hours=prod, other_hours=other,
        basis=basis, computed_ratio=ratio, note=note,
        created_at=_now(),
    )
    log_audit("SHARING_CREATE", "EquipmentSharing", rec.id,
              detail=f"共用设备分摊登记 设备={equipment_id} 月份={cost_month} 研发占比={ratio:.2%}", actor="系统管理员")
    log_data_change("equipment_sharing", getattr(rec, "id", 0), "computed_ratio",
                    old_val="", new_val=f"设备{equipment_id} {cost_month} 研发占比{ratio:.2%}",
                    operator="system")
    return RedirectResponse(url="/equipment/sharing", status_code=303)


@ar("/equipment/sharing/{sid}/approve", methods=["POST"])
def equipment_sharing_approve(sid: int):
    """审批通过：记录审批人"""
    r = equipment_sharing_tb[sid]
    if not r:
        return alert_box("登记不存在", "danger")
    if not r.approver:
        r.approver = "系统管理员"
        r.approve_date = date.today().strftime("%Y-%m-%d")
        equipment_sharing_tb.update(r)
        log_audit("SHARING_APPROVE", "EquipmentSharing", r.id,
                  detail=f"审批共用设备分摊 设备={r.equipment_id} 月份={r.cost_month}", actor="系统管理员")
    return RedirectResponse(url="/equipment/sharing", status_code=303)


@ar("/equipment/sharing/{sid}/apply", methods=["POST"])
def equipment_sharing_apply(sid: int):
    """回写折旧总账：将分摊占比写入当月折旧记录的 rd_usage_ratio"""
    r = equipment_sharing_tb[sid]
    if not r:
        return alert_box("登记不存在", "danger")
    if r.applied:
        return alert_box("该记录已回写，无需重复操作", "warning")
    if not r.approver:
        return alert_box("请先审批再回写折旧总账。", "warning")

    ratio = r.computed_ratio if r.computed_ratio is not None else 0.0
    updated = 0
    for d in equipment_depreciation_tb(where=f"equipment_id={r.equipment_id} AND cost_month='{r.cost_month}'"):
        d.rd_usage_ratio = ratio
        equipment_depreciation_tb.update(d)
        updated += 1

    r.applied = 1
    equipment_sharing_tb.update(r)
    log_audit("SHARING_APPLY", "EquipmentSharing", r.id,
              detail=f"回写折旧总账 设备={r.equipment_id} 月份={r.cost_month} 占比={ratio:.2%} 记录数={updated}", actor="系统管理员")
    return RedirectResponse(url="/equipment/sharing", status_code=303)


@ar("/equipment/sharing/{sid}/delete", methods=["POST"])
def equipment_sharing_delete(sid: int):
    """删除分摊登记"""
    r = equipment_sharing_tb[sid]
    if r:
        equipment_sharing_tb.delete(sid)
        log_audit("SHARING_DELETE", "EquipmentSharing", sid,
                  detail=f"删除共用设备分摊登记 {sid}", actor="系统管理员")
    return RedirectResponse(url="/equipment/sharing", status_code=303)


# ── 多用途设备分摊比例（DeviceSharingRatio） ──────────────

@ar("/equipment/sharing/ratio")
def sharing_ratio_index(effective_month: str = ""):
    """设备-项目级分摊比例管理"""
    effective_month = effective_month or date.today().strftime("%Y-%m")
    rows = device_sharing_ratios_tb(order_by="-id")

    table_rows = []
    for r in rows:
        eq = equipment_tb[r.equipment_id] if r.equipment_id else None
        p = projects_tb[r.project_id] if r.project_id else None
        table_rows.append([
            eq.code if eq else "—", eq.name if eq else "—",
            p.name if p else "—",
            f"{(r.share_ratio or 0) * 100:.1f}%",
            r.share_reason or "—",
            r.effective_month or "长期有效",
            Form(Button("删除", cls="btn btn-danger btn-sm", type="submit"),
                 method="post", action=f"/equipment/sharing/ratio/{r.id}/delete",
                 style="display:inline-block;"),
        ])

    body = data_table(
        ["设备编码", "设备名称", "项目", "分摊比例", "分摊理由", "生效月份", "操作"],
        table_rows) if table_rows else empty_state("tool", "暂无分摊比例配置")

    return page_layout(
        "多用途设备分摊比例", "首页 / 研发资产 / 共用设备分摊 / 分摊比例", "/equipment",
        Div(
            Div(
                Span("新增分摊比例", style="font-size:15px;font-weight:600;"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("设备", cls="nat-label"), Select(*_eq_options(), name="equipment_id", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("项目", cls="nat-label"), Select(*_proj_options(), name="project_id", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("分摊比例(0-1)", cls="nat-label"),
                        Input(name="share_ratio", type="number", step="0.01", value="0.5", cls="input"),
                        cls="nat-field", style="flex:0.8;"),
                    Div(Label("生效月份", cls="nat-label"),
                        Select(*month_options(effective_month), name="effective_month", cls="input"),
                        cls="nat-field", style="flex:1;"),
                    Div(Label("分摊理由", cls="nat-label"), Input(name="share_reason", cls="input", placeholder="如：按机时/产量分摊"),
                        cls="nat-field", style="flex:1.5;"),
                    Div(Label("", cls="nat-label"), Button("保存", cls="btn btn-primary", type="submit", style="width:100%;"),
                        cls="nat-field", style="flex:0.8;"),
                    style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;"
                ),
                method="post", action="/equipment/sharing/ratio/save",
                cls="nat-form"
            ),
            cls="card"
        ),
        Div(
            Div("分摊比例列表", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            body,
            cls="card"
        ),
    )


@ar("/equipment/sharing/ratio/save", methods=["POST"])
def sharing_ratio_save(equipment_id: str, project_id: str, share_ratio: str = "0.5",
                       effective_month: str = "", share_reason: str = ""):
    """保存分摊比例"""
    if not equipment_id or not project_id:
        return alert_box("设备与项目为必填项。", "danger")
    ratio = max(0.0, min(1.0, float(share_ratio or 0)))
    rec = device_sharing_ratios_tb.insert(
        equipment_id=int(equipment_id), project_id=int(project_id),
        share_ratio=ratio, share_reason=share_reason,
        effective_month=effective_month, created_at=_now(),
    )
    log_audit("SHARING_RATIO_CREATE", "DeviceSharingRatio", rec.id,
              detail=f"设备={equipment_id} 项目={project_id} 比例={ratio:.2%} 生效={effective_month or '长期'}", actor="系统管理员")
    log_data_change("device_sharing_ratio", getattr(rec, "id", 0), "share_ratio",
                    old_val="", new_val=f"设备{equipment_id} 项目{project_id} {ratio:.2%}",
                    operator="system")
    return RedirectResponse(url="/equipment/sharing/ratio", status_code=303)


@ar("/equipment/sharing/ratio/{rid}/delete", methods=["POST"])
def sharing_ratio_delete(rid: int):
    """删除分摊比例"""
    r = device_sharing_ratios_tb[rid]
    if r:
        device_sharing_ratios_tb.delete(rid)
        log_audit("SHARING_RATIO_DELETE", "DeviceSharingRatio", rid,
                  detail=f"删除分摊比例 {rid}", actor="系统管理员")
    return RedirectResponse(url="/equipment/sharing/ratio", status_code=303)
