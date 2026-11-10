# -*- coding: utf-8 -*-
"""风控预警模块（缺口⑩-a：规则库+扫描引擎+预警列表）"""

from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime
import json

from .db import (
    projects_tb, expenses_tb, risk_rules_tb, risk_alerts_tb,
    work_time_tb, worktime_alert_rules_tb,
    audit_tb, members_tb, labor_cost_tb, project_nodes_tb,
)
from .components import (
    page_layout, data_table, empty_state, stat_block,
)

ar = APIRouter()

now = lambda: datetime.now().strftime("%Y-%m-%d %H:%M")


# ═══════════════════════ 规则库管理 ═══════════════════════

@ar("/risk-rules")
def risk_rules(rule_type: str = ""):
    """风控规则库"""
    rules = risk_rules_tb(order_by="-id")
    if rule_type:
        rules = [r for r in rules if r.rule_type == rule_type]
    total = len(risk_rules_tb())
    enabled = len([r for r in risk_rules_tb() if r.enabled])
    types = sorted(set(r.rule_type for r in risk_rules_tb()))

    rows = []
    for r in rules:
        status_cls = "badge-green" if r.enabled else "badge-gray"
        status_txt = "启用" if r.enabled else "禁用"
        toggle_url = f"/risk-rules/{r.id}/toggle"
        rows.append(
            Tr(
                Td(r.rule_name),
                Td(Span(r.rule_type, cls="chip")),
                Td(r.description[:50] + ("..." if len(r.description) > 50 else "")),
                Td(Span(status_txt, cls=status_cls)),
                Td(
                    A("切换", href=toggle_url, cls="btn btn-sm btn-outline"),
                    " ",
                    A("编辑", href=f"/risk-rules/{r.id}/edit", cls="btn btn-sm"),
                ),
            )
        )
    rule_table = Table(
        Thead(Tr(Th("规则名称"), Th("类型"), Th("描述"), Th("状态"), Th("操作"))),
        Tbody(*rows), cls="table",
    ) if rows else empty_state("", "暂无规则")

    # 新增规则表单
    add_form = Form(
        Div(
            Div(
                Label("规则名称", _for="rule_name"),
                Input(id="rule_name", name="rule_name", required=True, cls="form-input"),
            ),
            Div(
                Label("规则类型", _for="rule_type"),
                Select(
                    Option("费用", value="费用"),
                    Option("政策", value="政策"),
                    Option("管理", value="管理"),
                    id="rule_type", name="rule_type", cls="form-input",
                ),
            ),
            Div(
                Label("阈值(JSON)", _for="threshold"),
                Textarea(id="threshold", name="threshold", rows=2, cls="form-input",
                         placeholder='{"max_single_hours": 12}'),
            ),
            Div(
                Label("执行动作", _for="action"),
                Select(
                    Option("警告", value="警告"),
                    Option("提示", value="提示"),
                    Option("拦截", value="拦截"),
                    id="action", name="action", cls="form-input",
                ),
            ),
            Div(
                Label("描述", _for="description"),
                Textarea(id="description", name="description", rows=2, cls="form-input"),
            ),
            Button("添加规则", type="submit", cls="btn btn-primary"),
            cls="form-grid",
        ),
        action="/risk-rules/add", method="POST",
    )

    # 过滤 tabs
    type_tabs = Div(
        A("全部", href="/risk-rules", cls=f"tab {'active' if not rule_type else ''}"),
        *[A(f"{t}", href=f"/risk-rules?rule_type={t}", cls=f"tab {'active' if rule_type == t else ''}") for t in types],
        cls="tab-row",
    )

    content = Div(
        Div(
            Div(stat_block("规则总数", str(total), "blue"), cls="card"),
            Div(stat_block("已启用", str(enabled), "green"), cls="card"),
            Div(stat_block("已禁用", str(total - enabled), "gray"), cls="card"),
            cls="stats-grid-3",
        ),
        Div(
            H3("新增规则", cls="card-title"),
            add_form, cls="card",
        ),
        Div(
            H3("规则列表", cls="card-title"),
            type_tabs,
            rule_table, cls="card",
        ),
        cls="page",
    )
    return page_layout("风控规则库", "首页 / 风控 / 规则库", "/risk-rules", content)


@ar("/risk-rules/add", methods=["POST"])
def risk_rule_add(rule_name: str, rule_type: str, threshold: str = "{}",
                  action: str = "警告", description: str = ""):
    """新增规则"""
    try:
        json.loads(threshold)
    except (json.JSONDecodeError, TypeError):
        threshold = "{}"
    risk_rules_tb.insert(
        rule_name=rule_name, rule_type=rule_type, threshold=threshold,
        action=action, description=description, enabled=True, created_at=now(),
    )
    log_audit("风控规则", "新增", rule_name)
    return RedirectResponse(url="/risk-rules", status_code=303)


@ar("/risk-rules/{rid}/toggle")
def risk_rule_toggle(rid: int):
    """启用/禁用规则"""
    r = risk_rules_tb[rid]
    if r:
        risk_rules_tb.update({"enabled": not r.enabled}, r.id)
        log_audit("风控规则", "切换", f"{r.rule_name}->{'启用' if not r.enabled else '禁用'}")
    return RedirectResponse(url="/risk-rules", status_code=303)


@ar("/risk-rules/{rid}/edit")
def risk_rule_edit(rid: int):
    """编辑规则表单"""
    r = risk_rules_tb[rid]
    if not r:
        return RedirectResponse(url="/risk-rules", status_code=303)
    form = Form(
        Div(
            Div(
                Label("规则名称", _for="rule_name"),
                Input(id="rule_name", name="rule_name", value=r.rule_name, required=True, cls="form-input"),
            ),
            Div(
                Label("规则类型", _for="rule_type"),
                Select(
                    Option("费用", value="费用", selected=r.rule_type == "费用"),
                    Option("政策", value="政策", selected=r.rule_type == "政策"),
                    Option("管理", value="管理", selected=r.rule_type == "管理"),
                    id="rule_type", name="rule_type", cls="form-input",
                ),
            ),
            Div(
                Label("阈值(JSON)", _for="threshold"),
                Textarea(id="threshold", name="threshold", rows=2, cls="form-input"),
            ),
            Div(
                Label("执行动作", _for="action"),
                Select(
                    Option("警告", value="警告", selected=r.action == "警告"),
                    Option("提示", value="提示", selected=r.action == "提示"),
                    Option("拦截", value="拦截", selected=r.action == "拦截"),
                    id="action", name="action", cls="form-input",
                ),
            ),
            Div(
                Label("描述", _for="description"),
                Textarea(id="description", name="description", rows=2, cls="form-input"),
            ),
            Input(type="hidden", name="id", value=str(rid)),
            Button("保存", type="submit", cls="btn btn-primary"),
            A("取消", href="/risk-rules", cls="btn btn-outline"),
            cls="form-grid",
        ),
        action="/risk-rules/update", method="POST",
    )
    content = Div(
        H2("编辑规则", cls="page-title"),
        Div(form, cls="card"),
        cls="page",
    )
    return page_layout("编辑规则", "首页 / 风控 / 规则库 / 编辑", "/risk-rules", content)


@ar("/risk-rules/update", methods=["POST"])
def risk_rule_update(id: int, rule_name: str, rule_type: str,
                     threshold: str = "{}", action: str = "警告", description: str = ""):
    """更新规则"""
    try:
        json.loads(threshold)
    except (json.JSONDecodeError, TypeError):
        threshold = "{}"
    risk_rules_tb.update({
        "rule_name": rule_name, "rule_type": rule_type, "threshold": threshold,
        "action": action, "description": description,
    }, id)
    log_audit("风控规则", "更新", rule_name)
    return RedirectResponse(url="/risk-rules", status_code=303)


# ═══════════════════════ 预警扫描引擎 ═══════════════════════

def _scan_rule(rule):
    """执行单条规则扫描，返回 (level, desc, action) 列表

    支持两类阈值格式：
    1) 通用 metric 格式（种子规则）：{"metric":"<指标>","op":">|<|>=|<=|==|in","value":N}
    2) 兼容旧格式（历史规则）：personnel_ratio_max / other_ratio_max /
       min_rd_personnel_ratio / max_single_hours
    """
    results = []
    try:
        th = json.loads(rule.threshold) if rule.threshold else {}
    except (json.JSONDecodeError, TypeError):
        th = {}

    # 归一化为 metric 格式（旧键 → metric 映射）
    metric = th.get("metric")
    op = th.get("op", ">")
    value = th.get("value")
    if not metric:
        if th.get("personnel_ratio_max") is not None:
            metric, op, value = "personnel_ratio_max", ">", th["personnel_ratio_max"]
        elif th.get("other_ratio_max") is not None:
            metric, op, value = "other_ratio_max", ">", th["other_ratio_max"]
        elif th.get("min_rd_personnel_ratio") is not None:
            metric, op, value = "rd_personnel_ratio", "<", th["min_rd_personnel_ratio"]
        elif th.get("max_single_hours") is not None:
            metric, op, value = "max_single_hours", ">", th["max_single_hours"]

    def _cmp(actual, threshold):
        """通用比较器：阈值可为数值或数值字符串"""
        try:
            t = float(threshold)
            a = float(actual)
        except (TypeError, ValueError):
            return False
        if op == ">":
            return a > t
        if op == "<":
            return a < t
        if op in (">=", ">="):
            return a >= t
        if op in ("<=", "<="):
            return a <= t
        if op == "==":
            return a == t
        if op == "in":
            return bool(a)
        return False

    if metric == "monthly_expense_growth_pct":
        # 某项目当月研发费用环比增幅 > value%
        from collections import defaultdict
        by_proj_month = defaultdict(float)
        for e in expenses_tb():
            m = (e.expense_date or "")[:7]
            if len(m) == 7:
                by_proj_month[(e.project_id, m)] += e.amount or 0
        months = sorted({m for (_, m) in by_proj_month})
        for (pid, m) in sorted(by_proj_month):
            idx = months.index(m)
            if idx <= 0:
                continue
            prev = by_proj_month.get((pid, months[idx - 1]), 0.0)
            cur = by_proj_month[(pid, m)]
            if prev <= 0:
                continue
            growth = (cur - prev) / prev * 100
            if _cmp(growth, value):
                results.append(("高",
                    f"项目{pid} {m} 研发费用环比增幅 {growth:.0f}% > 阈值 {value}%",
                    "核查费用异常增长原因，必要时补充佐证"))
    elif metric in ("personnel_ratio_max", "other_ratio_max"):
        # 费用占比检查：人员人工占比、其他费用占比（旧格式兼容）
        all_expenses = expenses_tb()
        if not all_expenses:
            return results
        total = sum(e.amount for e in all_expenses)
        if total <= 0:
            return results
        for e in all_expenses:
            name = str(e.subject_name or "")
            pct = e.amount / total
            if metric == "personnel_ratio_max" and "人员人工" in name and _cmp(pct, value):
                results.append(("高",
                    f"项目{e.project_id} 人员人工费用占比 {pct:.1%} > 阈值 {float(value):.0%}",
                    "调整人员人工费用分配"))
            elif metric == "other_ratio_max" and "其他" in name and _cmp(pct, value):
                results.append(("高",
                    f"项目{e.project_id} 其他费用占比 {pct:.1%} > 阈值 {float(value):.0%}",
                    "其他费用已超限，需调整或归入其他科目"))
    elif metric == "rd_personnel_ratio":
        # 政策类：高企认定研发人员占比检查
        for p in projects_tb():
            members = members_tb(where=f"project_id={p.id}")
            rd_members = [m for m in members if getattr(m, "role", "") == "研发人员"]
            if members and _cmp(len(rd_members) / len(members), value):
                results.append(("中",
                    f"项目{p.name} 研发人员占比 {len(rd_members)}/{len(members)} < {float(value):.0%}",
                    "增加研发人员或调整人员结构"))
    elif metric == "other_expense_pct":
        # 其他相关费用占项目研发费用比例 > value%（加计扣除 10% 限额）
        from collections import defaultdict
        proj_total = defaultdict(float)
        proj_other = defaultdict(float)
        for e in expenses_tb():
            proj_total[e.project_id] += e.amount or 0
            if "其他" in str(e.subject_name or ""):
                proj_other[e.project_id] += e.amount or 0
        for pid in proj_total:
            if proj_total[pid] <= 0:
                continue
            pct = proj_other.get(pid, 0.0) / proj_total[pid] * 100
            if _cmp(pct, value):
                results.append(("高",
                    f"项目{pid} 其他相关费用占比 {pct:.1f}% > 限额 {value}%",
                    "超过加计扣除 10% 限额，需调整科目或控制其他费用"))
    elif metric == "negative_list":
        # 负面清单支出混入研发费用（业务招待/市场推广/广告费等）
        negative_words = ("业务招待", "招待费", "市场推广", "广告费", "娱乐", "罚款", "滞纳金")
        for e in expenses_tb():
            name = str(e.subject_name or "")
            desc = str(getattr(e, "description", "") or "")
            if any(w in name or w in desc for w in negative_words):
                results.append(("高",
                    f"费用 #{e.id}（{name or '未分类'} ¥{e.amount:,.0f}）命中负面清单",
                    "负面清单支出不得归集研发费用，请剔除或调整科目"))
    elif metric == "building_depreciation":
        # 建筑物折旧计入加计扣除（财税[2015]119号：建筑物折旧不得加计）
        from .db import equipment_tb
        building_cats = ("在用建筑物", "房屋", "房屋建筑物", "建筑物")
        for eq in equipment_tb():
            cat = str(getattr(eq, "category", "") or "")
            if cat.strip() in building_cats:
                results.append(("高",
                    f"设备 #{eq.id}（{eq.name}）属在用建筑物类资产",
                    "建筑物折旧只能计入高企认定口径，不得计入加计扣除"))
    elif metric == "dev_without_approval":
        # 项目进入开发阶段但未完成立项审批（状态仍为立项中）
        for p in projects_tb():
            nodes = project_nodes_tb(where=f"project_id={p.id}")
            if any(n.phase == "开发" for n in nodes) and p.status == "立项中":
                results.append(("中",
                    f"项目{p.name} 已进入开发阶段但未完成立项审批",
                    "尽快完成立项审批，避免阶段口径违规"))
    elif metric == "approve_no_collect_days":
        # 节点审批通过超过 value 天无费用归集记录
        from datetime import datetime, timedelta
        today = datetime.now().date()
        for n in project_nodes_tb():
            if not (n.status == "已完成" or n.deliverable_status == "已通过"):
                continue
            ref = (n.end_date or n.start_date or "")[:10]
            if len(ref) != 10:
                continue
            try:
                ref_d = datetime.strptime(ref, "%Y-%m-%d").date()
            except ValueError:
                continue
            days = (today - ref_d).days
            if days < 0:
                continue
            has_collect = any(e.node_id == n.id for e in expenses_tb())
            if not has_collect and _cmp(days, value):
                results.append(("中",
                    f"项目{n.project_id} 节点「{n.node_name}」通过 {days} 天无费用归集",
                    "补充归集记录或说明未归集原因"))
    elif metric == "max_single_hours":
        # 管理类：工时异常检查（旧格式兼容）
        max_h = float(value)
        for wt in work_time_tb():
            if float(wt.hours) > max_h:
                results.append(("低",
                    f"人员{wt.person_id} 单日工时 {wt.hours}h > {max_h}h",
                    "工时异常，请核实"))
    return results


def _ensure_alert(project_id, rule_id, level, description, action):
    """去重写入预警"""
    today = datetime.now().strftime("%Y-%m-%d")
    exists = risk_alerts_tb(where=f"rule_id={rule_id} AND description='{description}' AND created_at LIKE '{today}%'")
    if exists:
        return
    risk_alerts_tb.insert(
        project_id=project_id, rule_id=rule_id, level=level,
        description=description, status="未处理",
        suggested_action=action, created_at=now(),
    )


@ar("/risk-scan")
def risk_scan():
    """手动触发预警扫描"""
    rules = risk_rules_tb(where="enabled=1")
    scanned = 0
    alerts_generated = 0
    for rule in rules:
        results = _scan_rule(rule)
        scanned += 1
        for level, desc, action in results:
            _ensure_alert(0, rule.id, level, desc, action)
            alerts_generated += 1
    log_audit("风控扫描", "手动", f"扫描 {scanned} 条规则，生成 {alerts_generated} 条预警")
    return RedirectResponse(url=f"/risk-alerts?msg=扫描完成，共生成 {alerts_generated} 条预警", status_code=303)


# ═══════════════════════ 预警列表与处理 ═══════════════════════

@ar("/risk-alerts")
def risk_alerts(level_filter: str = "", status_filter: str = "", msg: str = ""):
    """预警列表"""
    alerts = risk_alerts_tb(order_by="-id")
    if level_filter:
        alerts = [a for a in alerts if a.level == level_filter]
    if status_filter:
        alerts = [a for a in alerts if a.status == status_filter]

    total = len(risk_alerts_tb())
    pending = len([a for a in risk_alerts_tb() if a.status == "未处理"])
    high = len([a for a in risk_alerts_tb() if a.level == "高" and a.status == "未处理"])

    rows = []
    for a in alerts:
        level_cls = {"高": "badge-red", "中": "badge-amber", "低": "badge-gray"}.get(a.level, "badge-gray")
        status_cls = {"未处理": "badge-red", "已处理": "badge-green", "已忽略": "badge-gray"}.get(a.status, "badge-gray")
        actions = []
        if a.status == "未处理":
            actions.append(A("处理", href=f"/risk-alerts/{a.id}/resolve", cls="btn btn-sm btn-success"))
            actions.append(" ")
            actions.append(A("忽略", href=f"/risk-alerts/{a.id}/ignore", cls="btn btn-sm btn-outline"))
        rows.append(
            Tr(
                Td(Span(a.level, cls=level_cls)),
                Td(a.description[:60]),
                Td(a.suggested_action[:30]),
                Td(Span(a.status, cls=status_cls)),
                Td(a.created_at[:10] if a.created_at else ""),
                Td(*actions),
            )
        )

    alert_table = Table(
        Thead(Tr(Th("等级"), Th("描述"), Th("建议操作"), Th("状态"), Th("时间"), Th("操作"))),
        Tbody(*rows), cls="table",
    ) if rows else empty_state("", "暂无预警")

    # 消息提示
    msg_banner = Div(msg, cls="alert alert-info") if msg else ""

    # 过滤
    filter_area = Div(
        A("全部", href="/risk-alerts", cls=f"tab {'active' if not level_filter and not status_filter else ''}"),
        A("高风险", href="/risk-alerts?level_filter=高", cls=f"tab {'active' if level_filter == '高' else ''}"),
        A("未处理", href="/risk-alerts?status_filter=未处理", cls=f"tab {'active' if status_filter == '未处理' else ''}"),
        A("已处理", href="/risk-alerts?status_filter=已处理", cls=f"tab {'active' if status_filter == '已处理' else ''}"),
        cls="tab-row",
    )

    content = Div(
        msg_banner,
        Div(
            Div(stat_block("预警总数", str(total), "blue"), cls="card"),
            Div(stat_block("待处理", str(pending), "red"), cls="card"),
            Div(stat_block("高风险待处理", str(high), "red"), cls="card"),
            cls="stats-grid-3",
        ),
        Div(
            Div(
                H3("预警列表", cls="card-title"),
                A("执行扫描", href="/risk-scan", cls="btn btn-sm btn-primary"),
                cls="card-header",
            ),
            filter_area,
            alert_table,
            cls="card",
        ),
        cls="page",
    )
    return page_layout("风控预警", "首页 / 风控 / 预警", "/risk-alerts", content)


@ar("/risk-alerts/{aid}/resolve")
def risk_alert_resolve(aid: int):
    """处理预警"""
    a = risk_alerts_tb[aid]
    if a and a.status == "未处理":
        risk_alerts_tb.update({"status": "已处理"}, aid)
        log_audit("风控预警", "处理", a.description[:50])
    return RedirectResponse(url="/risk-alerts", status_code=303)


@ar("/risk-alerts/{aid}/ignore")
def risk_alert_ignore(aid: int):
    """忽略预警"""
    a = risk_alerts_tb[aid]
    if a and a.status == "未处理":
        risk_alerts_tb.update({"status": "已忽略"}, aid)
        log_audit("风控预警", "忽略", a.description[:50])
    return RedirectResponse(url="/risk-alerts", status_code=303)


# ═══════════════════════ 辅助 ═══════════════════════

def log_audit(action, entity, detail):
    """写入审计日志"""
    try:
        audit_tb.insert(
            ts=now(), action=action, entity=entity,
            entity_id=0, detail=detail, actor="system",
            before="", after="",
        )
    except Exception:
        pass