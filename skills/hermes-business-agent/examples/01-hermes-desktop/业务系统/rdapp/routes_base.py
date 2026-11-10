"""routes_base.py — 基础数据管理路由

管理：费用科目、流程模板、政策规则、组织架构、人员档案、研发费用口径
（研发费用口径原位于设置中心，2026-07-28 起整体迁入本模块；
  数据契约不变，仍复用 /api/hub/rd 与 /api/hub/rd/sync-memory 端点。）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from .db import (
    templates_tb, nodes_tb, subjects_tb, policies_tb, orgs_tb, personnel_tb
)
from .components import (
    page_layout, phase_badge, data_table, empty_state, alert_box
)
from .biz_config import get_hermes_home, get_rd_settings

ar = APIRouter()


@ar("/base-data")
def base_data():
    """基础数据管理首页 — 概览"""
    subj_count = len(subjects_tb())
    tpl_count = len(templates_tb())
    policy_count = len(policies_tb())
    org_count = len(orgs_tb())
    person_count = len(personnel_tb())
    try:
        rd_proj_count = len((get_rd_settings(get_hermes_home()) or {}).get("projects") or [])
    except Exception:
        rd_proj_count = 0

    items = [
        ("研发费用口径", "企业信息/加计扣除/资本化/合规阈值/报表偏好", rd_proj_count, "/base-data/rd-caliber", "gauge"),
        ("费用科目", "8大研发费用科目体系", subj_count, "/base-data/subjects", "01"),
        ("流程模板", "标准研发流程模板库", tpl_count, "/base-data/templates", "workflow"),
        ("政策规则", "多口径政策规则配置", policy_count, "/base-data/policies", "book"),
        ("组织架构", "集团/子公司/部门三级架构", org_count, "/base-data/orgs", "building"),
        ("人员档案", "研发人员档案与工时标准", person_count, "/base-data/personnel", "users"),
    ]

    cards = []
    for title, desc, count, href, icon in items:
        cards.append(
            A(
                Div(
                    Div(icon, style="font-size:32px;margin-bottom:12px;color:var(--primary);"),
                    Div(title, style="font-size:16px;font-weight:600;margin-bottom:4px;"),
                    Div(desc, style="font-size:12px;color:var(--text-muted);margin-bottom:12px;"),
                    Div(
                        Span(str(count), style="font-size:24px;font-weight:700;color:var(--text);"),
                        Span(" 条记录", style="font-size:12px;color:var(--text-muted);"),
                    ),
                    style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:24px;height:100%;transition:all 0.15s;"
                ),
                href=href,
                style="text-decoration:none;color:inherit;display:block;"
            )
        )

    return page_layout(
        "基础数据管理", "首页 / 基础数据", "/base-data",
        Div(alert_box("基础数据是系统运行的数据底座，请先完成费用科目和流程模板的配置，再创建研发项目。", "info")),
        Div(*cards, style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;")
    )


@ar("/base-data/subjects")
def subjects():
    """费用科目列表"""
    all_subjects = subjects_tb(order_by="code")
    rows = []
    for s in all_subjects:
        cap_badge = Span("可资本化", cls="badge badge-orange") if s.capitalizable else Span("费用化", cls="badge badge-blue")
        rows.append([
            s.code, s.name, cap_badge,
            s.description[:50] + "..." if len(s.description) > 50 else s.description,
            A("编辑", href=f"/base-data/subjects/{s.id}/edit", cls="btn btn-outline btn-sm"),
        ])

    return page_layout(
        "费用科目管理", "首页 / 基础数据 / 费用科目", "/base-data",
        Div(
            Div(
                Span("费用科目体系（8大科目）"),
                A("+ 新增科目", href="/base-data/subjects/new", cls="btn btn-primary"),
                cls="card-title"
            ),
            alert_box("每个科目标记资本化/费用化属性：研究阶段费用自动费用化；开发阶段符合条件可资本化。", "info"),
            data_table(["编码", "科目名称", "资本化属性", "说明", "操作"], rows) if rows else empty_state("📋", "暂无费用科目"),
            cls="card"
        )
    )


@ar("/base-data/subjects/new")
def subject_new():
    """新增费用科目表单"""
    return page_layout(
        "新增费用科目", "首页 / 基础数据 / 费用科目 / 新增", "/base-data",
        Div(
            Form(
                Div(Label("科目编码", cls="form-label"), Input(name="code", placeholder="如：09", cls="form-input", required=True), cls="form-group"),
                Div(Label("科目名称", cls="form-label"), Input(name="name", placeholder="如：研发管理费用", cls="form-input", required=True), cls="form-group"),
                Div(
                    Label("资本化属性", cls="form-label"),
                    Select(Option("费用化", value="false"), Option("可资本化", value="true"), name="capitalizable", cls="form-select"),
                    Div("研究阶段费用自动费用化；开发阶段可资本化科目在满足条件时可资本化", cls="form-hint"),
                    cls="form-group"
                ),
                Div(Label("说明", cls="form-label"), Textarea(name="description", placeholder="科目说明...", cls="form-textarea"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/base-data/subjects", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/base-data/subjects/save"
            ),
            cls="card"
        )
    )


@ar("/base-data/subjects/save", methods=["POST"])
def subject_save(code: str, name: str, capitalizable: str, description: str = ""):
    """保存费用科目"""
    subjects_tb.insert(code=code, name=name, capitalizable=(capitalizable == "true"), description=description)
    return RedirectResponse(url="/base-data/subjects", status_code=303)


@ar("/base-data/subjects/{sid}/edit")
def subject_edit(sid: int):
    """编辑费用科目"""
    s = subjects_tb[sid]
    return page_layout(
        "编辑费用科目", "首页 / 基础数据 / 费用科目 / 编辑", "/base-data",
        Div(
            Form(
                Div(Label("科目编码", cls="form-label"), Input(name="code", value=s.code, cls="form-input", required=True), cls="form-group"),
                Div(Label("科目名称", cls="form-label"), Input(name="name", value=s.name, cls="form-input", required=True), cls="form-group"),
                Div(
                    Label("资本化属性", cls="form-label"),
                    Select(Option("费用化", value="false", selected=not s.capitalizable), Option("可资本化", value="true", selected=s.capitalizable), name="capitalizable", cls="form-select"),
                    cls="form-group"
                ),
                Div(Label("说明", cls="form-label"), Textarea(name="description", cls="form-textarea")(s.description), cls="form-group"),
                Input(type="hidden", name="id", value=s.id),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/base-data/subjects", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/base-data/subjects/update"
            ),
            cls="card"
        )
    )


@ar("/base-data/subjects/update", methods=["POST"])
def subject_update(id: int, code: str, name: str, capitalizable: str, description: str = ""):
    """更新费用科目"""
    s = subjects_tb[id]
    s.code, s.name, s.capitalizable, s.description = code, name, (capitalizable == "true"), description
    subjects_tb.update(s)
    return RedirectResponse(url="/base-data/subjects", status_code=303)


@ar("/base-data/templates")
def templates():
    """流程模板列表"""
    all_templates = templates_tb()
    cards = []
    for t in all_templates:
        nodes = nodes_tb(where=f"template_id={t.id}", order_by="order_idx")
        research_nodes = [n for n in nodes if n.phase == "研究"]
        develop_nodes = [n for n in nodes if n.phase == "开发"]
        produce_nodes = [n for n in nodes if n.phase == "生产"]

        node_display = [Span(phase_badge(n.phase), Span(f" {n.name}", style="font-size:12px;"), style="margin-right:8px;margin-bottom:4px;display:inline-block;") for n in nodes]

        cards.append(
            Div(
                Div(
                    Span(t.model_type, cls="badge badge-purple"),
                    Span(t.name, style="font-size:16px;font-weight:600;margin-left:8px;"),
                    cls="card-title"
                ),
                P(t.description, style="font-size:13px;color:var(--text-muted);margin-bottom:12px;"),
                Div(*node_display, style="margin-bottom:12px;"),
                Div(
                    Div(f"研究阶段：{len(research_nodes)} 节点", style="font-size:12px;color:var(--phase-research);margin-right:16px;"),
                    Div(f"开发阶段：{len(develop_nodes)} 节点", style="font-size:12px;color:var(--phase-develop);margin-right:16px;"),
                    Div(f"生产阶段：{len(produce_nodes)} 节点", style="font-size:12px;color:var(--phase-produce);"),
                ),
                A("查看详情 →", href=f"/base-data/templates/{t.id}", cls="btn btn-outline btn-sm"),
                cls="card"
            )
        )

    return page_layout(
        "流程模板管理", "首页 / 基础数据 / 流程模板", "/base-data",
        alert_box("流程模板预设研究阶段→开发阶段的节点划分，费用随流程节点影子归集，系统自动标记资本化/费用化。", "info"),
        Div(*cards, style="display:grid;grid-template-columns:1fr;gap:16px;") if cards else empty_state("📋", "暂无流程模板"),
    )


@ar("/base-data/templates/{tid}")
def template_detail(tid: int):
    """流程模板详情"""
    t = templates_tb[tid]
    nodes = nodes_tb(where=f"template_id={tid}", order_by="order_idx")
    rows = [[n.order_idx, n.name, phase_badge(n.phase), n.deliverable, f"{n.budget_ratio}%", n.approver] for n in nodes]

    return page_layout(
        f"流程模板：{t.name}", "首页 / 基础数据 / 流程模板 / 详情", "/base-data",
        Div(
            Div(Span(t.model_type, cls="badge badge-purple"), Span(t.name, style="font-size:18px;font-weight:600;margin-left:8px;")),
            P(t.description, style="color:var(--text-muted);margin-top:8px;"),
            cls="card"
        ),
        Div(
            Div("流程节点配置", cls="card-title"),
            data_table(["序号", "节点名称", "所属阶段", "交付物", "预算占比", "审批人"], rows),
            cls="card"
        ),
        Div(
            Div("阶段划分说明", cls="card-title"),
            Div(
                Div(
                    Span("研究阶段", cls="badge phase-research"),
                    P("需求调研、可行性研究、技术预研、方案探索等节点。费用自动费用化，计入当期损益。", style="font-size:13px;margin-top:8px;color:var(--text-muted);"),
                    style="margin-bottom:16px;"
                ),
                Div(
                    Span("开发阶段", cls="badge phase-develop"),
                    P("系统设计、编码实现、集成测试、用户验收等节点。系统自动检查资本化条件，符合条件可资本化。", style="font-size:13px;margin-top:8px;color:var(--text-muted);"),
                    style="margin-bottom:16px;"
                ),
                Div(
                    Span("生产阶段", cls="badge phase-produce"),
                    P("批量生产、大规模部署等节点。费用自动标记为非研发费用，不纳入研发费用归集。", style="font-size:13px;margin-top:8px;color:var(--text-muted);"),
                ),
            ),
            cls="card"
        )
    )


@ar("/base-data/policies")
def policies():
    """政策规则列表"""
    import json
    all_policies = policies_tb()
    rows = []
    for p in all_policies:
        params = json.loads(p.params) if p.params else {}
        param_str = "；".join(f"{k}={v}" for k, v in params.items())
        caliber_badge = {"高企认定": "badge-blue", "加计扣除": "badge-green", "统计报表": "badge-purple"}.get(p.caliber, "badge-gray")
        rows.append([
            p.name, Span(p.caliber, cls=f"badge {caliber_badge}"),
            param_str[:60] + "..." if len(param_str) > 60 else param_str,
            p.description[:40] + "..." if len(p.description) > 40 else p.description,
        ])

    return page_layout(
        "政策规则管理", "首页 / 基础数据 / 政策规则", "/base-data",
        Div(
            Div("多口径政策规则", cls="card-title"),
            alert_box("内置高企认定、加计扣除、统计报表三套口径规则，同一笔费用在不同口径下可能有不同的归集结果。", "info"),
            data_table(["规则名称", "归集口径", "参数配置", "说明"], rows) if rows else empty_state("📋", "暂无政策规则"),
            cls="card"
        )
    )


@ar("/base-data/orgs")
def orgs():
    """组织架构列表"""
    all_orgs = orgs_tb()
    rows = []
    for o in all_orgs:
        level_badge = {"集团": "badge-purple", "子公司": "badge-blue", "部门": "badge-gray"}.get(o.level, "badge-gray")
        parent_name = orgs_tb[o.parent_id].name if o.parent_id else "—"
        person_count = len(personnel_tb(where=f"org_id={o.id}"))
        rows.append([o.name, Span(o.level, cls=f"badge {level_badge}"), parent_name, f"{person_count} 人"])

    return page_layout(
        "组织架构", "首页 / 基础数据 / 组织架构", "/base-data",
        Div(
            Div("组织架构（集团/子公司/部门三级）", cls="card-title"),
            data_table(["名称", "层级", "上级组织", "人员数"], rows) if rows else empty_state("📋", "暂无组织架构"),
            cls="card"
        )
    )


@ar("/base-data/personnel")
def personnel():
    """人员档案列表"""
    all_personnel = personnel_tb()
    rows = []
    for p in all_personnel:
        org = orgs_tb[p.org_id] if p.org_id else None
        rd_badge = Span("研发人员", cls="badge badge-green") if p.is_rd else Span("非研发", cls="badge badge-gray")
        rows.append([p.name, p.title, org.name if org else "—", rd_badge, f"¥{p.hourly_rate}/h" if p.hourly_rate else "—"])

    return page_layout(
        "人员档案", "首页 / 基础数据 / 人员档案", "/base-data",
        Div(
            Div(Span("研发人员档案"), A("+ 新增人员", href="/base-data/personnel/new", cls="btn btn-primary"), cls="card-title"),
            data_table(["姓名", "职务", "所属组织", "研发属性", "工时标准"], rows) if rows else empty_state("📋", "暂无人员档案"),
            cls="card"
        )
    )


@ar("/base-data/personnel/new")
def personnel_new():
    """新增人员表单"""
    all_orgs = orgs_tb()
    org_options = [Option("— 请选择 —", value="")] + [Option(f"{o.name}（{o.level}）", value=o.id) for o in all_orgs]
    return page_layout(
        "新增人员", "首页 / 基础数据 / 人员档案 / 新增", "/base-data",
        Div(
            Form(
                Div(Label("姓名", cls="form-label"), Input(name="name", cls="form-input", required=True), cls="form-group"),
                Div(Label("职务", cls="form-label"), Input(name="title", placeholder="如：高级工程师", cls="form-input"), cls="form-group"),
                Div(Label("所属组织", cls="form-label"), Select(*org_options, name="org_id", cls="form-select"), cls="form-group"),
                Div(
                    Label("研发人员", cls="form-label"),
                    Select(Option("是", value="true"), Option("否", value="false"), name="is_rd", cls="form-select"),
                    cls="form-group"
                ),
                Div(Label("工时标准（元/小时）", cls="form-label"), Input(name="hourly_rate", type="number", placeholder="如：200", cls="form-input"), cls="form-group"),
                Div(
                    Button("保存", type="submit", cls="btn btn-primary"),
                    A("取消", href="/base-data/personnel", cls="btn btn-outline"),
                    style="display:flex;gap:10px;"
                ),
                method="post", action="/base-data/personnel/save"
            ),
            cls="card"
        )
    )


@ar("/base-data/personnel/save", methods=["POST"])
def personnel_save(name: str, title: str = "", org_id: str = "", is_rd: str = "true", hourly_rate: str = "0"):
    """保存人员"""
    personnel_tb.insert(name=name, title=title, org_id=int(org_id) if org_id else 0, is_rd=(is_rd == "true"), hourly_rate=float(hourly_rate) if hourly_rate else 0.0)
    return RedirectResponse(url="/base-data/personnel", status_code=303)


# ── 研发费用口径（自设置中心整体迁入） ──────────────────────
def _rd_toggle(label: str, cid: str) -> Div:
    """研发费用口径页复用的开关行。"""
    return Div(
        Span(label, style="font-weight:500;"),
        Label(
            Input(id=cid, type="checkbox"),
            Span(cls="skill-toggle-slider"),
            cls="skill-toggle", _for=cid,
        ),
        cls="toggle-row",
    )


_RD_CALIBER_JS = """
window.RdCaliber = (function () {
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function setStatus(msg, isErr) {
    const el = $("rd_status");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "var(--danger, #b91c1c)" : "var(--success, #166534)";
  }
  function chkSet(id, v) { if ($(id)) $(id).checked = !!v; }
  function valSet(id, v) { if ($(id)) $(id).value = (v == null ? "" : v); }
  function chk(id) { return $(id) ? $(id).checked : false; }
  function num(id, def) { const v = $(id) ? parseFloat($(id).value) : NaN; return isNaN(v) ? def : v; }
  function val(id, def) { return ($(id) && $(id).value) || def || ""; }

  function fill(rd) {
    rd = rd || {};
    const ent = rd.enterprise || {}, tax = rd.tax || {}, cats = tax.categories || {};
    const cap = rd.capitalization || {}, risk = rd.risk || {}, checks = risk.checks || {};
    const rep = rd.reports || {}, inc = rep.include || {}, fmts = rep.formats || [];
    valSet("rd_ent_name", ent.name); valSet("rd_ent_code", ent.credit_code);
    valSet("rd_ent_industry", ent.industry); valSet("rd_ent_standard", ent.accounting_standard || "企业会计准则");
    chkSet("rd_ent_hightech", ent.is_high_tech); chkSet("rd_ent_scisme", ent.is_sci_sme);
    valSet("rd_tax_rate", tax.super_deduction_rate); valSet("rd_tax_othercap", tax.other_cap_rate);
    valSet("rd_tax_method", tax.collection_method || "auxiliary_account"); valSet("rd_tax_basis", tax.policy_basis);
    chkSet("rd_cat_personnel", cats.personnel); chkSet("rd_cat_direct", cats.direct);
    chkSet("rd_cat_depreciation", cats.depreciation); chkSet("rd_cat_amortization", cats.amortization);
    chkSet("rd_cat_design", cats.design); chkSet("rd_cat_other", cats.other);
    chkSet("rd_cap_research", cap.research_expense); chkSet("rd_cap_dev", cap.dev_capitalize);
    valSet("rd_cap_years", cap.amortization_years);
    valSet("rd_risk_personnel", Math.round((risk.personnel_ratio_max || 0) * 100));
    valSet("rd_risk_other", Math.round((risk.other_ratio_max || 0) * 100));
    valSet("rd_risk_single", risk.single_project_max || 0);
    chkSet("rd_chk_cross", checks.cross_project); chkSet("rd_chk_nonrd", checks.non_rd_personnel);
    chkSet("rd_chk_cap", checks.capitalization_misuse); chkSet("rd_chk_invoice", checks.invoice_compliance);
    valSet("rd_rep_period", rep.default_period || "monthly");
    chkSet("rd_fmt_xlsx", fmts.indexOf("xlsx") >= 0); chkSet("rd_fmt_pdf", fmts.indexOf("pdf") >= 0);
    chkSet("rd_inc_summary", inc.summary); chkSet("rd_inc_project", inc.by_project);
    chkSet("rd_inc_category", inc.by_category); chkSet("rd_inc_deduction", inc.super_deduction);
    chkSet("rd_inc_cap", inc.capitalization);
    const projs = rd.projects || [];
    if ($("rd_projects_json")) $("rd_projects_json").value = JSON.stringify(projs, null, 2);
    renderProjects(projs);
  }

  function renderProjects(projs) {
    const el = $("rd_projects_preview");
    if (!el) return;
    if (!projs.length) { el.innerHTML = "<p class='muted'>暂无研发项目。</p>"; return; }
    el.innerHTML = "";
    projs.forEach(function (p) {
      const row = document.createElement("div");
      row.className = "kv-row";
      row.innerHTML = "<div><b>" + esc(p.code || "") + " " + esc(p.name || "") + "</b><br><span class='muted'>" +
        esc("类型：" + (p.type || "-") + " · 开始：" + (p.start || "-") + " · 状态：" + (p.status || "-")) + "</span></div>";
      el.appendChild(row);
    });
  }

  function collect() {
    const fmts = [];
    if (chk("rd_fmt_xlsx")) fmts.push("xlsx");
    if (chk("rd_fmt_pdf")) fmts.push("pdf");
    let projects = [];
    try { const p = JSON.parse($("rd_projects_json").value || "[]"); if (Array.isArray(p)) projects = p; }
    catch (e) { throw new Error("研发项目 JSON 格式错误：" + e.message); }
    return {
      enterprise: {
        name: val("rd_ent_name"), credit_code: val("rd_ent_code"),
        industry: val("rd_ent_industry"), accounting_standard: val("rd_ent_standard", "企业会计准则"),
        is_high_tech: chk("rd_ent_hightech"), is_sci_sme: chk("rd_ent_scisme"),
      },
      tax: {
        super_deduction_rate: num("rd_tax_rate", 100), other_cap_rate: num("rd_tax_othercap", 10),
        collection_method: val("rd_tax_method", "auxiliary_account"),
        policy_basis: val("rd_tax_basis"),
        categories: {
          personnel: chk("rd_cat_personnel"), direct: chk("rd_cat_direct"),
          depreciation: chk("rd_cat_depreciation"), amortization: chk("rd_cat_amortization"),
          design: chk("rd_cat_design"), other: chk("rd_cat_other"),
        },
      },
      capitalization: {
        research_expense: chk("rd_cap_research"), dev_capitalize: chk("rd_cap_dev"),
        amortization_years: num("rd_cap_years", 10),
      },
      risk: {
        personnel_ratio_max: num("rd_risk_personnel", 70) / 100,
        other_ratio_max: num("rd_risk_other", 10) / 100,
        single_project_max: num("rd_risk_single", 0),
        checks: {
          cross_project: chk("rd_chk_cross"), non_rd_personnel: chk("rd_chk_nonrd"),
          capitalization_misuse: chk("rd_chk_cap"), invoice_compliance: chk("rd_chk_invoice"),
        },
      },
      reports: {
        default_period: val("rd_rep_period", "monthly"), formats: fmts,
        include: {
          summary: chk("rd_inc_summary"), by_project: chk("rd_inc_project"),
          by_category: chk("rd_inc_category"), super_deduction: chk("rd_inc_deduction"),
          capitalization: chk("rd_inc_cap"),
        },
      },
      projects: projects,
    };
  }

  async function getJSON(url) {
    const r = await fetch(url);
    return r.json();
  }
  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await r.json(); } catch (e) {}
    return { ok: r.ok && data.ok !== false, body: data };
  }

  async function load() {
    try { const r = await getJSON("/api/hub/rd"); fill(r.rd || r.default || {}); }
    catch (e) { setStatus("加载失败：" + e.message, true); }
  }
  async function save() {
    let rd;
    try { rd = collect(); }
    catch (e) { setStatus(e.message, true); return; }
    const r = await postJSON("/api/hub/rd", { rd: rd });
    if (r.ok && r.body && r.body.rd) { fill(r.body.rd); setStatus("已保存研发费用口径。", false); }
    else setStatus("保存失败：" + JSON.stringify(r.body || {}), true);
  }
  async function syncMemory() {
    try { const rd = collect(); await postJSON("/api/hub/rd", { rd: rd }); }
    catch (e) { setStatus(e.message, true); return; }
    const r = await postJSON("/api/hub/rd/sync-memory", {});
    if (r.ok) setStatus("已同步为 AI 记忆（rd-policy.md，" + ((r.body && r.body.bytes) || 0) + " 字节）。此后对话将遵循本企业口径。", false);
    else setStatus("同步失败：" + JSON.stringify(r.body || {}), true);
  }

  document.addEventListener("DOMContentLoaded", load);
  return { load: load, save: save, syncMemory: syncMemory };
})();
"""


@ar("/base-data/rd-caliber")
def rd_caliber():
    """研发费用口径配置页（原设置中心「研发费用口径设置」面板整体迁入）"""
    body = Div(
        alert_box("本页原为「设置中心 → 研发费用口径」，现已并入基础数据管理。保存后可一键同步为 AI 记忆（rd-policy.md），使对话遵循本企业口径。", "info"),

        # ① 企业基本信息
        Div(H5("① 企业基本信息", cls="rd-sec-title"),
            Div(
                Div(Label("企业名称", _for="rd_ent_name"),
                    Input(id="rd_ent_name", cls="form-input", placeholder="如：某某科技有限公司"), cls="form-col"),
                Div(Label("统一社会信用代码", _for="rd_ent_code"),
                    Input(id="rd_ent_code", cls="form-input", placeholder="18 位"), cls="form-col"),
                cls="form-row"),
            Div(
                Div(Label("所属行业", _for="rd_ent_industry"),
                    Input(id="rd_ent_industry", cls="form-input", placeholder="如：软件和信息技术服务业"), cls="form-col"),
                Div(Label("会计准则", _for="rd_ent_standard"),
                    Select(
                        Option("企业会计准则", value="企业会计准则"),
                        Option("小企业会计准则", value="小企业会计准则"),
                        id="rd_ent_standard", cls="form-select"), cls="form-col"),
                cls="form-row"),
            _rd_toggle("高新技术企业", "rd_ent_hightech"),
            _rd_toggle("科技型中小企业", "rd_ent_scisme"),
            cls="rd-section"),

        # ② 加计扣除口径
        Div(H5("② 加计扣除口径", cls="rd-sec-title"),
            Div(
                Div(Label("加计扣除比例(%)", _for="rd_tax_rate"),
                    Input(id="rd_tax_rate", type="number", cls="form-input", min="0", max="200", step="5"), cls="form-col"),
                Div(Label("其他费用限额(%)", _for="rd_tax_othercap"),
                    Input(id="rd_tax_othercap", type="number", cls="form-input", min="0", max="100", step="1"), cls="form-col"),
                cls="form-row"),
            Div(
                Div(Label("归集方式", _for="rd_tax_method"),
                    Select(
                        Option("研发支出辅助账", value="auxiliary_account"),
                        Option("研发支出专账", value="special_account"),
                        id="rd_tax_method", cls="form-select"), cls="form-col"),
                Div(Label("政策依据", _for="rd_tax_basis"),
                    Input(id="rd_tax_basis", cls="form-input", placeholder="如：财政部 税务总局公告2023年第7号"), cls="form-col"),
                cls="form-row"),
            P("可加计的费用类别（六大类）：", cls="hint-inline"),
            _rd_toggle("人员人工费用", "rd_cat_personnel"),
            _rd_toggle("直接投入费用", "rd_cat_direct"),
            _rd_toggle("折旧费用", "rd_cat_depreciation"),
            _rd_toggle("无形资产摊销", "rd_cat_amortization"),
            _rd_toggle("新产品设计费等", "rd_cat_design"),
            _rd_toggle("其他相关费用（限额）", "rd_cat_other"),
            cls="rd-section"),

        # ③ 资本化政策
        Div(H5("③ 资本化政策（研究/开发阶段）", cls="rd-sec-title"),
            _rd_toggle("研究阶段支出全部费用化", "rd_cap_research"),
            _rd_toggle("开发阶段满足条件资本化", "rd_cap_dev"),
            Div(
                Div(Label("无形资产摊销年限(年)", _for="rd_cap_years"),
                    Input(id="rd_cap_years", type="number", cls="form-input", min="1", max="40", step="1"), cls="form-col"),
                cls="form-row"),
            P("开发阶段资本化五条件将随配置一并写入 AI 记忆（企业会计准则第6号）。", cls="hint-inline"),
            cls="rd-section"),

        # ④ 风险与合规阈值
        Div(H5("④ 风险与合规阈值", cls="rd-sec-title"),
            Div(
                Div(Label("人员人工占比预警线(%)", _for="rd_risk_personnel"),
                    Input(id="rd_risk_personnel", type="number", cls="form-input", min="0", max="100", step="1"), cls="form-col"),
                Div(Label("其他费用占比预警线(%)", _for="rd_risk_other"),
                    Input(id="rd_risk_other", type="number", cls="form-input", min="0", max="100", step="1"), cls="form-col"),
                cls="form-row"),
            Div(
                Div(Label("单项目费用上限(元，0=不限)", _for="rd_risk_single"),
                    Input(id="rd_risk_single", type="number", cls="form-input", min="0", step="10000"), cls="form-col"),
                cls="form-row"),
            P("启用的合规检查项：", cls="hint-inline"),
            _rd_toggle("跨项目费用重复归集检查", "rd_chk_cross"),
            _rd_toggle("非研发人员工资计入检查", "rd_chk_nonrd"),
            _rd_toggle("资本化/费用化误用检查", "rd_chk_cap"),
            _rd_toggle("票据合规性检查", "rd_chk_invoice"),
            cls="rd-section"),

        # ⑤ 报表偏好
        Div(H5("⑤ 报表偏好", cls="rd-sec-title"),
            Div(
                Div(Label("默认周期", _for="rd_rep_period"),
                    Select(
                        Option("按月", value="monthly"),
                        Option("按季", value="quarterly"),
                        Option("按年", value="yearly"),
                        id="rd_rep_period", cls="form-select"), cls="form-col"),
                cls="form-row"),
            P("导出格式：", cls="hint-inline"),
            _rd_toggle("Excel (xlsx)", "rd_fmt_xlsx"),
            _rd_toggle("PDF", "rd_fmt_pdf"),
            P("报表包含内容：", cls="hint-inline"),
            _rd_toggle("费用汇总", "rd_inc_summary"),
            _rd_toggle("分项目明细", "rd_inc_project"),
            _rd_toggle("分费用类别", "rd_inc_category"),
            _rd_toggle("加计扣除测算", "rd_inc_deduction"),
            _rd_toggle("资本化明细", "rd_inc_cap"),
            cls="rd-section"),

        # ⑥ 在册研发项目
        Div(H5("⑥ 在册研发项目", cls="rd-sec-title"),
            P("每行一个项目，用 JSON 数组维护。字段：code(编号) / name(名称) / type(类型) / start(开始) / status(状态)。", cls="hint-inline"),
            Div(id="rd_projects_preview", cls="kv-list"),
            Textarea(id="rd_projects_json", cls="form-textarea", style="min-height:120px;font-family:monospace;",
                     placeholder='[\n  {"code":"RD-2026-001","name":"新一代算法研发","type":"自主研发","start":"2026-01","status":"进行中"}\n]'),
            cls="rd-section"),

        Div(id="rd_status", cls="form-status"),
        Div(
            Button("保存配置", cls="btn btn-primary", **{"onclick": "RdCaliber.save()"}),
            Button("同步为 AI 记忆", cls="btn btn-outline", style="margin-left:8px;",
                   title="生成 rd-policy.md 并注入 AI 记忆，让对话遵循本企业口径",
                   **{"onclick": "RdCaliber.syncMemory()"}),
            A("返回基础数据", href="/base-data", cls="btn btn-outline", style="margin-left:8px;"),
            style="margin-top:12px;",
        ),
        Script(_RD_CALIBER_JS),
        cls="card rd-caliber-page",
    )
    return page_layout(
        "研发费用口径", "首页 / 基础数据 / 研发费用口径", "/base-data",
        body,
    )
