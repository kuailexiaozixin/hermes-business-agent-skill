"""routes_reporting.py — 外部监管报送（缺口⑮：真实数据导出版）

依据 rd-governor：
- 外部报送场景（高企年报、加计扣除申报、R&D 统计、IPO 申报）为 P2 远期扩展；
- 本模块基于系统真实数据（费用 / 项目 / 人员 / 科目）生成各口径报送导出文件（CSV），
  并记录报送审计留痕（audit_tb, action=EXPORT），形成证据链闭环；
- 对外 API 提交（submit）与外部系统回执对接仍为预留，避免虚假报送承诺。

功能：
- /reporting                         外部报送总览（真实数据概览）
- /reporting/{target}                单类报送页（口径预览 + 导出 + 报送记录）
- /api/reporting/{target}/export     导出报送文件（CSV，GBK+BOM，Excel 可直接打开）
- /api/reporting/{target}/receipt    查询最近报送记录（审计留痕）
"""
from collections import OrderedDict
from datetime import datetime
from urllib.parse import quote

from fasthtml.common import *
from fasthtml.core import APIRouter
from .db import expenses_tb, projects_tb, personnel_tb, subjects_tb, audit_tb
from .components import page_layout, alert_box, data_table, stat_block, empty_state

ar = APIRouter()

REPORTING_TARGETS = [
    ("高企年报", "科技部火炬统计 / 高企年报", "按会计口径归集研发费用，附项目立项与人员清单", "P2"),
    ("加计扣除申报", "企业所得税汇算清缴 A107012", "按加计扣除口径（研发项目辅助账 + 留存备查资料）", "P2"),
    ("R&D 统计", "统计局企业研发活动统计（107-1/107-2）", "按项目-人员-费用三要素填报", "P2"),
    ("IPO 申报", "招股说明书研发投入披露（发行类第9号）", "研发人员认定、费用归集真实性、资本化政策一致性", "P2"),
]

_TARGET_KEY = {"高企年报": "gaoqin", "加计扣除申报": "jjk", "R&D 统计": "rdstat", "IPO 申报": "ipo"}
_TARGETS_MAP = {_TARGET_KEY[k]: (k, desc, scope, pri) for k, desc, scope, pri in REPORTING_TARGETS}

# 科目代码 → 报送列名（对齐 A107012 / 107-1 分项）
_SUBJECT_COLS = [
    ("01", "人员人工费用"),
    ("02", "直接投入费用"),
    ("03", "折旧费用与长期待摊"),
    ("04", "无形资产摊销"),
    ("05", "设计费用"),
    ("06", "装备调试费用与试验"),
    ("07", "委托外部研究费用"),
    ("08", "其他费用"),
]

_SUBJECT_MAP = None


def _subjects():
    """科目 id → Subject"""
    return {s.id: s for s in subjects_tb()}


def _projects():
    """项目 id → Project"""
    return {p.id: p for p in projects_tb()}


def _year_of(d: str) -> str:
    try:
        return str(d)[:4]
    except Exception:
        return "—"


def _agg(caliber_filter: str = ""):
    """按 项目×科目 聚合真实费用（排除生产阶段非研发费用）。

    caliber_filter 非空时仅统计口径包含该值的费用（如"加计扣除"）。
    """
    subj = _subjects()
    agg: "OrderedDict[int, OrderedDict[str, float]]" = OrderedDict()
    for e in expenses_tb():
        if getattr(e, "phase", "") == "生产":
            continue
        if caliber_filter and caliber_filter not in (getattr(e, "caliber", "") or ""):
            continue
        s = subj.get(getattr(e, "subject_id", 0))
        code = s.code if s else "00"
        agg.setdefault(e.project_id, OrderedDict()).setdefault(code, 0.0)
        agg[e.project_id][code] += e.amount or 0.0
    return agg


def _base_rows(agg):
    """项目维度基础行：编码/名称/形式 + 01-08 分项 + 合计"""
    projs = _projects()
    rows = []
    for pid, codes in agg.items():
        p = projs.get(pid)
        row = [
            p.code if p else "",
            p.name if p else f"项目#{pid}",
            p.boundary_type if p else "",
        ]
        for code, _ in _SUBJECT_COLS:
            row.append(round(codes.get(code, 0.0), 2))
        row.append(round(sum(codes.values()), 2))
        rows.append(row)
    return rows


def _limit_other(codes):
    """加计扣除口径：其他费用(08) 不得超过 01-07 合计的 10%（财税[2015]119号）"""
    base = sum(codes.get(c, 0.0) for c, _ in _SUBJECT_COLS[:7])
    other = codes.get("08", 0.0)
    return round(min(other, round(base * 0.10, 2)), 2)


def _reporting_rows(target: str):
    """按报送目标返回 (header, rows, total, extra)"""
    if target == "gaoqin":
        agg = _agg()
        header = ["项目编码", "项目名称", "研发形式"] + [n for _, n in _SUBJECT_COLS] + ["费用合计(元)"]
        rows = _base_rows(agg)
        total = sum(r[-1] for r in rows)
        return header, rows, total, {}
    if target == "jjk":
        agg = _agg(caliber_filter="加计扣除")
        header = ["项目编码", "项目名称", "研发形式"] + [n for _, n in _SUBJECT_COLS] + ["可加计合计(元)"]
        projs = _projects()
        rows = []
        for pid, codes in agg.items():
            p = projs.get(pid)
            other_ok = _limit_other(codes)
            row = [p.code if p else "", p.name if p else f"项目#{pid}", p.boundary_type if p else ""]
            for code, _ in _SUBJECT_COLS:
                row.append(round(codes.get(code, 0.0), 2) if code != "08" else other_ok)
            row.append(round(sum(codes.get(c, 0.0) for c, _ in _SUBJECT_COLS[:7]) + other_ok, 2))
            rows.append(row)
        total = sum(r[-1] for r in rows)
        return header, rows, total, {"限额说明": "其他费用已按可加计研发费用总额 10% 上限截断"}
    if target == "rdstat":
        agg = _agg()
        header = ["项目编码", "项目名称", "研发形式"] + [n for _, n in _SUBJECT_COLS] + ["研究开发费用合计(元)"]
        rows = _base_rows(agg)
        total = sum(r[-1] for r in rows)
        # 107-2 人员表：研发人员档案（含费用归属人员）
        projs = _projects()
        exp_pids = set(getattr(e, "person_id", 0) for e in expenses_tb() if getattr(e, "phase", "") != "生产")
        person_rows = []
        for per in personnel_tb():
            if not getattr(per, "is_rd", True) and per.id not in exp_pids:
                continue
            person_rows.append([
                per.name,
                getattr(per, "person_category", "") or "研发人员",
                getattr(per, "education", "") or "",
                "是" if getattr(per, "is_rd", True) else "否",
                f"{getattr(per, 'hourly_rate', 0.0):.0f}",
            ])
        extra = {
            "人员表": person_rows,
            "人员表头": ["人员姓名", "人员类别", "学历", "是否研发人员", "小时费率(元)"],
        }
        return header, rows, total, extra
    if target == "ipo":
        # 年度 × 科目：研发投入三年一期披露结构
        subj = _subjects()
        by_year = OrderedDict()
        for e in expenses_tb():
            if getattr(e, "phase", "") == "生产":
                continue
            y = _year_of(getattr(e, "expense_date", ""))
            s = subj.get(getattr(e, "subject_id", 0))
            code = s.code if s else "00"
            by_year.setdefault(y, OrderedDict()).setdefault(code, 0.0)
            by_year[y][code] += e.amount or 0.0
        header = ["年度", "研发费用总额(元)", "费用化(元)", "资本化(元)", "资本化比例"]
        rows = []
        for y, codes in by_year.items():
            total_y = round(sum(codes.values()), 2)
            cap = round(sum(codes.get(c, 0.0) for c, _ in _SUBJECT_COLS if c in ("05", "06")), 2)
            exp = round(total_y - cap, 2)
            ratio = f"{cap / total_y * 100:.1f}%" if total_y else "0.0%"
            rows.append([y, total_y, exp, cap, ratio])
        total = sum(r[1] for r in rows)
        extra = {}
        return header, rows, total, extra
    return [], [], 0.0, {}


def _csv_response(fname: str, header, rows):
    lines = [",".join(str(c) for c in header)]
    lines += [",".join(str(c) for c in r) for r in rows]
    data = b"\xef\xbb\xbf" + "\r\n".join(lines).encode("gbk", errors="replace")
    return Response(
        content=data,
        media_type="text/csv; charset=gbk",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


def _audit_export(target: str, name: str, rows, total: float):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    audit_tb.insert(
        ts=now, actor="system", action="EXPORT", entity="reporting",
        entity_id=0,
        detail=f"外部报送导出：{name}（{len(rows)} 行，合计 ¥{total:,.2f}）",
    )


def _recent_exports(target_name: str, limit: int = 5):
    logs = [l for l in audit_tb(where="entity='reporting'") if target_name in (l.detail or "")]
    return logs[::-1][:limit]


@ar("/reporting")
def reporting_index():
    """外部报送总览（真实数据概览）"""
    all_exp = [e for e in expenses_tb() if getattr(e, "phase", "") != "生产"]
    total = sum(e.amount or 0 for e in all_exp)
    proj_cnt = len({e.project_id for e in all_exp})
    rows = []
    for name, desc, scope, pri in REPORTING_TARGETS:
        target_key = _TARGET_KEY[name]
        _, _, t, _ = _reporting_rows(target_key)
        rows.append([
            A(name, href=f"/reporting/{target_key}", style="color:var(--primary);text-decoration:none;"),
            desc, scope,
            f"¥{t:,.0f}",
            A("查看与导出", href=f"/reporting/{target_key}", cls="btn btn-primary btn-sm"),
        ])
    return page_layout(
        "外部监管报送", "首页 / 外部报送", "/reporting",
        alert_box(
            "本模块基于系统真实数据生成高企年报、加计扣除申报、R&D 统计、IPO 申报四类口径的报送导出文件（CSV），"
            "每次导出自动写入审计留痕，形成证据链闭环。对外 API 提交与外部系统回执对接仍为预留。",
            "info"
        ),
        Div(
            Div("数据概览", cls="card-title"),
            Div(
                stat_block("可报送研发费用", f"¥{total:,.0f}", "green"),
                stat_block("研发项目数", str(proj_cnt), "blue"),
                stat_block("报送目标", str(len(REPORTING_TARGETS)), "orange"),
                stat_block("导出记录", str(len(_recent_exports("", limit=1000))), "purple"),
                style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px;"
            ),
            cls="card"
        ),
        Div(
            Div("报送目标与可导出数据", cls="card-title"),
            data_table(["报送目标", "报送场景", "数据口径要求", "当前可导出金额", "操作"], rows),
            cls="card"
        ),
    )


@ar("/reporting/{target}")
def reporting_detail(target: str):
    if target not in _TARGETS_MAP:
        return page_layout(
            "外部报送", "首页 / 外部报送", "/reporting",
            alert_box("未识别的报送目标", "warning"),
            A("← 返回报送总览", href="/reporting", cls="btn btn-outline")
        )
    name, desc, scope, pri = _TARGETS_MAP[target]
    header, rows, total, extra = _reporting_rows(target)

    # 预览：按科目汇总
    subj = _subjects()
    by_code = OrderedDict()
    for r in rows:
        for i, (code, cname) in enumerate(_SUBJECT_COLS):
            by_code.setdefault(code, 0.0)
            by_code[code] += r[3 + i]
    preview = []
    for code, cname in _SUBJECT_COLS:
        amt = by_code.get(code, 0.0)
        pct = f"{amt / total * 100:.1f}%" if total else "0.0%"
        preview.append([code, cname, f"¥{amt:,.2f}", pct])

    recents = _recent_exports(name)
    rec_rows = [[l.ts, l.action, l.detail] for l in recents]

    parts = [
        alert_box(f"{name}：{desc}。数据口径：{scope}。基于系统真实费用数据生成，导出即留痕。", "info"),
        Div(
            Div("数据预览", cls="card-title"),
            Div(
                stat_block("可导出金额", f"¥{total:,.0f}", "green"),
                stat_block("项目数", str(len(rows)), "blue"),
                stat_block("导出次数", str(len(recents)), "orange"),
                style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px;"
            ),
            data_table(["科目代码", "科目名称", "金额(元)", "占比"], preview) if preview else empty_state("📊", "暂无数据"),
            cls="card"
        ),
        Div(
            Div("操作", cls="card-title"),
            Div(
                A("导出报送文件 (CSV)", href=f"/api/reporting/{target}/export", cls="btn btn-success"),
                A("查询报送记录", href=f"/api/reporting/{target}/receipt", cls="btn btn-outline"),
                style="display:flex;gap:10px;"
            ),
            cls="card"
        ),
    ]

    if extra.get("人员表"):
        parts.append(Div(
            Div("107-2 研发人员表（随 R&D 统计导出）", cls="card-title"),
            data_table(extra["人员表头"], extra["人员表"][:50]) if extra["人员表"] else empty_state("👤", "暂无研发人员档案"),
            cls="card"
        ))

    parts.append(Div(
        Div("最近报送记录（审计留痕）", cls="card-title"),
        data_table(["时间", "动作", "摘要"], rec_rows) if rec_rows else empty_state("📄", "暂无报送记录，导出后自动生成"),
        cls="card"
    ))
    parts.append(Div(A("← 返回报送总览", href="/reporting", cls="btn btn-outline"), style="margin-top:16px;"))
    return page_layout(f"外部报送：{name}", "首页 / 外部报送 / 详情", "/reporting", *parts)


@ar("/api/reporting/{target}/export")
def reporting_export(target: str):
    if target not in _TARGETS_MAP:
        return alert_box("未识别的报送目标", "warning")
    name, _, _, _ = _TARGETS_MAP[target]
    header, rows, total, extra = _reporting_rows(target)
    if not rows:
        return page_layout(
            f"外部报送：{name}", "首页 / 外部报送 / 详情", "/reporting",
            alert_box("当前口径下暂无真实费用数据可导出，请先在费用归集 / 工时 / 材料等模块录入数据。", "warning"),
            A("← 返回", href=f"/reporting/{target}", cls="btn btn-outline")
        )
    _audit_export(target, name, rows, total)
    fname = f"{name}_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(fname, header, rows)


@ar("/api/reporting/{target}/receipt")
def reporting_receipt(target: str):
    if target not in _TARGETS_MAP:
        return alert_box("未识别的报送目标", "warning")
    name, _, _, _ = _TARGETS_MAP[target]
    recents = _recent_exports(name)
    rec_rows = [[l.ts, l.detail] for l in recents]
    return page_layout(
        f"报送记录：{name}", "首页 / 外部报送 / 记录", "/reporting",
        Div(
            Div("历史报送记录（审计留痕）", cls="card-title"),
            data_table(["时间", "摘要"], rec_rows) if rec_rows else empty_state("📄", "暂无报送记录"),
            cls="card"
        ),
        Div(A("← 返回", href=f"/reporting/{target}", cls="btn btn-outline"), style="margin-top:16px;")
    )
