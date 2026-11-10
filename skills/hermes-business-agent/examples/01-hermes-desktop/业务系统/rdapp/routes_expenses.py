"""routes_expenses.py — 费用归集引擎路由

影子归集引擎：随流程节点推进自动归集、资本化/费用化自动标记、
多口径映射、AI 智能匹配（简化版）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from urllib.parse import quote
from .db import (
    subjects_tb, projects_tb, project_nodes_tb, expenses_tb, personnel_tb,
    get_project_node_for_date, negative_list_hit
)
from .components import (
    stat_block,

    page_layout, phase_badge, status_badge, data_table, empty_state,
    alert_box
)
from .routes_datacenter import log_data_change

ar = APIRouter()


@ar("/expenses")
def expenses(caliber: str = "高企认定", phase_filter: str = "", status_filter: str = ""):
    """费用归集列表"""
    all_expenses = expenses_tb()

    # 过滤
    if phase_filter == "研究":
        all_expenses = [e for e in all_expenses if e.phase == "研究"]
    elif phase_filter == "开发":
        all_expenses = [e for e in all_expenses if e.phase == "开发"]
    elif phase_filter == "生产":
        all_expenses = [e for e in all_expenses if e.phase == "生产"]

    if status_filter == "费用化":
        all_expenses = [e for e in all_expenses if e.capitalize_status == "费用化"]
    elif status_filter == "待资本化":
        all_expenses = [e for e in all_expenses if e.capitalize_status == "待资本化"]
    elif status_filter == "已资本化":
        all_expenses = [e for e in all_expenses if e.capitalize_status == "已资本化"]

    # 按归集口径筛选（caliber 包含所选口径）
    if caliber and caliber != "全部":
        all_expenses = [e for e in all_expenses if caliber in e.caliber]

    rows = []
    for e in sorted(all_expenses, key=lambda x: x.expense_date, reverse=True):
        project = projects_tb[e.project_id]
        rows.append([
            e.expense_date,
            A(project.name, href=f"/projects/{e.project_id}", style="color:var(--primary);text-decoration:none;"),
            e.subject_name,
            phase_badge(e.phase),
            f"¥{e.amount:,.0f}",
            status_badge(e.capitalize_status),
            e.caliber,
            e.source,
        ])

    # 统计
    total = sum(e.amount for e in all_expenses)
    research_total = sum(e.amount for e in all_expenses if e.phase == "研究")
    develop_total = sum(e.amount for e in all_expenses if e.phase == "开发")
    capitalized_total = sum(e.amount for e in all_expenses if e.capitalize_status in ("待资本化", "已资本化"))

    return page_layout(
        "费用归集引擎", "首页 / 费用归集", "/expenses",
        # 口径筛选标签
        Div(
            A("高企认定", href="/expenses?caliber=高企认定", cls=f"tab {'active' if caliber=='高企认定' else ''}"),
            A("加计扣除", href="/expenses?caliber=加计扣除", cls=f"tab {'active' if caliber=='加计扣除' else ''}"),
            A("全部", href="/expenses?caliber=全部", cls=f"tab {'active' if caliber=='全部' else ''}"),
            cls="tabs"
        ),
        # 统计卡
        Div(
            stat_block("归集总额", f"¥{total:,.0f}", "green"),
            stat_block("研究阶段（费用化）", f"¥{research_total:,.0f}", "blue"),
            stat_block("开发阶段（待资本化）", f"¥{develop_total:,.0f}", "orange"),
            stat_block("资本化金额", f"¥{capitalized_total:,.0f}", "purple"),
            style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px;"
        ),
        # 归集列表
        Div(
            Div(
                Span("费用归集明细"),
                A("+ 手动录入", href="/expenses/new", cls="btn btn-primary btn-sm"),
                A("批量导入", href="/import/expenses", cls="btn btn-outline btn-sm"),
                A("一键归集", href="/expenses/collect", cls="btn btn-success btn-sm"),
                style="display:flex;align-items:center;justify-content:space-between;"
            ),
            data_table(
                ["日期", "项目", "科目", "阶段", "金额", "资本化状态", "归集口径", "来源"],
                rows
            ) if rows else empty_state("📋", "暂无费用记录"),
            cls="card"
        )
    )




@ar("/expenses/new")
def expense_new(project_id: str = ""):
    """手动录入费用表单"""
    all_projects = projects_tb()
    all_subjects = subjects_tb(order_by="code")

    proj_options = [Option("— 请选择项目 —", value="")] + [
        Option(f"{p.code} {p.name}", value=p.id, selected=(str(p.id) == str(project_id))) for p in all_projects
    ]
    subj_options = [Option(f"{s.code} {s.name}", value=s.id) for s in all_subjects]
    person_options = [Option("— 无 —", value="")] + [
        Option(per.name, value=per.id) for per in personnel_tb()
    ]

    return page_layout(
        "手动录入费用", "首页 / 费用归集 / 录入", "/expenses",
        Div(
            Form(
                Div(
                    Div(
                        Label("所属项目", cls="form-label"),
                        Select(*proj_options, name="project_id", cls="form-select", required=True),
                        cls="form-group"
                    ),
                    Div(
                        Label("费用科目", cls="form-label"),
                        Select(*subj_options, name="subject_id", cls="form-select", required=True),
                        cls="form-group"
                    ),
                    cls="form-row"
                ),
                Div(
                    Div(
                        Label("金额（元）", cls="form-label"),
                        Input(name="amount", type="number", placeholder="如：30000", cls="form-input", required=True),
                        cls="form-group"
                    ),
                    Div(
                        Label("费用日期", cls="form-label"),
                        Input(name="expense_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"),
                        cls="form-group"
                    ),
                    Div(
                        Label("归属人员", cls="form-label"),
                        Select(*person_options, name="person_id", cls="form-select"),
                        cls="form-group"
                    ),
                    cls="form-row-3"
                ),
                Div(
                    Div(
                        Label("归集口径", cls="form-label"),
                        Select(
                            Option("高企认定", value="高企认定"),
                            Option("加计扣除", value="加计扣除"),
                            Option("全部口径", value="高企认定,加计扣除"),
                            name="caliber", cls="form-select"
                        ),
                        cls="form-group"
                    ),
                    Div(
                        Label("费用说明", cls="form-label"),
                        Input(name="description", placeholder="费用用途说明", cls="form-input"),
                        cls="form-group"
                    ),
                    cls="form-row"
                ),
                Div(
                    Label("智能归集提示", cls="form-label"),
                    Div(
                        "系统将根据项目流程节点自动标记阶段（研究→费用化；开发→待资本化）并匹配归属。",
                        cls="form-hint"
                    ),
                    cls="form-group"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/expenses", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/expenses/save"
            ),
            cls="card"
        )
    )


@ar("/expenses/save", methods=["POST"])
async def expense_save(project_id: str, subject_id: str, amount: str,
                        expense_date: str, person_id: str = "", caliber: str = "高企认定", description: str = ""):
    """保存费用 — 自动标记阶段与资本化状态"""
    pid = int(project_id)
    sid = int(subject_id)

    # 阶段按【费用发生日】判定，而非当前进行中节点
    target_node = get_project_node_for_date(pid, expense_date) if expense_date else None
    if not target_node:
        proj_nodes = project_nodes_tb(where=f"project_id={pid}")
        active_node = [n for n in proj_nodes if n.status == "进行中"]
        target_node = active_node[0] if active_node else (proj_nodes[0] if proj_nodes else None)

    phase = target_node.phase if target_node else "研究"

    # 判断资本化状态
    subject = subjects_tb[sid]
    if phase == "研究":
        cap_status = "费用化"
    elif phase == "生产":
        cap_status = "非研发"
    else:  # 开发
        cap_status = "待资本化" if subject.capitalizable else "费用化"

    person_name = ""
    if person_id:
        person_obj = personnel_tb[int(person_id)]
        person_name = person_obj.name

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # P1：负面清单拦截 —— 不得归集支出（业务招待/市场推广/常规升级/批量生产工装等）
    # 命中即拦截，告知该支出不属于研发费用归集范围（财税口径）。
    neg = negative_list_hit(description)
    if neg:
        return page_layout(
            "录入被拦截", "首页 / 费用归集 / 录入", "/expenses",
            alert_box(
                f"⚠ 录入失败：根据研发费用归集口径，{neg}，不得计入研发费用。"
                f"请确认该支出性质，如属生产经营活动或非研发管理费用，请勿归集。",
                "danger"),
            Div(A("← 返回录入", href="/expenses/new", cls="btn btn-outline"), style="margin-top:16px;")
        )

    # 手工录入其他相关费用（科目08）且选择加计扣除口径时，强制校验 10% 上限，
    # 防止绕过 routes_others.others_collect 的归集校验（财税[2015]119号）。
    # 基数口径与 others_collect 保持一致：所有加计扣除口径费用（不含科目08自身）。
    if subject.code == "08" and "加计扣除" in caliber:
        amt = float(amount) if amount else 0.0
        base_rows = expenses_tb(where="caliber LIKE '%加计扣除%' AND source != '其他费用归集'")
        base_amount = sum(r.amount for r in base_rows)
        deductible_base = base_amount + amt
        limit = round(deductible_base * 0.10, 2)
        if amt > limit + 0.005:
            exceed = round(amt - limit, 2)
            return page_layout(
                "录入被拦截", "首页 / 费用归集 / 录入", "/expenses",
                alert_box(
                    f"⚠ 录入失败：本次其他相关费用 ¥{amt:,.2f} 已超过可加计扣除研发费用总额 "
                    f"（¥{deductible_base:,.2f}）的 10% 限额（¥{limit:,.2f}），超出 ¥{exceed:,.2f}。"
                    f"根据税法规定，超出部分不得加计扣除。请核减金额或调整至其他科目后再录入。",
                    "danger"),
                Div(A("← 返回录入", href="/expenses/new", cls="btn btn-outline"), style="margin-top:16px;")
            )

    rec = expenses_tb.insert(
        project_id=pid,
        node_id=target_node.id if target_node else 0,
        subject_id=sid,
        subject_name=subject.name,
        amount=float(amount),
        expense_date=expense_date,
        phase=phase,
        capitalize_status=cap_status,
        caliber=caliber,
        person_id=int(person_id) if person_id else 0,
        person_name=person_name,
        description=description,
        source="手动录入",
        created_at=now
    )
    log_data_change("expenses", getattr(rec, "id", 0), "amount",
                    old_val="", new_val=f"{subject.name} ¥{float(amount):,.2f} 手动录入",
                    operator="system")

    return RedirectResponse(url="/expenses", status_code=303)


@ar("/expenses/collect")
def expense_collect(msg: str = ""):
    """一键归集 — 真实归集引擎 + 影子归集概览"""
    all_expenses = expenses_tb()
    total = sum(e.amount for e in all_expenses)
    research = sum(e.amount for e in all_expenses if e.phase == "研究")
    develop = sum(e.amount for e in all_expenses if e.phase == "开发")
    non_rd = sum(e.amount for e in all_expenses if e.phase == "生产")

    # 已归集节点统计
    done_nodes = [n for n in project_nodes_tb()
                  if n.status == "已完成" or n.deliverable_status == "已通过"]
    auto_source = [e for e in all_expenses if getattr(e, "source", "") == "系统自动归集"]
    pending_nodes = [n for n in done_nodes
                     if not any(e.node_id == n.id and getattr(e, "source", "") == "系统自动归集"
                                for e in auto_source)]

    # 数据源统计（真实 expense.source 分组，替代早期影子源展示）
    from collections import OrderedDict
    src_map = OrderedDict()
    for e in all_expenses:
        s = getattr(e, "source", "") or "手动录入"
        if s not in src_map:
            src_map[s] = [0, 0.0]
        src_map[s][0] += 1
        src_map[s][1] += e.amount or 0
    collect_summary = [
        [src, str(cnt), f"¥{amt:,.0f}", "✓ 已归集"]
        for src, (cnt, amt) in src_map.items()
    ]

    msg_bar = alert_box(msg, "success") if msg else ""

    components = [
        msg_bar,
        Div(
            Div("归集结果概览", cls="card-title"),
            Div(
                stat_block("研究阶段（费用化）", f"¥{research:,.0f}", "blue"),
                stat_block("开发阶段（待资本化）", f"¥{develop:,.0f}", "orange"),
                stat_block("生产阶段（非研发）", f"¥{non_rd:,.0f}", "gray"),
                stat_block("归集总额", f"¥{total:,.0f}", "green"),
                style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;"
            ),
            Div(
                H4(f"已完成节点: {len(done_nodes)} 个 | 自动归集: {len(auto_source)} 笔 | 待归集节点: {len(pending_nodes)} 个"),
                A("执行真实归集", href="/expenses/collect/run", cls="btn btn-primary", style="margin-top:8px;"),
                style="margin-top:12px;"
            ),
            cls="card"
        ),
        Div(
            Div("数据源同步状态", cls="card-title"),
            data_table(["数据源", "费用笔数", "归集金额", "归集状态"], collect_summary[1:]),
            cls="card"
        ),
    ]

    # 最近 5 笔自动归集记录
    if auto_source:
        recent = sorted(auto_source, key=lambda e: getattr(e, "id", 0), reverse=True)[:5]
        rows = [[
            getattr(e, "id", ""),
            e.subject_name,
            f"¥{e.amount:,.0f}",
            e.project_id,
            getattr(e, "description", "")[:30],
        ] for e in recent]
        components.append(
            Div(
                Div("最近自动归集记录", cls="card-title"),
                data_table(["ID", "科目", "金额", "项目", "描述"], rows),
                cls="card"
            )
        )

    return page_layout(
        "一键归集", "首页 / 费用归集 / 一键归集", "/expenses", *components
    )


@ar("/expenses/collect/run")
def expense_collect_run():
    """遍历已完成节点执行真实归集（expense_collect_from_node）"""
    from .operations import expense_collect_from_node, evidence_create_snapshot

    done_nodes = [n for n in project_nodes_tb()
                  if n.status == "已完成" or n.deliverable_status == "已通过"]
    results = []  # (node_name, 新增笔数, 金额)
    errors = []

    for n in done_nodes:
        try:
            created = expense_collect_from_node(n.project_id, n.id)
            if created:
                total_amt = sum(r["amount"] for r in created)
                results.append((n.node_name, len(created), total_amt))
                # 同时生成证据快照
                try:
                    evidence_create_snapshot(n.project_id, n.id, n.phase)
                except Exception:
                    pass
        except Exception as e:
            errors.append(f"{n.node_name}: {e}")

    # 展示结果
    lines = []
    if results:
        lines.append(f"归集完成：共 {len(results)} 个节点产生归集记录")
        for name, cnt, amt in results:
            lines.append(f"  · {name}: {cnt} 笔，合计 ¥{amt:,.0f}")
    else:
        lines.append("归集完成：所有已完成节点已归集，无新增记录（或无可归集数据）")
    for e in errors:
        lines.append(f"  ⚠ {e}")

    msg = "；".join(lines)
    return RedirectResponse(url=f"/expenses/collect?msg={quote(msg)}", status_code=303)
