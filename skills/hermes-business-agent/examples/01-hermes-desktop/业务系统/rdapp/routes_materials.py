"""routes_materials.py — 研发原材料领用与去向管理

功能：
- 原材料领用登记（名称/规格/数量/单价/金额/去向项目/用途）
- 去向状态追踪（已领用 / 使用中 / 闲置 / 报废）
- 一键归集：将未归集领用记录写入直接投入费用（科目02）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from .db import (
    material_requisition_tb, material_sub_types_tb, sample_scrap_tb,
    projects_tb, personnel_tb, get_project_node_for_date, subject_by_code, add_expense
)
from .components import (
    project_options,
    person_options,

    page_layout, data_table, empty_state, alert_box
)
from .routes_datacenter import log_data_change

ar = APIRouter()

USAGE_STATUS = ["已领用", "使用中", "闲置", "报废"]






@ar("/materials")
def materials_index(status_filter: str = "", project_id: str = ""):
    """原材料领用与去向列表"""
    rows = []
    for m in material_requisition_tb(order_by="requisition_date DESC"):
        proj = projects_tb[m.project_id] if m.project_id else None
        person = personnel_tb[m.requisitioner_id] if m.requisitioner_id else None
        usage_cls = {
            "使用中": "badge-green", "已领用": "badge-blue",
            "闲置": "badge-orange", "报废": "badge-gray"
        }.get(m.usage_status, "badge-gray")
        if status_filter and m.usage_status != status_filter:
            continue
        if project_id and str(m.project_id) != str(project_id):
            continue
        coll_badge = Span("已归集", cls="badge badge-green") if m.collected else Span("待归集", cls="badge badge-orange")
        rows.append([
            m.material_name, m.specification, f"{m.quantity} {m.unit}",
            f"¥{m.unit_price:,.0f}", f"¥{m.amount:,.2f}",
            proj.name if proj else "—", person.name if person else "—",
            m.requisition_date, m.purpose or "—",
            Span(m.usage_status, cls=f"badge {usage_cls}"),
            coll_badge,
            A("编辑", href=f"/materials/{m.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "研发原材料领用与去向", "首页 / 研发资产 / 原材料领用", "/materials",
        Div(
            Div(
                Span("原材料领用台账"),
                A("+ 领用登记", href="/materials/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/materials", cls="btn btn-outline btn-sm"),
                A("一键归集到费用", href="/materials/collect", cls="btn btn-success btn-sm"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("去向状态", cls="form-label"), Select(Option("全部", value=""), *[Option(s, value=s) for s in USAGE_STATUS], name="status_filter", cls="form-select"), cls="form-group"),
                    Div(Label("去向项目", cls="form-label"), Select(*project_options(project_id), name="project_id", cls="form-select"), cls="form-group"),
                    Div(Button("筛选", type="submit", cls="btn btn-primary"), style="align-self:end;"),
                    cls="form-row"
                ),
                method="get", action="/materials"
            ),
            alert_box("原材料领用归集到「直接投入费用（科目02）」。领用后可在「去向追踪」中更新使用状态（使用中 / 闲置 / 报废），报废材料不纳入归集。", "info"),
            data_table(["物料名称", "规格", "数量", "单价", "金额", "去向项目", "领用人", "领用日期", "用途", "使用状态", "归集", "操作"], rows) if rows else empty_state("📦", "暂无原材料领用记录"),
            cls="card"
        )
    )


@ar("/materials/new")
def materials_new():
    return page_layout(
        "领用登记", "首页 / 研发资产 / 原材料领用 / 新增", "/materials",
        Div(
            Form(
                Div(
                    Div(Label("物料名称", cls="form-label"), Input(name="material_name", placeholder="如：服务器 CPU", cls="form-input", required=True), cls="form-group"),
                    Div(Label("规格型号", cls="form-label"), Input(name="specification", placeholder="如：Xeon 8480", cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("数量", cls="form-label"), Input(name="quantity", type="number", step="0.01", min="0", placeholder="如：4", cls="form-input", required=True), cls="form-group"),
                    Div(Label("单位", cls="form-label"), Input(name="unit", value="个", cls="form-input"), cls="form-group"),
                    Div(Label("单价（元）", cls="form-label"), Input(name="unit_price", type="number", step="0.01", min="0", placeholder="如：12000", cls="form-input", required=True), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("去向项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("领用人", cls="form-label"), Select(*person_options(), name="requisitioner_id", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("领用日期", cls="form-label"), Input(name="requisition_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"), cls="form-group"),
                    Div(Label("用途 / 去向说明", cls="form-label"), Input(name="purpose", placeholder="如：核心模块搭建", cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/materials", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/materials/save"
            ),
            cls="card"
        )
    )


@ar("/materials/save", methods=["POST"])
def materials_save(material_name: str, specification: str = "", quantity: str = "1",
                   unit: str = "个", unit_price: str = "0", project_id: str = "",
                   requisitioner_id: str = "", requisition_date: str = "",
                   purpose: str = ""):
    qty = float(quantity) if quantity else 0.0
    price = float(unit_price) if unit_price else 0.0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = material_requisition_tb.insert(
        material_name=material_name, specification=specification, unit=unit,
        quantity=qty, unit_price=price, amount=round(qty * price, 2),
        project_id=int(project_id) if project_id else 0,
        requisition_date=requisition_date, requisitioner_id=int(requisitioner_id) if requisitioner_id else 0,
        purpose=purpose, usage_status="已领用", collected=0, created_at=now
    )
    log_data_change("material_requisition", getattr(rec, "id", 0), "amount",
                    old_val="", new_val=f"{material_name} ×{qty:g} ¥{round(qty * price, 2):,.2f}",
                    operator="system")
    return RedirectResponse(url="/materials", status_code=303)


@ar("/materials/{mid}/edit")
def materials_edit(mid: int):
    m = material_requisition_tb[mid]
    return page_layout(
        "编辑领用记录", "首页 / 研发资产 / 原材料领用 / 编辑", "/materials",
        Div(
            Form(
                Input(type="hidden", name="id", value=m.id),
                Div(
                    Div(Label("物料名称", cls="form-label"), Input(name="material_name", value=m.material_name, cls="form-input", required=True), cls="form-group"),
                    Div(Label("规格型号", cls="form-label"), Input(name="specification", value=m.specification, cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("数量", cls="form-label"), Input(name="quantity", type="number", step="0.01", min="0", value=m.quantity, cls="form-input", required=True), cls="form-group"),
                    Div(Label("单位", cls="form-label"), Input(name="unit", value=m.unit, cls="form-input"), cls="form-group"),
                    Div(Label("单价（元）", cls="form-label"), Input(name="unit_price", type="number", step="0.01", min="0", value=m.unit_price, cls="form-input", required=True), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("去向项目", cls="form-label"), Select(*project_options(m.project_id), name="project_id", cls="form-select"), cls="form-group"),
                    Div(Label("使用状态", cls="form-label"), Select(*[Option(s, value=s, selected=(s == m.usage_status)) for s in USAGE_STATUS], name="usage_status", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/materials", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/materials/update"
            ),
            cls="card"
        )
    )


@ar("/materials/update", methods=["POST"])
def materials_update(id: int, material_name: str, specification: str = "", quantity: str = "1",
                     unit: str = "个", unit_price: str = "0", project_id: str = "",
                     usage_status: str = "已领用"):
    m = material_requisition_tb[id]
    m.material_name = material_name
    m.specification = specification
    m.quantity = float(quantity) if quantity else 0.0
    m.unit = unit
    m.unit_price = float(unit_price) if unit_price else 0.0
    m.amount = round(m.quantity * m.unit_price, 2)
    m.project_id = int(project_id) if project_id else 0
    m.usage_status = usage_status
    material_requisition_tb.update(m)
    return RedirectResponse(url="/materials", status_code=303)


@ar("/materials/collect")
def materials_collect():
    """将未归集且未报废的领用记录归集到直接投入费用（科目02）"""
    subject = subject_by_code("02")
    pending = material_requisition_tb(where="collected=0 AND usage_status<>'报废'")
    if not pending:
        return page_layout("归集原材料", "首页 / 研发资产 / 原材料领用", "/materials",
            alert_box("没有待归集的原材料领用记录。", "warning"),
            A("← 返回", href="/materials", cls="btn btn-outline"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    created_count = 0
    total_amount = 0.0
    details = []
    for m in pending:
        proj = projects_tb[m.project_id] if m.project_id else None
        if not proj:
            continue
        node = get_project_node_for_date(m.project_id, m.requisition_date)
        phase = node.phase if node else "研究"
        cap_status = "待资本化" if phase == "开发" else "费用化"
        add_expense(
            project_id=m.project_id, node_id=node.id if node else 0,
            subject_id=subject.id, subject_name=subject.name,
            amount=m.amount, expense_date=m.requisition_date, phase=phase,
            capitalize_status=cap_status, caliber=proj.caliber,
            description=f"原材料领用归集：{m.material_name}（{m.specification}）×{m.quantity}{m.unit} → {proj.name}",
            source="原材料归集", created_at=now
        )
        m.collected = 1
        material_requisition_tb.update(m)
        created_count += 1
        total_amount += m.amount
        details.append((m.material_name, proj.name, m.amount))

    result_rows = [[name, proj, f"¥{amt:,.2f}"] for name, proj, amt in details]
    return page_layout(
        "归集结果", "首页 / 研发资产 / 原材料领用 / 归集结果", "/materials",
        alert_box(f"原材料归集完成：共 {created_count} 笔，合计 ¥{total_amount:,.2f}，已写入「直接投入费用（科目02）」。", "success"),
        Div(
            Div("归集明细", cls="card-title"),
            data_table(["物料名称", "去向项目", "金额"], result_rows),
            cls="card"
        ),
        Div(A("← 返回领用台账", href="/materials", cls="btn btn-outline"), style="margin-top:16px;")
    )


# 局部安全取节点已移除，统一使用 db.get_active_project_node


# ── 缺口④：样品/废料细分建账 ──────────────────────────────

@ar("/materials/types")
def materials_types():
    """物料类型细分台账（原料/样品/废料字典 + 各类型发生额统计）"""
    sub_types = material_sub_types_tb()
    reqs = list(material_requisition_tb())
    scraps = list(sample_scrap_tb())

    # 按 material_class 粗分：研发专用 / 研发生产共用 / 生产用料
    class_amount = {}
    for r in reqs:
        cls_key = r.material_class or "未分类"
        class_amount[cls_key] = class_amount.get(cls_key, 0.0) + (r.net_amount or r.amount or 0.0)

    rows = []
    for st in sub_types:
        if st.name == "原料":
            total = sum(r.amount or 0.0 for r in reqs if (r.material_class or "研发专用") == "研发专用")
            cnt = len([r for r in reqs if (r.material_class or "研发专用") == "研发专用"])
            sub = "研发专用领料合计"
        elif st.name == "样品":
            total = sum(s.realized_amount or 0.0 for s in scraps if s.item_type == "样品")
            cnt = len([s for s in scraps if s.item_type == "样品"])
            sub = "样品销售实现收入"
        else:  # 废料
            total = sum(s.realized_amount or 0.0 for s in scraps if s.item_type == "废料")
            total += sum(r.scrap_value or 0.0 for r in reqs)
            cnt = len([s for s in scraps if s.item_type == "废料"]) + len([r for r in reqs if (r.scrap_value or 0) > 0])
            sub = "废料残值/处置收入（应冲减）"
        rows.append([
            st.code, st.name,
            Span("研发材料" if st.is_rd_material else "非研发材料",
                 cls="badge badge-green" if st.is_rd_material else "badge badge-gray"),
            cnt,
            f"¥{total:,.2f}",
            sub,
        ])

    return page_layout(
        "物料类型细分台账", "首页 / 研发资产 / 物料类型细分", "/materials/types",
        Div(
            Div(
                Span("原料 / 样品 / 废料 细分"),
                A("样品废料台账", href="/sample-scrap", cls="btn btn-outline btn-sm"),
                A("原材料领用", href="/materials", cls="btn btn-outline btn-sm"),
                cls="card-title"
            ),
            alert_box(
                "物料管理 9 章要求：原料、样品、废料分别建账。样品销售与废料处置残值均须冲减研发费用基数，"
                "防止将形成样品/废料的部分仍按全额归集研发费用。",
                "info"
            ),
            data_table(
                ["编码", "类型", "研发材料", "发生笔数", "金额/收入", "说明"],
                rows
            ) if rows else empty_state("📦", "暂无物料类型数据"),
            cls="card"
        )
    )


@ar("/materials/sample-scrap-summary")
def materials_sample_scrap_summary():
    """样品/废料专项汇总：原料领用 → 形成样品/废料 → 冲减金额 全链路"""
    reqs = list(material_requisition_tb())
    scraps = list(sample_scrap_tb())

    # 原材料中形成废料的记录（scrap_value > 0）
    scrap_reqs = [r for r in reqs if (r.scrap_value or 0) > 0]
    scrap_req_rows = []
    for r in scrap_reqs:
        proj = projects_tb[r.project_id] if r.project_id else None
        scrap_req_rows.append([
            r.material_name, proj.name if proj else "—",
            f"{r.scrap_qty or 0:g} {r.unit or ''}",
            f"¥{r.scrap_value:,.2f}",
            Span("需冲减", cls="badge badge-orange"),
        ])

    scrap_rows = []
    for s in scraps:
        proj = projects_tb[s.project_id] if s.project_id else None
        disposal_cls = {
            "销售": "badge-green", "报废": "badge-gray",
            "留存": "badge-blue", "领回生产": "badge-orange"
        }.get(s.disposal, "badge-gray")
        scrap_rows.append([
            s.name, s.item_type, proj.name if proj else "—",
            f"{s.quantity:g} {s.unit or ''}",
            Span(s.disposal, cls=f"badge {disposal_cls}"),
            f"¥{s.realized_amount or 0:,.2f}" if s.disposal in ("销售", "报废") else "—",
        ])

    total_sample_income = sum(s.realized_amount or 0 for s in scraps if s.item_type == "样品" and s.disposal == "销售")
    total_scrap_residue = sum(s.realized_amount or 0 for s in scraps if s.item_type == "废料")
    total_scrap_residue += sum(r.scrap_value or 0 for r in scrap_reqs)

    return page_layout(
        "样品/废料专项汇总", "首页 / 研发资产 / 样品废料汇总", "/materials/sample-scrap-summary",
        Div(
            Div("样品/废料冲减概览", style="font-size:15px;font-weight:600;margin-bottom:16px;"),
            Div(
                Div(Div("样品销售收入（冲减）", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{total_sample_income:,.2f}", style="font-size:20px;font-weight:700;color:var(--warning);")),
                Div(Div("废料处置残值（冲减）", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{total_scrap_residue:,.2f}", style="font-size:20px;font-weight:700;color:var(--danger);")),
                Div(Div("应冲减合计", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{total_sample_income + total_scrap_residue:,.2f}", style="font-size:20px;font-weight:700;color:var(--primary);")),
                style="display:flex;gap:32px;"
            ),
            cls="card"
        ),
        Div(
            Div(
                Span("原材料领用中形成废料"),
                cls="card-title"
            ),
            data_table(["物料", "项目", "废料数量", "残值", "状态"], scrap_req_rows) if scrap_req_rows else empty_state("♻️", "暂无原材料形成废料的记录"),
            cls="card"
        ),
        Div(
            Div(
                Span("样品/废料台账明细"),
                A("去登记", href="/sample-scrap/new", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            data_table(["名称", "类型", "项目", "数量", "处置方式", "实现收入/残值"], scrap_rows) if scrap_rows else empty_state("📦", "暂无样品/废料台账记录"),
            cls="card"
        ),
        Div(A("← 返回物料类型细分", href="/materials/types", cls="btn btn-outline"), style="margin-top:16px;")
    )
