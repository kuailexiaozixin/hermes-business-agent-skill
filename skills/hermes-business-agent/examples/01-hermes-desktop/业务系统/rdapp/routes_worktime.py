"""routes_worktime.py — 研发人员工时登记与人工费用分摊

功能：
- 工时登记（按人员/项目/日期）
- 工时统计（按人员/项目/月份汇总）
- 人工费用总账管理
- 按工时自动分摊生成人员人工费用记录
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from collections import defaultdict
from .db import (
    work_time_tb, labor_cost_tb, labor_alloc_tb, personnel_tb, projects_tb, expenses_tb,
    subjects_tb, get_project_node_for_date, capitalize_status_for_phase,
    worktime_alert_rules_tb, risk_alerts_tb, audit_tb,
)
from .components import (
    project_options,
    month_options,
    person_options,

    page_layout, data_table, empty_state, alert_box
)
from .routes_datacenter import log_data_change

ar = APIRouter()

# ── 辅助函数（选项下拉，局部复用）────────────────────────








# ── 工时登记 ──────────────────────────────────────────────


@ar("/worktime")
def worktime_index(person_id: str = "", project_id: str = "", start: str = "", end: str = ""):
    """工时登记首页"""
    where = []
    if person_id:
        where.append(f"person_id={person_id}")
    if project_id:
        where.append(f"project_id={project_id}")
    if start:
        where.append(f"work_date>='{start}'")
    if end:
        where.append(f"work_date<='{end}'")
    cond = " AND ".join(where) if where else None

    if cond:
        records = work_time_tb(where=cond, order_by="work_date DESC")
    else:
        records = work_time_tb(order_by="work_date DESC")

    rows = []
    total_hours = 0.0
    for r in records:
        person = personnel_tb[r.person_id] if r.person_id else None
        proj = projects_tb[r.project_id] if r.project_id else None
        total_hours += r.hours
        rows.append([
            person.name if person else "—",
            proj.name if proj else "—",
            r.work_date,
            f"{r.hours:.1f}",
            r.task_desc or "—",
            A("编辑", href=f"/worktime/{r.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "工时登记", "首页 / 工时管理 / 工时登记", "/worktime",
        Div(
            Div(
                Span("工时记录"),
                A("+ 登记工时", href="/worktime/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/worktime", cls="btn btn-outline btn-sm"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("人员", cls="form-label"), Select(*person_options(person_id), name="person_id", cls="form-select"), cls="form-group"),
                    Div(Label("项目", cls="form-label"), Select(*project_options(project_id), name="project_id", cls="form-select"), cls="form-group"),
                    Div(Label("开始日期", cls="form-label"), Input(name="start", type="date", value=start, cls="form-input"), cls="form-group"),
                    Div(Label("结束日期", cls="form-label"), Input(name="end", type="date", value=end, cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("筛选", type="submit", cls="btn btn-primary"),
                    A("重置", href="/worktime", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="get", action="/worktime"
            ),
            alert_box(f"当前筛选共 {len(rows)} 条记录，合计工时 {total_hours:.1f} 小时。", "info"),
            data_table(["人员", "项目", "日期", "工时", "工作内容", "操作"], rows) if rows else empty_state("📋", "暂无工时记录"),
            cls="card"
        )
    )


@ar("/worktime/new")
def worktime_new():
    """新增工时登记表单"""
    return page_layout(
        "登记工时", "首页 / 工时管理 / 工时登记 / 新增", "/worktime",
        Div(
            Form(
                Div(
                    Div(Label("人员", cls="form-label"), Select(*person_options(), name="person_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("日期", cls="form-label"), Input(name="work_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input", required=True), cls="form-group"),
                    Div(Label("工时（小时）", cls="form-label"), Input(name="hours", type="number", step="0.5", min="0.5", max="24", placeholder="如：8", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("工作内容", cls="form-label"), Textarea(name="task_desc", placeholder="简要描述本次工作内容...", cls="form-textarea"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/worktime", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/worktime/save"
            ),
            cls="card"
        )
    )


@ar("/worktime/save", methods=["POST"])
def worktime_save(person_id: str, project_id: str, work_date: str, hours: str, task_desc: str = ""):
    """保存工时登记"""
    pid = int(person_id)
    proj_id = int(project_id)
    h = float(hours)

    # 校验：单日同一人员同一项目不能重复
    existing = work_time_tb(where=f"person_id={pid} AND project_id={proj_id} AND work_date='{work_date}'")
    if existing:
        return page_layout(
            "登记工时", "首页 / 工时管理 / 工时登记 / 新增", "/worktime",
            alert_box(f"该人员在该项目 {work_date} 已有工时记录，请勿重复登记。", "danger"),
            A("← 返回", href="/worktime/new", cls="btn btn-outline")
        )

    # 校验：单日总工时不超过24小时
    same_day = work_time_tb(where=f"person_id={pid} AND work_date='{work_date}'")
    day_total = sum(rec.hours for rec in same_day) + h
    if day_total > 24:
        return page_layout(
            "登记工时", "首页 / 工时管理 / 工时登记 / 新增", "/worktime",
            alert_box(f"该人员 {work_date} 当日总工时 {day_total:.1f} 小时，超过 24 小时上限。", "danger"),
            A("← 返回", href="/worktime/new", cls="btn btn-outline")
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = work_time_tb.insert(
        person_id=pid, project_id=proj_id, work_date=work_date,
        hours=h, task_desc=task_desc, created_at=now
    )
    log_data_change("worktime", getattr(rec, "id", 0), "hours",
                    old_val="", new_val=f"人员{pid} 项目{proj_id} {work_date} {h}h",
                    operator="system")
    # ── 工时预警检查（缺口②）────────────────────────
    check_worktime_alerts(pid, proj_id, work_date, h, day_total)
    return RedirectResponse(url="/worktime", status_code=303)


@ar("/worktime/{wid}/edit")
def worktime_edit(wid: int):
    """编辑工时"""
    r = work_time_tb[wid]
    return page_layout(
        "编辑工时", "首页 / 工时管理 / 工时登记 / 编辑", "/worktime",
        Div(
            Form(
                Input(type="hidden", name="id", value=r.id),
                Div(
                    Div(Label("人员", cls="form-label"), Select(*person_options(r.person_id), name="person_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("项目", cls="form-label"), Select(*project_options(r.project_id), name="project_id", cls="form-select", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("日期", cls="form-label"), Input(name="work_date", type="date", value=r.work_date, cls="form-input", required=True), cls="form-group"),
                    Div(Label("工时（小时）", cls="form-label"), Input(name="hours", type="number", step="0.5", min="0.5", max="24", value=r.hours, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("工作内容", cls="form-label"), Textarea(name="task_desc", cls="form-textarea")(r.task_desc or ""), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/worktime", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/worktime/update"
            ),
            cls="card"
        )
    )


@ar("/worktime/update", methods=["POST"])
def worktime_update(id: int, person_id: str, project_id: str, work_date: str, hours: str, task_desc: str = ""):
    """更新工时"""
    r = work_time_tb[id]
    r.person_id = int(person_id)
    r.project_id = int(project_id)
    r.work_date = work_date
    r.hours = float(hours)
    r.task_desc = task_desc
    work_time_tb.update(r)
    return RedirectResponse(url="/worktime", status_code=303)


# ── 工时统计 ──────────────────────────────────────────────


@ar("/worktime/summary")
def worktime_summary(month: str = ""):
    """工时统计（按人员+项目汇总）"""
    if not month:
        month = date.today().strftime("%Y-%m")

    records = work_time_tb(where=f"work_date LIKE '{month}%'")

    # 按人员+项目汇总
    summary = defaultdict(lambda: {"hours": 0.0, "person_name": "", "project_name": "", "days": 0})
    for r in records:
        person = personnel_tb[r.person_id] if r.person_id else None
        proj = projects_tb[r.project_id] if r.project_id else None
        key = (r.person_id, r.project_id)
        summary[key]["hours"] += r.hours
        summary[key]["days"] += 1
        summary[key]["person_name"] = person.name if person else "—"
        summary[key]["project_name"] = proj.name if proj else "—"

    rows = []
    for (pid, projid), v in summary.items():
        rows.append([
            v["person_name"],
            v["project_name"],
            f"{v['hours']:.1f}",
            str(v["days"]),
            f"{v['hours'] / max(v['days'], 1):.1f}",
        ])
    rows.sort(key=lambda x: (x[0], x[1]))

    return page_layout(
        "工时统计", "首页 / 工时管理 / 工时统计", "/worktime",
        Div(
            Div(
                Span("工时统计"),
                Form(
                    Div(
                        Div(Label("月份", cls="form-label"), Select(*month_options(month), name="month", cls="form-select"), cls="form-group"),
                        Button("查询", type="submit", cls="btn btn-primary"),
                        cls="form-row", style="gap:12px;align-items:end;"
                    ),
                    method="get", action="/worktime/summary"
                ),
                cls="card-title"
            ),
            data_table(["人员", "项目", "总工时", "登记天数", "日均工时"], rows) if rows else empty_state("📋", "该月份暂无工时数据"),
            cls="card"
        )
    )


# ── 人工费用总账 ──────────────────────────────────────────────


@ar("/labor-costs")
def labor_cost_index():
    """人工费用总账列表"""
    all_costs = labor_cost_tb(order_by="cost_month DESC")
    rows = []
    for lc in all_costs:
        person = personnel_tb[lc.person_id] if lc.person_id else None
        status_cls = "badge-green" if lc.status == "已分摊" else "badge-orange"
        rows.append([
            person.name if person else "—",
            lc.cost_month,
            f"¥{lc.total_salary:,.2f}",
            f"{lc.work_hours_total:.1f}",
            f"¥{lc.hourly_cost:.2f}/h",
            Span(lc.status, cls=f"badge {status_cls}"),
            A("编辑", href=f"/labor-costs/{lc.id}/edit", cls="btn btn-outline btn-sm") if lc.status == "待分摊" else "—",
        ])

    return page_layout(
        "人工费用总账", "首页 / 工时管理 / 人工费用总账", "/labor-costs",
        Div(
            Div(
                Span("人工费用总账"),
                A("+ 新增总账", href="/labor-costs/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/labor_cost", cls="btn btn-outline btn-sm"),
                cls="card-title"
            ),
            alert_box("人工费用总账记录每位研发人员每月的人工总成本（工资+社保+公积金等）。系统按工时占比自动分摊到各项目。", "info"),
            data_table(["人员", "月份", "人工总成本", "总工时", "单位工时成本", "状态", "操作"], rows) if rows else empty_state("📋", "暂无人工费用总账"),
            cls="card"
        )
    )


@ar("/labor-costs/new")
def labor_cost_new():
    """新增人工费用总账"""
    return page_layout(
        "新增人工费用总账", "首页 / 工时管理 / 人工费用总账 / 新增", "/labor-costs",
        Div(
            Form(
                Div(
                    Div(Label("人员", cls="form-label"), Select(*person_options(), name="person_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("月份", cls="form-label"), Select(*month_options(), name="cost_month", cls="form-select", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("人工总成本（元）", cls="form-label"), Input(name="total_salary", type="number", step="0.01", min="0", placeholder="如：30000", cls="form-input", required=True), cls="form-group"),
                    Div(Label("总工时（小时）", cls="form-label"), Input(name="work_hours_total", type="number", step="0.5", min="0", placeholder="如：176", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/labor-costs", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/labor-costs/save"
            ),
            cls="card"
        )
    )


@ar("/labor-costs/save", methods=["POST"])
def labor_cost_save(person_id: str, cost_month: str, total_salary: str, work_hours_total: str):
    """保存人工费用总账"""
    salary = float(total_salary)
    hours = float(work_hours_total)
    hourly = round(salary / hours, 2) if hours > 0 else 0.0

    # 校验：同一人员同一月份不能重复
    existing = labor_cost_tb(where=f"person_id={int(person_id)} AND cost_month='{cost_month}'")
    if existing:
        return page_layout(
            "新增人工费用总账", "首页 / 工时管理 / 人工费用总账 / 新增", "/labor-costs",
            alert_box("该人员该月份已存在人工费用总账，请勿重复创建。", "danger"),
            A("← 返回", href="/labor-costs/new", cls="btn btn-outline")
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = labor_cost_tb.insert(
        person_id=int(person_id), cost_month=cost_month, total_salary=salary,
        work_hours_total=hours, hourly_cost=hourly, status="待分摊", created_at=now
    )
    log_data_change("labor_cost", getattr(rec, "id", 0), "total_salary",
                    old_val="", new_val=f"人员{person_id} {cost_month} ¥{salary:,.2f}",
                    operator="system")
    return RedirectResponse(url="/labor-costs", status_code=303)


@ar("/labor-costs/{lcid}/edit")
def labor_cost_edit(lcid: int):
    """编辑人工费用总账"""
    lc = labor_cost_tb[lcid]
    return page_layout(
        "编辑人工费用总账", "首页 / 工时管理 / 人工费用总账 / 编辑", "/labor-costs",
        Div(
            Form(
                Input(type="hidden", name="id", value=lc.id),
                Div(
                    Div(Label("人员", cls="form-label"), Select(*person_options(lc.person_id), name="person_id", cls="form-select", required=True), cls="form-group"),
                    Div(Label("月份", cls="form-label"), Select(*month_options(lc.cost_month), name="cost_month", cls="form-select", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("人工总成本（元）", cls="form-label"), Input(name="total_salary", type="number", step="0.01", value=lc.total_salary, cls="form-input", required=True), cls="form-group"),
                    Div(Label("总工时（小时）", cls="form-label"), Input(name="work_hours_total", type="number", step="0.5", value=lc.work_hours_total, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/labor-costs", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/labor-costs/update"
            ),
            cls="card"
        )
    )


@ar("/labor-costs/update", methods=["POST"])
def labor_cost_update(id: int, person_id: str, cost_month: str, total_salary: str, work_hours_total: str):
    """更新人工费用总账"""
    lc = labor_cost_tb[id]
    lc.person_id = int(person_id)
    lc.cost_month = cost_month
    lc.total_salary = float(total_salary)
    lc.work_hours_total = float(work_hours_total)
    lc.hourly_cost = round(lc.total_salary / lc.work_hours_total, 2) if lc.work_hours_total > 0 else 0.0
    labor_cost_tb.update(lc)
    return RedirectResponse(url="/labor-costs", status_code=303)


# ── 人工费用分摊 ──────────────────────────────────────────────


@ar("/labor-costs/allocate")
def labor_cost_allocate(month: str = ""):
    """人工费用分摊页面：展示待分摊记录与执行分摊"""
    if not month:
        month = date.today().strftime("%Y-%m")

    pending = labor_cost_tb(where=f"cost_month='{month}' AND status='待分摊'")
    rows = []
    for lc in pending:
        person = personnel_tb[lc.person_id] if lc.person_id else None
        rows.append([
            person.name if person else "—",
            lc.cost_month,
            f"¥{lc.total_salary:,.2f}",
            f"{lc.work_hours_total:.1f}",
            f"¥{lc.hourly_cost:.2f}/h",
        ])

    return page_layout(
        "人工费用分摊", "首页 / 工时管理 / 人工费用分摊", "/labor-costs",
        Div(
            Div(
                Span("待分摊总账"),
                Form(
                    Div(
                        Div(Label("月份", cls="form-label"), Select(*month_options(month), name="month", cls="form-select"), cls="form-group"),
                        Button("查询", type="submit", cls="btn btn-primary"),
                        cls="form-row", style="gap:12px;align-items:end;"
                    ),
                    method="get", action="/labor-costs/allocate"
                ),
                cls="card-title"
            ),
            alert_box(f"选择月份后，点击「执行分摊」将按该月工时记录把人工费用自动分摊到各项目。", "info"),
            data_table(["人员", "月份", "人工总成本", "总工时", "单位工时成本"], rows) if rows else empty_state("✓", f"{month} 没有待分摊记录"),
            cls="card"
        ),
        Div(
            A("执行分摊", href=f"/labor-costs/allocate/run?month={month}", cls="btn btn-success"),
            A("← 返回总账", href="/labor-costs", cls="btn btn-outline"),
            style="display:flex;gap:10px;margin-top:16px;"
        ) if rows else Div(
            A("← 返回总账", href="/labor-costs", cls="btn btn-outline"),
            style="margin-top:16px;"
        )
    )


@ar("/labor-costs/allocate/run")
def labor_cost_allocate_run(month: str = ""):
    """执行人工费用分摊"""
    if not month:
        month = date.today().strftime("%Y-%m")

    pending = labor_cost_tb(where=f"cost_month='{month}' AND status='待分摊'")
    if not pending:
        return page_layout(
            "人工费用分摊", "首页 / 工时管理 / 人工费用分摊", "/labor-costs",
            alert_box(f"{month} 没有待分摊的人工费用总账。", "warning"),
            A("← 返回", href="/labor-costs/allocate", cls="btn btn-outline")
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    batch_no = f"LC-{month}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    subject = subjects_tb[1]  # 人员人工费用

    phase_date = f"{month}-28"  # 月末日期（作为阶段判定代表日）
    created_count = 0
    total_amount = 0.0
    details = []  # [(person, project, hours, amount)]

    for lc in pending:
        if lc.work_hours_total <= 0:
            continue

        # 查询该人员该月工时，按项目汇总
        work_records = work_time_tb(where=f"person_id={lc.person_id} AND work_date LIKE '{month}%'")
        if not work_records:
            continue

        # 按项目汇总工时
        project_hours = defaultdict(float)
        for rec in work_records:
            project_hours[rec.project_id] += rec.hours

        total_wh = sum(project_hours.values())
        if total_wh <= 0:
            continue

        person = personnel_tb[lc.person_id]

        # ── 研发工时占比（仅研发工时可计入研发费用，排除非研发工时）──
        # work_hours_total 为当月总工时（研发+非研发）；non_rd_hours 为当月非研发工时。
        # 当未登记非研发工时时，默认全部工时计入研发（并在结果页提示可能高估）。
        rd_hours = lc.work_hours_total - lc.non_rd_hours
        if rd_hours <= 0:
            details.append((person.name, "（跳过）", 0.0, 0.0))
            continue
        rd_ratio = rd_hours / lc.work_hours_total

        for proj_id, hours in project_hours.items():
            proj = projects_tb[proj_id]
            # 阶段按【费用发生日】判定（而非当前进度节点）
            node = get_project_node_for_date(proj_id, phase_date)
            phase = node.phase if node else "研究"
            cap_status = capitalize_status_for_phase(phase)
            node_id = node.id if node else 0

            amount = round(lc.total_salary * rd_ratio * (hours / total_wh), 2)
            if amount <= 0:
                continue
            # 分摊明细落库（LaborAllocation / AL-07 分配表），形成可复查、可导出的举证依据
            alloc_rec = labor_alloc_tb.insert(
                cost_month=month,
                person_id=lc.person_id,
                person_name=person.name,
                person_category=getattr(person, "person_category", ""),
                project_id=proj_id,
                project_name=proj.name,
                project_hours=hours,
                person_total_hours=lc.work_hours_total,
                rd_hours=rd_hours,
                rd_ratio=rd_ratio,
                alloc_ratio=hours / total_wh,
                salary_base=lc.total_salary,
                amount=amount,
                caliber=proj.caliber,
                phase=phase,
                batch_no=batch_no,
                created_at=now,
            )
            log_data_change("labor_alloc", getattr(alloc_rec, "id", 0), "amount",
                            old_val="", new_val=f"批次{batch_no} {person.name}→{proj.name} ¥{amount:,.2f}",
                            operator="system")
            exp_rec = expenses_tb.insert(
                project_id=proj_id,
                node_id=node_id,
                subject_id=subject.id,
                subject_name=subject.name,
                amount=amount,
                expense_date=f"{month}-28",  # 月末日期
                phase=phase,
                capitalize_status=cap_status,
                caliber=proj.caliber,
                person_id=lc.person_id,
                person_name=person.name,
                description=f"{month} 工时分摊：{person.name} → {proj.name}（{hours:.1f}h，研发工时占比 {rd_ratio*100:.0f}%）",
                source="工时分摊",
                created_at=now
            )
            log_data_change("expenses", getattr(exp_rec, "id", 0), "amount",
                            old_val="", new_val=f"工时分摊 {month} {person.name}→{proj.name} ¥{amount:,.2f}",
                            operator="system")
            created_count += 1
            total_amount += amount
            details.append((person.name, proj.name, hours, amount))

        lc.status = "已分摊"
        labor_cost_tb.update(lc)

    # 展示结果（含研发工时占比提示）
    warn_msgs = []
    if any(d[1] == "（跳过）" for d in details):
        warn_msgs.append("存在非研发工时≥总工时的人员，其人工费用未计入研发。")
    # 注：no_nonrd_warning 仅对最后一人有效，改为基于 pending 整体判断
    pending_no_nonrd = [lc for lc in pending if lc.non_rd_hours <= 0.0]
    if pending_no_nonrd:
        warn_msgs.append("部分人员未登记「非研发工时」，系统默认其全部工时计入研发，可能高估研发费用。")

    result_rows = [[p, proj, f"{h:.1f}", f"¥{a:,.2f}"] for p, proj, h, a in details if proj != "（跳过）"]

    extra = alert_box(" ".join(warn_msgs), "warning") if warn_msgs else Div()
    return page_layout(
        "分摊结果", "首页 / 工时管理 / 人工费用分摊 / 结果", "/labor-costs",
        alert_box(f"{month} 人工费用分摊完成：共生成 {created_count} 笔费用记录，合计 ¥{total_amount:,.2f}。", "success"),
        extra,
        Div(
            Div("分摊明细", cls="card-title"),
            data_table(["人员", "项目", "工时", "分摊金额"], result_rows) if result_rows else empty_state("📋", "无分摊明细"),
            cls="card"
        ),
        Div(
            A("查看费用归集", href="/expenses", cls="btn btn-primary"),
            A("← 返回", href="/labor-costs/allocate", cls="btn btn-outline"),
            style="display:flex;gap:10px;"
        )
    )


# ── 人工费用分摊明细（LaborAllocation 落库查询与导出） ───────


@ar("/labor-allocation")
def labor_allocation_index(month: str = "", batch_no: str = ""):
    """人工费用分摊明细：按月份/批次查询（AL-07 分配表举证）"""
    month = month or date.today().strftime("%Y-%m")
    if batch_no:
        recs = labor_alloc_tb(where=f"batch_no='{batch_no}'", order_by="id")
    else:
        recs = labor_alloc_tb(where=f"cost_month='{month}'", order_by="id")

    # 该月份最近 10 个批次号（下拉选择用）
    batches = []
    seen = set()
    for r in labor_alloc_tb(order_by="-id"):
        if r.cost_month == month and r.batch_no and r.batch_no not in seen:
            seen.add(r.batch_no)
            batches.append(r.batch_no)
        if len(batches) >= 10:
            break

    total = sum(r.amount for r in recs)
    rows = []
    for r in recs:
        rows.append([
            r.batch_no or "—", r.person_name or "—", r.person_category or "—",
            r.project_name or "—", f"{r.project_hours:.1f}",
            f"{r.rd_ratio*100:.0f}%", f"{r.alloc_ratio*100:.1f}%",
            f"¥{r.amount:,.2f}", r.caliber or "—", r.phase or "—", r.created_at or "—",
        ])

    batch_opts = [Option("— 全部批次 —", value="")]
    for b in batches:
        batch_opts.append(Option(b, value=b, selected=(b == batch_no)))

    return page_layout(
        "分摊明细", "首页 / 工时管理 / 分摊明细", "/labor-allocation",
        Div(
            Div(
                Span("人工费用分摊明细（AL-07）", style="font-size:15px;font-weight:600;"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("月份", cls="form-label"), Select(*month_options(month), name="month", cls="form-select"), cls="form-group"),
                    Div(Label("批次号", cls="form-label"), Select(*batch_opts, name="batch_no", cls="form-select"), cls="form-group"),
                    Button("查询", type="submit", cls="btn btn-primary"),
                    cls="form-row", style="gap:12px;align-items:end;"
                ),
                method="get", action="/labor-allocation"
            ),
            alert_box(f"{month} 分摊明细共 {len(rows)} 条，合计 ¥{total:,.2f}；每条对应一次工时分摊落库，可作人工费用分摊依据举证。", "info"),
            Div(
                A("导出 Excel", href=f"/labor-allocation/export?month={month}&batch_no={batch_no}", cls="btn btn-success btn-sm"),
                A("执行分摊", href=f"/labor-costs/allocate?month={month}", cls="btn btn-outline btn-sm"),
                style="display:flex;gap:8px;margin-top:12px;"
            ),
            cls="card"
        ),
        Div(
            Div("明细列表", cls="card-title"),
            data_table(["批次号", "人员", "类别", "项目", "项目工时", "研发占比", "项目占比", "分摊金额", "口径", "阶段", "落库时间"], rows)
            if rows else empty_state("📋", f"{month} 暂无分摊明细，请先执行人工费用分摊"),
            cls="card"
        ),
    )


@ar("/labor-allocation/export")
def labor_allocation_export(month: str = "", batch_no: str = ""):
    """导出分摊明细 Excel（.xlsx）"""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    month = month or date.today().strftime("%Y-%m")
    if batch_no:
        recs = labor_alloc_tb(where=f"batch_no='{batch_no}'", order_by="id")
    else:
        recs = labor_alloc_tb(where=f"cost_month='{month}'", order_by="id")

    wb = Workbook()
    ws = wb.active
    ws.title = "分摊明细"
    ws.append(["人工费用分摊明细", month, f"批次 {batch_no}" if batch_no else "全部批次"])
    ws.append([])
    ws.append(["批次号", "人员", "类别", "项目", "项目工时", "人员总工时", "研发工时",
               "研发占比", "项目占比", "人工总成本", "分摊金额", "口径", "阶段", "落库时间"])
    for r in recs:
        ws.append([r.batch_no or "", r.person_name or "", r.person_category or "",
                   r.project_name or "", r.project_hours or 0, r.person_total_hours or 0,
                   r.rd_hours or 0, r.rd_ratio or 0, r.alloc_ratio or 0,
                   r.salary_base or 0, r.amount or 0, r.caliber or "", r.phase or "",
                   r.created_at or ""])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 10
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 10
    ws.column_dimensions["H"].width = 10
    ws.column_dimensions["I"].width = 10
    ws.column_dimensions["J"].width = 12
    ws.column_dimensions["K"].width = 12
    ws.column_dimensions["L"].width = 10
    ws.column_dimensions["M"].width = 8
    ws.column_dimensions["N"].width = 20

    import io
    from urllib.parse import quote
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"人工费用分摊明细_{month}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    )


# ═══════════════════════════════════════════════
# 工时预警检查（缺口②：WorkTimeAlertRule 检测）
# ═══════════════════════════════════════════════

@ar("/worktime-alert-rules")
def worktime_alert_rules_index():
    """工时预警规则管理"""
    rules = worktime_alert_rules_tb(order_by="-id")

    rows = []
    for r in rules:
        status_cls = "badge-green" if r.enabled else "badge-gray"
        status_txt = "启用" if r.enabled else "禁用"
        scope = []
        if r.project_id:
            p = projects_tb[r.project_id]
            scope.append(f"项目:{p.name if p else r.project_id}")
        if r.person_id:
            per = personnel_tb[r.person_id]
            scope.append(f"人员:{per.name if per else r.person_id}")
        if not scope:
            scope.append("全局")
        rows.append(
            Tr(
                Td("、".join(scope)),
                Td(f"{r.min_rd_ratio:.0%}"),
                Td(f"{r.max_single_hours:g}h" if r.max_single_hours else "-"),
                Td(Span(status_txt, cls=status_cls)),
                Td(A("切换", href=f"/worktime-alert-rules/{r.id}/toggle", cls="btn btn-sm btn-outline"),
                   " ",
                   A("删除", href=f"/worktime-alert-rules/{r.id}/del", cls="btn btn-sm btn-outline")),
            )
        )
    table = Table(
        Thead(Tr(Th("范围"), Th("最低研发工时占比"), Th("单日上限"), Th("状态"), Th("操作"))),
        Tbody(*rows), cls="table",
    ) if rows else empty_state("", "暂无工时预警规则")

    add_form = Form(
        Div(
            Div(
                Label("项目ID（0=全局）", _for="project_id"),
                Input(id="project_id", name="project_id", type="number", value="0", cls="form-input"),
            ),
            Div(
                Label("人员ID（0=全局）", _for="person_id"),
                Input(id="person_id", name="person_id", type="number", value="0", cls="form-input"),
            ),
            Div(
                Label("最低研发工时占比", _for="min_rd_ratio"),
                Input(id="min_rd_ratio", name="min_rd_ratio", type="number", step="0.05", value="0.3", cls="form-input"),
            ),
            Div(
                Label("单日最高工时", _for="max_single_hours"),
                Input(id="max_single_hours", name="max_single_hours", type="number", step="0.5", value="12", cls="form-input"),
            ),
            Button("新增规则", type="submit", cls="btn btn-primary"),
            cls="form-grid",
        ),
        action="/worktime-alert-rules/add", method="POST",
    )

    content = Div(
        Div(
            H3("新增工时预警规则", cls="card-title"),
            add_form, cls="card",
        ),
        Div(
            H3("规则列表", cls="card-title"),
            table, cls="card",
        ),
        cls="page",
    )
    return page_layout("工时预警规则", "首页 / 工时管理 / 工时预警规则", "/worktime-alert-rules", content)


@ar("/worktime-alert-rules/add", methods=["POST"])
def worktime_alert_rule_add(project_id: str = "0", person_id: str = "0",
                            min_rd_ratio: str = "0.3", max_single_hours: str = "12"):
    """新增工时预警规则"""
    worktime_alert_rules_tb.insert(
        project_id=int(project_id or 0), person_id=int(person_id or 0),
        min_rd_ratio=float(min_rd_ratio or 0.3),
        max_single_hours=float(max_single_hours or 12),
        enabled=True, created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return RedirectResponse(url="/worktime-alert-rules", status_code=303)


@ar("/worktime-alert-rules/{rid}/toggle")
def worktime_alert_rule_toggle(rid: int):
    """启用/禁用工时预警规则"""
    r = worktime_alert_rules_tb[rid]
    if r:
        worktime_alert_rules_tb.update({"enabled": not r.enabled}, rid)
    return RedirectResponse(url="/worktime-alert-rules", status_code=303)


@ar("/worktime-alert-rules/{rid}/del")
def worktime_alert_rule_del(rid: int):
    """删除工时预警规则"""
    r = worktime_alert_rules_tb[rid]
    if r:
        worktime_alert_rules_tb.delete(rid)
    return RedirectResponse(url="/worktime-alert-rules", status_code=303)


def check_worktime_alerts(person_id: int, project_id: int,
                          work_date: str, hours: float, day_total: float):
    """保存工时后检查是否触发预警规则，生成 RiskAlert"""
    today = datetime.now().strftime("%Y-%m-%d")
    now_full = datetime.now().strftime("%Y-%m-%d %H:%M")
    rules = worktime_alert_rules_tb(where="enabled=1")

    for rule in rules:
        # 过滤条件：项目/人员匹配
        if rule.project_id and rule.project_id != project_id:
            continue
        if rule.person_id and rule.person_id != person_id:
            continue

        alerts = []

        # 单日工时上限
        if rule.max_single_hours > 0 and hours > rule.max_single_hours:
            alerts.append(("高",
                f"人员{person_id} 单日工时 {hours}h 超过上限 {rule.max_single_hours}h",
                "请核实工时记录"))

        # 研发工时占比过低（按月检查）
        if rule.min_rd_ratio > 0:
            month = work_date[:7]
            all_wt = work_time_tb(where=f"person_id={person_id} AND work_date LIKE '{month}%'")
            month_total = sum(w.hours for w in all_wt)
            if month_total > 0:
                # 研发项目通过 rd_nature 判断
                from .db import projects_tb
                rd_projects = projects_tb(where="rd_nature IS NOT NULL AND rd_nature != ''")
                rd_ids = [p.id for p in rd_projects]
                rd_hours = sum(w.hours for w in all_wt if w.project_id in rd_ids)
                rd_ratio = rd_hours / month_total
                if rd_ratio < rule.min_rd_ratio:
                    alerts.append(("中",
                        f"人员{person_id} {month} 研发工时占比 {rd_ratio:.1%} < {rule.min_rd_ratio:.0%}",
                        "增加研发工时投入"))

        # 去重写入预警
        for level, desc, action in alerts:
            exists = risk_alerts_tb(where=f"description='{desc}' AND created_at LIKE '{today}%'")
            if not exists:
                risk_alerts_tb.insert(
                    project_id=project_id, rule_id=rule.id,
                    level=level, description=desc,
                    status="未处理", suggested_action=action,
                    created_at=now_full,
                )
                try:
                    audit_tb.insert(
                        ts=now_full, action="工时预警", entity="工时",
                        entity_id=0, detail=desc[:80], actor="system",
                        before="", after="",
                    )
                except Exception:
                    pass
