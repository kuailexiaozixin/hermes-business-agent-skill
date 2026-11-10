"""routes_compliance.py — 合规管理路由

证据链、风险预警、报表中心
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime
import html
from .db import (
    projects_tb, outsourcing_tb, expenses_tb, evidence_tb, risks_tb,
    capitalization_tb, capitalizable_ready, rd_personnel_ratio
)
from .components import (
    stat_block,

    page_layout, status_badge, level_badge, data_table,
    empty_state, alert_box, progress_bar, stat_card
)
from .biz_config import get_rd_settings
from .routes_policy import get_policy_params

ar = APIRouter()


# ════════════════════ 证据链 ══════════════════════

@ar("/evidence")
def evidence(pid: int = 0):
    """证据链管理"""
    if pid == 0:
        # 选择项目
        all_projects = projects_tb()
        project_cards = []
        for p in all_projects:
            ev_count = len(evidence_tb(where=f"project_id={p.id}"))
            project_cards.append(
                A(
                    Div(
                        Span(p.name, style="font-size:15px;font-weight:600;"),
                        Div(f"证据材料：{ev_count} 份", style="font-size:12px;color:var(--text-muted);margin-top:6px;"),
                        cls="card"
                    ),
                    href=f"/evidence?pid={p.id}",
                    style="text-decoration:none;color:inherit;display:block;"
                )
            )
        return page_layout(
            "合规证据链", "首页 / 证据链", "/evidence",
            alert_box("证据链以项目为单位，以流程节点为线索，自动关联并整理研发费用归集所需的全量证据材料，形成可审计、可追溯的电子证据链。", "info"),
            Div(*project_cards, style="display:grid;grid-template-columns:1fr 1fr;gap:16px;") if project_cards else empty_state("📋", "暂无项目"),
        )

    p = projects_tb[pid]
    all_ev = evidence_tb(where=f"project_id={pid}", order_by="upload_date")

    # 按阶段分组
    research_ev = [e for e in all_ev if e.phase == "研究"]
    develop_ev = [e for e in all_ev if e.phase == "开发"]
    produce_ev = [e for e in all_ev if e.phase == "生产"]

    def ev_block(title, badge_cls, evs):
        rows = [[e.ev_type, e.name, e.upload_date, e.description or "—"] for e in evs]
        return Div(
            Div(
                Span(title, cls=f"badge {badge_cls}"),
                f"（{len(evs)} 份）",
                style="font-size:14px;font-weight:600;margin-bottom:12px;"
            ),
            data_table(["证据类型", "证据名称", "上传日期", "说明"], rows) if rows else P("暂无证据", style="color:var(--text-muted);font-size:13px;"),
            cls="card"
        )

    # 完整性检查（P5：分阶段证据清单，对齐 PPTX 证据链要求）
    # 研究阶段：立项/计划/可行性/预研；开发阶段：设计评审/成果/可行性证明；结题：验收报告
    missing = []
    study_req = ["立项决议", "项目计划", "可行性证明"]
    develop_req = ["设计评审", "交付物", "可行性证明"]
    close_req = ["验收报告"]
    # 按项目实际经历的阶段判定需要哪些清单
    phases = set(e.phase for e in all_ev) | set(e.phase for e in all_ev)
    needed = set(study_req)
    if any(e.phase == "开发" for e in all_ev) or any(e.phase == "开发" for e in [e for e in expenses_tb() if e.project_id == p.id]):
        needed |= set(develop_req)
    if any(e.capitalize_status in ("待资本化", "已资本化") for e in expenses_tb() if e.project_id == p.id):
        needed.add("可行性证明")
    # 结题证据：若项目有已资本化或存在验收报告类型则要求
    if any(e.ev_type == "验收报告" for e in all_ev) or any(e.capitalize_status == "已资本化" for e in expenses_tb() if e.project_id == p.id):
        needed |= set(close_req)
    # 费用凭证始终必需
    needed.add("费用凭证")
    for t in sorted(needed):
        if not any(e.ev_type == t for e in all_ev):
            missing.append(t)

    return page_layout(
        f"证据链：{p.name}", "首页 / 证据链 / 详情", "/evidence",
        Div(
            Div(
                Span(p.name, style="font-size:16px;font-weight:600;margin-right:12px;"),
                A("← 返回项目选择", href="/evidence", cls="btn btn-outline btn-sm"),
                A("批量导入", href="/import/evidence", cls="btn btn-outline btn-sm"),
            ),
            cls="card"
        ),
        Div(
            Div("完整性检查", cls="card-title"),
            alert_box(f"证据链完整，已包含所有必需证据类型。" if not missing else f"缺少以下证据类型：{', '.join(missing)}，请补充上传。", "success" if not missing else "warning"),
            cls="card"
        ),
        ev_block("研究阶段证据", "phase-research", research_ev),
        ev_block("开发阶段证据", "phase-develop", develop_ev),
        ev_block("生产阶段证据（如有）", "phase-produce", produce_ev),
        # 新增证据材料（工作流 B：回写证据链写入口）
        Div(
            Div("新增证据材料", cls="card-title"),
            Form(
                NotStr(f'<input type="hidden" name="project_id" value="{pid}">'),
                Div(Label("证据类型", cls="form-label"),
                    Select(
                        Option("立项决议", value="立项决议"),
                        Option("项目计划", value="项目计划"),
                        Option("可行性证明", value="可行性证明"),
                        Option("设计评审", value="设计评审"),
                        Option("交付物", value="交付物"),
                        Option("验收报告", value="验收报告"),
                        Option("费用凭证", value="费用凭证"),
                        Option("合同", value="合同"),
                        Option("发票", value="发票"),
                        Option("领料单", value="领料单"),
                        Option("工时记录", value="工时记录"),
                        Option("其他", value="其他", selected=True),
                        name="ev_type", cls="form-select"),
                    cls="form-group"),
                Div(Label("证据名称", cls="form-label"),
                    Input(name="name", placeholder="如：RD-2026-001 立项决议书", cls="form-input", required=True),
                    cls="form-group"),
                Div(Label("所属阶段", cls="form-label"),
                    Select(
                        Option("研究", value="研究", selected=True),
                        Option("开发", value="开发"),
                        Option("生产", value="生产"),
                        name="phase", cls="form-select"),
                    cls="form-group"),
                Div(Label("说明（可选）", cls="form-label"),
                    Textarea(name="description", placeholder="证据要点说明", cls="form-input", rows=2),
                    cls="form-group"),
                Button("保存证据", type="submit", cls="btn btn-primary"),
                method="post", action="/evidence/create",
            ),
            cls="card"
        ),
        Div(
            A("导出证据链报告（PDF）", href=f"/evidence/{pid}/export", cls="btn btn-primary"),
            style="margin-top:8px;"
        )
    )


@ar("/evidence/create", methods=["POST"])
def evidence_create(project_id: int, ev_type: str = "其他", name: str = "",
                    phase: str = "研究", description: str = ""):
    """新增证据材料（工作流 B：回写证据链写入口）"""
    evidence_tb.insert(
        project_id=int(project_id), node_id=0, ev_type=ev_type or "其他",
        name=name or "未命名证据", phase=phase or "研究",
        upload_date=datetime.now().strftime("%Y-%m-%d"),
        description=description or "",
    )
    return RedirectResponse(url=f"/evidence?pid={project_id}", status_code=303)


@ar("/evidence/{pid}/export")
def evidence_export(pid: int):
    """导出证据链报告（独立可打印 HTML，浏览器可另存为 PDF；零依赖）"""
    p = projects_tb[pid]
    all_ev = evidence_tb(where=f"project_id={pid}", order_by="upload_date")
    proj_expenses = expenses_tb(where=f"project_id={pid}")
    total = sum(e.amount for e in proj_expenses)
    research = sum(e.amount for e in proj_expenses if e.phase == "研究")
    develop = sum(e.amount for e in proj_expenses if e.phase == "开发")
    produce = sum(e.amount for e in proj_expenses if e.phase == "生产")

    # 完整性检查口径（与详情页保持一致）
    needed = {"立项决议", "项目计划", "可行性证明", "费用凭证"}
    if any(e.phase == "开发" for e in proj_expenses):
        needed |= {"设计评审", "交付物"}
    if any(e.capitalize_status in ("待资本化", "已资本化") for e in proj_expenses):
        needed.add("可行性证明")
    if any(e.ev_type == "验收报告" for e in all_ev) or \
       any(e.capitalize_status == "已资本化" for e in proj_expenses):
        needed.add("验收报告")
    missing = [t for t in sorted(needed) if not any(e.ev_type == t for e in all_ev)]

    ev_rows = "".join(
        f"<tr><td>{html.escape(e.ev_type)}</td><td>{html.escape(e.name)}</td>"
        f"<td>{html.escape(e.phase)}</td><td>{html.escape(e.upload_date)}</td>"
        f"<td>{html.escape(e.description or '—')}</td></tr>"
        for e in all_ev
    ) or '<tr><td colspan="5" style="text-align:center;color:#888;">暂无证据</td></tr>'

    completeness_cls = "ok" if not missing else "warn"
    completeness_text = ("✓ 证据链完整，已包含全部必需证据类型。" if not missing
                         else "⚠ 缺少以下证据类型：" + "、".join(missing) + "，建议补充。")
    gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>研发证据链报告：{html.escape(p.name)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei","PingFang SC",sans-serif; color:#1f2933; margin:0; padding:32px 40px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .sub {{ color:#6b7280; font-size:13px; margin-bottom:20px; }}
  .meta {{ display:flex; gap:16px; flex-wrap:wrap; margin:16px 0; }}
  .meta div {{ background:#f5f7fa; border:1px solid #e5e7eb; border-radius:8px; padding:10px 14px; min-width:130px; }}
  .meta .k {{ font-size:12px; color:#6b7280; }}
  .meta .v {{ font-size:18px; font-weight:700; margin-top:4px; }}
  .card {{ border:1px solid #e5e7eb; border-radius:10px; padding:16px 18px; margin:16px 0; }}
  .card h2 {{ font-size:15px; margin:0 0 10px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ border:1px solid #e5e7eb; padding:8px 10px; text-align:left; }}
  th {{ background:#f5f7fa; }}
  .ok {{ color:#16a34a; font-weight:600; }}
  .warn {{ color:#d97706; font-weight:600; }}
  .bar {{ margin-top:16px; }}
  .btn {{ display:inline-block; background:#2563eb; color:#fff; border:none; border-radius:8px; padding:10px 18px; font-size:14px; cursor:pointer; text-decoration:none; margin-right:10px; }}
  @media print {{ body {{ padding:0 8mm; }} .bar {{ display:none; }} .card,table,th,td {{ page-break-inside:avoid; }} }}
</style>
</head>
<body>
  <h1>研发费用证据链报告</h1>
  <div class="sub">项目名称：{html.escape(p.name)}（{html.escape(p.code)}）　|　生成时间：{gen_date}</div>
  <div class="meta">
    <div><div class="k">研发费用总额</div><div class="v">¥{total:,.0f}</div></div>
    <div><div class="k">研究阶段（费用化）</div><div class="v">¥{research:,.0f}</div></div>
    <div><div class="k">开发阶段（待资本化）</div><div class="v">¥{develop:,.0f}</div></div>
    <div><div class="k">生产阶段</div><div class="v">¥{produce:,.0f}</div></div>
    <div><div class="k">证据总数</div><div class="v">{len(all_ev)} 份</div></div>
  </div>
  <div class="card">
    <h2>证据链完整性声明</h2>
    <p class="{completeness_cls}">{completeness_text}</p>
    <p style="color:#6b7280;font-size:13px;">本报告依据《财政部 国家税务总局 科技部关于完善研究开发费用税前加计扣除政策的通知》（财税〔2015〕119号）、《国家税务总局关于研发费用税前加计扣除归集范围有关问题的公告》（国家税务总局公告2017年第40号）等政策自动生成，所有证据均可追溯至对应流程节点与项目。</p>
    <p style="color:#6b7280;font-size:12px;margin-top:8px;">免责声明：本证据链报告由系统自动归集生成，结果仅供参考，不构成审计或法律意见；最终以税务机关、科技主管部门或具备资质的会计师事务所审核认定为准。</p>
  </div>
  <div class="card">
    <h2>证据清单</h2>
    <table>
      <thead><tr><th>证据类型</th><th>证据名称</th><th>所属阶段</th><th>上传日期</th><th>说明</th></tr></thead>
      <tbody>{ev_rows}</tbody>
    </table>
  </div>
  <div class="bar">
    <button class="btn" onclick="window.print()">打印 / 另存为 PDF</button>
    <a class="btn" href="/evidence?pid={pid}">返回证据链</a>
  </div>
</body>
</html>"""
    from starlette.responses import HTMLResponse
    return HTMLResponse(report)


# ══════════════════════ 风险预警 ════════════════════════

@ar("/risks")
def risks(level_filter: str = "", status_filter: str = ""):
    """风险预警列表"""
    all_risks = risks_tb(order_by="-id")

    if level_filter == "高":
        all_risks = [r for r in all_risks if r.level == "高"]
    elif level_filter == "中":
        all_risks = [r for r in all_risks if r.level == "中"]
    elif level_filter == "低":
        all_risks = [r for r in all_risks if r.level == "低"]

    if status_filter == "待处理":
        all_risks = [r for r in all_risks if r.status == "待处理"]
    elif status_filter == "已整改":
        all_risks = [r for r in all_risks if r.status == "已整改"]
    elif status_filter == "已忽略":
        all_risks = [r for r in all_risks if r.status == "已忽略"]

    total_risks = len(risks_tb())
    pending = len([r for r in risks_tb() if r.status == "待处理"])
    high = len([r for r in risks_tb() if r.level == "高" and r.status == "待处理"])

    rows = []
    for r in all_risks:
        proj = projects_tb[r.project_id] if r.project_id else None
        suggestion_preview = r.suggestion[:50] + "..." if len(r.suggestion) > 50 else r.suggestion
        rows.append([
            level_badge(r.level),
            r.risk_type,
            proj.name if proj else "—",
            r.description[:50] + "..." if len(r.description) > 50 else r.description,
            status_badge(r.status),
            Div(
                A("整改", href=f"/risks/{r.id}/resolve", cls="btn btn-success btn-sm") if r.status == "待处理" else "",
                A("忽略", href=f"/risks/{r.id}/ignore", cls="btn btn-outline btn-sm") if r.status == "待处理" else "",
                style="display:flex;gap:6px;"
            ),
        ])

    return page_layout(
        "风险预警", "首页 / 风险预警", "/risks",
        Div(
            Div(
                stat_block("风险总数", str(total_risks), "blue"),
                stat_block("待处理", str(pending), "orange"),
                stat_block("高风险待处理", str(high), "red"),
                stat_block("已闭环", str(total_risks - pending), "green"),
                style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px;"
            )
        ),
        # 筛选标签
        Div(
            A("全部", href="/risks", cls=f"tab {'active' if not level_filter and not status_filter else ''}"),
            A("高风险", href="/risks?level_filter=高", cls=f"tab {'active' if level_filter=='高' else ''}"),
            A("待处理", href="/risks?status_filter=待处理", cls=f"tab {'active' if status_filter=='待处理' else ''}"),
            cls="tabs"
        ),
        Div(
            Div("风险预警列表", cls="card-title"),
            data_table(["等级", "类型", "关联项目", "风险描述", "状态", "操作"], rows) if rows else empty_state("✓", "暂无风险预警"),
            cls="card"
        )
    )




@ar("/risks/{rid}/resolve")
def risk_resolve(rid: int):
    """标记风险已整改"""
    r = risks_tb[rid]
    r.status = "已整改"
    risks_tb.update(r)
    return RedirectResponse(url="/risks", status_code=303)


@ar("/risks/{rid}/ignore")
def risk_ignore(rid: int):
    """忽略风险"""
    r = risks_tb[rid]
    r.status = "已忽略"
    risks_tb.update(r)
    return RedirectResponse(url="/risks", status_code=303)


# ══════════════════════ 报表中心 ════════════════════════

_DISCLAIMER = ("免责声明：本系统依据公开税收政策自动归集与测算，结果仅供参考，不构成税务或法律意见；"
                "最终以税务机关、科技主管部门或具备资质的会计师事务所审核认定为准。")


def _policy_citation(report_type: str):
    """按报表类型返回「政策依据 + 免责声明」区块（rd-governor 红三线：引用须标注依据[文件/文号]）。"""
    cites = {
        "辅助账": ("依据《财政部 国家税务总局 科技部关于完善研究开发费用税前加计扣除政策的通知》"
                   "（财税〔2015〕119号）及《国家税务总局关于研发费用税前加计扣除归集范围有关问题的公告》"
                   "（国家税务总局公告2017年第40号）：企业应按照国家财务会计制度要求对研发支出进行会计处理，"
                   "并设立辅助账归集可加计扣除的研发费用。"),
        "加计扣除": ("依据财税〔2015〕119号、国家税务总局公告2017年第40号：允许加计扣除的研发费用按人员人工等"
                     "六大类归集；其他相关费用不得超过可加计扣除研发费用总额的 10%；委托研发按实际发生额的 80% "
                     "计入（委托境外研发不超过境内符合条件的研发费用的三分之二）；一般企业现行按 100% 比例加计。"),
        "高企认定": ("依据《高新技术企业认定管理办法》（国科发火〔2016〕32号）及《高新技术企业认定管理工作指引》"
                     "（国科发火〔2016〕195号）：近三年研发费用占销售收入比例须达 3%/4%/5%（按收入档），"
                     "高新技术产品（服务）收入占比≥60%，科技人员占比≥10%，境内研发费用占比≥60%。"),
        "投入分析": ("依据《企业会计准则第6号——无形资产》：企业内部研究开发项目支出，区分研究阶段（费用化）"
                     "与开发阶段（符合条件资本化）；本表按阶段列示研发投入。"),
    }
    text = cites.get(report_type, "")
    return [
        alert_box(text, "info"),
        alert_box(_DISCLAIMER, "info"),
    ]


@ar("/reports")
def reports(report_type: str = "辅助账", caliber: str = "高企认定"):
    """报表中心"""
    # 标签切换
    tabs = Div(
        A("研发辅助账", href="/reports?report_type=辅助账", cls=f"tab {'active' if report_type=='辅助账' else ''}"),
        A("加计扣除明细", href="/reports?report_type=加计扣除", cls=f"tab {'active' if report_type=='加计扣除' else ''}"),
        A("高企认定专项", href="/reports?report_type=高企认定", cls=f"tab {'active' if report_type=='高企认定' else ''}"),
        A("研发投入分析", href="/reports?report_type=投入分析", cls=f"tab {'active' if report_type=='投入分析' else ''}"),
        cls="tabs"
    )

    all_expenses = expenses_tb()
    all_projects = projects_tb()

    if report_type == "辅助账":
        return page_layout(
            "报表中心", "首页 / 报表中心", "/reports",
            tabs,
            alert_box("研发辅助账按研究阶段/开发阶段分别列示费用，开发阶段单独列示资本化金额，符合税务要求。", "info"),
            Div(
                Div("研发辅助账", cls="card-title"),
                aux_table(all_expenses, all_projects),
                A("导出 Excel", href="/reports/export?type=辅助账", cls="btn btn-primary btn-sm", style="margin-top:12px;"),
                cls="card"
            ),
            *_policy_citation(report_type)
        )
    elif report_type == "加计扣除":
        dc = deduct_compliance(all_expenses)
        report_add_other_ratio = get_policy_params("加计扣除", "other_ratio_max", 0.10)
        if dc["over_limit"]:
            deduct_alert = alert_box(
                f"⚠ 其他相关费用 ¥{dc['other']:,.0f} 已超出可加计基数（¥{dc['base']:,.0f}）的 {report_add_other_ratio*100:.0f}% 限额 "
                f"（¥{dc['limit']:,.0f}），超出部分 ¥{dc['other'] - dc['limit']:,.0f} 不得加计。",
                "warning")
        else:
            deduct_alert = alert_box(
                f"✓ 其他相关费用 ¥{dc['other']:,.0f} 未超出可加计基数（¥{dc['base']:,.0f}）的 {report_add_other_ratio*100:.0f}% 限额 "
                f"（¥{dc['limit']:,.0f}），可全额计入加计扣除基数。",
                "success")
        entrusted_note = alert_box(
            "委托 / 委外 / 外包研发费用按实际发生额的 80% 计入可加计扣除基数"
            "（依据财税〔2015〕119号、国家税务总局公告2017年第40号）；"
            "委托境外研发费用不超过境内符合条件的研发费用的三分之二。",
            "info")
        return page_layout(
            "报表中心", "首页 / 报表中心", "/reports",
            tabs,
            deduct_alert,
            entrusted_note,
            Div(
                Div("研发费用加计扣除明细表", cls="card-title"),
                deduct_table(all_expenses, all_projects),
                A("导出 Excel", href="/reports/export?type=加计扣除", cls="btn btn-primary btn-sm", style="margin-top:12px;"),
                cls="card"
            ),
            *_policy_citation(report_type)
        )
    elif report_type == "高企认定":
        return page_layout(
            "报表中心", "首页 / 报表中心", "/reports",
            tabs,
            Div(
                Div("高新技术企业认定专项报表", cls="card-title"),
                hitech_table(all_expenses, all_projects),
                A("导出 Excel", href="/reports/export?type=高企认定", cls="btn btn-primary btn-sm", style="margin-top:12px;"),
                cls="card"
            ),
            *_policy_citation(report_type)
        )
    else:  # 投入分析
        return page_layout(
            "报表中心", "首页 / 报表中心", "/reports",
            tabs,
            Div(
                Div("研发投入分析", cls="card-title"),
                Div(*invest_rows(all_projects, all_expenses)),
                cls="card"
            ),
            *_policy_citation(report_type)
        )


def aux_table(expenses, projects):
    """研发辅助账表格"""
    rows = []
    total_research = total_develop = total_cap = 0
    for p in projects:
        proj_exp = [e for e in expenses if e.project_id == p.id]
        research = sum(e.amount for e in proj_exp if e.phase == "研究")
        develop = sum(e.amount for e in proj_exp if e.phase == "开发")
        cap = sum(e.amount for e in proj_exp if e.capitalize_status in ("待资本化", "已资本化"))
        total_research += research
        total_develop += develop
        total_cap += cap
        # P7：混合项目研发分摊比例折算提示（原始归集额保留，另列折算列）
        split_note = f"{int(p.rd_split_ratio*100)}%" if p.boundary_type == "混合" else "—"
        rows.append([
            p.code, p.name, p.boundary_type, split_note,
            f"¥{research:,.0f}", f"¥{develop:,.0f}", f"¥{cap:,.0f}",
            f"¥{research+develop:,.0f}"
        ])
    rows.append([
        "合计", "全部项目", "—", "—",
        f"¥{total_research:,.0f}", f"¥{total_develop:,.0f}", f"¥{total_cap:,.0f}",
        f"¥{total_research+total_develop:,.0f}"
    ])
    return data_table(
        ["项目编码", "项目名称", "边界类型", "研发分摊比例", "研究阶段", "开发阶段", "资本化金额", "合计"],
        rows
    )


_ENTRUSTED_KEYWORDS = ("委托", "委外", "外包")


def _is_entrusted(subject: str) -> bool:
    """判断科目是否为委托/委外/外包研发（须按实际发生额 80% 计入可加计基数）。"""
    return any(k in (subject or "") for k in _ENTRUSTED_KEYWORDS)


def deduct_compliance(expenses):
    """加计扣除合规计算（财税〔2015〕119号 / 税务总局公告2017年第40号）。

    返回 dict：rest/entrusted_raw/entrusted_in/other/base/limit/over_limit/deductible/count。
    - 仅归集口径含「加计扣除」且阶段为 研究/开发 的费用（生产阶段不可加计）；
    - 委托/委外/外包研发按实际发生额 80% 计入（财税口径，境外受 2/3 约束）；
    - 其他相关费用 ≤ 可加计基数(非其他费用部分) × 10%；超出部分不得加计。
    """
    deduc = [e for e in expenses
             if "加计扣除" in (e.caliber or "") and e.phase in ("研究", "开发")]
    rest = 0.0
    entrusted_raw = 0.0
    other = 0.0
    for e in deduc:
        s = e.subject_name or ""
        amt = float(e.amount or 0)
        if _is_entrusted(s):
            entrusted_raw += amt
        elif s == "其他费用":
            other += amt
        else:
            rest += amt
    entrusted_in = round(entrusted_raw * 0.8, 2)
    base = round(rest + entrusted_in, 2)
    limit = round(base * get_policy_params("加计扣除", "other_ratio_max", 0.10), 2)
    over_limit = other > limit + 0.005
    deductible = round(base + min(other, limit), 2)
    return {
        "rest": rest, "entrusted_raw": entrusted_raw, "entrusted_in": entrusted_in,
        "other": other, "base": base, "limit": limit,
        "over_limit": over_limit, "deductible": deductible, "count": len(deduc),
    }


def deduct_table(expenses, projects):
    """加计扣除明细表（财税〔2015〕119号 / 40号公告：委外按80%计入、仅研究/开发阶段）"""
    rows = []
    total = 0
    for p in projects:
        proj_exp = [e for e in expenses if e.project_id == p.id]
        deduc = 0.0
        for e in proj_exp:
            if "加计扣除" in (e.caliber or "") and e.phase in ("研究", "开发"):
                amt = float(e.amount or 0)
                deduc += amt * 0.8 if _is_entrusted(e.subject_name) else amt
        total += deduc
        rows.append([p.code, p.name, f"¥{deduc:,.0f}", f"¥{deduc:,.0f}", "100%"])
    rows.append(["合计", "全部项目", f"¥{total:,.0f}", f"¥{total:,.0f}", "—"])
    return data_table(
        ["项目编码", "项目名称", "归集金额", "加计扣除基数", "扣除比例"],
        rows
    )


def hitech_table(expenses, projects):
    """高企认定专项报表"""
    rows = []
    total = 0
    for p in projects:
        proj_exp = [e for e in expenses if e.project_id == p.id]
        rd = sum(e.amount for e in proj_exp if e.phase in ("研究", "开发"))
        total += rd
        rows.append([p.code, p.name, p.boundary_type, f"¥{rd:,.0f}", f"¥{rd:,.0f}"])
    rows.append(["合计", "全部项目", "—", f"¥{total:,.0f}", f"¥{total:,.0f}"])
    return data_table(
        ["项目编码", "项目名称", "边界类型", "研发费用额", "高企口径归集"],
        rows
    )


def invest_rows(projects, expenses):
    """研发投入分析卡片"""
    cards = []
    for p in projects:
        proj_exp = [e for e in expenses if e.project_id == p.id]
        used = sum(e.amount for e in proj_exp)
        research = sum(e.amount for e in proj_exp if e.phase == "研究")
        develop = sum(e.amount for e in proj_exp if e.phase == "开发")
        pct = (used / p.budget * 100) if p.budget > 0 else 0

        cards.append(
            Div(
                Div(
                    Span(p.name, style="font-size:14px;font-weight:600;"),
                    Span(f"预算执行率 {pct:.1f}%", style="font-size:12px;color:var(--text-muted);"),
                    style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;"
                ),
                progress_bar(pct, "red" if pct > 90 else "green"),
                Div(
                    Div(f"研究阶段：¥{research:,.0f}", style="font-size:12px;color:var(--phase-research);margin-top:10px;"),
                    Div(f"开发阶段：¥{develop:,.0f}", style="font-size:12px;color:var(--phase-develop);margin-top:4px;"),
                    Div(f"归集总额：¥{used:,.0f}", style="font-size:12px;color:var(--text);margin-top:4px;font-weight:500;"),
                ),
                cls="card"
            )
        )
    return cards


import tempfile


def _xlsx_sheet(rows):
    """根据二维数据生成单个 worksheet XML（使用 inlineStr，避免共享字符串表）"""
    body = []
    for r in rows:
        cells = []
        for c in r:
            if c is None:
                c = ""
            # 数值类型判定
            isnum = isinstance(c, (int, float)) and not isinstance(c, bool)
            if isnum:
                cells.append(f'<c r="{_col_letter(len(cells)+1)}{len(body)+1}"><v>{c}</v></c>')
            else:
                txt = str(c).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cells.append(f'<c r="{_col_letter(len(cells)+1)}{len(body)+1}" t="inlineStr"><is><t xml:space="preserve">{txt}</t></is></c>')
        body.append(f'<row r="{len(body)+1}">' + "".join(cells) + '</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData></worksheet>'
    )


def _col_letter(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _build_xlsx(sheets):
    """sheets: [(name, rows), ...] -> xlsx bytes（纯标准库 zipfile 生成，无需 openpyxl）"""
    import zipfile
    from io import BytesIO
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml
        z.writestr("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(len(sheets)))
            + '</Types>')
        z.writestr("_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
        # workbook.xml
        sheets_xml = "".join(
            f'<sheet name="{name}" sheetId="{i+1}" r:id="rId{i+1}"/>'
            for i, (name, _) in enumerate(sheets))
        z.writestr("xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{sheets_xml}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i+1}.xml"/>'
                for i in range(len(sheets)))
            + '</Relationships>')
        for i, (name, rows) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i+1}.xml", _xlsx_sheet(rows))
    return buf.getvalue()


@ar("/reports/export")
def report_export(type: str = "辅助账"):
    """导出真实 .xlsx 报表（纯标准库生成，无需 openpyxl）"""
    projects = projects_tb()
    if type == "辅助账":
        header = ["项目", "科目", "阶段", "资本化状态", "归集口径", "金额", "费用日期"]
        rows = [header]
        for e in expenses_tb():
            proj = projects_tb[e.project_id] if e.project_id else None
            rows.append([proj.name if proj else "—", e.subject_name, e.phase,
                         e.capitalize_status, e.caliber, e.amount, e.expense_date])
        sheets = [("辅助账", rows)]
        fname = "研发费用辅助账.xlsx"
    elif type == "加计扣除":
        # 加计扣除明细表：仅 caliber 含「加计扣除」
        header = ["项目", "科目", "金额", "可加计基数", f"其他费用{get_policy_params('加计扣除', 'other_ratio_max', 0.10)*100:.0f}%上限"]
        rows = [header]
        deduct_rows = [e for e in expenses_tb() if "加计扣除" in e.caliber]
        base = sum(e.amount for e in deduct_rows if e.subject_name != "其他费用")
        limit = round(base * get_policy_params("加计扣除", "other_ratio_max", 0.10), 2)
        for e in deduct_rows:
            rows.append([(projects_tb[e.project_id].name if e.project_id and projects_tb[e.project_id] else "—"),
                         e.subject_name, e.amount, base, limit])
        rows.append(["合计", "", round(sum(e.amount for e in deduct_rows), 2), base, limit])
        sheets = [("加计扣除明细", rows)]
        fname = "加计扣除明细表.xlsx"
    else:  # 高企认定
        header = ["项目", "研发费用额", "年度销售收入", "研发占比", "高企其他费用占比"]
        rows = [header]
        for p in projects:
            proj_exp = [e for e in expenses_tb() if e.project_id == p.id]
            rd = sum(e.amount for e in proj_exp if e.phase in ("研究", "开发"))
            hi_other = sum(e.amount for e in proj_exp if e.subject_name == "其他费用" and "高企认定" in e.caliber)
            hi_base = sum(e.amount for e in proj_exp if "高企认定" in e.caliber) or 1
            rev = p.annual_revenue or 0
            rows.append([p.name, round(rd, 2), round(rev, 2),
                         f"{(rd/rev*100):.1f}%" if rev else "待录入",
                         f"{(hi_other/hi_base*100):.1f}%"])
        sheets = [("高企认定专项", rows)]
        fname = "高企认定专项审计表.xlsx"

    data = _build_xlsx(sheets)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp.write(data)
    tmp.close()
    from starlette.responses import FileResponse
    return FileResponse(
        tmp.name,
        filename=fname,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=None,
    )


# ══════════════════════ 高企认定比例指标（P3）══════════════════════
# 研发人员占比≥10%、研发费用占比(3/4/5%)、高新技术收入≥60%、其他费用≤10%(加计)/≤20%(高企)

# 研发费用加计扣除负面清单行业（财税〔2015〕119号）：下列行业不得享受加计扣除。
_NEGATIVE_LIST = ("烟草", "住宿和餐饮", "批发和零售", "房地产", "租赁和商务服务", "娱乐")


@ar("/metrics")
def metrics():
    """高企认定比例指标看板"""
    # 政策可配置参数（4.8 规则库，未配置回退默认值）
    add_other_ratio = get_policy_params("加计扣除", "other_ratio_max", 0.10)
    hi_personnel_min = get_policy_params("高企认定", "personnel_ratio_min", 0.10)
    negative_list = get_policy_params("加计扣除", "negative_industries", _NEGATIVE_LIST)
    # 企业级汇总（跨项目）
    projects = projects_tb()
    total_rev = sum(p.annual_revenue or 0 for p in projects)
    total_hi = sum(p.hightech_income or 0 for p in projects)
    rd_personnel = rd_personnel_ratio()
    rd_exp_total = sum(e.amount for e in expenses_tb() if e.phase in ("研究", "开发"))
    # 其他费用占比
    other_deduct = sum(e.amount for e in expenses_tb()
                       if e.subject_name == "其他费用" and "加计扣除" in e.caliber)
    deduct_base = sum(e.amount for e in expenses_tb() if "加计扣除" in e.caliber) or 1
    other_hitech = sum(e.amount for e in expenses_tb()
                       if e.subject_name == "其他费用" and "高企认定" in e.caliber)
    hitech_base = sum(e.amount for e in expenses_tb() if "高企认定" in e.caliber) or 1

    # 境内研发费用占比（高企认定：≥60%）。境外研发费用以「委托境外」合同额近似估算。
    overseas_entrusted = sum(o.actual_amount for o in outsourcing_tb() if o.is_overseas)
    domestic_rd_ratio = ((rd_exp_total - overseas_entrusted) / rd_exp_total) if rd_exp_total else None
    industry = ((get_rd_settings().get("enterprise", {}) or {}).get("industry", "") or "")

    def badge(ok):
        if ok is None:
            return status_badge("待录入")
        return status_badge("达标" if ok else "未达标")

    def fmt_ratio(v):
        return f"{v*100:.1f}%" if v is not None else "—"

    cards = [
        stat_card("研发人员占比", fmt_ratio(rd_personnel), "≥10%", "blue"),
        stat_card("研发费用占比", fmt_ratio(rd_exp_total / total_rev if total_rev else None),
                 "3%/4%/5%", "green") if total_rev else stat_card("研发费用占比", "—", "需录入收入", "gray"),
        stat_card("高新技术收入占比", fmt_ratio(total_hi / total_rev if total_rev else None),
                 "≥60%", "purple") if total_rev else stat_card("高新技术收入占比", "—", "需录入收入", "gray"),
        stat_card("其他费用占比(加计)", fmt_ratio(other_deduct / deduct_base), f"≤{add_other_ratio*100:.0f}%", "orange"),
        stat_card("其他费用占比(高企)", fmt_ratio(other_hitech / hitech_base), "≤20%", "orange"),
        stat_card("境内研发费用占比", fmt_ratio(domestic_rd_ratio), "≥60%", "teal")
        if domestic_rd_ratio is not None else stat_card("境内研发费用占比", "—", "未录入境外委托", "gray"),
    ]
    if rd_personnel is not None and rd_personnel < hi_personnel_min:
        _ensure_risk("研发人员占比不足10%", "高企认定", "中")
    if total_rev and rd_exp_total / total_rev < 0.03:
        _ensure_risk("研发费用占销售收入比例低于3%", "高企认定", "中")
    if total_rev and total_hi / total_rev < 0.60:
        _ensure_risk("高新技术产品（服务）收入占比低于60%", "高企认定", "高")
    if other_deduct / deduct_base > add_other_ratio:
        _ensure_risk("其他相关费用占可加计扣除总额比例超过10%", "加计扣除", "高")
    if domestic_rd_ratio is not None and domestic_rd_ratio < 0.60:
        _ensure_risk("境内研发费用占全部研发费用比例低于60%", "高企认定", "高")
    # 加计扣除负面清单行业提示（财税〔2015〕119号）
    negative_alert = None
    if industry and any(k in industry for k in negative_list):
        _ensure_risk(f"企业所属行业「{industry}」属于研发费用加计扣除负面清单行业", "加计扣除", "高")
        negative_alert = alert_box(
            f"⚠ 企业所属行业「{industry}」属于财税〔2015〕119号规定的负面清单行业"
            f"（如烟草制造业、住宿和餐饮业、批发和零售业、房地产业、租赁和商务服务业、娱乐业等），不得享受研发费用加计扣除政策。",
            "warning")

    page_children = [
        alert_box("以下指标依据《高新技术企业认定管理办法》测算。研发人员占比、其他费用占比由系统数据直接计算；研发费用占比、高新技术收入占比需在企业档案中录入年度销售收入与高新技术收入后测算。", "info"),
    ]
    if negative_alert:
        page_children.append(negative_alert)
    page_children += [
        Div(*cards, style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;"),
        Div(
            Div("指标明细", cls="card-title"),
            data_table(["指标", "当前值", "达标阈值", "状态"], [
                ["研发人员占比", fmt_ratio(rd_personnel), "≥10%", badge(rd_personnel is not None and rd_personnel >= hi_personnel_min)],
                ["研发费用占销售收入比", fmt_ratio(rd_exp_total / total_rev if total_rev else None), "3%/4%/5%", badge(total_rev and rd_exp_total/total_rev >= 0.03)],
                ["高新技术产品（服务）收入占比", fmt_ratio(total_hi / total_rev if total_rev else None), "≥60%", badge(total_rev and total_hi/total_rev >= 0.60)],
                ["境内研发费用占全部研发费用比", fmt_ratio(domestic_rd_ratio), "≥60%", badge(domestic_rd_ratio is not None and domestic_rd_ratio >= 0.60)],
                ["其他费用占比（加计扣除）", fmt_ratio(other_deduct / deduct_base), f"≤{add_other_ratio*100:.0f}%", badge(other_deduct/deduct_base <= add_other_ratio)],
                ["其他费用占比（高企认定）", fmt_ratio(other_hitech / hitech_base), "≤20%", badge(other_hitech/hitech_base <= 0.20)],
            ]),
            cls="card"
        ),
    ]
    return page_layout("高企认定比例指标", "首页 / 合规管理 / 比例指标", "/metrics", *page_children)


def _ensure_risk(title, category, level):
    """去重写入风险（同一描述不存在则插入）"""
    exists = [r for r in risks_tb() if r.description == title]
    if not exists:
        risks_tb.insert(project_id=0, level=level, risk_type=category,
                        description=title, status="待处理",
                        suggestion="依据高企认定比例指标自动识别，请核查。",
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"))

CAP_CONDITIONS = [
    ("cond_tech", "①技术可行：完成该无形资产以使其能够使用或出售在技术上具有可行性"),
    ("cond_intent", "②意图完成：具有完成该无形资产并使用或出售的意图"),
    ("cond_usable", "③能够使用或出售：无形资产能够使用或出售"),
    ("cond_benefit", "④经济利益：运用该无形资产生产的产品存在市场或无形资产自身存在市场；"),
    ("cond_measure", "⑤可靠计量：归属于该无形资产开发阶段的支出能够可靠计量"),
]


@ar("/capitalization")
def capitalization(pid: int = 0):
    """资本化条件审批列表（按项目聚合「待资本化」费用）"""
    pending = [e for e in expenses_tb() if e.capitalize_status == "待资本化"]
    rows = []
    for e in pending:
        proj = projects_tb[e.project_id] if e.project_id else None
        passed, _ = capitalizable_ready(e.id)
        # 找关联的可行性证明证据（本项目研究阶段交付物/可行性报告）
        feasi = [ev for ev in evidence_tb(where=f"project_id={e.project_id}")
                 if ev.ev_type in ("交付物", "项目计划") and "可行性" in (ev.name or "")]
        rows.append([
            proj.name if proj else "—",
            e.subject_name,
            f"¥{e.amount:,.0f}",
            e.expense_date,
            status_badge("已通过" if passed else "待审批"),
            Div(
                A("审批", href=f"/capitalization/{e.id}/review", cls="btn btn-primary btn-sm"),
                style="display:flex;gap:6px;",
            ),
        ])
    return page_layout(
        "资本化条件审批", "首页 / 合规管理 / 资本化审批", "/capitalization",
        alert_box("开发阶段费用资本化须满足 5 项条件（财税[2015]119号、企业会计准则）：技术可行、有意图完成、能够使用/出售、带来经济利益、支出可计量，且须关联可行性证明证据。未通过审批的费用维持「待资本化」，不得转为「已资本化」。", "info"),
        Div(
            Div("待资本化费用审批清单", cls="card-title"),
            data_table(["关联项目", "费用科目", "金额", "费用日期", "审批状态", "操作"], rows) if rows else empty_state("✓", "暂无待资本化费用"),
            cls="card"
        )
    )


@ar("/capitalization/{eid}/review")
def capitalization_review(eid: int):
    """资本化 5 条件审批表单"""
    e = expenses_tb[eid]
    proj = projects_tb[e.project_id] if e.project_id else None
    feasi_options = [ev for ev in evidence_tb(where=f"project_id={e.project_id}")
                     if ev.ev_type in ("交付物", "项目计划")]
    options = "".join(
        f'<option value="{ev.id}">{ev.ev_type}：{ev.name}</option>' for ev in feasi_options)
    cond_rows = [
        Div(
            Label(Input(type="checkbox", name=key, value="1"),
                  style="margin-right:8px;"),
            Span(desc),
            cls="form-group", style="display:flex;align-items:flex-start;gap:8px;"
        ) for key, desc in CAP_CONDITIONS
    ]
    return page_layout(
        "资本化条件审批", "首页 / 合规管理 / 资本化审批 / 审批", "/capitalization",
        Div(
            Div("审批对象", cls="card-title"),
            data_table(["项目", "科目", "金额", "费用日期"],
                       [[proj.name if proj else "—", e.subject_name,
                         f"¥{e.amount:,.0f}", e.expense_date]]),
            cls="card"
        ),
        Div(
            Div("资本化 5 条件（全部勾选方可资本化）", cls="card-title"),
            *cond_rows,
            cls="card"
        ),
        Form(
            NotStr(f'<input type="hidden" name="eid" value="{eid}">'),
            Div(Label("关联可行性证明证据", cls="form-label"),
                Select(NotStr(options), name="feasibility_evidence_id", cls="form-select"),
                cls="form-group") if options else
                Div(alert_box("本项目暂无「交付物/项目计划」类证据，请先在证据链上传可行性证明。", "warning"), cls="form-group"),
            Div(Label("审批人", cls="form-label"),
                Input(name="reviewer", placeholder="如：技术总监", cls="form-input"),
                cls="form-group"),
            Div(Label("审批结论", cls="form-label"),
                Select(
                    Option("通过（转为已资本化）", value="通过", selected=True),
                    Option("驳回（维持待资本化）", value="驳回"),
                    name="decision", cls="form-select"),
                cls="form-group"),
            Button("提交审批", type="submit", cls="btn btn-primary"),
            method="post", action="/capitalization/review/save",
        ),
        Div(A("← 返回审批清单", href="/capitalization", cls="btn btn-outline"), style="margin-top:12px;")
    )


@ar("/capitalization/review/save", methods=["POST"])
def capitalization_review_save(eid: int, cond_tech: int = 0, cond_intent: int = 0,
                                cond_usable: int = 0, cond_benefit: int = 0,
                                cond_measure: int = 0, feasibility_evidence_id: int = 0,
                                reviewer: str = "", decision: str = "通过"):
    """提交资本化审批：5 条件全勾选 + 关联可行性证明 → 通过并转「已资本化」"""
    e = expenses_tb[eid]
    all_met = all(int(x) for x in (cond_tech, cond_intent, cond_usable, cond_benefit, cond_measure))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if decision == "通过" and all_met and feasibility_evidence_id:
        status = "通过"
        e.capitalize_status = "已资本化"
        expenses_tb.update(e)
    else:
        status = "驳回"
        if decision == "通过" and not (all_met and feasibility_evidence_id):
            status = "驳回"
    capitalization_tb.insert(
        project_id=e.project_id, expense_id=e.id,
        cond_tech=int(cond_tech), cond_intent=int(cond_intent),
        cond_usable=int(cond_usable), cond_benefit=int(cond_benefit),
        cond_measure=int(cond_measure),
        feasibility_evidence_id=int(feasibility_evidence_id),
        reviewer=reviewer, decided_at=now, status=status, note=""
    )
    return RedirectResponse(url="/capitalization", status_code=303)

