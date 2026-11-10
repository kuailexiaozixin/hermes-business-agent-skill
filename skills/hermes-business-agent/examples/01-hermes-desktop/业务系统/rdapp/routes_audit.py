"""routes_audit.py — 全系统操作审计日志查看器

满足 rd-governor 红线"有据可查、可审计"：集中展示系统内所有关键写操作的
"谁/何时/对什么/做了什么"，支持按实体、动作、操作人、日期范围筛选。
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date

from .db import audit_tb
from .components import page_layout, stat_card, data_table, empty_state

ar = APIRouter()

KNOWN_ENTITIES = [
    "expense", "approval", "assessment", "project", "evidence", "risk",
    "outsourcing", "other_expense", "personnel", "organization",
]
KNOWN_ACTIONS = [
    "CREATE", "UPDATE", "DELETE", "APPROVE", "REJECT", "REVIEW",
    "WITHDRAW", "LOGIN", "IMPORT", "EXPORT",
]


def _opt(items, current):
    return [Option("全部", value="", selected=(current == ""))] + \
        [Option(i, value=i, selected=(i == current)) for i in items]


@ar("/audit")
def audit(entity: str = "", action: str = "", actor: str = "",
         date_from: str = "", date_to: str = ""):
    """审计日志首页 — 筛选 + 时间倒序列表"""
    conds = []
    if entity:
        conds.append(f"entity='{entity}'")
    if action:
        conds.append(f"action='{action}'")
    if actor:
        safe = actor.replace("'", "''")
        conds.append(f"actor LIKE '%{safe}%'")
    if date_from:
        conds.append(f"ts >= '{date_from} 00:00'")
    if date_to:
        conds.append(f"ts <= '{date_to} 23:59'")
    where = " AND ".join(conds) if conds else "1=1"

    logs = list(audit_tb(where=where))[::-1]

    today = date.today().strftime("%Y-%m-%d")
    total = len(logs)
    today_cnt = sum(1 for lg in logs if (lg.ts or "").startswith(today))
    create_cnt = sum(1 for lg in logs if lg.action == "CREATE")

    filter_form = Form(
        Div(Label("实体", cls="form-label"),
            Select(*_opt(KNOWN_ENTITIES, entity), name="entity", cls="form-select"), cls="form-group"),
        Div(Label("动作", cls="form-label"),
            Select(*_opt(KNOWN_ACTIONS, action), name="action", cls="form-select"), cls="form-group"),
        Div(Label("操作人", cls="form-label"),
            Input(name="actor", value=actor, cls="form-input", placeholder="模糊匹配"), cls="form-group"),
        Div(Label("起始日期", cls="form-label"),
            Input(name="date_from", type="date", value=date_from, cls="form-input"), cls="form-group"),
        Div(Label("截止日期", cls="form-label"),
            Input(name="date_to", type="date", value=date_to, cls="form-input"), cls="form-group"),
        Div(Button("查询", type="submit", cls="btn btn-primary"),
            A("重置", href="/audit", cls="btn btn-outline"),
            style="display:flex;gap:10px;align-items:flex-end;"),
        method="get", action="/audit",
        style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;align-items:end;"
    )

    rows = []
    for lg in logs:
        chg = ""
        if lg.before or lg.after:
            b = (lg.before or "")[:24]
            a = (lg.after or "")[:24]
            chg = f"前：{b}{'…' if len(lg.before or '') > 24 else ''} → 后：{a}{'…' if len(lg.after or '') > 24 else ''}"
        rows.append([
            lg.ts, lg.actor or "—", lg.action, f"{lg.entity}#{lg.entity_id}",
            lg.detail or "—", chg or "—",
        ])

    return page_layout(
        "操作审计", "首页 / 操作审计", "/audit",
        Div(
            stat_card("日志总数", str(total), f"今日 {today_cnt} 条", "blue"),
            stat_card("新建操作(CREATE)", str(create_cnt), "归集与审批记录", "green"),
            stat_card("最近操作", (logs[0].ts if logs else "—"), "最新一条", "orange"),
            cls="stat-grid",
        ),
        Div(Div("筛选条件", cls="card-title"), filter_form, cls="card"),
        Div(
            Div("操作日志（时间倒序）", cls="card-title"),
            data_table(
                ["时间", "操作人", "动作", "对象", "操作摘要", "变更"],
                rows
            ) if rows else empty_state("🔍", "暂无符合条件的审计日志"),
            cls="card",
        ),
    )
