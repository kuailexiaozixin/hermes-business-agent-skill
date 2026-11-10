"""routes_patent.py — 专利成果管理（缺口③，M6）

研发费用最终往往要落到"专利、成果"上。本模块：
- 专利/成果台账：录入专利号、名称、类型、申请日、授权日，并关联研发项目
- 研发产出与投入关联：按项目展示专利产出 vs 研发费用投入
- IPO 核查视图：专利数量/授权情况/与研发投入的匹配性
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date
from .db import (
    patent_records_tb, projects_tb, expenses_tb, log_audit,
)
from .components import (
    project_options, page_layout, data_table, empty_state, alert_box, stat_card,
)

ar = APIRouter()

PATENT_TYPES = ["发明", "实用新型", "外观设计", "软著", "其他"]


def _type_badge(t):
    cls = {
        "发明": "badge-green", "实用新型": "badge-blue",
        "外观设计": "badge-orange", "软著": "badge-purple",
    }.get(t, "badge-gray")
    return Span(t or "—", cls=f"badge {cls}")


def _grant_badge(p):
    if p.grant_date:
        return Span(f"已授权 {p.grant_date}", cls="badge badge-green")
    return Span("已申请 · 待授权", cls="badge badge-orange")


@ar("/patents")
def patents_index(project_id: str = "", keyword: str = ""):
    """专利成果台账"""
    rows_all = list(patent_records_tb(order_by="id DESC"))
    if project_id:
        rows_all = [p for p in rows_all if str(p.project_id) == str(project_id)]
    if keyword:
        kw = keyword.strip()
        rows_all = [p for p in rows_all
                    if kw in (p.title or "") or kw in (p.patent_no or "")]

    rows = []
    for p in rows_all:
        proj = projects_tb[p.project_id] if p.project_id else None
        rows.append([
            p.patent_no or "—",
            p.title or "—",
            _type_badge(p.patent_type),
            proj.name if proj else "—",
            p.application_date or "—",
            _grant_badge(p),
            p.relation_note or "—",
            A("编辑", href=f"/patents/{p.id}/edit", cls="btn btn-outline btn-sm"),
            A("删除", href=f"/patents/{p.id}/del", cls="btn btn-outline btn-sm",
              onclick="return confirm('确认删除该专利记录？')"),
        ])

    granted = len([p for p in rows_all if p.grant_date])
    inv = len([p for p in rows_all if p.patent_type == "发明"])
    proj_ids = set(p.project_id for p in rows_all if p.project_id)

    return page_layout(
        "专利成果管理", "首页 / 研发资产 / 专利成果", "/patents",
        Div(
            stat_card("专利/成果总数", str(len(rows_all)), "条", "blue"),
            stat_card("已授权", str(granted), f"占 {granted/max(len(rows_all),1)*100:.0f}%", "green"),
            stat_card("发明专利", str(inv), "高含金量产出", "purple"),
            stat_card("关联项目", str(len(proj_ids)), "个研发项目", "orange"),
            cls="stat-grid"
        ),
        alert_box(
            "研发费用最终往往要落到专利、成果上。专利台账与研发项目关联，可在 IPO 核查视图中"
            "展示「研发投入 → 专利产出」的匹配性，支撑高新技术企业认定与上市审核。",
            "info"
        ),
        Div(
            Div(
                Span("专利/成果台账"),
                Div(
                    A("IPO 核查视图", href="/patents/ipo-check", cls="btn btn-outline btn-sm"),
                    A("+ 新增专利/成果", href="/patents/new", cls="btn btn-primary btn-sm"),
                    style="display:flex;gap:8px;"
                ),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("关联项目", cls="form-label"),
                        Select(*project_options(project_id), name="project_id", cls="form-select"),
                        cls="form-group"),
                    Div(Label("专利号/名称", cls="form-label"),
                        Input(name="keyword", value=keyword, placeholder="模糊查询", cls="form-input"),
                        cls="form-group"),
                    Div(Button("筛选", type="submit", cls="btn btn-primary"), style="align-self:end;"),
                    cls="form-row"
                ),
                method="get", action="/patents"
            ),
            data_table(
                ["专利号", "名称/标题", "类型", "关联项目", "申请日", "授权状态", "与研发投入关联说明", "", ""],
                rows
            ) if rows else empty_state("📜", "暂无专利记录，点击「新增专利/成果」录入"),
            cls="card"
        )
    )


@ar("/patents/new")
def patent_new():
    return page_layout(
        "新增专利/成果", "首页 / 研发资产 / 专利成果 / 新增", "/patents",
        Div(
            Form(
                Div(
                    Div(Label("专利号/登记号", cls="form-label"),
                        Input(name="patent_no", placeholder="如：ZL202510123456.7 / 软著登记号", cls="form-input"),
                        cls="form-group"),
                    Div(Label("名称/标题", cls="form-label"),
                        Input(name="title", placeholder="如：一种基于大模型的智能分析方法", cls="form-input", required=True),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("类型", cls="form-label"),
                        Select(*[Option(t, value=t, selected=(t == "实用新型")) for t in PATENT_TYPES],
                               name="patent_type", cls="form-select"), cls="form-group"),
                    Div(Label("关联项目", cls="form-label"),
                        Select(*project_options("", placeholder="— 请选择关联项目 —"), name="project_id",
                               cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("申请日", cls="form-label"),
                        Input(name="application_date", type="date", cls="form-input"), cls="form-group"),
                    Div(Label("授权日（空=待授权）", cls="form-label"),
                        Input(name="grant_date", type="date", cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Label("与研发投入关联说明", cls="form-label"),
                    Textarea(name="relation_note",
                             placeholder="说明该专利对应的研发项目、关键投入（如：由XX项目研发形成，对应人工费XX万元、直接投入XX万元）",
                             cls="form-textarea"), cls="form-group"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/patents", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/patents/save"
            ),
            cls="card"
        )
    )


@ar("/patents/save", methods=["POST"])
def patent_save(patent_no: str = "", title: str = "", patent_type: str = "实用新型",
                project_id: str = "", application_date: str = "", grant_date: str = "",
                relation_note: str = ""):
    rec = patent_records_tb.insert(
        project_id=int(project_id) if project_id else 0,
        patent_no=patent_no.strip(), title=title.strip(), patent_type=patent_type,
        application_date=application_date, grant_date=grant_date,
        relation_note=relation_note,
        created_at=date.today().strftime("%Y-%m-%d"),
    )
    log_audit("CREATE", "patent_records", rec.id, f"新增专利成果：{title}（{patent_no or '未填专利号'}）")
    return RedirectResponse(url="/patents", status_code=303)


@ar("/patents/{pid}/edit")
def patent_edit(pid: int):
    p = patent_records_tb[pid]
    return page_layout(
        "编辑专利/成果", "首页 / 研发资产 / 专利成果 / 编辑", "/patents",
        Div(
            Form(
                Input(type="hidden", name="id", value=p.id),
                Div(
                    Div(Label("专利号/登记号", cls="form-label"),
                        Input(name="patent_no", value=p.patent_no or "", cls="form-input"),
                        cls="form-group"),
                    Div(Label("名称/标题", cls="form-label"),
                        Input(name="title", value=p.title or "", cls="form-input", required=True),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("类型", cls="form-label"),
                        Select(*[Option(t, value=t, selected=(t == p.patent_type)) for t in PATENT_TYPES],
                               name="patent_type", cls="form-select"), cls="form-group"),
                    Div(Label("关联项目", cls="form-label"),
                        Select(*project_options(p.project_id, placeholder="— 请选择关联项目 —"),
                               name="project_id", cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("申请日", cls="form-label"),
                        Input(name="application_date", type="date", value=p.application_date or "", cls="form-input"),
                        cls="form-group"),
                    Div(Label("授权日（空=待授权）", cls="form-label"),
                        Input(name="grant_date", type="date", value=p.grant_date or "", cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Label("与研发投入关联说明", cls="form-label"),
                    Textarea(name="relation_note", value=p.relation_note or "", cls="form-textarea"),
                    cls="form-group"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/patents", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/patents/update"
            ),
            cls="card"
        )
    )


@ar("/patents/update", methods=["POST"])
def patent_update(id: int, patent_no: str = "", title: str = "", patent_type: str = "实用新型",
                  project_id: str = "", application_date: str = "", grant_date: str = "",
                  relation_note: str = ""):
    p = patent_records_tb[id]
    before = f"{p.title}/{p.patent_no}/{p.grant_date}"
    p.patent_no = patent_no.strip()
    p.title = title.strip()
    p.patent_type = patent_type
    p.project_id = int(project_id) if project_id else 0
    p.application_date = application_date
    p.grant_date = grant_date
    p.relation_note = relation_note
    patent_records_tb.update(p)
    after = f"{p.title}/{p.patent_no}/{p.grant_date}"
    log_audit("UPDATE", "patent_records", p.id, f"更新专利成果：{p.title}",
              before=before, after=after)
    return RedirectResponse(url="/patents", status_code=303)


@ar("/patents/{pid}/del")
def patent_del(pid: int):
    p = patent_records_tb[pid]
    log_audit("DELETE", "patent_records", p.id, f"删除专利成果：{p.title}")
    patent_records_tb.delete(pid)
    return RedirectResponse(url="/patents", status_code=303)


@ar("/patents/ipo-check")
def patents_ipo_check():
    """IPO 核查视图：研发投入 → 专利产出匹配性"""
    all_patents = list(patent_records_tb())
    all_expenses = list(expenses_tb())
    all_projects = list(projects_tb())

    rows = []
    for proj in all_projects:
        pats = [p for p in all_patents if p.project_id == proj.id]
        exps = [e for e in all_expenses if e.project_id == proj.id]
        used = sum(e.amount for e in exps)
        granted = len([p for p in pats if p.grant_date])
        if not pats and used <= 0:
            continue
        pat_per_million = (len(pats) / (used / 1000000)) if used > 0 else 0
        match_flag = "—"
        if used > 0 and not pats:
            match_flag = Span("有投入无产出", cls="badge badge-red")
        elif pats and used <= 0:
            match_flag = Span("有产出无投入", cls="badge badge-red")
        elif used > 0:
            match_flag = Span("匹配正常", cls="badge badge-green")
        rows.append([
            A(proj.name, href=f"/projects/{proj.id}",
              style="color:var(--primary);text-decoration:none;font-weight:500;"),
            str(len(pats)),
            str(granted),
            f"¥{used:,.0f}",
            f"{pat_per_million:.2f} 件/百万元",
            match_flag,
        ])

    total_pat = len(all_patents)
    total_granted = len([p for p in all_patents if p.grant_date])
    total_used = sum(e.amount for e in all_expenses)

    return page_layout(
        "IPO 核查视图", "首页 / 研发资产 / 专利成果 / IPO核查", "/patents",
        Div(
            stat_card("专利/成果总数", str(total_pat), "条", "blue"),
            stat_card("已授权", str(total_granted), f"授权率 {total_granted/max(total_pat,1)*100:.0f}%", "green"),
            stat_card("研发费用投入", f"¥{total_used:,.0f}", "全部项目", "orange"),
            stat_card("投入产出比", f"{total_pat/max(total_used/1000000,0.0001):.2f}", "件/百万元", "purple"),
            cls="stat-grid"
        ),
        alert_box(
            "IPO 审核（发行类第9号）关注研发投入与研发成果的匹配性：持续大额研发投入但长期无专利/成果产出，"
            "可能被质疑研发投入真实性。本视图按项目展示「研发费用投入 vs 专利产出」，供核查准备使用。",
            "info"
        ),
        Div(
            Div(
                Span("项目投入产出匹配表"),
                A("← 返回台账", href="/patents", cls="btn btn-outline btn-sm"),
                cls="card-title"
            ),
            data_table(
                ["项目", "专利数", "已授权", "研发费用投入", "投入产出比", "匹配性"],
                rows
            ) if rows else empty_state("📊", "暂无专利或费用数据"),
            cls="card"
        )
    )
