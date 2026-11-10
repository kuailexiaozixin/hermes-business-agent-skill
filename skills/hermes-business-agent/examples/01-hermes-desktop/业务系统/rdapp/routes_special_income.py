"""routes_special_income.py — 特殊收入冲减与样品废料台账

M4 特殊收入（不征税收入 / 政府补助 / 样品销售 / 废料处置）冲减研发费用加计扣除基数
M7 样品、废料台账（研发产出去向，样品销售自动计入特殊收入冲减）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from .db import (
    special_income_tb, sample_scrap_tb, projects_tb
)
from .components import (
    project_options,
    stat_block,

    page_layout, data_table, empty_state, alert_box
)

ar = APIRouter()






# ── M4 特殊收入冲减 ────────────────────────────────────────

@ar("/special-income")
def special_income_index():
    """特殊收入台账（需冲减研发费用加计扣除基数）"""
    rows = []
    total = 0.0
    for r in special_income_tb(order_by="income_date DESC"):
        proj = projects_tb.get(r.project_id, default=None) if r.project_id else None
        total += r.amount
        rows.append([
            r.income_type,
            proj.name if proj else "企业级",
            f"¥{r.amount:,.0f}", r.income_date, r.offset_caliber, r.note,
        ])

    return page_layout(
        "特殊收入冲减", "首页 / 合规管理 / 特殊收入", "/special-income",
        Div(
            Div(stat_block("特殊收入合计（冲减）", f"¥{total:,.0f}", "red"), style="flex:1;"),
            Div(stat_block("加计扣除净额影响", f"-¥{total:,.0f}", "orange"), style="flex:1;"),
            style="display:flex;gap:16px;margin-bottom:16px;"
        ),
        alert_box(
            "以下收入需从研发费用加计扣除基数中冲减：① 不征税收入用于研发的部分，对应支出不得加计扣除；"
            "② 作为不征税收入处理的政府补助专项；③ 样品 / 副产品销售收入（见样品废料台账）。"
            "冲减按企业级整体执行，不直接分摊到单个项目。",
            "info"),
        Div(
            Div(
                Span("特殊收入登记"),
                A("+ 新增", href="/special-income/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/special_income", cls="btn btn-outline btn-sm"),
                cls="card-title"
            ),
            data_table(["收入类型", "关联项目", "金额", "日期", "冲减口径", "说明"], rows) if rows else empty_state("🧾", "暂无特殊收入登记"),
            cls="card"
        )
    )


@ar("/special-income/new")
def special_income_new():
    return page_layout(
        "新增特殊收入", "首页 / 合规管理 / 特殊收入 / 新增", "/special-income",
        Div(
            Form(
                Div(
                    Div(Label("收入类型", cls="form-label"),
                        Select(
                            Option("不征税收入", value="不征税收入"),
                            Option("政府补助", value="政府补助"),
                            Option("样品销售", value="样品销售"),
                            Option("废料处置", value="废料处置"),
                            name="income_type", cls="form-select"), cls="form-group"),
                    Div(Label("关联项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("金额（元）", cls="form-label"), Input(name="amount", type="number", placeholder="如：500000", cls="form-input", required=True), cls="form-group"),
                    Div(Label("收入日期", cls="form-label"), Input(name="income_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"), cls="form-group"),
                    Div(Label("冲减口径", cls="form-label"),
                        Select(Option("加计扣除", value="加计扣除"), Option("高企认定", value="高企认定"), Option("全部口径", value="高企认定,加计扣除"), name="offset_caliber", cls="form-select"),
                        cls="form-group"),
                    cls="form-row-3"
                ),
                Div(Label("说明", cls="form-label"), Textarea(name="note", placeholder="收入来源与冲减依据", cls="form-textarea"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/special-income", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/special-income/save"
            ),
            cls="card"
        )
    )


@ar("/special-income/save", methods=["POST"])
def special_income_save(income_type: str, project_id: str = "", amount: str = "0",
                        income_date: str = "", offset_caliber: str = "加计扣除", note: str = ""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    special_income_tb.insert(
        project_id=int(project_id) if project_id else 0,
        income_type=income_type,
        amount=float(amount) if amount else 0.0,
        income_date=income_date, offset_caliber=offset_caliber, note=note,
        created_at=now
    )
    return RedirectResponse(url="/special-income", status_code=303)


# ── M7 样品废料台账 ────────────────────────────────────────

@ar("/sample-scrap")
def sample_scrap_index():
    """样品、废料台账（研发产出去向）"""
    rows = []
    sample_sales = 0.0
    scrap_value = 0.0
    for s in sample_scrap_tb(order_by="record_date DESC"):
        proj = projects_tb.get(s.project_id, default=None) if s.project_id else None
        if s.item_type == "样品" and s.disposal == "销售":
            sample_sales += s.realized_amount
        if s.item_type == "废料" and s.disposal == "销售":
            scrap_value += s.realized_amount
        rows.append([
            s.item_type, s.name, proj.name if proj else "—",
            f"{s.quantity:g}{s.unit}", s.disposal,
            f"¥{s.realized_amount:,.0f}", s.record_date, s.note,
        ])

    return page_layout(
        "样品废料台账", "首页 / 合规管理 / 样品废料", "/sample-scrap",
        Div(
            Div(stat_block("样品销售实现收入", f"¥{sample_sales:,.0f}", "orange"), style="flex:1;"),
            Div(stat_block("废料处置残值", f"¥{scrap_value:,.0f}", "green"), style="flex:1;"),
            style="display:flex;gap:16px;margin-bottom:16px;"
        ),
        alert_box(
            "研发过程中形成的样品对外销售，其销售收入应冲减研发费用（计入特殊收入冲减）；"
            "废料处置残值单独记录。本台账用于完整追踪研发产出去向，样品销售记录可一键生成特殊收入冲减项。",
            "info"),
        Div(
            Div(
                Span("样品 / 废料登记"),
                A("+ 新增", href="/sample-scrap/new", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            data_table(["类型", "名称", "项目", "数量", "处置方式", "实现收入", "记录日期", "说明"], rows) if rows else empty_state("📦", "暂无样品/废料记录"),
            cls="card"
        )
    )


@ar("/sample-scrap/new")
def sample_scrap_new():
    return page_layout(
        "新增样品/废料记录", "首页 / 合规管理 / 样品废料 / 新增", "/sample-scrap",
        Div(
            Form(
                Div(
                    Div(Label("类型", cls="form-label"),
                        Select(Option("样品", value="样品"), Option("废料", value="废料"), name="item_type", cls="form-select"), cls="form-group"),
                    Div(Label("名称", cls="form-label"), Input(name="name", placeholder="如：试制样机 / 边角料", cls="form-input", required=True), cls="form-group"),
                    Div(Label("关联项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("数量", cls="form-label"), Input(name="quantity", type="number", step="0.01", placeholder="如：5", cls="form-input"), cls="form-group"),
                    Div(Label("单位", cls="form-label"), Input(name="unit", value="个", cls="form-input"), cls="form-group"),
                    Div(Label("处置方式", cls="form-label"),
                        Select(Option("留存", value="留存"), Option("销售", value="销售"), Option("报废", value="报废"), Option("领回生产", value="领回生产"), name="disposal", cls="form-select"),
                        cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("实现收入 / 残值（元）", cls="form-label"), Input(name="realized_amount", type="number", step="0.01", placeholder="销售时填写", cls="form-input"), cls="form-group"),
                    Div(Label("记录日期", cls="form-label"), Input(name="record_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("说明", cls="form-label"), Textarea(name="note", placeholder="样品用途/废料来源", cls="form-textarea"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/sample-scrap", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/sample-scrap/save"
            ),
            cls="card"
        )
    )


@ar("/sample-scrap/save", methods=["POST"])
def sample_scrap_save(item_type: str, name: str, project_id: str = "", quantity: str = "0",
                      unit: str = "个", disposal: str = "留存", realized_amount: str = "0",
                      record_date: str = "", note: str = ""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    s = sample_scrap_tb.insert(
        project_id=int(project_id) if project_id else 0,
        item_type=item_type, name=name,
        quantity=float(quantity) if quantity else 0.0, unit=unit,
        disposal=disposal, realized_amount=float(realized_amount) if realized_amount else 0.0,
        record_date=record_date, note=note, created_at=now
    )
    # 样品销售 / 废料处置 → 自动生成特殊收入冲减（M4 联动）
    if disposal == "销售" and (realized_amount and float(realized_amount) > 0):
        special_income_tb.insert(
            project_id=int(project_id) if project_id else 0,
            income_type="样品销售" if item_type == "样品" else "废料处置",
            amount=float(realized_amount), income_date=record_date or date.today().strftime("%Y-%m-%d"),
            offset_caliber="加计扣除", note=f"来自样品废料台账 #{s.id}", created_at=now
        )
    return RedirectResponse(url="/sample-scrap", status_code=303)
