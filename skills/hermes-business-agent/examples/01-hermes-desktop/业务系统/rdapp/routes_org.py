"""routes_org.py — 组织树管理与跨主体合规视图（缺口⑬，M5）

功能：
- 组织树管理：集团-子公司-部门三级结构展示、新增节点、编辑、启停
- 跨主体项目视图：按法人实体分组展示项目 + 各主体费用汇总
- 重复申报检测：识别不同主体下相似项目名 / 重叠费用期间的潜在重复归集风险
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime

from .db import (
    org_tree_tb, orgs_tb, projects_tb, expenses_tb, project_nodes_tb, log_audit,
)
from .components import (
    page_layout, stat_card, data_table, empty_state, alert_box, status_badge,
)

ar = APIRouter()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _org_name(org_id: int) -> str:
    """org_id → 组织名（0 视为未分配）。"""
    if not org_id:
        return "未分配主体"
    try:
        o = orgs_tb[org_id]
        return f"{o.name}（{o.level}）" if o else "未分配主体"
    except Exception:
        return "未分配主体"


def _build_tree(nodes: list, parent_id: int = 0, depth: int = 0, visited: set = None) -> list:
    """递归构建组织树（按 parent_id 嵌套）。

    防环保护：visited 记录已展开的 org_id，避免异常数据（如 org_id=0
    且挂有父节点）导致无限递归。
    """
    if visited is None:
        visited = set()
    out = []
    for n in nodes:
        if n.parent_id == parent_id:
            out.append((n, depth))
            if n.org_id in visited:
                continue  # 已展开过，跳过防止成环
            visited.add(n.org_id)
            out.extend(_build_tree(nodes, n.org_id, depth + 1, visited))
    return out


@ar("/org-tree")
def org_tree_view():
    """组织树管理页：三级结构 + 新增/编辑/启停"""
    nodes = list(org_tree_tb())
    tree = _build_tree(nodes)

    tree_rows = []
    for n, depth in tree:
        level_badge = {
            "集团": "badge-purple", "子公司": "badge-blue", "部门": "badge-gray"
        }.get(n.level, "badge-gray")
        tree_rows.append([
            Span(n.name, style=f"padding-left:{depth * 24}px;font-weight:600;" if depth == 0 else f"padding-left:{depth * 24}px;"),
            Span(n.level, cls=f"badge {level_badge}"),
            f"org_id={n.org_id}",
            A("编辑", href=f"/org-tree/{n.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    # 统计：各主体项目数 / 费用
    proj_by_org = {}
    for p in projects_tb():
        proj_by_org.setdefault(p.org_id, 0)
        proj_by_org[p.org_id] += 1
    exp_by_org = {}
    for e in expenses_tb():
        p = projects_tb[e.project_id] if e.project_id else None
        oid = p.org_id if p else 0
        exp_by_org[oid] = exp_by_org.get(oid, 0.0) + e.amount

    stat_cards = [
        stat_card("组织节点", str(len(nodes)), f"集团-子公司-部门三级", "blue"),
        stat_card("关联项目主体", str(len([k for k in proj_by_org if k])), "已分配法人实体", "green"),
        stat_card("跨主体费用", f"¥{sum(exp_by_org.values()):,.0f}", "全主体归集合计", "orange"),
    ]

    return page_layout(
        "组织树管理", "首页 / 系统概览 / 组织树", "/org-tree",
        Div(*stat_cards, cls="stat-grid"),
        Div(
            Div(
                Span("组织树结构"),
                A("+ 新增节点", href="/org-tree/new", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            data_table(
                ["组织名称", "层级", "关联ID", "操作"],
                tree_rows
            ) if tree_rows else empty_state("🏢", "暂无组织节点，点击「新增节点」开始"),
            cls="card"
        ),
    )


@ar("/org-tree/new")
def org_tree_new():
    """新增组织节点表单"""
    parent_opts = [Option("— 顶级（集团） —", value="0")] + [
        Option(f"{o.name}（{o.level}）", value=o.org_id)
        for o in org_tree_tb()
    ]
    level_opts = [
        Option("集团", value="集团"),
        Option("子公司", value="子公司"),
        Option("部门", value="部门"),
    ]
    return page_layout(
        "新增组织节点", "首页 / 系统概览 / 组织树 / 新增", "/org-tree",
        Div(
            Form(
                Div(
                    Div(Label("组织名称", cls="form-label"),
                        Input(name="name", placeholder="如：华东研发中心", cls="form-input", required=True),
                        cls="form-group"),
                    Div(Label("层级", cls="form-label"),
                        Select(*level_opts, name="level", cls="form-select", required=True),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("上级节点", cls="form-label"),
                        Select(*parent_opts, name="parent_id", cls="form-select"),
                        cls="form-group"),
                    Div(Label("关联法人实体ID（可选）", cls="form-label"),
                        Input(name="org_id", type="number", placeholder="留空=0", cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/org-tree", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/org-tree/add"
            ),
            cls="card"
        )
    )


@ar("/org-tree/add", methods=["POST"])
def org_tree_add(name: str, level: str, parent_id: str = "0", org_id: str = "0"):
    """保存组织节点

    org_id 为 0/空时，自动在 orgs_tb 创建对应法人实体记录，
    保证 OrgTree.org_id 始终指向真实 Organization（避免 0 与根 parent_id 冲突成环）。
    """
    pid = int(parent_id or 0)
    oid = int(org_id or 0)
    if oid == 0:
        # 自动创建法人实体：parent_id 取上级节点的 org_id（无则 0）
        parent_org = 0
        if pid:
            for n in org_tree_tb():
                if n.org_id == pid:
                    parent_org = n.org_id
                    break
        new_org = orgs_tb.insert(name=name, level=level, parent_id=parent_org)
        oid = new_org.id
    org_tree_tb.insert(
        name=name, level=level, parent_id=pid, org_id=oid, created_at=_now()
    )
    log_audit("CREATE", "OrgTree", 0, detail=f"新增组织节点：{name}（{level}）", actor="系统管理员")
    return RedirectResponse(url="/org-tree", status_code=303)


@ar("/org-tree/{nid}/edit")
def org_tree_edit(nid: int):
    """编辑组织节点表单"""
    n = org_tree_tb[nid]
    parent_opts = [Option("— 顶级（集团） —", value="0")] + [
        Option(f"{o.name}（{o.level}）", value=o.org_id, selected=(o.org_id == n.parent_id))
        for o in org_tree_tb() if o.id != nid
    ]
    level_opts = [
        Option("集团", value="集团", selected=(n.level == "集团")),
        Option("子公司", value="子公司", selected=(n.level == "子公司")),
        Option("部门", value="部门", selected=(n.level == "部门")),
    ]
    return page_layout(
        "编辑组织节点", f"首页 / 系统概览 / 组织树 / 编辑", "/org-tree",
        Div(
            Form(
                Div(
                    Div(Label("组织名称", cls="form-label"),
                        Input(name="name", value=n.name, cls="form-input", required=True),
                        cls="form-group"),
                    Div(Label("层级", cls="form-label"),
                        Select(*level_opts, name="level", cls="form-select", required=True),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("上级节点", cls="form-label"),
                        Select(*parent_opts, name="parent_id", cls="form-select"),
                        cls="form-group"),
                    Div(Label("关联法人实体ID", cls="form-label"),
                        Input(name="org_id", type="number", value=n.org_id, cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/org-tree", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action=f"/org-tree/{nid}/update"
            ),
            cls="card"
        )
    )


@ar("/org-tree/{nid}/update", methods=["POST"])
def org_tree_update(nid: int, name: str, level: str, parent_id: str = "0", org_id: str = "0"):
    """更新组织节点"""
    n = org_tree_tb[nid]
    n.name = name
    n.level = level
    n.parent_id = int(parent_id or 0)
    oid = int(org_id or 0)
    if oid == 0:
        # 避免把已有节点的 org_id 清零造成成环/断链；保持原关联
        oid = n.org_id
    n.org_id = oid
    org_tree_tb.update(n)
    log_audit("UPDATE", "OrgTree", nid, detail=f"编辑组织节点：{name}", actor="系统管理员")
    return RedirectResponse(url="/org-tree", status_code=303)


@ar("/projects/cross-org")
def cross_org_view():
    """跨主体项目视图：按法人实体分组 + 各主体费用汇总"""
    projects = list(projects_tb())
    expenses = list(expenses_tb())

    # 费用=>项目映射（容错：expense.project_id 找不到项目时跳过）
    proj_map = {p.id: p for p in projects}
    # 按 org_id 分组
    groups = {}
    for p in projects:
        groups.setdefault(p.org_id, []).append(p)

    group_rows = []
    for oid, projs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        org_name = _org_name(oid)
        grp_exp = sum(
            e.amount for e in expenses
            if e.project_id in proj_map and proj_map[e.project_id].org_id == oid
        ) if oid else 0
        # 按研发性质折算可归集金额：自主研发 100%、委托研发 80%（加计口径）、受托研发 0（隔离）
        nature_ratio = {"自主研发": 1.0, "委托研发": 0.8, "受托研发": 0.0}
        grp_rd = sum(
            e.amount * nature_ratio.get(proj_map[e.project_id].rd_nature, 1.0)
            for e in expenses
            if e.project_id in proj_map and proj_map[e.project_id].org_id == oid
        ) if oid else 0
        grp_budget = sum(p.budget for p in projs)
        nature_tags = "、".join(sorted({p.rd_nature or "自主研发" for p in projs}))
        proj_links = "、".join(
            f'<a href="/projects/{p.id}" style="color:var(--primary);text-decoration:none;">{p.name}</a>'
            for p in projs[:5]
        )
        if len(projs) > 5:
            proj_links += f" 等 {len(projs)} 个"
        group_rows.append([
            Span(org_name, style="font-weight:600;"),
            str(len(projs)),
            nature_tags,
            f"¥{grp_budget:,.0f}",
            f"¥{grp_exp:,.0f}",
            f"¥{grp_rd:,.0f}",
            NotStr(proj_links),
        ])

    # 跨主体重复申报检测（相似项目名）
    dup_hits = _detect_duplicate_projects(projects)

    return page_layout(
        "跨主体项目视图", "首页 / 研发项目 / 跨主体视图", "/projects/cross-org",
        Div(
            Div(
                Span("按法人实体分组的项目分布"),
                A("重复申报检测 →", href="/projects/duplicate-check", cls="btn btn-warning btn-sm"),
                cls="card-title"
            ),
            data_table(
                ["法人主体", "项目数", "研发性质", "预算合计", "已归集费用", "可归集研发费用（按性质折算）", "项目清单"],
                group_rows
            ) if group_rows else empty_state("🏢", "暂无项目数据"),
            cls="card"
        ),
        Div(
            alert_box("核算规则：自主研发 100% 计入；委托研发按实际支出的 80% 计入加计扣除基数；受托研发支出不属于我方研发费用，按 0 折算并隔离展示。", "info"),
            cls="card"
        ),
        Div(
            Div("跨主体重复申报风险提示", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            _dup_alert(dup_hits),
            cls="card"
        ),
    )


def _detect_duplicate_projects(projects: list) -> list:
    """检测不同主体下相似项目名（名称包含匹配）的潜在重复申报。"""
    hits = []
    for i, a in enumerate(projects):
        for b in projects[i + 1:]:
            if a.org_id == b.org_id:
                continue  # 同主体不视为跨主体重复
            if not a.org_id or not b.org_id:
                continue  # 未分配主体跳过
            # 名称相似：一方包含另一方核心词（去除常见前缀/后缀）
            na, nb = a.name, b.name
            if na in nb or nb in na or _similar(na, nb):
                hits.append((a, b))
    return hits


def _similar(a: str, b: str) -> bool:
    """简单相似度：去除空格/研发/项目等词后包含匹配。"""
    import re
    def _norm(s):
        return re.sub(r"[\s（(】)]", "", s)
    na, nb = _norm(a), _norm(b)
    if len(na) < 3 or len(nb) < 3:
        return False
    return na in nb or nb in na


def _dup_alert(hits: list):
    if not hits:
        return alert_box("未检测到跨主体相似项目名，重复申报风险低。", "success")
    items = []
    for a, b in hits:
        items.append(Div(
            f"● 「{a.name}」（{_org_name(a.org_id)}）与「{b.name}」（{_org_name(b.org_id)}）"
            f"名称高度相似，存在跨主体重复归集风险，请核实是否为同一研发活动。",
            style="padding:6px 0;border-bottom:1px solid var(--app-split);font-size:13px;"
        ))
    return Div(*items)


@ar("/projects/duplicate-check")
def duplicate_check():
    """重复申报检测页：跨主体相似项目名 + 重叠费用期间"""
    projects = list(projects_tb())
    expenses = list(expenses_tb())

    # 1) 相似项目名
    name_hits = _detect_duplicate_projects(projects)

    # 2) 重叠费用期间（同主体不同项目，费用月份重叠度高）
    period_hits = _detect_overlap_periods(projects, expenses)

    return page_layout(
        "重复申报检测", "首页 / 研发项目 / 重复申报检测", "/projects/duplicate-check",
        Div(
            Div("一、跨主体相似项目名检测", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            _dup_alert(name_hits) if name_hits else alert_box("未检测到跨主体相似项目名。", "success"),
            cls="card"
        ),
        Div(
            Div("二、费用期间重叠检测", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            _overlap_table(period_hits) if period_hits else alert_box("未检测到显著费用期间重叠。", "success"),
            cls="card"
        ),
    )


def _detect_overlap_periods(projects: list, expenses: list) -> list:
    """检测不同主体项目间费用月份重叠（潜在重复归集同一期间费用）。"""
    # 构建 项目 → 费用月份集合
    proj_months = {}
    proj_map = {p.id: p for p in projects}
    for e in expenses:
        p = proj_map.get(e.project_id)
        if not p:
            continue
        m = (e.expense_date or "")[:7]
        if len(m) == 7:
            proj_months.setdefault(p.id, set()).add(m)

    hits = []
    plist = list(projects)
    for i, a in enumerate(plist):
        for b in plist[i + 1:]:
            if a.org_id == b.org_id or not a.org_id or not b.org_id:
                continue
            ma = proj_months.get(a.id, set())
            mb = proj_months.get(b.id, set())
            overlap = ma & mb
            if overlap:
                hits.append((a, b, sorted(overlap)))
    return hits


def _overlap_table(hits: list):
    rows = []
    for a, b, months in hits:
        rows.append([
            a.name, _org_name(a.org_id),
            b.name, _org_name(b.org_id),
            "、".join(months[:6]) + (f" 等 {len(months)} 个月" if len(months) > 6 else ""),
        ])
    return data_table(
        ["项目A", "主体A", "项目B", "主体B", "重叠费用月份"],
        rows
    )
