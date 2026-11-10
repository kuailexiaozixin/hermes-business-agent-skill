"""routes_segregation.py — 研发/非研发边界隔离

M2 受托研发合同登记（我方为受托方，收入属营业收入，隔离不计入研发费用）
M3 研发性质设置（自主研发/委托研发/受托研发）+ 营业成本隔离看板
M6 互派人员识别（同一研发人员跨多项目/研发-非研发混岗，提示工时归集风险）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import datetime, date
from collections import defaultdict
from .db import (
    entrusted_tb, projects_tb, members_tb, personnel_tb, expenses_tb,
    entrusted_isolated_total
)
from .components import (
    project_options,
    stat_block,

    page_layout, data_table, empty_state, alert_box
)

ar = APIRouter()




# ── M2 受托研发合同 ────────────────────────────────────────

@ar("/entrusted")
def entrusted_index():
    """受托研发合同台账（我方为受托方）"""
    rows = []
    total_revenue = 0.0
    for c in entrusted_tb(order_by="sign_date DESC"):
        proj = projects_tb[c.project_id] if c.project_id else None
        total_revenue += c.recognized_revenue
        st_cls = "badge-green" if c.status == "已结题" else "badge-orange"
        rows.append([
            c.contract_no, c.entrustor, proj.name if proj else "—",
            f"¥{c.contract_amount:,.0f}", f"¥{c.recognized_revenue:,.0f}",
            f"¥{c.our_rd_cost:,.0f}",
            Span(c.status, cls=f"badge {st_cls}"),
            A("编辑", href=f"/entrusted/{c.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "受托研发隔离", "首页 / 合规管理 / 受托研发", "/entrusted",
        Div(
            Div(
                Span("受托研发合同（我方为受托方）"),
                A("+ 新增受托合同", href="/entrusted/new", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            Div(
                Div(stat_block("受托合同总额", f"¥{sum(c.contract_amount for c in entrusted_tb()):,.0f}", "blue"), style="flex:1;"),
                Div(stat_block("已确认营业收入", f"¥{total_revenue:,.0f}", "orange"), style="flex:1;"),
                Div(stat_block("隔离（不计入研费用）", f"¥{total_revenue:,.0f}", "red"), style="flex:1;"),
                style="display:flex;gap:16px;margin-bottom:16px;"
            ),
            alert_box(
                "受托研发取得的收入属于「营业收入」，其对应支出若由委托方支付，不应重复计入我方研发"
                "费用加计扣除基数（避免双重归集）。本项目单独建账隔离，营业收入不并入研发费用统计。",
                "info"),
            data_table(
                ["合同编号", "委托方", "关联项目", "合同金额", "已确认收入", "我方研发投入", "状态", "操作"],
                rows) if rows else empty_state("🤝", "暂无受托研发合同"),
            cls="card"
        )
    )




@ar("/entrusted/new")
def entrusted_new():
    return page_layout(
        "新增受托研发合同", "首页 / 合规管理 / 受托研发 / 新增", "/entrusted",
        Div(
            Form(
                Div(
                    Div(Label("合同编号", cls="form-label"), Input(name="contract_no", placeholder="如：ST-2026-001", cls="form-input", required=True), cls="form-group"),
                    Div(Label("委托方（客户）", cls="form-label"), Input(name="entrustor", placeholder="如：某制造企业", cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("关联项目", cls="form-label"), Select(*project_options(), name="project_id", cls="form-select"), cls="form-group"),
                    Div(Label("签约日期", cls="form-label"), Input(name="sign_date", type="date", value=date.today().strftime("%Y-%m-%d"), cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("合同金额（元）", cls="form-label"), Input(name="contract_amount", type="number", placeholder="如：200000", cls="form-input"), cls="form-group"),
                    Div(Label("已确认营业收入（元）", cls="form-label"), Input(name="recognized_revenue", type="number", placeholder="如：100000", cls="form-input"), cls="form-group"),
                    Div(Label("我方实际研发投入（元）", cls="form-label"), Input(name="our_rd_cost", type="number", placeholder="如：0（委托方支付则不填）", cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(Label("说明", cls="form-label"), Textarea(name="note", placeholder="受托研发内容与收入归属说明", cls="form-textarea"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/entrusted", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/entrusted/save"
            ),
            cls="card"
        )
    )


@ar("/entrusted/save", methods=["POST"])
def entrusted_save(contract_no: str, entrustor: str, project_id: str = "", sign_date: str = "",
                   contract_amount: str = "0", recognized_revenue: str = "0",
                   our_rd_cost: str = "0", note: str = ""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entrusted_tb.insert(
        contract_no=contract_no, entrustor=entrustor,
        project_id=int(project_id) if project_id else 0,
        contract_amount=float(contract_amount) if contract_amount else 0.0,
        recognized_revenue=float(recognized_revenue) if recognized_revenue else 0.0,
        our_rd_cost=float(our_rd_cost) if our_rd_cost else 0.0,
        caliber="高企认定", status="进行中", sign_date=sign_date, note=note,
        created_at=now
    )
    return RedirectResponse(url="/entrusted", status_code=303)


@ar("/entrusted/{cid}/edit")
def entrusted_edit(cid: int):
    c = entrusted_tb[cid]
    return page_layout(
        "编辑受托研发合同", "首页 / 合规管理 / 受托研发 / 编辑", "/entrusted",
        Div(
            Form(
                Input(type="hidden", name="id", value=c.id),
                Div(
                    Div(Label("合同编号", cls="form-label"), Input(name="contract_no", value=c.contract_no, cls="form-input", required=True), cls="form-group"),
                    Div(Label("委托方", cls="form-label"), Input(name="entrustor", value=c.entrustor, cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("已确认营业收入（元）", cls="form-label"), Input(name="recognized_revenue", type="number", value=c.recognized_revenue, cls="form-input"), cls="form-group"),
                    Div(Label("我方实际研发投入（元）", cls="form-label"), Input(name="our_rd_cost", type="number", value=c.our_rd_cost, cls="form-input"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Label("状态", cls="form-label"),
                    Select(Option("进行中", value="进行中"), Option("已结题", value="已结题"), name="status", cls="form-select"),
                    cls="form-group"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/entrusted", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/entrusted/update"
            ),
            cls="card"
        )
    )


@ar("/entrusted/update", methods=["POST"])
def entrusted_update(id: int, contract_no: str, entrustor: str,
                     recognized_revenue: str = "0", our_rd_cost: str = "0", status: str = "进行中"):
    c = entrusted_tb[id]
    c.contract_no, c.entrustor = contract_no, entrustor
    c.recognized_revenue = float(recognized_revenue) if recognized_revenue else 0.0
    c.our_rd_cost = float(our_rd_cost) if our_rd_cost else 0.0
    c.status = status
    entrusted_tb.update(c)
    return RedirectResponse(url="/entrusted", status_code=303)


# ── M3 研发性质 + 营业成本隔离看板 ──────────────────────────

@ar("/business-cost")
def business_cost_index():
    """营业成本隔离看板：分项目展示研发性质、受托研发隔离额、生产阶段（非研发）费用。"""
    rows = []
    total_isolated = entrusted_isolated_total()
    total_nonrd = 0.0
    for p in projects_tb(where="status='进行中' OR status='已结题'"):
        proj_exp = [e for e in expenses_tb() if e.project_id == p.id]
        nonrd = sum(e.amount for e in proj_exp if e.capitalize_status == "非研发" or e.phase == "生产")
        total_nonrd += nonrd
        nature_badge = {
            "自主研发": "badge-green", "委托研发": "badge-blue", "受托研发": "badge-orange"
        }.get(p.rd_nature, "badge-gray")
        rows.append([
            A(p.name, href=f"/projects/{p.id}", style="color:var(--primary);text-decoration:none;"),
            Span(p.rd_nature, cls=f"badge {nature_badge}"),
            f"¥{nonrd:,.0f}",
            "计入营业成本（隔离）" if p.rd_nature == "受托研发" else ("生产阶段不计入" if nonrd > 0 else "—"),
        ])

    return page_layout(
        "营业成本隔离看板", "首页 / 合规管理 / 营业成本隔离", "/business-cost",
        Div(
            Div(
                Div(stat_block("受托研发隔离收入", f"¥{total_isolated:,.0f}", "red"), style="flex:1;"),
                Div(stat_block("生产/非研发费用", f"¥{total_nonrd:,.0f}", "orange"), style="flex:1;"),
                style="display:flex;gap:16px;margin-bottom:16px;"
            ),
            alert_box(
                "研发/非研发边界隔离原则：① 受托研发收入计入营业收入，不并入研发费用；"
                "② 项目生产阶段费用及常规化量产支出标记为「非研发」，隔离出研发费用；"
                "③ 混合项目按 rd_split_ratio 折算研发部分。以下为各项目隔离情况概览。",
                "info"
            ),
            data_table(["项目", "研发性质", "生产/非研发费用", "隔离处理"], rows) if rows else empty_state("✓", "暂无项目"),
            cls="card"
        )
    )


@ar("/projects/{pid}/nature/edit")
def project_nature_edit(pid: int):
    """M3：设置项目研发性质（自主研发/委托研发/受托研发）"""
    p = projects_tb[pid]
    return page_layout(
        "设置研发性质", "首页 / 研发项目 / 研发性质", "/projects",
        Div(
            Form(
                Input(type="hidden", name="pid", value=p.id),
                Div(
                    Div(Label("当前项目", cls="form-label"), Input(name="pname", value=f"{p.code} {p.name}", cls="form-input", disabled=True), cls="form-group"),
                    Div(Label("研发性质", cls="form-label"),
                        Select(
                            Option("自主研发", value="自主研发"),
                            Option("委托研发", value="委托研发"),
                            Option("受托研发", value="受托研发"),
                            name="rd_nature", cls="form-select"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("说明", cls="form-label"),
                    Input(name="note", value=p.boundary_desc or "", cls="form-input",
                          placeholder="受托/委托研发的边界说明"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href=f"/projects/{pid}", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/projects/nature/save"
            ),
            cls="card"
        )
    )


@ar("/projects/nature/save", methods=["POST"])
def project_nature_save(pid: int, rd_nature: str = "自主研发", note: str = ""):
    p = projects_tb[int(pid)]
    p.rd_nature = rd_nature
    if note:
        p.boundary_desc = note
    projects_tb.update(p)
    return RedirectResponse(url=f"/projects/{pid}", status_code=303)


# ── M6 互派人员识别 ────────────────────────────────────────

@ar("/shared-personnel")
def shared_personnel_index():
    """M6：识别跨项目/跨研发-非研发的互派人员，提示工时归集风险。"""
    # 人员 → 参与项目（含性质）
    person_projects = defaultdict(list)
    for m in members_tb():
        person_projects[m.person_id].append(m.project_id)

    # 人员 → 工时登记项目
    from .db import work_time_tb
    person_work_projects = defaultdict(set)
    for w in work_time_tb():
        person_work_projects[w.person_id].add(w.project_id)

    rows = []
    for per in personnel_tb():
        proj_ids = set(person_projects.get(per.id, [])) | set(person_work_projects.get(per.id, []))
        proj_objs = [p for i in proj_ids if i and (p := projects_tb.get(i, default=None))]
        natures = set(pr.rd_nature for pr in proj_objs)
        multi = len(proj_ids) > 1
        cross = len(natures) > 1
        if not (multi or cross):
            continue
        risk_tags = []
        if multi:
            risk_tags.append("跨多项目")
        if cross:
            risk_tags.append("研发-受托混岗")
        badge_cls = "badge-red" if cross else "badge-orange"
        rows.append([
            per.name,
            per.title,
            "是" if per.is_rd else "否（非研发）",
            str(len(proj_ids)),
            "、".join(pr.name for pr in proj_objs),
            Span(" + ".join(risk_tags), cls=f"badge {badge_cls}"),
        ])

    return page_layout(
        "互派人员识别", "首页 / 合规管理 / 互派人员", "/shared-personnel",
        Div(
            Div("跨项目 / 研发-非研发混岗人员", cls="card-title"),
            alert_box(
                "同一研发人员若同时服务于多个项目（尤其自主研发与受托研发混岗），其人工费用需按实际"
                "工时在各项目间准确分摊，受托研发部分对应的工时不得计入我方研发费用加计扣除基数。"
                "以下人员存在跨项目或混岗情形，请核实工时分摊口径。",
                "warning"),
            data_table(["姓名", "职务", "是否研发岗", "参与项目数", "参与项目", "风险标记"], rows) if rows else empty_state("✓", "未识别到跨项目/混岗人员"),
            cls="card"
        )
    )
