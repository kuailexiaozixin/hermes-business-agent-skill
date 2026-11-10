"""routes_datacenter.py — 研发数据中心（缺口⑪）

功能：
- 数据归集视图：项目/人员/工时/设备/材料/财务凭证 六类源头数据统一视图
- 跨模块一致性校验：手动触发扫描 expense/worktime/equipment/material 关联矛盾
- 数据血缘追踪：DataCenterLog 变更日志 + 时间线展示
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date

from .db import (
    expenses_tb, projects_tb, work_time_tb, equipment_tb,
    equipment_depreciation_tb, material_requisition_tb, labor_cost_tb,
    personnel_tb, evidence_docs_tb, datacenter_logs_tb, log_audit,
    outsourcing_tb, other_expense_tb,
)
from .components import (
    page_layout, stat_card, data_table, empty_state, alert_box, stat_block,
)

ar = APIRouter()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _today():
    return date.today().strftime("%Y-%m-%d")


def log_data_change(source_table: str, source_id: int, field_key: str,
                    old_val: str = "", new_val: str = "", operator: str = "system"):
    """写入数据中心变更日志（血缘追踪）"""
    try:
        datacenter_logs_tb.insert(
            source_table=source_table, source_id=source_id,
            field_key=field_key, old_val=str(old_val)[:200],
            new_val=str(new_val)[:200],
            sync_time=_now(), operator=operator, created_at=_now(),
        )
    except Exception:
        pass


def _source_stats():
    """六类源头数据统计（数量 + 最新更新时间）"""
    def _latest(rows, field="created_at"):
        vals = [str(getattr(r, field, "") or "") for r in rows]
        vals = [v for v in vals if v]
        return max(vals) if vals else "—"

    stats = [
        ("项目", projects_tb(), "projects"),
        ("人员", personnel_tb(), "personnel"),
        ("工时", work_time_tb(), "worktime"),
        ("设备", equipment_tb(), "equipment"),
        ("材料", material_requisition_tb(), "material"),
        ("财务凭证", evidence_docs_tb(), "evidence"),
    ]
    out = []
    for name, rows, key in stats:
        out.append({
            "name": name, "count": len(rows),
            "latest": _latest(rows),
            "key": key,
        })
    return out


def _consistency_check():
    """跨模块一致性校验，返回 [(级别, 模块, 问题, 建议)]"""
    issues = []
    proj_ids = {p.id for p in projects_tb()}
    equip_ids = {e.id for e in equipment_tb()}
    person_ids = {p.id for p in personnel_tb()}

    # ① 费用无项目 / 项目不存在
    for e in expenses_tb():
        if not e.project_id:
            issues.append(("高", "费用", f"费用 #{e.id}（{e.subject_name or '未分类'} ¥{e.amount:,.0f}）未关联项目", "请补录项目归属，否则无法归集与追溯"))
        elif e.project_id not in proj_ids:
            issues.append(("高", "费用", f"费用 #{e.id} 关联的项目 {e.project_id} 不存在", "项目可能已删除，请修正关联"))

    # ② 费用科目为空
    for e in expenses_tb():
        if not (e.subject_name or "").strip():
            issues.append(("中", "费用", f"费用 #{e.id} 未设置科目", "请补充费用科目，避免口径统计缺失"))

    # ③ 工时无项目 / 无人员
    for w in work_time_tb():
        if w.project_id and w.project_id not in proj_ids:
            issues.append(("中", "工时", f"工时 #{w.id}（{w.work_date} {w.hours}h）关联项目 {w.project_id} 不存在", "请修正工时归属"))
        if w.person_id and w.person_id not in person_ids:
            issues.append(("中", "工时", f"工时 #{w.id} 关联人员 {w.person_id} 不存在", "人员档案缺失，请检查"))

    # ④ 设备折旧无设备
    for d in equipment_depreciation_tb():
        if d.equipment_id and d.equipment_id not in equip_ids:
            issues.append(("中", "设备", f"设备折旧 #{d.id}（{d.cost_month}）关联设备 {d.equipment_id} 不存在", "设备档案缺失，请检查"))

    # ⑤ 人员工时与人工费对比（按月粗校验）
    from collections import defaultdict
    hours_by_person = defaultdict(float)
    for w in work_time_tb():
        if w.person_id:
            hours_by_person[w.person_id] += w.hours or 0
    labor_by_person = defaultdict(float)
    for lc in labor_cost_tb():
        labor_by_person[lc.person_id] += lc.total_salary or 0
    for pid in person_ids:
        h = hours_by_person.get(pid, 0.0)
        l = labor_by_person.get(pid, 0.0)
        # 有工时却无人工费，或有人工费却无工时（按人员粗略提示）
        if h > 0 and l <= 0:
            issues.append(("低", "工时/人工费", f"人员 {pid} 存在工时 {h:.0f}h 但无人工费归集", "确认是否漏归集人员人工费用"))
        elif l > 0 and h <= 0:
            issues.append(("低", "工时/人工费", f"人员 {pid} 有人工费 ¥{l:,.0f} 但无工时记录", "确认工时台账是否完整"))

    # ⑥ 材料领用未归集
    uncollected = [m for m in material_requisition_tb() if not int(getattr(m, "collected", 0) or 0)]
    if uncollected:
        issues.append(("中", "材料", f"有 {len(uncollected)} 笔材料领用未归集", "请执行费用归集或确认未归集原因"))

    return issues


@ar("/datacenter")
def datacenter_index():
    """数据中心首页：六源统一归集视图 + 血缘时间线"""
    stats = _source_stats()
    issues = _consistency_check()
    logs = sorted(datacenter_logs_tb(), key=lambda r: r.created_at or "", reverse=True)[:20]

    stat_cards = Div(
        *[stat_card(s["name"], f"{s['count']} 条", f"最新 {s['latest']}") for s in stats],
        cls="stats-grid",
    )

    issue_cards = []
    for level, mod, desc, sug in issues[:6]:
        badge = {"高": ("高", "red"), "中": ("中", "amber"), "低": ("低", "gray")}[level]
        issue_cards.append(
            Div(
                Div(badge[0], cls=f"badge badge-{badge[1]}"),
                Span(f"[{mod}] {desc}", cls="issue-desc"),
                Div(sug, cls="issue-sug"),
                cls="issue-item",
            )
        )
    issues_area = Div(
        H3("跨模块一致性校验"),
        Div(*issue_cards, cls="issue-list") if issue_cards else alert_box("未发现问题，账账相符", "success"),
        A("立即执行校验", href="/datacenter/check", cls="button button-sm"),
        cls="card",
    )

    timeline = []
    for lg in logs:
        timeline.append(
            Div(
                Div(f"{lg.source_table}#{lg.source_id} · {lg.field_key}", cls="tl-title"),
                Div(f"{lg.old_val} → {lg.new_val}", cls="tl-detail"),
                Div(f"{lg.sync_time} · {lg.operator}", cls="tl-time"),
                cls="timeline-item",
            )
        )
    timeline_area = Div(
        H3("数据血缘时间线（最近变更）"),
        Div(*timeline, cls="timeline") if timeline else empty_state("", "暂无变更日志"),
        A("查看全部日志", href="/datacenter/logs", cls="button button-sm"),
        cls="card",
    )

    body = Div(
        Div(H2("研发数据中心"), cls="page-title"),
        stat_cards,
        Div(
            A("账账相符自动核对报告", href="/datacenter/reconcile", cls="button"),
            A("一致性校验", href="/datacenter/check", cls="button button-outline"),
            A("变更日志", href="/datacenter/logs", cls="button button-outline"),
            style="margin-bottom:16px;display:flex;gap:10px;",
        ),
        Div(issues_area, timeline_area, cls="two-col"),
        cls="page",
    )
    return page_layout("研发数据中心", "数据中心", "/datacenter", body)


@ar("/datacenter/check")
def datacenter_check():
    """手动触发跨模块一致性校验，并写入血缘日志"""
    issues = _consistency_check()
    log_data_change("datacenter_check", 0, "consistency",
                    old_val="", new_val=f"发现 {len(issues)} 个问题", operator="system")
    log_audit("DATACENTER_CHECK", "DataCenterLog", 0,
              detail=f"数据中心一致性校验，发现 {len(issues)} 个问题")

    rows = []
    for level, mod, desc, sug in issues:
        rows.append([level, mod, desc, sug])
    if not rows:
        rows.append(["ok", "—", "未发现跨模块矛盾数据", "账账相符"])

    table = data_table(
        ["级别", "模块", "问题描述", "处理建议"],
        rows,
    ) if rows else empty_state("✓", "未发现跨模块矛盾数据，账账相符")
    body = Div(
        Div(H2("一致性校验结果"), cls="page-title"),
        alert_box(f"共发现 {len(issues)} 个问题；校验结果已写入数据中心日志", "info"),
        table,
        A("返回数据中心", href="/datacenter", cls="button"),
        cls="page",
    )
    return page_layout("一致性校验", "数据中心 / 一致性校验", "/datacenter", body)


@ar("/datacenter/logs")
def datacenter_logs(source_table: str = ""):
    """数据中心变更日志列表（可按表过滤）"""
    logs = datacenter_logs_tb()
    if source_table:
        logs = [lg for lg in logs if lg.source_table == source_table]
    logs = sorted(logs, key=lambda r: r.created_at or "", reverse=True)

    tables = sorted({lg.source_table for lg in datacenter_logs_tb()})
    filter_links = [A("全部", href="/datacenter/logs", cls="chip active" if not source_table else "chip")]
    for t in tables:
        filter_links.append(A(t, href=f"/datacenter/logs?source_table={t}",
                              cls="chip active" if source_table == t else "chip"))

    rows = []
    for lg in logs:
        rows.append([
            lg.source_table, lg.source_id, lg.field_key,
            (lg.old_val or "—")[:80], (lg.new_val or "—")[:80],
            lg.sync_time, lg.operator,
        ])
    body = Div(
        Div(H2("数据中心变更日志"), cls="page-title"),
        Div(*filter_links, cls="chip-row"),
        data_table(
            ["来源表", "记录ID", "字段", "旧值", "新值", "时间", "操作者"],
            rows,
        ) if rows else empty_state("", "暂无变更日志"),
        A("返回数据中心", href="/datacenter", cls="button"),
        cls="page",
    )
    return page_layout("变更日志", "数据中心 / 变更日志", "/datacenter", body)


# ═══════════════════════ 账账相符自动核对报告 ═══════════════════════

def _reconcile_report():
    """账账相符自动核对：费用总账 vs 各类明细台账

    返回 (rows, diffs)：
    - rows: 核对明细行 [账套/科目类别, 金额, 核对状态, 差异说明]
    - diffs: 存在差异的类别名列表
    """
    from collections import defaultdict

    # ── 总账口径：费用总账（expenses_tb）按科目关键字归类 ──
    ledger = defaultdict(float)
    expense_cnt = defaultdict(int)
    for e in expenses_tb():
        name = str(e.subject_name or "")
        amt = e.amount or 0.0
        if "人员人工" in name or "工资" in name or "社保" in name or "公积金" in name:
            key = "人员人工"
        elif "材料" in name or "原料" in name or "耗材" in name:
            key = "直接材料"
        elif "折旧" in name or "摊销" in name:
            key = "折旧摊销"
        elif "委托" in name or "外协" in name or "外包" in name:
            key = "委托研发"
        elif "其他" in name:
            key = "其他费用"
        elif "差旅" in name or "会议" in name or "图书" in name or "咨询" in name or "知识产权" in name:
            key = "其他费用"
        else:
            key = "其他费用"
        ledger[key] += amt
        expense_cnt[key] += 1

    # ── 明细账口径：各业务台账（已归集部分） ──
    detail = defaultdict(float)
    detail_src = {
        "人员人工": "人工费用台账",
        "直接材料": "材料领用台账",
        "折旧摊销": "设备折旧台账",
        "委托研发": "委托外部研发台账",
        "其他费用": "其他费用台账",
    }
    for lc in labor_cost_tb():
        if getattr(lc, "status", "") == "已分摊":
            detail["人员人工"] += (lc.total_salary or 0.0)
    for m in material_requisition_tb():
        if int(getattr(m, "collected", 0) or 0):
            detail["直接材料"] += (getattr(m, "net_amount", 0.0) or m.amount or 0.0)
    for d in equipment_depreciation_tb():
        if getattr(d, "status", "") == "已分摊":
            detail["折旧摊销"] += (d.monthly_depreciation or 0.0) * (d.rd_usage_ratio or 1.0)
    for o in outsourcing_tb():
        if int(getattr(o, "collected", 0) or 0):
            detail["委托研发"] += (o.actual_amount or 0.0)
    for o in other_expense_tb():
        if int(getattr(o, "collected", 0) or 0):
            detail["其他费用"] += (o.amount or 0.0)

    # ── 核对：容差 1 元 ──
    TOLERANCE = 1.0
    rows = []
    diffs = []
    for key in ["人员人工", "直接材料", "折旧摊销", "委托研发", "其他费用"]:
        l = ledger.get(key, 0.0)
        d = detail.get(key, 0.0)
        diff = l - d
        ok = abs(diff) <= TOLERANCE
        if not ok:
            diffs.append(key)
        rows.append([
            key,
            f"¥{l:,.0f}（{expense_cnt.get(key, 0)} 笔）",
            f"¥{d:,.0f}",
            f"¥{diff:,.0f}",
            "相符" if ok else "差异",
            detail_src[key],
        ])

    # 汇总行
    total_l = sum(ledger.values())
    total_d = sum(detail.values())
    total_ok = abs(total_l - total_d) <= TOLERANCE
    rows.append([
        "合计",
        f"¥{total_l:,.0f}",
        f"¥{total_d:,.0f}",
        f"¥{total_l - total_d:,.0f}",
        "相符" if total_ok else "差异",
        "全台账",
    ])
    return rows, diffs


@ar("/datacenter/reconcile")
def datacenter_reconcile():
    """账账相符自动核对报告"""
    rows, diffs = _reconcile_report()
    status_ok = not diffs
    status_box = alert_box(
        "账账相符：费用总账与各明细台账核对一致，无重大差异。" if status_ok
        else f"发现差异类别：{'、'.join(diffs)}，请核查对应台账归集口径。",
        "success" if status_ok else "warning",
    )
    body = Div(
        Div(H2("账账相符自动核对报告"), cls="page-title"),
        status_box,
        alert_box("核对口径：费用总账（expenses 科目汇总）与人工/材料/折旧/委托/其他五类明细台账（已归集部分）比对，容差 1 元。", "info"),
        data_table(
            ["费用类别", "总账金额", "明细台账金额", "差异", "核对结果", "台账来源"],
            rows,
        ),
        Div(
            A("导出 CSV", href="/datacenter/reconcile/export", cls="button"),
            A("返回数据中心", href="/datacenter", cls="button button-outline"),
            style="margin-top:12px;display:flex;gap:10px;",
        ),
        cls="page",
    )
    return page_layout("账账相符核对", "数据中心 / 账账相符核对", "/datacenter", body)


@ar("/datacenter/reconcile/export")
def datacenter_reconcile_export():
    """导出账账相符核对报告 CSV"""
    import csv, io
    rows, _ = _reconcile_report()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["费用类别", "总账金额", "明细台账金额", "差异", "核对结果", "台账来源"])
    for r in rows:
        w.writerow(r)
    csv_text = "\ufeff" + buf.getvalue()  # BOM 便于 Excel 识别 UTF-8
    return Response(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="reconcile_report_{_today()}.csv"'
        },
    )
