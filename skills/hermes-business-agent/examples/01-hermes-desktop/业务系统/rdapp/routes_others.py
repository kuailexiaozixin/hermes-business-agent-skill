"""routes_others.py — 其他相关费用

功能：
- 其他相关费用登记（技术图书/资料翻译/专家咨询/知识产权/差旅/会议等）
- 一键归集到「其他相关费用（科目08）」
- 归集口径校验：其他费用总额不得超过可归集研发费用总额的 10%
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from .db import (
    other_expense_tb, projects_tb, expenses_tb, subject_by_code, add_expense,
    get_project_node_for_date
)
from .components import (
    project_options,
    stat_block,

    page_layout, data_table, empty_state, alert_box
)

ar = APIRouter()

CATEGORIES = ["技术图书", "资料翻译", "专家咨询", "知识产权", "差旅", "会议", "其他"]




@ar("/others")
def others_index():
    """其他相关费用列表"""
    rows = []
    for o in other_expense_tb(order_by="expense_date DESC"):
        proj = projects_tb[o.project_id] if o.project_id else None
        coll = Span("已归集", cls="badge badge-green") if o.collected else Span("待归集", cls="badge badge-orange")
        rows.append([
            o.expense_date, proj.name if proj else "—", o.category,
            f"¥{o.amount:,.0f}", o.caliber, o.description or "—", coll,
            A("编辑", href=f"/others/{o.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    total = sum(o.amount for o in other_expense_tb())

    return page_layout(
        "其他相关费用", "首页 / 费用归集 / 其他费用", "/others",
        Div(
            Div(
                Span("其他相关费用台账"),
                A("+ 新增费用", href="/others/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/others", cls="btn btn-outline btn-sm"),
                A("一键归集", href="/others/collect", cls="btn btn-success btn-sm"),
                cls="card-title"
            ),
            Div(
                Div(stat_block("其他费用总额", f"¥{total:,.0f}", "purple"), style="flex:1;"),
                Div(stat_block("加计扣除上限(10%)", "归集时硬校验", "orange"), style="flex:1;"),
                style="display:flex;gap:16px;margin-bottom:16px;"
            ),
            alert_box("其他相关费用（技术图书、资料翻译、专家咨询、知识产权等，科目08）不得超过可加计扣除研发费用总额的 10%。系统在一键归集时强制校验：超出上限将拦截并提示，不予归集。", "info"),
            data_table(["日期", "项目", "类别", "金额", "归集口径", "说明", "归集", "操作"], rows) if rows else empty_state("🧾", "暂无其他相关费用"),
            cls="card"
        )
    )




@ar("/others/new")
def others_new():
    return page_layout(
        "新增其他费用", "首页 / 费用归集 / 其他费用 / 新增", "/others",
        Div(
            Form(
                Div(
                    Div(Label("关联项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("费用类别", cls="form-label"), Select(*[Option(c, value=c) for c in CATEGORIES], name="category", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("费用日期", cls="form-label"), Input(name="expense_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"), cls="form-group"),
                    Div(Label("金额（元）", cls="form-label"), Input(name="amount", type="number", placeholder="如：3000", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("归集口径", cls="form-label"), Select(Option("高企认定+加计扣除", value="高企认定,加计扣除"), Option("高企认定", value="高企认定"), Option("加计扣除", value="加计扣除"), name="caliber", cls="form-select"), cls="form-group"),
                    Div(Label("说明", cls="form-label"), Input(name="description", placeholder="费用说明", cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/others", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/others/save"
            ),
            cls="card"
        )
    )


@ar("/others/save", methods=["POST"])
def others_save(project_id: str, category: str, expense_date: str = "", amount: str = "0",
               caliber: str = "高企认定,加计扣除", description: str = ""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    other_expense_tb.insert(
        project_id=int(project_id), category=category, expense_date=expense_date,
        amount=float(amount) if amount else 0.0, description=description,
        caliber=caliber, collected=0, created_at=now
    )
    return RedirectResponse(url="/others", status_code=303)


@ar("/others/{oid}/edit")
def others_edit(oid: int):
    o = other_expense_tb[oid]
    return page_layout(
        "编辑其他费用", "首页 / 费用归集 / 其他费用 / 编辑", "/others",
        Div(
            Form(
                Input(type="hidden", name="id", value=o.id),
                Div(
                    Div(Label("关联项目", cls="form-label"), Select(*project_options(o.project_id), name="project_id", cls="form-select"), cls="form-group"),
                    Div(Label("费用类别", cls="form-label"), Select(*[Option(c, value=c, selected=(c == o.category)) for c in CATEGORIES], name="category", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("金额（元）", cls="form-label"), Input(name="amount", type="number", value=o.amount, cls="form-input", required=True), cls="form-group"),
                    Div(Label("说明", cls="form-label"), Input(name="description", value=o.description, cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/others", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/others/update"
            ),
            cls="card"
        )
    )


@ar("/others/update", methods=["POST"])
def others_update(id: int, project_id: str, category: str, amount: str = "0", description: str = ""):
    o = other_expense_tb[id]
    o.project_id, o.category, o.amount = int(project_id), category, float(amount) if amount else 0.0
    o.description = description
    other_expense_tb.update(o)
    return RedirectResponse(url="/others", status_code=303)


@ar("/others/collect")
def others_collect():
    """将未归集其他费用写入科目08，并强制校验加计扣除口径下「其他费用」
    不得超过可加计扣除研发费用总额的 10%（财税[2015]119号）。

    校验逻辑：
    1. 计算本次待归集的其他费用合计 other_total；
    2. 计算可加计扣除基数 base = 已归集(加计扣除口径、且非科目08) + 本次 other_total；
    3. 限额 = base × 10%；
    4. 若 other_total > 限额 ⇒ 拦截并提示（红色警示），不予归集；
       否则归集，并在结果页展示占比与剩余可归集额度。
    """
    subject = subject_by_code("08")
    pending = other_expense_tb(where="collected=0")
    if not pending:
        return page_layout("归集其他费用", "首页 / 费用归集 / 其他费用", "/others",
            alert_box("没有待归集的其他相关费用。", "warning"),
            A("← 返回", href="/others", cls="btn btn-outline"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 本次待归集合计（仅据实金额）
    other_total = sum(o.amount for o in pending if o.amount > 0)

    # 可加计扣除基数（不含科目08自身，按 caliber 含“加计扣除”的费用记录）
    base_rows = expenses_tb(where="caliber LIKE '%加计扣除%' AND source != '其他费用归集'")
    base_amount = sum(r.amount for r in base_rows)
    # 基数 = 已归集可加计费用 + 本次其他费用
    deductible_base = base_amount + other_total
    limit = round(deductible_base * 0.10, 2)

    # 硬性拦截：超 10% 上限
    if other_total > limit + 0.005:
        exceed = round(other_total - limit, 2)
        return page_layout(
            "归集被拦截", "首页 / 费用归集 / 其他费用", "/others",
            alert_box(
                f"⚠ 归集失败：本次其他相关费用合计 ¥{other_total:,.2f}，已超过可加计扣除研发费用总额 "
                f"（¥{deductible_base:,.2f}）的 10% 限额（¥{limit:,.2f}），超出 ¥{exceed:,.2f}。\n"
                f"根据税法规定，超出部分不得加计扣除。请核减其他费用、或将其调整至可据实扣除的科目，"
                f"再重新归集。",
                "danger"),
            Div(
                A("← 返回其他费用台账", href="/others", cls="btn btn-outline"),
                style="margin-top:16px;"
            )
        )

    created_count = 0
    total_amount = 0.0
    details = []
    for o in pending:
        proj = projects_tb[o.project_id] if o.project_id else None
        if not proj:
            continue
        if o.amount <= 0:
            continue
        node = get_project_node_for_date(o.project_id, o.expense_date)
        phase = node.phase if node else "研究"
        cap_status = "待资本化" if phase == "开发" else "费用化"
        add_expense(
            project_id=o.project_id, node_id=node.id if node else 0,
            subject_id=subject.id, subject_name=subject.name,
            amount=o.amount, expense_date=o.expense_date, phase=phase,
            capitalize_status=cap_status, caliber=o.caliber,
            description=f"其他相关费用（{o.category}）：{o.description}",
            source="其他费用归集", created_at=now
        )
        o.collected = 1
        other_expense_tb.update(o)
        created_count += 1
        total_amount += o.amount
        details.append((o.category, proj.name, o.amount))

    ratio = (total_amount / deductible_base * 100) if deductible_base > 0 else 0.0
    remain = round(limit - total_amount, 2)
    result_rows = [[c, proj, f"¥{amt:,.2f}"] for c, proj, amt in details]
    return page_layout(
        "归集结果", "首页 / 费用归集 / 其他费用 / 归集结果", "/others",
        alert_box(
            f"其他相关费用归集完成：共 {created_count} 笔，合计 ¥{total_amount:,.2f}（已写入科目08）。\n"
            f"占可加计扣除研发费用总额（¥{deductible_base:,.2f}）的 {ratio:.2f}%，"
            f"未超过 10% 法定上限（¥{limit:,.2f}），剩余可归集额度 ¥{remain:,.2f}。",
            "success"),
        Div(
            Div("归集明细", cls="card-title"),
            data_table(["类别", "项目", "金额"], result_rows),
            cls="card"
        ),
        Div(A("← 返回费用台账", href="/others", cls="btn btn-outline"), style="margin-top:16px;")
    )
