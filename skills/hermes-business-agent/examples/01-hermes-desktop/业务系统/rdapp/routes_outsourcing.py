"""routes_outsourcing.py — 委托外部研发费用

功能：
- 委托外部研发合同登记（受托方/金额/成果归属约定）
- 一键归集：按实际发生额的 80% 归集到委托外部研究开发费用（科目07）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from .db import (
    outsourcing_tb, projects_tb, subject_by_code, add_expense, get_project_node_for_date, deduct_overseas_cap
)
from .components import (
    project_options,
    stat_block,

    page_layout, data_table, empty_state, alert_box
)

ar = APIRouter()




@ar("/outsourcing")
def outsourcing_index():
    """委托外部研发合同列表"""
    rows = []
    for o in outsourcing_tb(order_by="expense_date DESC"):
        proj = projects_tb[o.project_id] if o.project_id else None
        ttype = Span("约定归委托方", cls="badge badge-green") if o.has_tech_transfer else Span("未约定", cls="badge badge-gray")
        coll = Span("已归集", cls="badge badge-green") if o.collected else Span("待归集", cls="badge badge-orange")
        rows.append([
            o.contract_no, o.contractor, proj.name if proj else "—",
            f"¥{o.contract_amount:,.0f}", f"¥{o.actual_amount:,.0f}",
            f"¥{o.actual_amount*0.8:,.2f}", ttype, coll,
            A("编辑", href=f"/outsourcing/{o.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    total_actual = sum(o.actual_amount for o in outsourcing_tb())
    total_collect = sum(o.actual_amount * 0.8 for o in outsourcing_tb())

    return page_layout(
        "委托外部研发费用", "首页 / 费用归集 / 委托外部研发", "/outsourcing",
        Div(
            Div(
                Span("委托外部研发合同"),
                A("+ 新增合同", href="/outsourcing/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/outsourcing", cls="btn btn-outline btn-sm"),
                A("一键归集（按80%）", href="/outsourcing/collect", cls="btn btn-success btn-sm"),
                cls="card-title"
            ),
            Div(
                Div(stat_block("合同总额", f"¥{total_actual:,.0f}", "blue"), style="flex:1;"),
                Div(stat_block("按80%归集额", f"¥{total_collect:,.0f}", "green"), style="flex:1;"),
                style="display:flex;gap:16px;margin-bottom:16px;"
            ),
            alert_box("委托外部研究开发费用按实际发生额的 80% 归集（科目07）。需在合同中约定「成果归委托方所有」，否则不得计入。归集金额超限时在报表端进行口径限额校验。", "info"),
            data_table(["合同编号", "受托方", "项目", "合同金额", "实际发生额", "归集额(80%)", "成果归属", "归集", "操作"], rows) if rows else empty_state("🤝", "暂无委托外部研发合同"),
            cls="card"
        )
    )




@ar("/outsourcing/new")
def outsourcing_new():
    return page_layout(
        "新增委托研发合同", "首页 / 费用归集 / 委托外部研发 / 新增", "/outsourcing",
        Div(
            Form(
                Div(
                    Div(Label("合同编号", cls="form-label"), Input(name="contract_no", placeholder="如：WT-2026-003", cls="form-input", required=True), cls="form-group"),
                    Div(Label("受托方", cls="form-label"), Input(name="contractor", placeholder="如：某软件外包公司", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("关联项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("费用日期", cls="form-label"), Input(name="expense_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("合同金额（元）", cls="form-label"), Input(name="contract_amount", type="number", placeholder="如：50000", cls="form-input"), cls="form-group"),
                    Div(Label("实际发生额（元）", cls="form-label"), Input(name="actual_amount", type="number", placeholder="如：50000", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("成果归属约定", cls="form-label"), Select(Option("约定归委托方", value="1"), Option("未明确约定", value="0"), name="has_tech_transfer", cls="form-select"), cls="form-group"),
                    Div(Label("归集口径", cls="form-label"), Select(Option("高企认定+加计扣除", value="高企认定,加计扣除"), Option("高企认定", value="高企认定"), Option("加计扣除", value="加计扣除"), name="caliber", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label(Input(type="checkbox", name="is_overseas", value="1"), "境外受托方（加计上限受境内委托2/3约束）", cls="form-label", style="display:flex;align-items:center;gap:8px;"), cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("说明", cls="form-label"), Textarea(name="description", placeholder="委托研发内容与成果说明", cls="form-textarea"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/outsourcing", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/outsourcing/save"
            ),
            cls="card"
        )
    )


@ar("/outsourcing/save", methods=["POST"])
def outsourcing_save(contract_no: str, contractor: str, project_id: str, expense_date: str = "",
                     contract_amount: str = "0", actual_amount: str = "0",
                     has_tech_transfer: str = "1", caliber: str = "高企认定,加计扣除",
                     is_overseas: str = "0", description: str = ""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    outsourcing_tb.insert(
        contract_no=contract_no, contractor=contractor, project_id=int(project_id),
        contract_amount=float(contract_amount) if contract_amount else 0.0,
        actual_amount=float(actual_amount) if actual_amount else 0.0,
        caliber=caliber, has_tech_transfer=int(has_tech_transfer), expense_date=expense_date,
        is_overseas=int(is_overseas), description=description, collected=0, created_at=now
    )
    return RedirectResponse(url="/outsourcing", status_code=303)


@ar("/outsourcing/{oid}/edit")
def outsourcing_edit(oid: int):
    o = outsourcing_tb[oid]
    return page_layout(
        "编辑委托研发合同", "首页 / 费用归集 / 委托外部研发 / 编辑", "/outsourcing",
        Div(
            Form(
                Input(type="hidden", name="id", value=o.id),
                Div(
                    Div(Label("合同编号", cls="form-label"), Input(name="contract_no", value=o.contract_no, cls="form-input", required=True), cls="form-group"),
                    Div(Label("受托方", cls="form-label"), Input(name="contractor", value=o.contractor, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("关联项目", cls="form-label"), Select(*project_options(o.project_id), name="project_id", cls="form-select"), cls="form-group"),
                    Div(Label("实际发生额（元）", cls="form-label"), Input(name="actual_amount", type="number", value=o.actual_amount, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/outsourcing", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/outsourcing/update"
            ),
            cls="card"
        )
    )


@ar("/outsourcing/update", methods=["POST"])
def outsourcing_update(id: int, contract_no: str, contractor: str, project_id: str,
                       actual_amount: str = "0"):
    o = outsourcing_tb[id]
    o.contract_no, o.contractor, o.project_id = contract_no, contractor, int(project_id)
    o.actual_amount = float(actual_amount) if actual_amount else 0.0
    outsourcing_tb.update(o)
    return RedirectResponse(url="/outsourcing", status_code=303)


@ar("/outsourcing/collect")
def outsourcing_collect():
    """将未归集合同按实际发生额 80% 归集到科目07"""
    subject = subject_by_code("07")
    pending = outsourcing_tb(where="collected=0")
    if not pending:
        return page_layout("归集委托研发", "首页 / 费用归集 / 委托外部研发", "/outsourcing",
            alert_box("没有待归集的委托外部研发合同。", "warning"),
            A("← 返回", href="/outsourcing", cls="btn btn-outline"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    created_count = 0
    total_amount = 0.0
    details = []
    # 委托境外上限：境内委托实际发生额合计 × 2/3（财税口径）
    domestic_base, overseas_cap = deduct_overseas_cap()
    overseas_accum = 0.0  # 已计入的境外归集额累计
    for o in pending:
        proj = projects_tb[o.project_id] if o.project_id else None
        if not proj:
            continue
        collect_amt = round(o.actual_amount * 0.8, 2)
        capped = False
        if o.is_overseas and overseas_cap > 0:
            remaining = round(overseas_cap - overseas_accum, 2)
            if collect_amt > remaining:
                collect_amt = max(remaining, 0.0)
                capped = True
        if collect_amt <= 0:
            continue
        if o.is_overseas:
            overseas_accum += collect_amt
        node = get_project_node_for_date(o.project_id, o.expense_date)
        phase = node.phase if node else "研究"
        cap_status = "待资本化" if phase == "开发" else "费用化"
        desc = f"委托外部研发归集（80%）：{o.contractor}（{o.contract_no}）"
        if o.is_overseas and capped:
            desc += "【境外委托：受境内委托2/3上限约束，部分未计入】"
        elif o.is_overseas:
            desc += "【境外委托】"
        if not o.has_tech_transfer:
            desc += "【注意：未约定成果归委托方，高企口径下可能不予计入】"
        add_expense(
            project_id=o.project_id, node_id=node.id if node else 0,
            subject_id=subject.id, subject_name=subject.name,
            amount=collect_amt, expense_date=o.expense_date, phase=phase,
            capitalize_status=cap_status, caliber=o.caliber,
            description=desc, source="委托研发归集", created_at=now
        )
        o.collected = 1
        outsourcing_tb.update(o)
        created_count += 1
        total_amount += collect_amt
        details.append((o.contractor, proj.name, collect_amt))

    result_rows = [[c, proj, f"¥{amt:,.2f}"] for c, proj, amt in details]
    return page_layout(
        "归集结果", "首页 / 费用归集 / 委托外部研发 / 归集结果", "/outsourcing",
        alert_box(f"委托外部研发归集完成：共 {created_count} 笔，合计 ¥{total_amount:,.2f}（按实际发生额 80%）。", "success"),
        Div(
            Div("归集明细", cls="card-title"),
            data_table(["受托方", "项目", "归集金额"], result_rows),
            cls="card"
        ),
        Div(A("← 返回合同列表", href="/outsourcing", cls="btn btn-outline"), style="margin-top:16px;")
    )
