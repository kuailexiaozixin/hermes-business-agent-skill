"""routes_equipment.py — 研发设备管理与折旧费用分摊

功能：
- 研发设备/资产档案管理
- 研发设备工时登记（按设备/项目/日期）
- 设备折旧费用按工时分摊（仿人员人工费用模式，写入折旧费用与长期待摊 科目03）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from collections import defaultdict
from .db import (
    equipment_tb, equipment_work_time_tb, equipment_depreciation_tb, projects_tb,
    get_project_node_for_date, capitalize_status_for_phase, subject_by_code, add_expense,
    equipment_caliber_for_category
)
from .components import (
    project_options,
    month_options,

    page_layout, data_table, empty_state, alert_box
)
from .routes_datacenter import log_data_change

ar = APIRouter()


def _eq_options(selected=""):
    opts = [Option("— 请选择设备 —", value="")]
    for e in equipment_tb(order_by="code"):
        opts.append(Option(f"{e.code} {e.name}", value=e.id, selected=str(e.id) == str(selected)))
    return opts






# ── 设备档案管理 ──────────────────────────────────────────

@ar("/equipment")
def equipment_index():
    """设备档案列表"""
    rows = []
    for e in equipment_tb(order_by="code"):
        status_badge_eq = {"在用": "badge-green", "闲置": "badge-orange", "报废": "badge-gray"}.get(e.status, "badge-gray")
        rows.append([
            e.code, e.name, e.category, f"¥{e.acquisition_cost:,.0f}",
            f"{e.useful_life} 月", f"¥{e.monthly_depreciation:,.0f}",
            Span(e.status, cls=f"badge {status_badge_eq}"),
            A("工时", href=f"/equipment/worktime?equipment_id={e.id}", cls="btn btn-outline btn-sm"),
            A("编辑", href=f"/equipment/{e.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "研发设备档案", "首页 / 研发资产 / 设备档案", "/equipment",
        Div(
            Div(
                Span("研发设备 / 资产台账"),
                A("+ 新增设备", href="/equipment/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/equipment", cls="btn btn-outline btn-sm"),
                cls="card-title"
            ),
            alert_box("研发设备的折旧费用与长期待摊费用（科目03）是研发费用的重要组成部分。登记设备工时后，可按工时占比将月折旧额分摊到各项目。", "info"),
            data_table(["编码", "名称", "类别", "原值", "使用年限", "月折旧额", "状态", "", ""], rows) if rows else empty_state("🔧", "暂无设备档案"),
            cls="card"
        )
    )


@ar("/equipment/new")
def equipment_new():
    return page_layout(
        "新增设备", "首页 / 研发资产 / 设备档案 / 新增", "/equipment",
        Div(
            Form(
                Div(
                    Div(Label("设备编码", cls="form-label"), Input(name="code", placeholder="如：EQ-004", cls="form-input", required=True), cls="form-group"),
                    Div(Label("设备名称", cls="form-label"), Input(name="name", placeholder="如：GPU 训练服务器", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("类别", cls="form-label"), Select(Option("仪器设备"), Option("专用设备"), Option("软件"), Option("在用建筑物"), name="category", cls="form-select"), cls="form-group"),
                    Div(Label("型号", cls="form-label"), Input(name="model", cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("购置日期", cls="form-label"), Input(name="acquisition_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"), cls="form-group"),
                    Div(Label("原值（元）", cls="form-label"), Input(name="acquisition_cost", type="number", placeholder="如：300000", cls="form-input"), cls="form-group"),
                    Div(Label("使用年限（月）", cls="form-label"), Input(name="useful_life", type="number", value="60", cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("月折旧额（元）", cls="form-label"), Input(name="monthly_depreciation", type="number", placeholder="原值/年限", cls="form-input"), cls="form-group"),
                    Div(Label("状态", cls="form-label"), Select(Option("在用", value="在用"), Option("闲置", value="闲置"), Option("报废", value="报废"), name="status", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/equipment", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/equipment/save"
            ),
            cls="card"
        )
    )


@ar("/equipment/save", methods=["POST"])
def equipment_save(code: str, name: str, category: str = "仪器设备", model: str = "",
                   acquisition_date: str = "", acquisition_cost: str = "0",
                   useful_life: str = "60", monthly_depreciation: str = "0", status: str = "在用"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = equipment_tb.insert(
        code=code, name=name, category=category, model=model,
        acquisition_date=acquisition_date, acquisition_cost=float(acquisition_cost) if acquisition_cost else 0.0,
        depreciation_method="年限平均法", useful_life=int(useful_life) if useful_life else 60,
        monthly_depreciation=float(monthly_depreciation) if monthly_depreciation else 0.0,
        status=status, dept_id=0, created_at=now
    )
    log_data_change("equipment", getattr(rec, "id", 0), "acquisition_cost",
                    old_val="", new_val=f"{code} {name} ¥{acquisition_cost or 0:,.2f}",
                    operator="system")
    return RedirectResponse(url="/equipment", status_code=303)


@ar("/equipment/{eid}/edit")
def equipment_edit(eid: int):
    e = equipment_tb[eid]
    return page_layout(
        "编辑设备", "首页 / 研发资产 / 设备档案 / 编辑", "/equipment",
        Div(
            Form(
                Input(type="hidden", name="id", value=e.id),
                Div(
                    Div(Label("设备编码", cls="form-label"), Input(name="code", value=e.code, cls="form-input", required=True), cls="form-group"),
                    Div(Label("设备名称", cls="form-label"), Input(name="name", value=e.name, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("类别", cls="form-label"), Select(Option("仪器设备"), Option("专用设备"), Option("软件"), Option("在用建筑物"), name="category", cls="form-select"), cls="form-group"),
                    Div(Label("型号", cls="form-label"), Input(name="model", value=e.model, cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("原值（元）", cls="form-label"), Input(name="acquisition_cost", type="number", value=e.acquisition_cost, cls="form-input"), cls="form-group"),
                    Div(Label("使用年限（月）", cls="form-label"), Input(name="useful_life", type="number", value=e.useful_life, cls="form-input"), cls="form-group"),
                    Div(Label("月折旧额（元）", cls="form-label"), Input(name="monthly_depreciation", type="number", value=e.monthly_depreciation, cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/equipment", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/equipment/update"
            ),
            cls="card"
        )
    )


@ar("/equipment/update", methods=["POST"])
def equipment_update(id: int, code: str, name: str, category: str = "仪器设备", model: str = "",
                     acquisition_cost: str = "0", useful_life: str = "60",
                     monthly_depreciation: str = "0"):
    e = equipment_tb[id]
    e.code, e.name, e.category, e.model = code, name, category, model
    e.acquisition_cost = float(acquisition_cost) if acquisition_cost else 0.0
    e.useful_life = int(useful_life) if useful_life else 60
    e.monthly_depreciation = float(monthly_depreciation) if monthly_depreciation else 0.0
    equipment_tb.update(e)
    return RedirectResponse(url="/equipment", status_code=303)


# ── 设备工时登记 ──────────────────────────────────────────

@ar("/equipment/worktime")
def equipment_worktime_index(equipment_id: str = "", project_id: str = "", month: str = ""):
    where = []
    if equipment_id:
        where.append(f"equipment_id={equipment_id}")
    if project_id:
        where.append(f"project_id={project_id}")
    if month:
        where.append(f"work_date LIKE '{month}%'")
    cond = " AND ".join(where) if where else None
    records = equipment_work_time_tb(where=cond, order_by="work_date DESC") if cond else equipment_work_time_tb(order_by="work_date DESC")

    rows = []
    total_hours = 0.0
    for r in records:
        eq = equipment_tb[r.equipment_id] if r.equipment_id else None
        proj = projects_tb[r.project_id] if r.project_id else None
        total_hours += r.hours
        rows.append([
            eq.code if eq else "—", eq.name if eq else "—",
            proj.name if proj else "—",
            r.work_date, f"{r.hours:.1f}", r.task_desc or "—",
            A("编辑", href=f"/equipment/worktime/{r.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "研发设备工时登记", "首页 / 研发资产 / 设备工时", "/equipment",
        Div(
            Div(
                Span("设备工时记录"),
                A("+ 登记设备工时", href="/equipment/worktime/new", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("设备", cls="form-label"), Select(*_eq_options(equipment_id), name="equipment_id", cls="form-select"), cls="form-group"),
                    Div(Label("项目", cls="form-label"), Select(*project_options(project_id), name="project_id", cls="form-select"), cls="form-group"),
                    Div(Label("月份", cls="form-label"), Select(*month_options(month), name="month", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(Button("筛选", type="submit", cls="btn btn-primary"), A("重置", href="/equipment/worktime", cls="btn btn-outline"), style="display:flex;gap:10px;"),
                method="get", action="/equipment/worktime"
            ),
            alert_box(f"当前共 {len(rows)} 条记录，合计设备工时 {total_hours:.1f} 小时。", "info") if rows else empty_state("🔧", "暂无设备工时记录"),
            data_table(["设备编码", "设备名称", "项目", "日期", "工时", "工作内容", "操作"], rows) if rows else Div(),
            cls="card"
        )
    )


@ar("/equipment/worktime/new")
def equipment_worktime_new():
    return page_layout(
        "登记设备工时", "首页 / 研发资产 / 设备工时 / 新增", "/equipment",
        Div(
            Form(
                Div(
                    Div(Label("设备", cls="form-label"), Select(*_eq_options(), name="equipment_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("日期", cls="form-label"), Input(name="work_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input", required=True), cls="form-group"),
                    Div(Label("工时（小时）", cls="form-label"), Input(name="hours", type="number", step="0.5", min="0.5", max="744", placeholder="如：40", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("工作内容", cls="form-label"), Textarea(name="task_desc", placeholder="简要描述本次设备用途...", cls="form-textarea"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/equipment/worktime", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/equipment/worktime/save"
            ),
            cls="card"
        )
    )


@ar("/equipment/worktime/save", methods=["POST"])
def equipment_worktime_save(equipment_id: str, project_id: str, work_date: str, hours: str, task_desc: str = ""):
    eid = int(equipment_id)
    pid = int(project_id)
    h = float(hours)
    existing = equipment_work_time_tb(where=f"equipment_id={eid} AND project_id={pid} AND work_date='{work_date}'")
    if existing:
        return page_layout("登记设备工时", "首页 / 研发资产 / 设备工时 / 新增", "/equipment",
            alert_box(f"该设备在该项目 {work_date} 已有工时记录，请勿重复登记。", "danger"),
            A("← 返回", href="/equipment/worktime/new", cls="btn btn-outline"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = equipment_work_time_tb.insert(equipment_id=eid, project_id=pid, work_date=work_date, hours=h, task_desc=task_desc, created_at=now)
    log_data_change("equipment_worktime", getattr(rec, "id", 0), "hours",
                    old_val="", new_val=f"设备{eid} 项目{pid} {work_date} {h}h",
                    operator="system")
    return RedirectResponse(url="/equipment/worktime", status_code=303)


@ar("/equipment/worktime/{wid}/edit")
def equipment_worktime_edit(wid: int):
    r = equipment_work_time_tb[wid]
    return page_layout(
        "编辑设备工时", "首页 / 研发资产 / 设备工时 / 编辑", "/equipment",
        Div(
            Form(
                Input(type="hidden", name="id", value=r.id),
                Div(
                    Div(Label("设备", cls="form-label"), Select(*_eq_options(r.equipment_id), name="equipment_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("项目", cls="form-label"), Select(*project_options(r.project_id), name="project_id", cls="form-select", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("日期", cls="form-label"), Input(name="work_date", type="date", value=r.work_date, cls="form-input", required=True), cls="form-group"),
                    Div(Label("工时（小时）", cls="form-label"), Input(name="hours", type="number", step="0.5", min="0.5", max="744", value=r.hours, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("工作内容", cls="form-label"), Textarea(name="task_desc", cls="form-textarea")(r.task_desc or ""), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/equipment/worktime", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/equipment/worktime/update"
            ),
            cls="card"
        )
    )


@ar("/equipment/worktime/update", methods=["POST"])
def equipment_worktime_update(id: int, equipment_id: str, project_id: str, work_date: str, hours: str, task_desc: str = ""):
    r = equipment_work_time_tb[id]
    r.equipment_id, r.project_id, r.work_date = int(equipment_id), int(project_id), work_date
    r.hours, r.task_desc = float(hours), task_desc
    equipment_work_time_tb.update(r)
    return RedirectResponse(url="/equipment/worktime", status_code=303)


# ── 设备折旧分摊 ──────────────────────────────────────────

@ar("/equipment/depreciation")
def equipment_depreciation_index(month: str = ""):
    if not month:
        month = date.today().strftime("%Y-%m")
    records = equipment_depreciation_tb(where=f"cost_month='{month}'", order_by="id")
    rows = []
    for d in records:
        eq = equipment_tb[d.equipment_id] if d.equipment_id else None
        status_cls = "badge-green" if d.status == "已分摊" else "badge-orange"
        ratio = d.rd_usage_ratio if d.rd_usage_ratio else 1.0
        rows.append([
            eq.code if eq else "—", eq.name if eq else "—",
            d.cost_month, f"¥{d.monthly_depreciation:,.0f}",
            f"{ratio:.0%}",
            f"{d.allocated_hours_total:.0f} h" if d.allocated_hours_total else "—",
            Span(d.status, cls=f"badge {status_cls}"),
            A("用途占比", href=f"/equipment/depreciation/{d.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "设备折旧费用分摊", "首页 / 研发资产 / 折旧分摊", "/equipment",
        Div(
            Div(
                Span("设备折旧总账"),
                Form(
                    Div(
                        Div(Label("月份", cls="form-label"), Select(*month_options(month), name="month", cls="form-select"), cls="form-group"),
                        Button("查询", type="submit", cls="btn btn-primary"),
                        cls="form-row", style="gap:12px;align-items:end;"
                    ),
                    method="get", action="/equipment/depreciation"
                ),
                cls="card-title"
            ),
            alert_box("选择月份后点击「执行分摊」，按当月各设备研发用途占比（默认100%）×工时占比将月折旧额分摊到各项目（写入折旧费用与长期待摊 科目03）。兼产设备请务必登记「研发用途占比」，否则将高估研发费用。", "info"),
            data_table(["设备编码", "设备名称", "月份", "月折旧额", "研发用途占比", "已分摊工时", "状态", ""], rows) if rows else empty_state("✓", f"{month} 没有折旧记录"),
            cls="card"
        ),
        Div(
            A("执行分摊", href=f"/equipment/depreciation/allocate/run?month={month}", cls="btn btn-success"),
            A("← 返回设备档案", href="/equipment", cls="btn btn-outline"),
            style="display:flex;gap:10px;margin-top:16px;"
        ) if rows else Div(A("← 返回设备档案", href="/equipment", cls="btn btn-outline"), style="margin-top:16px;")
    )


@ar("/equipment/depreciation/{did}/edit")
def equipment_depreciation_edit(did: int):
    d = equipment_depreciation_tb[did]
    eq = equipment_tb[d.equipment_id] if d.equipment_id else None
    ratio = d.rd_usage_ratio if d.rd_usage_ratio else 1.0
    return page_layout(
        "登记研发用途占比", "首页 / 研发资产 / 折旧分摊 / 用途占比", "/equipment",
        Div(
            alert_box("研发设备若同时用于生产、管理等非研发活动，仅可按“研发用途占比”将对应部分折旧归集为研发费用。"
                     "例如某服务器 80% 时间用于研发，则登记 0.8。未拆分将高估研发费用加计扣除基数。", "info"),
            Form(
                Input(type="hidden", name="id", value=d.id),
                Div(
                    Div(Label("设备", cls="form-label"), Input(name="eq_name", value=f"{eq.code if eq else ''} {eq.name if eq else ''}", cls="form-input", disabled=True), cls="form-group"),
                    Div(Label("月份", cls="form-label"), Input(name="month", value=d.cost_month, cls="form-input", disabled=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("月折旧额（元）", cls="form-label"), Input(name="dep", value=d.monthly_depreciation, cls="form-input", disabled=True), cls="form-group"),
                    Div(Label("研发用途占比", cls="form-label"), Input(name="rd_usage_ratio", type="number", step="0.05", min="0", max="1", value=ratio, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href=f"/equipment/depreciation?month={d.cost_month}", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/equipment/depreciation/update"
            ),
            cls="card"
        )
    )


@ar("/equipment/depreciation/update", methods=["POST"])
def equipment_depreciation_update(id: int, rd_usage_ratio: str = "1.0"):
    d = equipment_depreciation_tb[id]
    try:
        r = float(rd_usage_ratio)
    except ValueError:
        r = 1.0
    d.rd_usage_ratio = max(0.0, min(1.0, r))
    equipment_depreciation_tb.update(d)
    return RedirectResponse(url=f"/equipment/depreciation?month={d.cost_month}", status_code=303)


@ar("/equipment/depreciation/allocate/run")
def equipment_depreciation_run(month: str = ""):
    if not month:
        month = date.today().strftime("%Y-%m")

    pending = equipment_depreciation_tb(where=f"cost_month='{month}' AND status='待分摊'")
    if not pending:
        return page_layout("设备折旧分摊", "首页 / 研发资产 / 折旧分摊", "/equipment",
            alert_box(f"{month} 没有待分摊的设备折旧记录。", "warning"),
            A("← 返回", href="/equipment/depreciation", cls="btn btn-outline"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = subject_by_code("03")  # 折旧费用与长期待摊
    created_count = 0
    total_amount = 0.0
    details = []
    warn_no_ratio = False  # 是否存在未按研发用途占比登记的折旧（可能高估）
    warn_building_excluded = False  # 是否存在建筑物类折旧被剔除加计扣除口径

    for d in pending:
        if d.monthly_depreciation <= 0:
            continue
        eq = equipment_tb[d.equipment_id]
        # 研发用途占比：设备兼用于非研发活动时，仅按该比例归集（默认 1.0=全部研发）
        rd_ratio = d.rd_usage_ratio if d.rd_usage_ratio else 1.0
        if rd_ratio >= 1.0:
            warn_no_ratio = True
        work_records = equipment_work_time_tb(where=f"equipment_id={d.equipment_id} AND work_date LIKE '{month}%'")
        if not work_records:
            continue
        project_hours = defaultdict(float)
        for rec in work_records:
            project_hours[rec.project_id] += rec.hours
        total_wh = sum(project_hours.values())
        if total_wh <= 0:
            continue

        # 研发可归集折旧池 = 月折旧额 × 研发用途占比，再按各项目工时占比拆分
        rd_depr_pool = round(d.monthly_depreciation * rd_ratio, 2)
        for proj_id, hours in project_hours.items():
            proj = projects_tb[proj_id]
            node = get_project_node_for_date(proj_id, f"{month}-28")
            phase = node.phase if node else "研究"
            cap_status = capitalize_status_for_phase(phase)
            # 加计扣除口径仅接受仪器、设备折旧；建筑物类折旧剔除加计扣除口径
            alloc_caliber = equipment_caliber_for_category(eq.category, proj.caliber)
            if "加计扣除" not in alloc_caliber:
                warn_building_excluded = True
            ratio = hours / total_wh
            amount = round(rd_depr_pool * ratio, 2)
            if amount <= 0:
                continue
            add_expense(
                project_id=proj_id, node_id=node.id if node else 0,
                subject_id=subject.id, subject_name=subject.name,
                amount=amount, expense_date=f"{month}-28", phase=phase,
                capitalize_status=cap_status, caliber=alloc_caliber,
                description=f"{month} 设备折旧分摊：{eq.name} → {proj.name}（{hours:.0f}h，研发占比{rd_ratio:.0%}）",
                source="设备折旧分摊", created_at=now
            )
            created_count += 1
            total_amount += amount
            details.append((eq.name, proj.name, hours, amount))

        d.status = "已分摊"
        d.allocated_hours_total = total_wh
        equipment_depreciation_tb.update(d)

    warn_html = ""
    if warn_no_ratio:
        warn_html = alert_box(
            "提示：存在研发用途占比登记为 100% 的设备折旧（如兼产设备未拆分非研发工时）。"
            "请在各设备折旧总账中据实登记「研发用途占比」，否则可能高估研发费用加计扣除基数。",
            "warning")
    if warn_building_excluded:
        warn_html += alert_box(
            "注意：本次分摊包含「在用建筑物 / 房屋」类资产折旧。按税法规定，研发费用加计扣除口径"
            "仅认可仪器、设备的折旧费，建筑物折旧不得计入加计扣除（可计入高企认定口径）。"
            "系统已自动将其归集口径调整为不含「加计扣除」，避免高估加计扣除基数。",
            "info")

    result_rows = [[e, proj, f"{h:.0f}", f"¥{a:,.2f}"] for e, proj, h, a in details]
    return page_layout(
        "分摊结果", "首页 / 研发资产 / 折旧分摊 / 结果", "/equipment",
        warn_html,
        alert_box(f"{month} 设备折旧费用分摊完成：共生成 {created_count} 笔费用记录，合计 ¥{total_amount:,.2f}。", "success"),
        Div(
            Div("分摊明细", cls="card-title"),
            data_table(["设备", "项目", "工时", "分摊金额"], result_rows) if result_rows else empty_state("📋", "无分摊明细"),
            cls="card"
        ),
        Div(A("← 返回折旧分摊", href="/equipment/depreciation", cls="btn btn-outline"), style="margin-top:16px;")
    )
