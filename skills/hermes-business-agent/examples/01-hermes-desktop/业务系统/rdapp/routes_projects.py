"""routes_projects.py — 研发项目管理路由

管理项目全生命周期：立项（含研发/生产边界设置）→ 执行 → 结题
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date
from .db import (
    templates_tb, nodes_tb, projects_tb, project_nodes_tb, expenses_tb,
    evidence_tb, members_tb, personnel_tb, risks_tb, entrusted_tb,
    special_income_tb
)
from .components import (
    page_layout, phase_badge, status_badge, level_badge,
    data_table, empty_state, alert_box, progress_bar,
    org_options,
)

ar = APIRouter()


def _org_name(org_id):
    """org_id → 组织名（0 视为未分配主体）。"""
    from .db import orgs_tb
    if not org_id:
        return "未分配主体"
    try:
        o = orgs_tb[org_id]
        return f"{o.name}（{o.level}）" if o else "未分配主体"
    except Exception:
        return "未分配主体"


def _rd_nature_badge(nature):
    """研发性质徽标：自主研发/委托研发/受托研发"""
    cls = {"自主研发": "badge-green", "委托研发": "badge-orange", "受托研发": "badge-blue"}.get(nature, "badge-gray")
    return Span(nature, cls=f"badge {cls}")


@ar("/projects")
def projects():
    """项目列表"""
    all_projects = projects_tb()
    rows = []
    for p in all_projects:
        proj_expenses = expenses_tb(where=f"project_id={p.id}")
        used = sum(e.amount for e in proj_expenses)
        pct = (used / p.budget * 100) if p.budget > 0 else 0
        bar_color = "red" if pct > 90 else ("orange" if pct > 70 else "green")

        boundary_badge = {
            "纯研发": "badge-green", "混合": "badge-orange", "生产改进": "badge-blue"
        }.get(p.boundary_type, "badge-gray")

        rows.append([
            p.code,
            A(p.name, href=f"/projects/{p.id}", style="color:var(--primary);text-decoration:none;font-weight:500;"),
            p.manager,
            _org_name(p.org_id),
            _rd_nature_badge(p.rd_nature),
            Span(p.boundary_type, cls=f"badge {boundary_badge}"),
            f"¥{p.budget:,.0f}",
            f"¥{used:,.0f}",
            progress_bar(pct, bar_color),
            status_badge(p.status),
            A("详情", href=f"/projects/{p.id}", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "研发项目管理", "首页 / 研发项目", "/projects",
        Div(
            Div(
                Span("项目列表"),
                A("+ 新建项目", href="/projects/new", cls="btn btn-primary"),
                A("批量导入", href="/import/projects", cls="btn btn-outline"),
                cls="card-title"
            ),
            data_table(
                ["项目编号", "项目名称", "负责人", "法人主体", "研发性质", "研发/生产边界", "总预算", "已使用", "预算执行率", "状态", "操作"],
                rows
            ) if rows else empty_state("📋", "暂无项目，点击「新建项目」开始"),
            cls="card"
        )
    )


@ar("/projects/new")
def project_new():
    """新建项目表单"""
    all_templates = templates_tb()
    tpl_options = [Option("— 请选择流程模板 —", value="")] + [
        Option(f"{t.name}（{t.model_type}）", value=t.id) for t in all_templates
    ]

    return page_layout(
        "新建研发项目", "首页 / 研发项目 / 新建", "/projects",
        Div(
            Form(
                Div(
                    Div(
                        Label("项目名称", cls="form-label"),
                        Input(name="name", placeholder="如：智能数据分析平台研发", cls="form-input", required=True),
                        cls="form-group"
                    ),
                    Div(
                        Label("项目编号", cls="form-label"),
                        Input(name="code", placeholder="如：RD-2026-004", cls="form-input", required=True),
                        cls="form-group"
                    ),
                    cls="form-row"
                ),
                Div(
                    Div(
                        Label("项目经理", cls="form-label"),
                        Input(name="manager", placeholder="项目经理姓名", cls="form-input"),
                        cls="form-group"
                    ),
                    Div(
                        Label("适用流程模板", cls="form-label"),
                        Select(*tpl_options, name="template_id", cls="form-select", required=True),
                        cls="form-group"
                    ),
                    cls="form-row"
                ),
                Div(
                    Div(
                        Label("所属法人主体", cls="form-label"),
                        Select(*org_options(0), name="org_id", cls="form-select"),
                        cls="form-group"
                    ),
                    Div(
                        Label("研发性质", cls="form-label"),
                        Select(
                            Option("自主研发", value="自主研发", selected=True),
                            Option("委托研发（委托外部机构）", value="委托研发"),
                            Option("受托研发（受他人委托）", value="受托研发"),
                            name="rd_nature", cls="form-select"
                        ),
                        Div("核算规则：自主研发 100% 计入；委托研发按实际支出 80% 计入加计扣除；受托研发支出不属我方研发费用，须隔离。", cls="form-hint"),
                        cls="form-group"
                    ),
                    cls="form-row"
                ),
                Div(
                    Div(
                        Label("总预算（元）", cls="form-label"),
                        Input(name="budget", type="number", placeholder="如：500000", cls="form-input", required=True),
                        cls="form-group"
                    ),
                    Div(
                        Label("开始日期", cls="form-label"),
                        Input(name="start_date", type="date", cls="form-input"),
                        cls="form-group"
                    ),
                    Div(
                        Label("结束日期", cls="form-label"),
                        Input(name="end_date", type="date", cls="form-input"),
                        cls="form-group"
                    ),
                    cls="form-row-3"
                ),
                Div(
                    Label("研发/生产边界类型", cls="form-label"),
                    Select(
                        Option("纯研发项目", value="纯研发"),
                        Option("混合项目（研发+生产）", value="混合"),
                        Option("生产改进项目", value="生产改进"),
                        name="boundary_type", cls="form-select"
                    ),
                    Div("纯研发：全部费用归集为研发费用；混合：需明确研发部分与生产部分的费用划分规则；生产改进：仅研发改进部分归集", cls="form-hint"),
                    cls="form-group"
                ),
                Div(
                    Label("研发/生产边界说明", cls="form-label"),
                    Textarea(name="boundary_desc", placeholder="明确研发部分和生产部分的费用划分规则...", cls="form-textarea"),
                    cls="form-group"
                ),
                Div(
                    Label("归集口径（多选）", cls="form-label"),
                    Div(
                        Label(Input(type="checkbox", name="caliber", value="高企认定", checked=True), " 高企认定", style="margin-right:16px;font-size:13px;font-weight:normal;"),
                        Label(Input(type="checkbox", name="caliber", value="加计扣除", checked=True), " 加计扣除", style="margin-right:16px;font-size:13px;font-weight:normal;"),
                        Label(Input(type="checkbox", name="caliber", value="统计报表"), " 统计报表", style="font-size:13px;font-weight:normal;"),
                    ),
                    cls="form-group"
                ),
                Div(
                    Label("项目描述", cls="form-label"),
                    Textarea(name="description", placeholder="项目简要描述...", cls="form-textarea"),
                    cls="form-group"
                ),
                Div(
                    Button("创建项目", type="submit", cls="btn btn-primary"),
                    A("取消", href="/projects", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/projects/save_async"
            ),
            cls="card"
        )
    )


@ar("/projects/save_async", methods=["POST"])
async def project_save_async(name: str, code: str, template_id: str, budget: str,
                             manager: str = "", start_date: str = "", end_date: str = "",
                             boundary_type: str = "纯研发", boundary_desc: str = "",
                             description: str = "", org_id: str = "0",
                             rd_nature: str = "自主研发", req=None):
    """保存新项目（异步版本，处理多选 caliber）"""
    form = await req.form()
    caliber_list = form.getlist("caliber")
    caliber = ",".join(caliber_list) if caliber_list else "高企认定,加计扣除"

    p = projects_tb.insert(
        name=name, code=code, status="进行中",
        template_id=int(template_id),
        budget=float(budget),
        start_date=start_date, end_date=end_date,
        boundary_type=boundary_type, boundary_desc=boundary_desc,
        manager=manager, caliber=caliber,
        description=description,
        org_id=int(org_id or 0),
        rd_nature=rd_nature or "自主研发",
    )

    tpl_nodes = nodes_tb(where=f"template_id={int(template_id)}", order_by="order_idx")
    for node in tpl_nodes:
        project_nodes_tb.insert(
            project_id=p.id, node_id=node.id, node_name=node.name,
            phase=node.phase, status="待开始", assignee=node.approver,
            deliverable_status="未提交", budget_ratio=node.budget_ratio
        )

    all_pn = project_nodes_tb(where=f"project_id={p.id}", order_by="id")
    if all_pn:
        first = all_pn[0]
        first.status = "进行中"
        first.start_date = date.today().strftime("%Y-%m-%d")
        project_nodes_tb.update(first)

    return RedirectResponse(url=f"/projects/{p.id}", status_code=303)


@ar("/projects/{pid}")
async def project_detail(pid: int, req=None):
    """项目详情"""
    p = projects_tb[pid]
    proj_nodes = project_nodes_tb(where=f"project_id={pid}", order_by="id")
    proj_expenses = expenses_tb(where=f"project_id={pid}")
    proj_risks = risks_tb(where=f"project_id={pid}")
    proj_members = members_tb(where=f"project_id={pid}")
    proj_evidence = evidence_tb(where=f"project_id={pid}")

    total_used = sum(e.amount for e in proj_expenses)
    research_total = sum(e.amount for e in proj_expenses if e.phase == "研究")
    develop_total = sum(e.amount for e in proj_expenses if e.phase == "开发")
    capitalized = sum(e.amount for e in proj_expenses if e.capitalize_status == "待资本化")
    pct = (total_used / p.budget * 100) if p.budget > 0 else 0

    # 流程时间线
    timeline_items = []
    for n in proj_nodes:
        dot_cls = "done" if n.status == "已完成" else ("active" if n.status == "进行中" else "pending")
        timeline_items.append(
            Div(
                Div("", cls=f"timeline-dot {dot_cls}"),
                Div(
                    Div(
                        Span(n.node_name, style="font-weight:600;font-size:14px;margin-right:8px;"),
                        phase_badge(n.phase),
                        status_badge(n.status),
                        Span(n.assignee, style="font-size:12px;color:var(--text-muted);margin-left:8px;"),
                        style="display:flex;align-items:center;"
                    ),
                    Div(f"预算占比：{n.budget_ratio}% | 交付物状态：{n.deliverable_status}", style="font-size:12px;color:var(--text-muted);margin-top:4px;"),
                ),
                cls="timeline-item"
            )
        )

    # 费用明细
    expense_rows = []
    for e in proj_expenses:
        expense_rows.append([
            e.expense_date,
            e.subject_name,
            phase_badge(e.phase),
            f"¥{e.amount:,.0f}",
            status_badge(e.capitalize_status),
            e.person_name or "—",
            e.description[:30] + "..." if len(e.description) > 30 else e.description,
        ])

    # 风险
    risk_rows = []
    for r in proj_risks:
        risk_rows.append([
            level_badge(r.level),
            r.risk_type,
            r.description[:40] + "..." if len(r.description) > 40 else r.description,
            status_badge(r.status),
        ])

    # 成员
    member_rows = []
    for m in proj_members:
        person = personnel_tb[m.person_id]
        member_rows.append([person.name, person.title, m.role])

    # 基本信息卡片
    info_rows = [
        ["项目编号", p.code],
        ["项目经理", p.manager],
        ["项目状态", status_badge_text(p.status)],
        ["法人主体", _org_name(p.org_id)],
        ["研发性质", p.rd_nature],
        ["研发/生产边界", p.boundary_type],
        ["适用口径", p.caliber],
        ["研发周期", f"{p.start_date} ~ {p.end_date}"],
    ]

    return page_layout(
        f"项目详情：{p.name}", "首页 / 研发项目 / 详情", "/projects",
        # 操作栏
        Div(
            A("← 返回列表", href="/projects", cls="btn btn-outline btn-sm"),
            A("预算仪表盘", href=f"/projects/{pid}/budget", cls="btn btn-outline btn-sm"),
            A("归档结题", href=f"/projects/{pid}/close", cls="btn btn-success btn-sm") if p.status != "已结题" else Span("已结题", cls="badge badge-green"),
            style="display:flex;gap:10px;margin-bottom:16px;"
        ),
        # 基本信息
        Div(
            Div(
                Div("项目基本信息", style="font-size:15px;font-weight:600;margin-bottom:16px;"),
                Div(*[
                    Div(Div(k, style="font-size:12px;color:var(--text-muted);"), Div(v, style="font-size:14px;margin-bottom:10px;"), style="flex:1;")
                    for k, v in info_rows
                ], style="display:flex;flex-wrap:wrap;gap:16px;"),
                Div(p.boundary_desc or "—", style="font-size:12px;color:var(--text-muted);margin-top:8px;padding:10px;background:var(--bg);border-radius:6px;") if p.boundary_desc else "",
            ),
            cls="card"
        ),
        # 费用概览
        Div(
            Div("费用归集概览", style="font-size:15px;font-weight:600;margin-bottom:16px;"),
            Div(
                Div(
                    Div("总预算", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{p.budget:,.0f}", style="font-size:20px;font-weight:700;"),
                ),
                Div(
                    Div("已归集", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{total_used:,.0f}", style="font-size:20px;font-weight:700;color:var(--primary);"),
                ),
                Div(
                    Div("预算执行率", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"{pct:.1f}%", style="font-size:20px;font-weight:700;color:" + ("var(--danger)" if pct > 90 else "var(--success)") + ";"),
                ),
                Div(
                    Div("待资本化", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{capitalized:,.0f}", style="font-size:20px;font-weight:700;color:var(--warning);"),
                ),
                style="display:flex;gap:24px;"
            ),
            Div(progress_bar(pct, "orange" if pct > 70 else "green"), style="margin-top:12px;"),
            cls="card"
        ),
        # 阶段费用对比
        Div(
            Div("研究阶段 vs 开发阶段", style="font-size:15px;font-weight:600;margin-bottom:16px;"),
            Div(
                Div(
                    Div("研究阶段（费用化）", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{research_total:,.0f}", style="font-size:18px;font-weight:700;color:var(--phase-research);"),
                    progress_bar(research_total / total_used * 100 if total_used > 0 else 0, ""),
                ),
                Div(
                    Div("开发阶段（待资本化）", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{develop_total:,.0f}", style="font-size:18px;font-weight:700;color:var(--phase-develop);"),
                    progress_bar(develop_total / total_used * 100 if total_used > 0 else 0, "green"),
                ),
                style="display:flex;gap:24px;"
            ),
            cls="card"
        ),
        # 流程时间线
        Div(
            Div("研发流程进度", style="font-size:15px;font-weight:600;margin-bottom:16px;"),
            Div(*timeline_items, cls="timeline") if timeline_items else empty_state("📋", "暂无流程节点"),
            cls="card"
        ),
        # 费用明细
        Div(
            Div(
                Span("费用明细"),
                A("+ 新增费用", href=f"/expenses/new?project_id={pid}", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            data_table(["日期", "科目", "阶段", "金额", "资本化状态", "人员", "说明"], expense_rows) if expense_rows else empty_state("📋", "暂无费用记录"),
            cls="card"
        ),
        # 风险
        Div(
            Div("风险预警", cls="card-title"),
            data_table(["等级", "类型", "描述", "状态"], risk_rows) if risk_rows else empty_state("✓", "暂无风险预警"),
            cls="card"
        ),
        # 成员
        Div(
            Div("项目成员", cls="card-title"),
            data_table(["姓名", "职务", "角色"], member_rows) if member_rows else empty_state("📋", "暂无成员"),
            cls="card"
        ),
    )


def status_badge_text(status: str):
    """返回状态文本（用于基本信息展示）"""
    color_map = {
        "进行中": "var(--primary)", "已结题": "var(--success)",
        "立项中": "var(--info)", "已暂停": "var(--text-muted)"
    }
    color = color_map.get(status, "var(--text)")
    return Span(status, style=f"color:{color};font-weight:600;")


@ar("/projects/{pid}/close")
async def project_close(pid: int, req=None):
    """项目结题 — 生成结题报告并标记资本化/费用化

    M1 结题闸门：结题前置校验，存在未闭环事项则拦截结题。
    闸门项：① 流程节点未完成；② 待资本化费用未审批；
    ③ 受托研发收入未登记（受托管隔离缺失）；④ 特殊收入（样品销售等）未冲减；
    ⑤ 阶段证据链不完整。
    """
    p = projects_tb[pid]
    proj_nodes = project_nodes_tb(where=f"project_id={pid}")
    proj_expenses = expenses_tb(where=f"project_id={pid}")

    # 闸门①：未完成节点
    pending_nodes = [n for n in proj_nodes if n.status != "已完成"]
    # 闸门③：受托研发收入未登记（仅受托研发项目需要）
    entrusted_unrecorded = (p.rd_nature == "受托研发" and
                            not any(c.project_id == pid for c in entrusted_tb()))
    # 闸门④：样品销售未冲减（存在销售处置的样品/废料但未生成特殊收入）
    from .db import sample_scrap_tb as _ss
    sample_sales = [s for s in _ss() if s.project_id == pid and s.disposal == "销售"
                    and float(s.realized_amount or 0) > 0]
    offset_unrecorded = bool(sample_sales) and not any(
        r.project_id == pid for r in special_income_tb())
    # 闸门⑤：阶段证据链不完整
    all_ev = [e for e in evidence_tb() if e.project_id == pid]
    needed = set()
    for e in all_ev:
        needed.add(e.ev_type)
    study_req = {"立项书", "研究阶段方案"}
    develop_req = {"开发阶段方案", "阶段评审记录"}
    close_req = {"结题报告", "成果证明"}
    missing_ev = (study_req | develop_req | close_req) - needed

    block_reasons = []
    if pending_nodes:
        block_reasons.append(f"尚有 {len(pending_nodes)} 个流程节点未完成")
    if entrusted_unrecorded:
        block_reasons.append("受托研发项目尚未登记受托合同（营业隔离缺失）")
    if offset_unrecorded:
        block_reasons.append("存在样品/废料销售但未登记特殊收入冲减")
    if missing_ev:
        block_reasons.append(f"阶段证据链缺失：{ '、'.join(sorted(missing_ev)) }")

    if block_reasons:
        return page_layout(
            "无法结题（闸门拦截）", "首页 / 研发项目 / 结题", "/projects",
            Div(
                alert_box("结题前置校验未通过，存在以下未闭环事项，须处理后方可结题：", "danger"),
                Div(*[Div(f"● {r}", style="padding:6px 0;border-bottom:1px solid var(--app-split);") for r in block_reasons]),
                Div(A("← 返回项目详情", href=f"/projects/{pid}", cls="btn btn-outline"), style="margin-top:16px;"),
                cls="card"
            )
        )

    # 检查待资本化的费用（允许进入下一步确认）
    pending_cap = [e for e in proj_expenses if e.capitalize_status == "待资本化"]
    if pending_cap:
        return page_layout(
            "确认结题", "首页 / 研发项目 / 结题", "/projects",
            Div(
                alert_box(f"项目有 {len(pending_cap)} 笔开发阶段费用标记「待资本化」，结题将自动完成资本化确认，请确认。", "warning"),
                data_table(
                    ["日期", "科目", "金额", "说明"],
                    [[e.expense_date, e.subject_name, f"¥{e.amount:,.0f}", e.description] for e in pending_cap]
                ),
                Div(
                    A("确认资本化并结题", href=f"/projects/{pid}/close/confirm", cls="btn btn-success"),
                    A("← 返回", href=f"/projects/{pid}", cls="btn btn-outline"),
                    style="display:flex;gap:10px;margin-top:16px;"
                ),
                cls="card"
            )
        )

    # 直接结题
    return RedirectResponse(url=f"/projects/{pid}/close/confirm", status_code=303)


@ar("/projects/{pid}/close/confirm")
def project_close_confirm(pid: int):
    """确认结题"""
    p = projects_tb[pid]
    p.status = "已结题"
    projects_tb.update(p)

    # 自动确认资本化
    proj_expenses = expenses_tb(where=f"project_id={pid}")
    for e in proj_expenses:
        if e.capitalize_status == "待资本化":
            e.capitalize_status = "已资本化"
            e.created_at = ""  # 保留原记录
            expenses_tb.update(e)

    return RedirectResponse(url=f"/projects/{pid}", status_code=303)


# ── 缺口⑥：预算执行仪表盘 ─────────────────────────────────

def _budget_metrics(pid: int):
    """返回 (budget, used, remaining, pct, over_flag)"""
    p = projects_tb[pid]
    budget = float(p.budget or 0)
    exps = expenses_tb(where=f"project_id={pid}")
    used = sum(e.amount for e in exps)
    remaining = budget - used
    pct = (used / budget * 100) if budget > 0 else 0
    if pct > 100:
        over_flag = "超支"
    elif pct > 90:
        over_flag = "预警"
    else:
        over_flag = "正常"
    return p, budget, used, remaining, pct, over_flag


@ar("/projects/{pid}/budget")
def project_budget(pid: int):
    """预算执行仪表盘：预算 vs 已执行 vs 剩余 + 月度趋势 + 超支预警"""
    p, budget, used, remaining, pct, over_flag = _budget_metrics(pid)
    exps = expenses_tb(where=f"project_id={pid}")

    # 月度聚合（2025-01 起至当前月，缺失月份补 0）
    month_map = {}
    for e in exps:
        m = (e.expense_date or "")[:7]
        if len(m) == 7:
            month_map[m] = month_map.get(m, 0.0) + e.amount
    today = date.today()
    months = []
    y, m = 2025, 1
    while (y, m) <= (today.year, today.month):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    max_month_val = max([month_map.get(mm, 0) for mm in months] or [1])

    trend_bars = []
    for mm in months:
        val = month_map.get(mm, 0)
        h = int(val / max_month_val * 100) if max_month_val > 0 else 0
        bar_color = "var(--primary)"
        if mm == (today.strftime("%Y-%m")):
            bar_color = "var(--warning)" if val > 0 else "var(--border)"
        trend_bars.append(
            Div(
                Div("", style=f"height:{max(h, 2)}%;background:{bar_color};border-radius:4px 4px 0 0;"),
                Div(mm[5:], style="font-size:11px;color:var(--text-muted);margin-top:6px;"),
                Div(f"{val/10000:.1f}万", style="font-size:10px;color:var(--text-muted);margin-top:2px;"),
                style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:160px;"
            )
        )

    over_color = {"超支": "var(--danger)", "预警": "var(--warning)", "正常": "var(--success)"}[over_flag]
    pct_color = "var(--danger)" if pct > 100 else ("var(--warning)" if pct > 90 else "var(--success)")

    return page_layout(
        f"预算执行仪表盘：{p.name}", "首页 / 研发项目 / 预算仪表盘", "/projects",
        Div(
            A("← 返回项目", href=f"/projects/{pid}", cls="btn btn-outline btn-sm"),
            style="display:flex;gap:10px;margin-bottom:16px;"
        ),
        Div(
            Div("预算执行总览", style="font-size:15px;font-weight:600;margin-bottom:16px;"),
            Div(
                Div(Div("总预算", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{budget:,.0f}", style="font-size:22px;font-weight:700;")),
                Div(Div("已执行", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{used:,.0f}", style="font-size:22px;font-weight:700;color:var(--primary);")),
                Div(Div("剩余预算", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"¥{remaining:,.0f}", style="font-size:22px;font-weight:700;color:" + ("var(--danger)" if remaining < 0 else "var(--success)") + ";")),
                Div(Div("执行率", style="font-size:12px;color:var(--text-muted);"),
                    Div(f"{pct:.1f}%", style=f"font-size:22px;font-weight:700;color:{pct_color};")),
                Div(Div("预警状态", style="font-size:12px;color:var(--text-muted);"),
                    Div(Span(over_flag, cls="badge " + {"超支": "badge-red", "预警": "badge-orange", "正常": "badge-green"}[over_flag]),
                        style="font-size:22px;")),
                style="display:flex;gap:32px;"
            ),
            Div(progress_bar(min(pct, 100), "orange" if pct > 90 else "green"), style="margin-top:12px;"),
            Div(f"预算执行率 {pct:.1f}%（已执行 ¥{used:,.0f} / 总预算 ¥{budget:,.0f}）",
                style="font-size:12px;color:var(--text-muted);margin-top:8px;"),
            cls="card"
        ),
        Div(
            Div("月度费用趋势（2025-01 至今）", style="font-size:15px;font-weight:600;margin-bottom:16px;"),
            Div(*trend_bars, style="display:flex;gap:6px;align-items:flex-end;"),
            cls="card"
        ),
        Div(
            Div("超支/预警提示", cls="card-title"),
            Div(
                *[Div(f"● {r}", style="padding:6px 0;border-bottom:1px solid var(--app-split);")
                  for r in ([f"项目已超支 ¥{-remaining:,.0f}，须走预算追加审批或控制后续支出" if over_flag == "超支" else
                             f"预算执行率已达 {pct:.1f}%（>90%），触发预警，建议核查剩余支出计划" if over_flag == "预警" else
                             "预算执行正常，未触发预警"])],
                cls="card"
            ),
            cls="card"
        )
    )
