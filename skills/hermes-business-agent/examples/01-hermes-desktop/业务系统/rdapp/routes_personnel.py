"""routes_personnel.py — 研发人员认定台账与合规体检

依据 rd-governor：
- 人员管理10章：研发人员范围界定、三类人员结构、用工方式、社保个税匹配
- 指令17：研发人员认定与变更流程（全过程留痕）
- 指令19：研发人员绩效考核制度衔接
- AL-12 人员台账模板
- 《监管规则适用指引——发行类第9号：研发人员及研发投入》
- 高企认定管理办法：科技人员当年累计实际工作时间须满 183 天

功能：
- /rd-personnel            研发人员认定台账（AL-12）
- /rd-personnel/new|save   新增研发人员（带完整认定要素）
- /rd-personnel/{pid}/edit 编辑
- /rd-personnel/certify    认定 / 变更 / 停用（写变更记录 + 审计日志）
- /rd-personnel/check      人员合规体检（183天 / 社保 / 结构 / 认定状态）
- /rd-personnel/changes    认定与变更记录台账
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from datetime import date
from .db import (
    personnel_tb, orgs_tb, work_time_tb, labor_cost_tb, personnel_change_tb,
    attendance_records_tb, salary_records_tb,
    log_audit, PERSON_CATEGORIES,
    EMPLOYMENT_TYPES, CERT_STATUSES, HIGHTECH_MIN_WORK_DAYS,
    check_personnel_compliance,
    personnel_structure, record_personnel_change, _safe,
)
from .components import (
    page_layout, data_table, empty_state, alert_box, stat_card
)
from .routes_datacenter import log_data_change

ar = APIRouter()


# ── 辅助 ─────────────────────────────────────────────────

def _opt(values, selected=""):
    return [Option(v, value=v, selected=(v == selected)) for v in values]


def _org_options(selected=""):
    opts = [Option("— 不指定 —", value="0")]
    for o in orgs_tb():
        opts.append(Option(o.name, value=o.id, selected=str(o.id) == str(selected)))
    return opts


def _cert_badge(status):
    cls = {"已认定": "badge-green", "待认定": "badge-orange", "已停用": "badge-gray"}.get(status, "badge-gray")
    return Span(status or "待认定", cls=f"badge {cls}")


def _days_badge(days):
    d = int(days or 0)
    if d <= 0:
        return Span("未登记", cls="badge badge-gray")
    if d < HIGHTECH_MIN_WORK_DAYS:
        return Span(f"{d} 天 · 不足183", cls="badge badge-red")
    return Span(f"{d} 天 · 达标", cls="badge badge-green")


def _level_badge(level):
    cls = {"高": "badge-red", "中": "badge-orange", "低": "badge-gray"}.get(level, "badge-gray")
    return Span(level, cls=f"badge {cls}")


# ── 研发人员认定台账 ───────────────────────────────────────

@ar("/rd-personnel")
def rd_personnel_index(category: str = "", cert: str = "", keyword: str = ""):
    """研发人员认定台账（AL-12）"""
    persons = [p for p in personnel_tb() if p.is_rd]

    if category:
        persons = [p for p in persons if (_safe(p, "person_category", "") or "") == category]
    if cert:
        persons = [p for p in persons if (_safe(p, "certification_status", "待认定") or "待认定") == cert]
    if keyword:
        kw = keyword.strip()
        persons = [p for p in persons if kw in (p.name or "") or kw in (p.title or "")]

    rows = []
    for p in persons:
        org = None
        try:
            org = orgs_tb[p.org_id] if p.org_id else None
        except Exception:
            org = None
        rows.append([
            p.name,
            _safe(p, "person_category", "") or "—",
            p.title or "—",
            _safe(p, "education", "") or "—",
            _safe(p, "employment_type", "在职") or "在职",
            org.name if org else "—",
            _days_badge(_safe(p, "annual_rd_days", 0)),
            _cert_badge(_safe(p, "certification_status", "待认定")),
            A("编辑", href=f"/rd-personnel/{p.id}/edit", cls="btn btn-outline btn-sm"),
            A("认定", href=f"/rd-personnel/{p.id}/certify", cls="btn btn-primary btn-sm"),
        ])

    stat, others, total = personnel_structure()
    certified = len([p for p in personnel_tb()
                     if p.is_rd and (_safe(p, "certification_status", "") == "已认定")])
    qualified = len([p for p in personnel_tb()
                     if p.is_rd and int(_safe(p, "annual_rd_days", 0) or 0) >= HIGHTECH_MIN_WORK_DAYS])

    return page_layout(
        "研发人员认定台账", "首页 / 研发人员 / 认定台账", "/rd-personnel",
        Div(
            stat_card("研发人员总数", str(total), "人", "users"),
            stat_card("已完成认定", str(certified), f"占 {certified/max(total,1)*100:.0f}%", "check"),
            stat_card("满183天人数", str(qualified), "高企认定口径", "gauge"),
            stat_card("未分类人员", str(others), "需划分三类", "alert"),
            cls="stat-grid"
        ),
        alert_box(
            f"研发人员认定台账对应 rd-governor「AL-12 人员台账」。三类人员结构：研究人员 {stat['研究人员']} 人 / "
            f"技术人员 {stat['技术人员']} 人 / 辅助人员 {stat['辅助人员']} 人。"
            f"高新技术企业认定要求科技人员当年累计实际工作时间满 {HIGHTECH_MIN_WORK_DAYS} 天，"
            "不足者不得计入科技人员数量；IPO 审核（发行类第9号）还会核查社保、个税缴纳单位与研发主体是否一致。",
            "info"
        ),
        Div(
            Div(
                Span("研发人员名册"),
                Div(
                    A("合规体检", href="/rd-personnel/check", cls="btn btn-outline btn-sm"),
                    A("变更记录", href="/rd-personnel/changes", cls="btn btn-outline btn-sm"),
                    A("+ 新增人员", href="/rd-personnel/new", cls="btn btn-primary btn-sm"),
                    A("批量导入", href="/import/personnel", cls="btn btn-outline btn-sm"),
                    style="display:flex;gap:8px;"
                ),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("人员类别", cls="form-label"),
                        Select(Option("全部", value=""), *_opt(PERSON_CATEGORIES, category),
                               name="category", cls="form-select"), cls="form-group"),
                    Div(Label("认定状态", cls="form-label"),
                        Select(Option("全部", value=""), *_opt(CERT_STATUSES, cert),
                               name="cert", cls="form-select"), cls="form-group"),
                    Div(Label("姓名/职务", cls="form-label"),
                        Input(name="keyword", value=keyword, placeholder="模糊查询", cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(Button("筛选", type="submit", cls="btn btn-primary"),
                    A("重置", href="/rd-personnel", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"),
                method="get", action="/rd-personnel"
            ),
            data_table(
                ["姓名", "类别", "职务", "学历", "用工方式", "所属部门", "当年工作天数", "认定状态", "", ""],
                rows
            ) if rows else empty_state("👤", "暂无符合条件的研发人员"),
            cls="card"
        )
    )


@ar("/rd-personnel/new")
def rd_personnel_new():
    """新增研发人员"""
    return page_layout(
        "新增研发人员", "首页 / 研发人员 / 认定台账 / 新增", "/rd-personnel",
        Div(
            alert_box(
                "研发人员范围：直接从事研发活动的研究人员、技术人员、辅助人员。"
                "企业行政、后勤、销售等人员不属于研发人员；同时从事非研发活动的，"
                "须按实际工时占比拆分，不得全额计入。",
                "info"
            ),
            Form(
                Div(
                    Div(Label("姓名", cls="form-label"),
                        Input(name="name", cls="form-input", required=True), cls="form-group"),
                    Div(Label("人员类别", cls="form-label"),
                        Select(*_opt(PERSON_CATEGORIES, "研究人员"), name="person_category",
                               cls="form-select"), cls="form-group"),
                    Div(Label("职务/岗位", cls="form-label"),
                        Input(name="title", placeholder="如：算法工程师", cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("学历", cls="form-label"),
                        Select(*_opt(["博士", "硕士", "本科", "大专", "其他"], "本科"),
                               name="education", cls="form-select"), cls="form-group"),
                    Div(Label("专业", cls="form-label"),
                        Input(name="major", placeholder="如：计算机科学与技术", cls="form-input"), cls="form-group"),
                    Div(Label("用工方式", cls="form-label"),
                        Select(*_opt(EMPLOYMENT_TYPES, "在职"), name="employment_type",
                               cls="form-select"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("所属部门", cls="form-label"),
                        Select(*_org_options(), name="org_id", cls="form-select"), cls="form-group"),
                    Div(Label("入职日期", cls="form-label"),
                        Input(name="hire_date", type="date", cls="form-input"), cls="form-group"),
                    Div(Label("当年累计研发工作天数", cls="form-label"),
                        Input(name="annual_rd_days", type="number", min="0", max="366", value="0",
                              cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("社保缴纳单位", cls="form-label"),
                        Input(name="social_insurance_unit", placeholder="须与研发活动主体一致",
                              cls="form-input"), cls="form-group"),
                    Div(Label("证件号（选填）", cls="form-label"),
                        Input(name="id_number", placeholder="用于社保/个税比对", cls="form-input"),
                        cls="form-group"),
                    Div(Label("小时成本（元/时）", cls="form-label"),
                        Input(name="hourly_rate", type="number", step="0.01", value="0",
                              cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/rd-personnel", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/rd-personnel/save"
            ),
            cls="card"
        )
    )


@ar("/rd-personnel/save", methods=["POST"])
def rd_personnel_save(name: str, person_category: str = "研究人员", title: str = "",
                      education: str = "", major: str = "", employment_type: str = "在职",
                      org_id: str = "0", hire_date: str = "", annual_rd_days: str = "0",
                      social_insurance_unit: str = "", id_number: str = "",
                      hourly_rate: str = "0"):
    """保存新增研发人员"""
    try:
        days = int(annual_rd_days or 0)
    except ValueError:
        days = 0
    try:
        rate = float(hourly_rate or 0)
    except ValueError:
        rate = 0.0

    rec = personnel_tb.insert(
        name=name.strip(), org_id=int(org_id or 0), title=title, is_rd=True,
        hourly_rate=rate, person_category=person_category, education=education,
        major=major, employment_type=employment_type, id_number=id_number,
        hire_date=hire_date, leave_date="", annual_rd_days=days,
        social_insurance_unit=social_insurance_unit,
        certification_status="待认定", certification_date=""
    )
    log_audit("CREATE", "personnel", rec.id, f"新增研发人员：{name}（{person_category}）")
    log_data_change("personnel", getattr(rec, "id", 0), "name",
                    old_val="", new_val=f"{name}（{person_category}）{title}",
                    operator="system")
    return RedirectResponse(url="/rd-personnel", status_code=303)


@ar("/rd-personnel/{pid}/edit")
def rd_personnel_edit(pid: int):
    """编辑研发人员"""
    p = personnel_tb[pid]
    return page_layout(
        "编辑研发人员", "首页 / 研发人员 / 认定台账 / 编辑", "/rd-personnel",
        Div(
            Form(
                Input(type="hidden", name="id", value=p.id),
                Div(
                    Div(Label("姓名", cls="form-label"),
                        Input(name="name", value=p.name, cls="form-input", required=True), cls="form-group"),
                    Div(Label("人员类别", cls="form-label"),
                        Select(*_opt(PERSON_CATEGORIES, _safe(p, "person_category", "研究人员")),
                               name="person_category", cls="form-select"), cls="form-group"),
                    Div(Label("职务/岗位", cls="form-label"),
                        Input(name="title", value=p.title or "", cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("学历", cls="form-label"),
                        Select(*_opt(["博士", "硕士", "本科", "大专", "其他"],
                                     _safe(p, "education", "本科")), name="education",
                               cls="form-select"), cls="form-group"),
                    Div(Label("专业", cls="form-label"),
                        Input(name="major", value=_safe(p, "major", ""), cls="form-input"), cls="form-group"),
                    Div(Label("用工方式", cls="form-label"),
                        Select(*_opt(EMPLOYMENT_TYPES, _safe(p, "employment_type", "在职")),
                               name="employment_type", cls="form-select"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("所属部门", cls="form-label"),
                        Select(*_org_options(p.org_id), name="org_id", cls="form-select"), cls="form-group"),
                    Div(Label("入职日期", cls="form-label"),
                        Input(name="hire_date", type="date", value=_safe(p, "hire_date", ""),
                              cls="form-input"), cls="form-group"),
                    Div(Label("离职日期（空=在职）", cls="form-label"),
                        Input(name="leave_date", type="date", value=_safe(p, "leave_date", ""),
                              cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("当年累计研发工作天数", cls="form-label"),
                        Input(name="annual_rd_days", type="number", min="0", max="366",
                              value=_safe(p, "annual_rd_days", 0), cls="form-input"), cls="form-group"),
                    Div(Label("社保缴纳单位", cls="form-label"),
                        Input(name="social_insurance_unit",
                              value=_safe(p, "social_insurance_unit", ""), cls="form-input"),
                        cls="form-group"),
                    Div(Label("小时成本（元/时）", cls="form-label"),
                        Input(name="hourly_rate", type="number", step="0.01",
                              value=p.hourly_rate, cls="form-input"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/rd-personnel", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/rd-personnel/update"
            ),
            cls="card"
        )
    )


@ar("/rd-personnel/update", methods=["POST"])
def rd_personnel_update(id: int, name: str, person_category: str = "研究人员",
                        title: str = "", education: str = "", major: str = "",
                        employment_type: str = "在职", org_id: str = "0",
                        hire_date: str = "", leave_date: str = "",
                        annual_rd_days: str = "0", social_insurance_unit: str = "",
                        hourly_rate: str = "0"):
    """更新研发人员"""
    p = personnel_tb[id]
    before = f"{_safe(p,'person_category','')}/{_safe(p,'annual_rd_days',0)}天/{_safe(p,'employment_type','')}"

    p.name = name.strip()
    p.person_category = person_category
    p.title = title
    p.education = education
    p.major = major
    p.employment_type = employment_type
    p.org_id = int(org_id or 0)
    p.hire_date = hire_date
    p.leave_date = leave_date
    try:
        p.annual_rd_days = int(annual_rd_days or 0)
    except ValueError:
        p.annual_rd_days = 0
    p.social_insurance_unit = social_insurance_unit
    try:
        p.hourly_rate = float(hourly_rate or 0)
    except ValueError:
        p.hourly_rate = 0.0
    personnel_tb.update(p)

    after = f"{person_category}/{p.annual_rd_days}天/{employment_type}"
    if before != after:
        record_personnel_change(p.id, "变更", before, after, "台账编辑", "系统")
    log_audit("UPDATE", "personnel", p.id, f"更新研发人员：{p.name}", before=before, after=after)
    return RedirectResponse(url="/rd-personnel", status_code=303)


# ── 认定 / 变更 / 停用（指令17）─────────────────────────────

@ar("/rd-personnel/{pid}/certify")
def rd_personnel_certify_form(pid: int):
    """研发人员认定 / 变更表单"""
    p = personnel_tb[pid]
    cur = _safe(p, "certification_status", "待认定")
    days = int(_safe(p, "annual_rd_days", 0) or 0)

    warn = Div()
    if days and days < HIGHTECH_MIN_WORK_DAYS:
        warn = alert_box(
            f"该人员当年累计研发工作 {days} 天，不足 {HIGHTECH_MIN_WORK_DAYS} 天。"
            "按高新技术企业认定口径不得计入科技人员；若确需认定为研发人员，"
            "其人工费用仅可在加计扣除口径归集，高企口径须剔除。",
            "warning"
        )

    changes = personnel_change_tb(where=f"person_id={pid}", order_by="id DESC")
    hist_rows = [[c.change_date, c.change_type, c.before_value or "—",
                  c.after_value or "—", c.reason or "—", c.operator or "—"]
                 for c in changes]

    return page_layout(
        f"研发人员认定 · {p.name}", "首页 / 研发人员 / 认定台账 / 认定", "/rd-personnel",
        warn,
        Div(
            Div(Span(f"{p.name}（{_safe(p,'person_category','未分类')} · {p.title or '未填职务'}）"),
                cls="card-title"),
            alert_box(
                f"当前认定状态：{cur}。研发人员的认定、变更、停用全过程须留痕，"
                "作为高企复核与 IPO 审核（发行类第9号）的支撑材料。",
                "info"
            ),
            Form(
                Input(type="hidden", name="pid", value=p.id),
                Div(
                    Div(Label("操作类型", cls="form-label"),
                        Select(*_opt(["认定", "变更", "停用", "恢复"], "认定"),
                               name="change_type", cls="form-select"), cls="form-group"),
                    Div(Label("变更后状态", cls="form-label"),
                        Select(*_opt(CERT_STATUSES, "已认定"), name="new_status",
                               cls="form-select"), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("经办人", cls="form-label"),
                        Input(name="operator", value="研发部负责人", cls="form-input", required=True),
                        cls="form-group"),
                    Div(Label("生效日期", cls="form-label"),
                        Input(name="change_date", type="date",
                              value=date.today().strftime("%Y-%m-%d"), cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(Label("认定 / 变更理由", cls="form-label"),
                    Textarea(name="reason", placeholder="如：经研发部与人力资源部联合评审，确认其全年从事XX项目研发工作…",
                             cls="form-textarea", required=True), cls="form-group"),
                Div(
                    Button("提交", type="submit", cls="btn btn-primary"),
                    A("取消", href="/rd-personnel", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/rd-personnel/certify"
            ),
            cls="card"
        ),
        Div(
            Div("该人员认定 / 变更历史", cls="card-title"),
            data_table(["日期", "类型", "变更前", "变更后", "理由", "经办人"], hist_rows)
            if hist_rows else empty_state("📋", "暂无变更记录"),
            cls="card"
        )
    )


@ar("/rd-personnel/certify", methods=["POST"])
def rd_personnel_certify(pid: int, change_type: str = "认定", new_status: str = "已认定",
                         operator: str = "", change_date: str = "", reason: str = ""):
    """执行研发人员认定 / 变更 / 停用"""
    p = personnel_tb[pid]
    before = _safe(p, "certification_status", "待认定")

    p.certification_status = new_status
    p.certification_date = change_date or date.today().strftime("%Y-%m-%d")
    # 停用即视为不再作为研发人员归集人工费用
    if new_status == "已停用":
        p.is_rd = False
    else:
        p.is_rd = True
    personnel_tb.update(p)

    record_personnel_change(pid, change_type, before, new_status, reason,
                            operator or "系统")
    log_audit("APPROVE", "personnel", pid,
              f"研发人员{change_type}：{p.name} {before} → {new_status}",
              actor=operator or "系统", before=before, after=new_status)
    return RedirectResponse(url="/rd-personnel", status_code=303)


@ar("/rd-personnel/changes")
def rd_personnel_changes():
    """研发人员认定与变更记录台账"""
    recs = personnel_change_tb(order_by="id DESC")
    rows = [[c.change_date or "—", c.person_name or "—", c.change_type or "—",
             c.before_value or "—", c.after_value or "—",
             c.reason or "—", c.operator or "—"] for c in recs]
    return page_layout(
        "研发人员变更记录", "首页 / 研发人员 / 变更记录", "/rd-personnel",
        Div(
            Div(Span("认定与变更记录台账"),
                A("← 返回台账", href="/rd-personnel", cls="btn btn-outline btn-sm"),
                cls="card-title"),
            alert_box(
                "对应 rd-governor 指令17「研发人员认定与变更流程」。所有认定、类别调整、"
                "停用操作在此完整留痕，是高企复核与 IPO 现场核查的必备材料。",
                "info"
            ),
            data_table(["日期", "人员", "类型", "变更前", "变更后", "理由", "经办人"], rows)
            if rows else empty_state("📋", "暂无变更记录"),
            cls="card"
        )
    )


# ── 人员合规体检 ───────────────────────────────────────────

@ar("/rd-personnel/check")
def rd_personnel_check():
    """研发人员合规体检"""
    issues = check_personnel_compliance()
    stat, others, total = personnel_structure()

    high = len([i for i in issues if i[0] == "高"])
    mid = len([i for i in issues if i[0] == "中"])
    low = len([i for i in issues if i[0] == "低"])

    rows = [[_level_badge(lv), who, prob, sug] for lv, who, prob, sug in issues]

    # 工时与人工费用总账的衔接检查
    link_rows = []
    cur_month = date.today().strftime("%Y-%m")
    for p in personnel_tb():
        if not p.is_rd:
            continue
        wt = work_time_tb(where=f"person_id={p.id}")
        wt_hours = sum(w.hours for w in wt)
        lcs = labor_cost_tb(where=f"person_id={p.id}")
        lc_months = len(lcs)
        allocated = len([l for l in lcs if l.status == "已分摊"])
        flag = "—"
        if wt_hours > 0 and lc_months == 0:
            flag = Span("有工时无人工费总账", cls="badge badge-red")
        elif lc_months > 0 and wt_hours <= 0:
            flag = Span("有人工费无工时支撑", cls="badge badge-red")
        elif allocated < lc_months:
            flag = Span(f"{lc_months - allocated} 个月待分摊", cls="badge badge-orange")
        else:
            flag = Span("衔接正常", cls="badge badge-green")
        link_rows.append([p.name, f"{wt_hours:.1f} h", str(lc_months), str(allocated), flag])

    structure_rows = [[k, str(v), f"{v/max(total,1)*100:.0f}%"] for k, v in stat.items()]
    if others:
        structure_rows.append(["未分类", str(others), f"{others/max(total,1)*100:.0f}%"])

    return page_layout(
        "研发人员合规体检", "首页 / 研发人员 / 合规体检", "/rd-personnel",
        Div(
            stat_card("高风险问题", str(high), "须立即整改", "alert"),
            stat_card("中风险问题", str(mid), "限期补正", "gauge"),
            stat_card("低风险提示", str(low), "关注即可", "check"),
            stat_card("研发人员", str(total), "已纳入台账", "users"),
            cls="stat-grid"
        ),
        alert_box(
            "本体检覆盖 rd-governor 人员管理10章的关键控制点：三类人员结构、高企 183 天规则、"
            "认定状态、社保缴纳单位一致性、外聘与劳务派遣、离职人员清理、"
            "以及非研发人员误登工时。",
            "info"
        ) if issues else alert_box("研发人员台账未发现合规问题，各项控制点均已满足。", "success"),
        Div(
            Div("问题清单", cls="card-title"),
            data_table(["级别", "人员", "问题", "整改建议"], rows)
            if rows else empty_state("✓", "未发现问题"),
            cls="card"
        ),
        Div(
            Div("三类人员结构", cls="card-title"),
            alert_box(
                "高企认定要求科技人员占职工总数比例不低于 10%；IPO 审核关注研发人员数量、"
                "结构与研发投入的匹配性（发行类第9号）。",
                "info"
            ),
            data_table(["人员类别", "人数", "占比"], structure_rows)
            if structure_rows else empty_state("📊", "暂无数据"),
            cls="card"
        ),
        Div(
            Div("工时与人工费用衔接检查", cls="card-title"),
            alert_box(
                "研发人员的人工费用必须以工时记录为分摊依据。「有工时无人工费总账」意味着费用未归集；"
                "「有人工费无工时支撑」是稽查重点，属于缺少分摊依据。",
                "info"
            ),
            data_table(["人员", "累计工时", "人工费总账月数", "已分摊月数", "衔接状态"], link_rows)
            if link_rows else empty_state("📋", "暂无数据"),
            cls="card"
        ),
        Div(A("← 返回认定台账", href="/rd-personnel", cls="btn btn-outline"),
            style="margin-top:16px;")
    )


# ── 缺口⑧：考勤打卡 ───────────────────────────────────────

ATTENDANCE_STATUS = ["正常", "迟到", "早退", "缺勤", "请假"]


def _person_name(pid):
    try:
        return personnel_tb[pid].name if pid else "—"
    except Exception:
        return "—"


@ar("/attendance")
def attendance_index(month: str = "", person_id: str = "", status: str = ""):
    """考勤打卡记录台账"""
    recs = list(attendance_records_tb(order_by="work_date DESC, id DESC"))
    if month:
        recs = [r for r in recs if (r.work_date or "")[:7] == month]
    if person_id:
        recs = [r for r in recs if str(r.person_id) == str(person_id)]
    if status:
        recs = [r for r in recs if r.status == status]

    rows = []
    for r in recs:
        status_cls = {
            "正常": "badge-green", "迟到": "badge-orange",
            "早退": "badge-orange", "缺勤": "badge-red", "请假": "badge-blue"
        }.get(r.status, "badge-gray")
        rows.append([
            _person_name(r.person_id), r.work_date or "—",
            r.check_in or "—", r.check_out or "—",
            Span(r.status, cls=f"badge {status_cls}"),
            A("编辑", href=f"/attendance/{r.id}/edit", cls="btn btn-outline btn-sm"),
            A("删除", href=f"/attendance/{r.id}/del", cls="btn btn-outline btn-sm",
              onclick="return confirm('确认删除该考勤记录？')"),
        ])

    # 月度统计
    cur_month = month or date.today().strftime("%Y-%m")
    mrecs = [r for r in recs if (r.work_date or "")[:7] == cur_month]
    normal_cnt = len([r for r in mrecs if r.status == "正常"])
    abnormal = len([r for r in mrecs if r.status in ("迟到", "早退", "缺勤")])

    from .components import month_options
    return page_layout(
        "考勤打卡", "首页 / 人事管理 / 考勤打卡", "/attendance",
        Div(
            stat_card(f"{cur_month} 记录数", str(len(mrecs)), "条", "blue"),
            stat_card("正常出勤", str(normal_cnt), "条", "green"),
            stat_card("异常出勤", str(abnormal), "迟到/早退/缺勤", "alert"),
            stat_card("本月应出勤人员", str(len([p for p in personnel_tb() if p.is_rd])), "研发人员", "users"),
            cls="stat-grid"
        ),
        alert_box(
            "考勤记录用于支撑研发人员「当年累计实际工作时间 ≥ 183 天」的高企认定口径，"
            "并与工时管理、人工费用归集形成证据链。异常出勤（迟到/早退/缺勤）应核实原因。",
            "info"
        ),
        Div(
            Div(
                Span("考勤记录"),
                A("+ 打卡登记", href="/attendance/new", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("月份", cls="form-label"),
                        Select(*month_options(month), name="month", cls="form-select"), cls="form-group"),
                    Div(Label("人员", cls="form-label"),
                        Select(*person_options_rd(person_id), name="person_id", cls="form-select"),
                        cls="form-group"),
                    Div(Label("状态", cls="form-label"),
                        Select(Option("全部", value=""), *[Option(s, value=s, selected=(s == status)) for s in ATTENDANCE_STATUS],
                               name="status", cls="form-select"), cls="form-group"),
                    Div(Button("筛选", type="submit", cls="btn btn-primary"), style="align-self:end;"),
                    cls="form-row"
                ),
                method="get", action="/attendance"
            ),
            data_table(["人员", "日期", "上班打卡", "下班打卡", "状态", "", ""], rows)
            if rows else empty_state("🕐", "暂无考勤记录，点击「打卡登记」录入"),
            cls="card"
        )
    )


def person_options_rd(selected=""):
    """全部研发人员下拉（含在职与停用，用于考勤）"""
    from .db import personnel_tb
    from fasthtml.common import Option
    opts = [Option("— 全部人员 —", value="")]
    for p in personnel_tb(where="is_rd=1"):
        opts.append(Option(f"{p.name}（{p.title or '—'}）", value=p.id,
                           selected=str(p.id) == str(selected)))
    return opts


@ar("/attendance/new")
def attendance_new():
    return page_layout(
        "打卡登记", "首页 / 人事管理 / 考勤打卡 / 登记", "/attendance",
        Div(
            Form(
                Div(
                    Div(Label("人员", cls="form-label"),
                        Select(*person_options_rd(), name="person_id", cls="form-select", required=True),
                        cls="form-group"),
                    Div(Label("日期", cls="form-label"),
                        Input(name="work_date", type="date", value=date.today().strftime("%Y-%m-%d"),
                              cls="form-input", required=True), cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("上班打卡", cls="form-label"),
                        Input(name="check_in", type="time", value="09:00", cls="form-input"),
                        cls="form-group"),
                    Div(Label("下班打卡", cls="form-label"),
                        Input(name="check_out", type="time", value="18:00", cls="form-input"),
                        cls="form-group"),
                    Div(Label("状态", cls="form-label"),
                        Select(*[Option(s, value=s, selected=(s == "正常")) for s in ATTENDANCE_STATUS],
                               name="status", cls="form-select"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/attendance", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/attendance/save"
            ),
            cls="card"
        )
    )


@ar("/attendance/save", methods=["POST"])
def attendance_save(person_id: str, work_date: str, check_in: str = "",
                    check_out: str = "", status: str = "正常"):
    rec = attendance_records_tb.insert(
        person_id=int(person_id) if person_id else 0,
        work_date=work_date, check_in=check_in, check_out=check_out,
        status=status, created_at=date.today().strftime("%Y-%m-%d %H:%M")
    )
    log_audit("CREATE", "attendance_records", rec.id,
              f"考勤登记：{_person_name(rec.person_id)} {work_date} {status}")
    log_data_change("attendance", getattr(rec, "id", 0), "status",
                    old_val="", new_val=f"{_person_name(rec.person_id)} {work_date} {status}",
                    operator="system")
    return RedirectResponse(url="/attendance", status_code=303)


@ar("/attendance/{aid}/edit")
def attendance_edit(aid: int):
    a = attendance_records_tb[aid]
    return page_layout(
        "编辑考勤记录", "首页 / 人事管理 / 考勤打卡 / 编辑", "/attendance",
        Div(
            Form(
                Input(type="hidden", name="id", value=a.id),
                Div(
                    Div(Label("人员", cls="form-label"),
                        Select(*person_options_rd(a.person_id), name="person_id", cls="form-select"),
                        cls="form-group"),
                    Div(Label("日期", cls="form-label"),
                        Input(name="work_date", type="date", value=a.work_date, cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("上班打卡", cls="form-label"),
                        Input(name="check_in", type="time", value=a.check_in, cls="form-input"),
                        cls="form-group"),
                    Div(Label("下班打卡", cls="form-label"),
                        Input(name="check_out", type="time", value=a.check_out, cls="form-input"),
                        cls="form-group"),
                    Div(Label("状态", cls="form-label"),
                        Select(*[Option(s, value=s, selected=(s == a.status)) for s in ATTENDANCE_STATUS],
                               name="status", cls="form-select"), cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/attendance", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/attendance/update"
            ),
            cls="card"
        )
    )


@ar("/attendance/update", methods=["POST"])
def attendance_update(id: int, person_id: str, work_date: str, check_in: str = "",
                      check_out: str = "", status: str = "正常"):
    a = attendance_records_tb[id]
    a.person_id = int(person_id) if person_id else 0
    a.work_date = work_date
    a.check_in = check_in
    a.check_out = check_out
    a.status = status
    attendance_records_tb.update(a)
    log_audit("UPDATE", "attendance_records", a.id,
              f"更新考勤：{_person_name(a.person_id)} {work_date} {status}")
    return RedirectResponse(url="/attendance", status_code=303)


@ar("/attendance/{aid}/del")
def attendance_del(aid: int):
    a = attendance_records_tb[aid]
    log_audit("DELETE", "attendance_records", aid,
              f"删除考勤：{_person_name(a.person_id)} {a.work_date}")
    attendance_records_tb.delete(aid)
    return RedirectResponse(url="/attendance", status_code=303)


# ── 缺口⑧：月度薪酬计提（薪资/社保/公积金）────────────────────

@ar("/salary")
def salary_index(month: str = ""):
    """月度薪酬计提台账"""
    recs = list(salary_records_tb(order_by="month DESC, id DESC"))
    if month:
        recs = [r for r in recs if r.month == month]

    rows = []
    for r in recs:
        rows.append([
            r.month or "—", _person_name(r.person_id),
            f"¥{r.base_salary:,.0f}", f"¥{r.social_security:,.0f}",
            f"¥{r.housing_fund:,.0f}", f"¥{r.bonus:,.0f}",
            f"¥{r.other_allowance:,.0f}", f"¥{r.total:,.0f}",
            A("编辑", href=f"/salary/{r.id}/edit", cls="btn btn-outline btn-sm"),
            A("删除", href=f"/salary/{r.id}/del", cls="btn btn-outline btn-sm",
              onclick="return confirm('确认删除该薪酬记录？')"),
        ])

    cur_month = month or date.today().strftime("%Y-%m")
    mrecs = [r for r in recs if r.month == cur_month]
    total_payroll = sum(r.total for r in mrecs)
    total_social = sum(r.social_security for r in mrecs)
    total_fund = sum(r.housing_fund for r in mrecs)

    from .components import month_options
    return page_layout(
        "月度薪酬计提", "首页 / 人事管理 / 薪酬计提", "/salary",
        Div(
            stat_card(f"{cur_month} 计提人数", str(len(mrecs)), "人", "blue"),
            stat_card("应发工资", f"¥{total_payroll:,.0f}", "含奖金津贴", "green"),
            stat_card("社保合计", f"¥{total_social:,.0f}", "个人+单位", "orange"),
            stat_card("公积金合计", f"¥{total_fund:,.0f}", "个人+单位", "purple"),
            cls="stat-grid"
        ),
        alert_box(
            "薪酬计提与社保、公积金记录用于支撑人工费用归集的真实性核查：研发人员薪酬须与"
            "社保缴纳单位一致（IPO 发行类第9号）；薪酬总额与工时分配应可相互验证，防止虚构人工费用。",
            "info"
        ),
        Div(
            Div(
                Span("薪酬计提台账"),
                A("+ 计提登记", href="/salary/new", cls="btn btn-primary btn-sm"),
                cls="card-title"
            ),
            Form(
                Div(
                    Div(Label("月份", cls="form-label"),
                        Select(*month_options(month), name="month", cls="form-select"), cls="form-group"),
                    Div(Button("筛选", type="submit", cls="btn btn-primary"), style="align-self:end;"),
                    cls="form-row"
                ),
                method="get", action="/salary"
            ),
            data_table(
                ["月份", "人员", "基本工资", "社保", "公积金", "奖金", "其他津贴", "应发合计", "", ""],
                rows
            ) if rows else empty_state("💰", "暂无薪酬记录，点击「计提登记」录入"),
            cls="card"
        )
    )


@ar("/salary/new")
def salary_new(month: str = ""):
    return page_layout(
        "薪酬计提登记", "首页 / 人事管理 / 薪酬计提 / 登记", "/salary",
        Div(
            alert_box(
                "填写基本工资、社保、公积金、奖金与其他津贴后，系统自动计算应发合计。"
                "按月、按人计提；同一人员同月重复登记将提示覆盖（请勿重复录入）。",
                "info"
            ),
            Form(
                Div(
                    Div(Label("月份", cls="form-label"),
                        Input(name="month", type="month", value=month or date.today().strftime("%Y-%m"),
                              cls="form-input", required=True), cls="form-group"),
                    Div(Label("人员", cls="form-label"),
                        Select(*person_options_rd(), name="person_id", cls="form-select", required=True),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("基本工资（元）", cls="form-label"),
                        Input(name="base_salary", type="number", step="0.01", value="0", cls="form-input"),
                        cls="form-group"),
                    Div(Label("社保（元）", cls="form-label"),
                        Input(name="social_security", type="number", step="0.01", value="0", cls="form-input"),
                        cls="form-group"),
                    Div(Label("公积金（元）", cls="form-label"),
                        Input(name="housing_fund", type="number", step="0.01", value="0", cls="form-input"),
                        cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("奖金（元）", cls="form-label"),
                        Input(name="bonus", type="number", step="0.01", value="0", cls="form-input"),
                        cls="form-group"),
                    Div(Label("其他津贴（元）", cls="form-label"),
                        Input(name="other_allowance", type="number", step="0.01", value="0", cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/salary", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/salary/save"
            ),
            cls="card"
        )
    )


@ar("/salary/save", methods=["POST"])
def salary_save(person_id: str, month: str, base_salary: str = "0",
                social_security: str = "0", housing_fund: str = "0",
                bonus: str = "0", other_allowance: str = "0"):
    base = float(base_salary or 0)
    ss = float(social_security or 0)
    hf = float(housing_fund or 0)
    bn = float(bonus or 0)
    oa = float(other_allowance or 0)

    # 同人同月防重复：已存在则更新
    dup = [r for r in salary_records_tb(where=f"person_id={int(person_id or 0)}") if r.month == month]
    if dup:
        r = dup[0]
        before = f"{r.total:,.2f}"
        r.base_salary = base; r.social_security = ss; r.housing_fund = hf
        r.bonus = bn; r.other_allowance = oa; r.total = round(base + ss + hf + bn + oa, 2)
        salary_records_tb.update(r)
        log_audit("UPDATE", "salary_records", r.id,
                  f"更新薪酬：{_person_name(r.person_id)} {month} ¥{r.total:,.2f}",
                  before=before, after=f"{r.total:,.2f}")
        log_data_change("salary", r.id, "total",
                        old_val=before, new_val=f"{r.total:,.2f} {month}",
                        operator="system")
        return RedirectResponse(url="/salary", status_code=303)

    rec = salary_records_tb.insert(
        person_id=int(person_id) if person_id else 0, month=month,
        base_salary=base, social_security=ss, housing_fund=hf,
        bonus=bn, other_allowance=oa, total=round(base + ss + hf + bn + oa, 2),
        created_at=date.today().strftime("%Y-%m-%d %H:%M")
    )
    log_audit("CREATE", "salary_records", rec.id,
              f"薪酬计提：{_person_name(rec.person_id)} {month} ¥{rec.total:,.2f}")
    log_data_change("salary", getattr(rec, "id", 0), "total",
                    old_val="", new_val=f"{rec.total:,.2f} {month}",
                    operator="system")
    return RedirectResponse(url="/salary", status_code=303)


@ar("/salary/{sid}/edit")
def salary_edit(sid: int):
    r = salary_records_tb[sid]
    return page_layout(
        "编辑薪酬记录", "首页 / 人事管理 / 薪酬计提 / 编辑", "/salary",
        Div(
            Form(
                Input(type="hidden", name="id", value=r.id),
                Div(
                    Div(Label("月份", cls="form-label"),
                        Input(name="month", type="month", value=r.month, cls="form-input", required=True),
                        cls="form-group"),
                    Div(Label("人员", cls="form-label"),
                        Select(*person_options_rd(r.person_id), name="person_id", cls="form-select"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Div(Label("基本工资（元）", cls="form-label"),
                        Input(name="base_salary", type="number", step="0.01", value=r.base_salary, cls="form-input"),
                        cls="form-group"),
                    Div(Label("社保（元）", cls="form-label"),
                        Input(name="social_security", type="number", step="0.01", value=r.social_security, cls="form-input"),
                        cls="form-group"),
                    Div(Label("公积金（元）", cls="form-label"),
                        Input(name="housing_fund", type="number", step="0.01", value=r.housing_fund, cls="form-input"),
                        cls="form-group"),
                    cls="form-row-3"
                ),
                Div(
                    Div(Label("奖金（元）", cls="form-label"),
                        Input(name="bonus", type="number", step="0.01", value=r.bonus, cls="form-input"),
                        cls="form-group"),
                    Div(Label("其他津贴（元）", cls="form-label"),
                        Input(name="other_allowance", type="number", step="0.01", value=r.other_allowance, cls="form-input"),
                        cls="form-group"),
                    cls="form-row"
                ),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/salary", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/salary/update"
            ),
            cls="card"
        )
    )


@ar("/salary/update", methods=["POST"])
def salary_update(id: int, person_id: str, month: str, base_salary: str = "0",
                  social_security: str = "0", housing_fund: str = "0",
                  bonus: str = "0", other_allowance: str = "0"):
    r = salary_records_tb[id]
    r.person_id = int(person_id) if person_id else 0
    r.month = month
    r.base_salary = float(base_salary or 0)
    r.social_security = float(social_security or 0)
    r.housing_fund = float(housing_fund or 0)
    r.bonus = float(bonus or 0)
    r.other_allowance = float(other_allowance or 0)
    r.total = round(r.base_salary + r.social_security + r.housing_fund + r.bonus + r.other_allowance, 2)
    salary_records_tb.update(r)
    log_audit("UPDATE", "salary_records", r.id,
              f"更新薪酬：{_person_name(r.person_id)} {month} ¥{r.total:,.2f}")
    return RedirectResponse(url="/salary", status_code=303)


@ar("/salary/{sid}/del")
def salary_del(sid: int):
    r = salary_records_tb[sid]
    log_audit("DELETE", "salary_records", sid,
              f"删除薪酬：{_person_name(r.person_id)} {r.month}")
    salary_records_tb.delete(sid)
    return RedirectResponse(url="/salary", status_code=303)
