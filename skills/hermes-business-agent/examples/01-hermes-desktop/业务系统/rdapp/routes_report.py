"""routes_report.py — 报表中心（缺口①⑭）

功能：
- 月度报表生成：按 period=YYYY-MM + caliber 聚合 expense_tb 数据
- 版本锁定：报表生成时自动计算 data_hash（SHA256），锁定后只读
- 多口径并排：高企认定 / 加计扣除 / 会计 / R&D统计 / IPO / 业务管理 / 财务核算
- 导出：Excel（openpyxl 生成 .xlsx）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime
from urllib.parse import quote
import hashlib
import json
import io

from .db import (
    expenses_tb, projects_tb, report_versions_tb, log_audit,
)
from .components import (
    page_layout, stat_card, data_table, empty_state, alert_box,
    stat_block, month_options,
)

ar = APIRouter()

CALIBERS = ["高企认定", "加计扣除", "会计", "R&D统计", "IPO", "业务管理", "财务核算"]
CALIBER_NOTES = {
    "高企认定": "高新技术企业认定口径",
    "加计扣除": "研发费用加计扣除口径",
    "会计": "本系统会计口径（全量费用）",
    "R&D统计": "研发统计口径（全量费用）",
    "IPO": "IPO 核查口径（全量费用）",
    "业务管理": "业务管理口径（三类口径统一视图）",
    "财务核算": "财务核算口径（三类口径统一视图）",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _month_now():
    return datetime.now().strftime("%Y-%m")


def _caliber_match(expense, caliber: str) -> bool:
    """费用记录是否属于该口径。会计/R&D统计/IPO/业务管理/财务核算 取全量。"""
    if caliber in ("会计", "R&D统计", "IPO", "业务管理", "财务核算"):
        return True
    return caliber in (expense.caliber or "")


def _collect(project_id: int, period: str, caliber: str):
    """按 project/period/caliber 聚合费用明细。project_id=0 表示全部项目。"""
    rows = []
    for e in expenses_tb():
        if e.expense_date and not e.expense_date.startswith(period):
            continue
        if project_id and e.project_id != project_id:
            continue
        if not _caliber_match(e, caliber):
            continue
        rows.append(e)
    return rows


def _data_hash(project_id: int, period: str, caliber: str, rows) -> str:
    """报表内容 SHA256 指纹：按 科目汇总+阶段汇总+总金额 计算，内容变化则指纹变化。"""
    from collections import defaultdict
    subj = defaultdict(float)
    phase = defaultdict(float)
    total = 0.0
    for e in rows:
        subj[e.subject_name or "未分类"] += e.amount
        phase[e.phase or "未标注"] += e.amount
        total += e.amount
    payload = {
        "project_id": project_id, "period": period, "caliber": caliber,
        "total": round(total, 2),
        "subjects": {k: round(v, 2) for k, v in sorted(subj.items())},
        "phases": {k: round(v, 2) for k, v in sorted(phase.items())},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _find_version(project_id: int, period: str, caliber: str):
    for v in report_versions_tb():
        if v.project_id == project_id and v.period == period and v.caliber == caliber:
            return v
    return None


def _upsert_version(project_id: int, period: str, caliber: str, data_hash: str):
    """未锁定版本：存在则更新哈希，不存在则创建。锁定版本不更新。"""
    v = _find_version(project_id, period, caliber)
    if v:
        if not v.is_locked and v.data_hash != data_hash:
            v.data_hash = data_hash
            report_versions_tb.update(v)
        return v
    return report_versions_tb.insert(
        project_id=project_id, period=period, caliber=caliber,
        data_hash=data_hash, is_locked=False, created_at=_now(),
    )


def _project_options(selected=""):
    opts = [Option("— 全部项目 —", value="0")]
    for p in projects_tb():
        opts.append(Option(f"{p.code} {p.name}", value=p.id,
                           selected=str(p.id) == str(selected)))
    return opts


@ar("/reports/center")
def reports_index(project_id: str = "0", period: str = ""):
    """报表中心首页：项目+月份选择器 + 口径入口 + 版本列表"""
    pid = int(project_id or 0)
    period = period or _month_now()
    proj = projects_tb[pid] if pid else None
    title = proj.name if proj else "全部项目"

    # 各口径本月快速入口
    cal_links = []
    for c in CALIBERS:
        cal_links.append(
            A(
                Div(
                    Div(c, style="font-size:13px;font-weight:600;"),
                    Div(CALIBER_NOTES.get(c, ""), style="font-size:11px;color:var(--text-muted);margin-top:4px;"),
                    Div("查看报表 →", style="font-size:11px;color:var(--primary);margin-top:8px;"),
                    cls="card", style="padding:14px;"
                ),
                href=f"/reports/{period}/{quote(c)}?project_id={pid}",
                style="text-decoration:none;color:inherit;display:block;"
            )
        )

    # 版本列表
    versions = []
    for v in sorted(report_versions_tb(), key=lambda x: (x.period, x.caliber), reverse=True):
        if v.project_id != pid:
            continue
        lock_badge = Span("已锁定", cls="badge badge-green") if v.is_locked else Span("未锁定", cls="badge badge-orange")
        versions.append([
            v.period, v.caliber,
            v.data_hash[:16] + "…" if v.data_hash else "—",
            lock_badge,
            v.locked_at or "—", v.locked_by or "—",
            A("查看", href=f"/reports/{v.period}/{quote(v.caliber)}?project_id={pid}", cls="btn btn-outline btn-sm"),
        ])
    versions_body = data_table(
        ["期间", "口径", "数据指纹", "状态", "锁定时间", "锁定人", ""],
        versions) if versions else empty_state("chart", "该范围暂无已生成报表，点击上方口径卡片生成")

    return page_layout(
        "报表中心", "首页 / 合规管理 / 报表中心", "/reports/center",
        Div(
            Div(
                Span("版本化研发费用报表", style="font-size:15px;font-weight:600;"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(
                        Label("项目", cls="nat-label"),
                        Select(*_project_options(pid), name="project_id", cls="input", style="width:100%;"),
                        cls="nat-field", style="flex:1;"
                    ),
                    Div(
                        Label("月份", cls="nat-label"),
                        Select(*month_options(period), name="period", cls="input", style="width:100%;"),
                        cls="nat-field", style="flex:1;"
                    ),
                    Div(
                        Label("", cls="nat-label"),
                        Button("查询", cls="btn btn-primary", type="submit", style="width:100%;"),
                        cls="nat-field", style="flex:1;"
                    ),
                    style="display:flex;gap:14px;"
                ),
                method="get", action="/reports/center",
                cls="nat-form"
            ),
            cls="card"
        ),
        Div(
            Div(f"{title} · {period} 口径报表", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            Div(*cal_links, style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;"),
            cls="card"
        ),
        Div(
            Div("历史版本", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            versions_body,
            cls="card"
        ),
    )


@ar("/reports/{period}/{caliber}")
def report_detail(period: str, caliber: str, project_id: str = "0"):
    """单月单口径报表"""
    pid = int(project_id or 0)
    if caliber not in CALIBERS:
        return alert_box("未知口径", "danger")
    proj = projects_tb[pid] if pid else None
    title = proj.name if proj else "全部项目"

    rows = _collect(pid, period, caliber)
    total = sum(e.amount for e in rows)
    total_rd = sum(e.amount for e in rows if e.phase in ("研究", "开发"))
    total_expense = sum(e.amount for e in rows if e.capitalize_status == "费用化")

    # 科目汇总
    from collections import defaultdict
    subj_map = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for e in rows:
        key = e.subject_name or "未分类"
        subj_map[key]["amount"] += e.amount
        subj_map[key]["count"] += 1
    subj_rows = [
        [name, f"¥{v['amount']:,.2f}", v["count"],
         f"{v['amount']/total*100:.1f}%" if total else "0.0%"]
        for name, v in sorted(subj_map.items(), key=lambda x: -x[1]["amount"])
    ]

    # 阶段汇总
    phase_map = defaultdict(float)
    for e in rows:
        phase_map[e.phase or "未标注"] += e.amount

    # 版本指纹
    data_hash = _data_hash(pid, period, caliber, rows)
    version = _upsert_version(pid, period, caliber, data_hash)
    locked = bool(version and version.is_locked)

    hash_block = Div(
        Div(
            Span("报表指纹（SHA256）", style="font-size:12px;color:var(--text-muted);"),
            Div(Code(version.data_hash if version else data_hash,
                     style="font-size:11px;word-break:break-all;"),
                style="margin-top:6px;"),
            cls="card"
        ),
        style="flex:1;"
    )

    # 明细
    detail_rows = []
    for e in sorted(rows, key=lambda x: x.expense_date or ""):
        p = projects_tb[e.project_id] if e.project_id else None
        detail_rows.append([
            e.expense_date, p.name if p else "—", e.subject_name or "—",
            e.phase or "—", f"¥{e.amount:,.2f}", e.caliber or "—",
            e.source or "—",
        ])

    lock_btn = ""
    if not locked:
        lock_btn = Form(
            Button("锁定报表（锁定后只读）", cls="btn btn-warning btn-sm", type="submit"),
            method="post", action=f"/reports/{period}/{quote(caliber)}/lock?project_id={pid}",
            style="display:inline-block;margin-left:8px;"
        )

    return page_layout(
        "报表详情", f"首页 / 合规管理 / 报表中心 / {period} {caliber}", "/reports/center",
        Div(
            Div(
                Div(
                    Span(f"{title} · {period} · {caliber}", style="font-size:15px;font-weight:600;"),
                    Div(CALIBER_NOTES.get(caliber, ""), style="font-size:12px;color:var(--text-muted);margin-top:4px;"),
                ),
                Div(
                    A("导出 Excel", href=f"/reports/{period}/{quote(caliber)}/export?project_id={pid}",
                      cls="btn btn-primary btn-sm"),
                    lock_btn,
                    A("返回", href=f"/reports/center?project_id={pid}&period={period}", cls="btn btn-outline btn-sm"),
                    style="display:flex;align-items:center;gap:8px;"
                ),
                style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;"
            ),
            Div(
                Div(stat_block("总金额", f"¥{total:,.2f}", "blue"), style="flex:1;"),
                Div(stat_block("研究+开发阶段", f"¥{total_rd:,.2f}", "green"), style="flex:1;"),
                Div(stat_block("费用化金额", f"¥{total_expense:,.2f}", "purple"), style="flex:1;"),
                Div(stat_block("费用笔数", f"{len(rows)}", "orange"), style="flex:1;"),
                style="display:flex;gap:12px;margin-top:14px;"
            ),
            cls="card"
        ),
        Div(
            Div("科目汇总", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            data_table(["科目", "金额", "笔数", "占比"], subj_rows) if subj_rows else empty_state("coins", "该范围暂无费用数据"),
            cls="card"
        ),
        Div(
            Div("阶段汇总", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            data_table(["阶段", "金额"],
                       [[k, f"¥{v:,.2f}"] for k, v in sorted(phase_map.items(), key=lambda x: -x[1])]) if phase_map else empty_state("chart", "暂无阶段数据"),
            cls="card"
        ),
        Div(
            Div("费用明细", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            data_table(["日期", "项目", "科目", "阶段", "金额", "口径", "来源"], detail_rows) if detail_rows else empty_state("table", "该范围暂无费用明细"),
            cls="card"
        ),
        hash_block,
    )


@ar("/reports/{period}/{caliber}/lock", methods=["POST"])
def report_lock(period: str, caliber: str, project_id: str = "0"):
    """锁定报表：仅未锁定版本可锁定"""
    pid = int(project_id or 0)
    v = _find_version(pid, period, caliber)
    if not v:
        return alert_box("报表版本不存在，请先查看生成", "danger")
    if v.is_locked:
        return alert_box("报表已锁定，无需重复操作", "warning")
    v.is_locked = True
    v.locked_at = _now()
    v.locked_by = "系统管理员"
    report_versions_tb.update(v)
    log_audit("LOCK_REPORT", "ReportVersion", v.id,
              detail=f"锁定报表 {period} {caliber} project={pid}", actor="系统管理员")
    return RedirectResponse(
        url=f"/reports/{period}/{quote(caliber)}?project_id={pid}&msg=locked",
        status_code=303)


@ar("/reports/{period}/{caliber}/export")
def report_export(period: str, caliber: str, project_id: str = "0"):
    """导出 Excel（.xlsx）"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment

    pid = int(project_id or 0)
    proj = projects_tb[pid] if pid else None
    title = proj.name if proj else "全部项目"
    rows = _collect(pid, period, caliber)
    total = sum(e.amount for e in rows)

    from collections import defaultdict
    subj_map = defaultdict(float)
    for e in rows:
        subj_map[e.subject_name or "未分类"] += e.amount

    wb = Workbook()
    ws = wb.active
    ws.title = f"{period}报表"
    ws.append(["研发费用报表", period, caliber, title])
    ws.append(["生成时间", _now()])
    ws.append(["总金额", round(total, 2)])
    ws.append([])
    ws.append(["科目", "金额", "占比"])
    for name, amt in sorted(subj_map.items(), key=lambda x: -x[1]):
        ws.append([name, round(amt, 2), f"{amt/total*100:.1f}%" if total else "0.0%"])
    ws.append([])
    ws.append(["费用明细"])
    ws.append(["日期", "项目", "科目", "阶段", "金额", "口径", "来源", "描述"])
    for e in sorted(rows, key=lambda x: x.expense_date or ""):
        p = projects_tb[e.project_id] if e.project_id else None
        ws.append([e.expense_date, p.name if p else "—", e.subject_name or "—",
                   e.phase or "—", round(e.amount, 2), e.caliber or "—",
                   e.source or "—", e.description or ""])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 16
    ws.column_dimensions["G"].width = 14
    ws.column_dimensions["H"].width = 30

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"研发费用报表_{period}_{caliber}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"}
    )


# ── ⑭ 三类口径并排视图 ──────────────────────────────────────

COMPARE_CALIBERS = ["高企认定", "加计扣除", "会计"]


@ar("/reports/compare")
def report_compare(period: str = "", project_id: str = "0"):
    """三类口径（高企认定/加计扣除/会计）并排对比视图。"""
    from collections import defaultdict

    pid = int(project_id or 0)
    period = period or _month_now()
    proj = projects_tb[pid] if pid else None
    title = proj.name if proj else "全部项目"

    # 各口径聚合
    cal_data = {}
    all_subjects = set()
    for c in COMPARE_CALIBERS:
        rows = _collect(pid, period, c)
        total = sum(e.amount for e in rows)
        total_rd = sum(e.amount for e in rows if e.phase in ("研究", "开发"))
        total_expense = sum(e.amount for e in rows if e.capitalize_status == "费用化")
        subj_map = defaultdict(float)
        for e in rows:
            subj_map[e.subject_name or "未分类"] += e.amount
            all_subjects.add(e.subject_name or "未分类")
        cal_data[c] = {
            "rows": rows, "total": total, "total_rd": total_rd,
            "total_expense": total_expense, "subj": subj_map,
        }

    # 汇总对比表
    summary_rows = [
        [c,
         f"¥{cal_data[c]['total']:,.2f}",
         f"¥{cal_data[c]['total_rd']:,.2f}",
         f"¥{cal_data[c]['total_expense']:,.2f}",
         f"{len(cal_data[c]['rows'])}"]
        for c in COMPARE_CALIBERS
    ]

    # 科目横比表
    subj_rows = []
    for s in sorted(all_subjects):
        row = [s]
        for c in COMPARE_CALIBERS:
            row.append(f"¥{cal_data[c]['subj'].get(s, 0.0):,.2f}")
        subj_rows.append(row)

    # 各口径差异说明
    notes = []
    base_total = cal_data["会计"]["total"]
    for c in COMPARE_CALIBERS:
        if base_total:
            diff = cal_data[c]["total"] - base_total
            notes.append([
                c, f"¥{cal_data[c]['total']:,.2f}",
                f"{diff:+,.2f}",
                f"{diff/base_total*100:+.1f}%",
            ])
        else:
            notes.append([c, "¥0.00", "—", "—"])

    return page_layout(
        "三类口径并排", f"首页 / 合规管理 / 报表中心 / 三类口径对比", "/reports/center",
        Div(
            Div(
                Span("三类口径并排对比", style="font-size:15px;font-weight:600;"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(
                        Label("项目", cls="nat-label"),
                        Select(*_project_options(pid), name="project_id", cls="input", style="width:100%;"),
                        cls="nat-field", style="flex:1;"
                    ),
                    Div(
                        Label("月份", cls="nat-label"),
                        Select(*month_options(period), name="period", cls="input", style="width:100%;"),
                        cls="nat-field", style="flex:1;"
                    ),
                    Div(
                        Label("", cls="nat-label"),
                        Button("查询", cls="btn btn-primary", type="submit", style="width:100%;"),
                        cls="nat-field", style="flex:1;"
                    ),
                    style="display:flex;gap:14px;"
                ),
                method="get", action="/reports/compare",
                cls="nat-form"
            ),
            cls="card"
        ),
        Div(
            Div(f"{title} · {period} 口径差异", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            data_table(["口径", "总金额", "较会计口径差异", "差异比例"], notes)
            if base_total else empty_state("chart", "会计口径暂无数据"),
            cls="card"
        ),
        Div(
            Div("汇总指标对比", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            data_table(["口径", "总金额", "研究+开发阶段", "费用化金额", "笔数"], summary_rows)
            if any(cal_data[c]["rows"] for c in COMPARE_CALIBERS) else empty_state("coins", "该范围暂无费用数据"),
            cls="card"
        ),
        Div(
            Div("科目金额横比", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            data_table(["科目"] + COMPARE_CALIBERS, subj_rows)
            if subj_rows else empty_state("table", "暂无科目数据"),
            cls="card"
        ),
        Div(
            Div("明细并排（各口径同月费用明细）", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            *[
                Div(
                    Div(c, style="font-size:13px;font-weight:600;margin-bottom:8px;"),
                    data_table(
                        ["日期", "项目", "科目", "阶段", "金额", "来源"],
                        [
                            [e.expense_date,
                             (projects_tb[e.project_id].name if e.project_id and projects_tb[e.project_id] else "—"),
                             e.subject_name or "—", e.phase or "—",
                             f"¥{e.amount:,.2f}", e.source or "—"]
                            for e in sorted(cal_data[c]["rows"], key=lambda x: x.expense_date or "")
                        ]
                    ) if cal_data[c]["rows"] else empty_state("table", f"{c} 口径无明细"),
                    cls="card", style="flex:1;min-width:320px;"
                )
                for c in COMPARE_CALIBERS
            ],
            style="display:flex;gap:12px;flex-wrap:wrap;"
        ),
        Div(
            A("← 返回报表中心", href=f"/reports/center?project_id={pid}&period={period}", cls="btn btn-outline btn-sm"),
            style="margin-top:4px;"
        ),
    )
