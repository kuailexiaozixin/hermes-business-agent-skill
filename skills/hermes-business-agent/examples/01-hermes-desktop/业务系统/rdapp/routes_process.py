"""routes_process.py — 研发流程管理路由

管理流程模板、项目流程实例执行、节点审批、阶段推进、双阶段划分
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date
from .db import (
    projects_tb, project_nodes_tb
)
from .components import (
    page_layout, phase_badge, status_badge, data_table, empty_state,
    alert_box, progress_bar
)

ar = APIRouter()


@ar("/process")
def process():
    """流程管理首页 — 项目流程实例列表"""
    all_projects = projects_tb(where="status='进行中' OR status='立项中'")
    cards = []
    for p in all_projects:
        proj_nodes = project_nodes_tb(where=f"project_id={p.id}", order_by="id")
        completed = sum(1 for n in proj_nodes if n.status == "已完成")
        total = len(proj_nodes)
        pct = (completed / total * 100) if total > 0 else 0

        cards.append(
            A(
                Div(
                    Div(
                        Span(p.name, style="font-size:15px;font-weight:600;"),
                        status_badge(p.status),
                        style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;"
                    ),
                    Div(f"进度：{completed}/{total} 节点", style="font-size:12px;color:var(--text-muted);margin-bottom:8px;"),
                    progress_bar(pct, "green" if pct == 100 else ""),
                    cls="card"
                ),
                href=f"/process/{p.id}",
                style="text-decoration:none;color:inherit;display:block;"
            )
        )

    return page_layout(
        "流程管理", "首页 / 流程管理", "/process",
        Div(
            alert_box("流程管理遵循双阶段划分原则：研究阶段费用由系统自动费用化；开发阶段费用在满足条件时可资本化；生产阶段费用隔离为非研发费用。", "info"),
        ),
        Div(*cards, style="display:grid;grid-template-columns:1fr 1fr;gap:16px;") if cards else empty_state("📋", "暂无进行中的项目"),
    )


@ar("/process/{pid}")
def process_detail(pid: int):
    """项目流程实例详情 — 节点执行与审批"""
    p = projects_tb[pid]
    proj_nodes = project_nodes_tb(where=f"project_id={pid}", order_by="id")

    rows = []
    for n in proj_nodes:
        # 操作按钮
        actions = ""
        if n.status == "待开始":
            actions = A("开始节点", href=f"/process/{pid}/node/{n.id}/start", cls="btn btn-primary btn-sm")
        elif n.status == "进行中":
            if n.deliverable_status == "未提交":
                actions = A("提交交付物", href=f"/process/{pid}/node/{n.id}/submit", cls="btn btn-warning btn-sm")
            elif n.deliverable_status == "待审批":
                actions = Div(
                    A("通过", href=f"/process/{pid}/node/{n.id}/approve", cls="btn btn-success btn-sm"),
                    A("打回", href=f"/process/{pid}/node/{n.id}/reject", cls="btn btn-danger btn-sm"),
                    style="display:flex;gap:6px;",
                )
        elif n.status == "已完成":
            actions = Span("✓ 已完成", style="font-size:12px;color:var(--success);")

        rows.append([
            n.node_name,
            phase_badge(n.phase),
            n.assignee,
            status_badge(n.status),
            status_badge(n.deliverable_status),
            f"{n.budget_ratio}%",
            actions,
        ])

    # 阶段统计
    research_nodes = [n for n in proj_nodes if n.phase == "研究"]
    develop_nodes = [n for n in proj_nodes if n.phase == "开发"]
    produce_nodes = [n for n in proj_nodes if n.phase == "生产"]

    return page_layout(
        f"流程执行：{p.name}", "首页 / 流程管理 / 节点执行", "/process",
        Div(
            Div(
                Span(p.name, style="font-size:16px;font-weight:600;margin-right:12px;"),
                status_badge(p.status),
            ),
            cls="card"
        ),
        # 阶段概览
        Div(
            Div(
                Div(
                    Span("研究阶段", cls="badge phase-research"),
                    Div(f"{len(research_nodes)} 个节点 | 费用自动费用化", style="font-size:12px;color:var(--text-muted);margin-top:6px;"),
                    cls="card"
                ),
                Div(
                    Span("开发阶段", cls="badge phase-develop"),
                    Div(f"{len(develop_nodes)} 个节点 | 满足条件可资本化", style="font-size:12px;color:var(--text-muted);margin-top:6px;"),
                    cls="card"
                ),
                Div(
                    Span("生产阶段", cls="badge phase-produce"),
                    Div(f"{len(produce_nodes)} 个节点 | 隔离为非研发费用", style="font-size:12px;color:var(--text-muted);margin-top:6px;"),
                    cls="card"
                ),
                Div(style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;")
            )
        ),
        # 节点列表
        Div(
            Div("流程节点执行", cls="card-title"),
            data_table(
                ["节点名称", "阶段", "负责人", "节点状态", "交付物", "预算占比", "操作"],
                rows
            ) if rows else empty_state("📋", "暂无流程节点"),
            cls="card"
        )
    )


@ar("/process/{pid}/node/{nid}/start")
def process_node_start(pid: int, nid: int):
    """开始节点"""
    n = project_nodes_tb[nid]
    n.status = "进行中"
    n.start_date = date.today().strftime("%Y-%m-%d")
    project_nodes_tb.update(n)
    return RedirectResponse(url=f"/process/{pid}", status_code=303)


@ar("/process/{pid}/node/{nid}/submit")
def process_node_submit(pid: int, nid: int):
    """提交交付物"""
    n = project_nodes_tb[nid]
    n.deliverable_status = "待审批"
    project_nodes_tb.update(n)
    return RedirectResponse(url=f"/process/{pid}", status_code=303)


@ar("/process/{pid}/node/{nid}/approve")
def process_node_approve(pid: int, nid: int):
    """审批通过 — 推进流程（P0：审批通过即触发费用归集+证据快照）"""
    from .operations import expense_collect_from_node, evidence_create_snapshot
    from .db import log_audit
    n = project_nodes_tb[nid]
    n.deliverable_status = "已通过"
    n.status = "已完成"
    n.end_date = date.today().strftime("%Y-%m-%d")
    project_nodes_tb.update(n)

    # ── P0 核心打通：流程 → 费用 → 证据 ──
    try:
        expense_collect_from_node(pid, nid)
    except Exception as e:
        try:
            log_audit("APPROVE", "process_node", nid,
                      detail=f"节点审批通过但费用归集异常：{e}", actor="系统")
        except Exception:
            pass
    try:
        evidence_create_snapshot(pid, nid, phase=n.phase)
    except Exception as e:
        try:
            log_audit("APPROVE", "process_node", nid,
                      detail=f"节点审批通过但证据快照异常：{e}", actor="系统")
        except Exception:
            pass

    # 找到下一个待开始的节点，自动开始
    proj_nodes = project_nodes_tb(where=f"project_id={pid}", order_by="id")
    next_nodes = [nn for nn in proj_nodes if nn.status == "待开始"]
    if next_nodes:
        next_node = next_nodes[0]
        next_node.status = "进行中"
        next_node.start_date = date.today().strftime("%Y-%m-%d")
        project_nodes_tb.update(next_node)

    # 检查是否所有节点完成
    remaining = [nn for nn in proj_nodes if nn.status != "已完成"]
    if not remaining:
        p = projects_tb[pid]
        p.status = "已结题"
        projects_tb.update(p)

    return RedirectResponse(url=f"/process/{pid}", status_code=303)



@ar("/process/{pid}/node/{nid}/reject")
def process_node_reject(pid: int, nid: int):
    """审批打回"""
    n = project_nodes_tb[nid]
    n.deliverable_status = "已打回"
    n.status = "已打回"
    project_nodes_tb.update(n)
    return RedirectResponse(url=f"/process/{pid}", status_code=303)


@ar("/process/{pid}/node/{nid}/reset")
def process_reset_node(pid: int, nid: int):
    """重置被打回的节点"""
    n = project_nodes_tb[nid]
    n.deliverable_status = "未提交"
    n.status = "进行中"
    project_nodes_tb.update(n)
    return RedirectResponse(url=f"/process/{pid}", status_code=303)
