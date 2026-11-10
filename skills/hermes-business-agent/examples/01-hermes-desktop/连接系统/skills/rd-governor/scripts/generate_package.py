#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rd-governor 自动化生成引擎
==========================
从本系统 SQLite 数据库（data/rd_expense.db）抽取研发项目 / 费用 / 人员 / 工时 /
证据等数据，套用 rd-governor 的模板，生成：
  - 三套资料包草稿：加计扣除 / 高新技术企业认定 / IPO 申报
  - 证据清单草稿
  - 内控制度与日常管理规范骨架草稿

设计原则：
  - 不编造数据：抽不到的字段明确标注「（待补：...）」。
  - 防御式 schema：先 PRAGMA 探测表与列，只取存在的列，避免硬编码崩库。
  - 函数式可导入：extract()/render_package() 可被 run_python 直接调用；
    __main__ 负责连库、读库、写 output/。

运行方式（二选一）：
  A. run_python 工具集：exec(open('scripts/generate_package.py').read()); 
     ctx = extract(); out = render_package(ctx); save_outputs(out, 'output')
  B. 系统 Python：python scripts/generate_package.py [db_path] [out_dir]
"""

from __future__ import annotations
import os
import sqlite3
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# 路径探测：在常见部署位置寻找 rd_expense.db
#   规则：从「脚本所在目录」「当前工作目录」「EXE 所在目录（frozen 模式）」向上回溯，
#   凡命中 <root>/data/rd_expense.db 或 <root>/release/data/rd_expense.db 即采用。
#   这样无论开发态（仓库根）还是出厂态（EXE 同目录 release/）都能自动定位。
# ---------------------------------------------------------------------------

def _project_root_candidates() -> list[str]:
    """生成若干「可能的项目根目录」候选（绝对路径）。"""
    cands: list[str] = []
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(here)
    # 向上回溯至多 8 层，覆盖 scripts→rd-governor→default_skills→rdapp→src→仓库根
    cur = here
    for _ in range(8):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cands.append(parent)
        cur = parent
    # 当前工作目录及其向上回溯
    cwd = os.getcwd()
    cands.append(cwd)
    cur = cwd
    for _ in range(6):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cands.append(parent)
        cur = parent
    # frozen（PyInstaller onefile）：数据库在 EXE 同目录或 EXE/release 下
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cands.append(exe_dir)
        cands.append(os.path.join(exe_dir, "release"))
    # 去重保序
    seen = set()
    out = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _db_health(path: str) -> dict | None:
    """评估候选库健康度：业务表数 / 业务数据量 / 临时表残留。失败返回 None。"""
    try:
        conn = sqlite3.connect(path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        biz = ("project", "expense", "personnel", "work_time", "evidence", "risk",
               "labor_cost", "equipment", "material_requisition",
               "outsourcing_contract", "capitalization_review", "project_node",
               "expense_subject", "organization", "policy_rule")
        biz_count = sum(1 for t in tables if t in biz)
        junk = [t for t in tables if "_new_" in t]
        cnt: dict = {}
        for t in ("project", "expense"):
            if t in tables:
                try:
                    cnt[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                except Exception:
                    cnt[t] = 0
        conn.close()
        return {"biz": biz_count, "junk": len(junk),
                "projects": cnt.get("project", 0), "expenses": cnt.get("expense", 0)}
    except Exception:
        return None


def find_db(explicit: str | None = None) -> str | None:
    """定位 rd_expense.db；显式路径优先，否则在各候选根下探测 data/ 与 release/data/，
    并兼容 Marvis 部署的 业务系统/data 布局。多库并存时按健康度评分选优：
    业务表完整、有项目/费用数据、无 _new_ 临时表残留的库优先。"""
    if explicit and os.path.exists(explicit):
        return os.path.abspath(explicit)
    candidates: list[str] = []
    for root in _project_root_candidates():
        for sub in ("data",
                    os.path.join("release", "data"),
                    os.path.join("业务系统", "data"),
                    os.path.join("business", "data")):
            p = os.path.join(root, sub, "rd_expense.db")
            if os.path.exists(p):
                candidates.append(os.path.abspath(p))
    if not candidates:
        return None
    best, best_score = None, -1
    for p in sorted(set(candidates)):
        h = _db_health(p)
        if h is None:
            continue
        score = h["biz"] * 100 + h["projects"] * 10 + h["expenses"] - h["junk"] * 50
        if score > best_score:
            best, best_score = p, score
    return best if best is not None else candidates[0]


# ---------------------------------------------------------------------------
# 防御式数据抽取
# ---------------------------------------------------------------------------
def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


def _safe_select(conn: sqlite3.Connection, table: str, cols: list[str] | None = None,
                 limit: int = 0) -> list[dict]:
    if table not in _tables(conn):
        return []
    if cols is None:
        cols = _columns(conn, table)
    if not cols:
        return []
    col_list = ", ".join(f'"{c}"' for c in cols)
    sql = f'SELECT {col_list} FROM "{table}"'
    if limit:
        sql += f" LIMIT {int(limit)}"
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []


def _tables(conn: sqlite3.Connection) -> list[str]:
    """返回连接对应的全部表名（每次按连接即时查询，避免跨库 schema 串味）。"""
    return [r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]


def extract(db_path: str | None = None) -> dict:
    """抽取数据，返回结构化上下文 dict。抽不到的字段留空。"""
    db = find_db(db_path)
    ctx: dict = {
        "db_path": db,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tables_found": [],
        "projects": [],
        "expenses": [],
        "personnel": [],
        "worktime": [],
        "evidence": [],
        "risks": [],
        "capitalization": [],
        "materials": [],
        "outsourcing": [],
        "stats": {},
        "missing": [],
    }
    if not db:
        ctx["missing"].append("未找到 rd_expense.db（请提供 db_path）")
        return ctx

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    tables = _tables(conn)
    ctx["tables_found"] = tables

    # 项目（真实列：code/name/status/budget/manager/caliber/...）
    if "project" in tables:
        cols = _columns(conn, "project")
        pick = [c for c in ("id", "code", "name", "status", "budget", "manager",
                            "start_date", "end_date", "boundary_type", "caliber",
                            "rd_nature", "annual_revenue", "hightech_income")
                if c in cols]
        ctx["projects"] = _safe_select(conn, "project", pick or cols)

    # 费用（真实列：subject_name/amount/expense_date/phase/capitalize_status/
    #        caliber/person_id/person_name/evidence_id）
    if "expense" in tables:
        cols = _columns(conn, "expense")
        pick = [c for c in ("id", "project_id", "node_id", "subject_name", "amount",
                            "expense_date", "phase", "capitalize_status", "caliber",
                            "person_id", "person_name", "evidence_id")
                if c in cols]
        ctx["expenses"] = _safe_select(conn, "expense", pick or cols)

    # 人员（真实列：org_id/title/is_rd/hourly_rate）
    if "personnel" in tables:
        cols = _columns(conn, "personnel")
        pick = [c for c in ("id", "name", "org_id", "title", "is_rd", "hourly_rate")
                if c in cols]
        ctx["personnel"] = _safe_select(conn, "personnel", pick or cols)

    # 工时（真实表名 work_time）
    if "work_time" in tables:
        ctx["worktime"] = _safe_select(conn, "work_time")

    # 证据
    if "evidence" in tables:
        ctx["evidence"] = _safe_select(conn, "evidence")

    # 风险（真实表名为单数 risk；兼容历史别名 risks）
    risk_t = next((t for t in ("risk", "risks") if t in tables), None)
    if risk_t:
        ctx["risks"] = _safe_select(conn, risk_t)

    # 资本化
    if "capitalization_review" in tables:
        ctx["capitalization"] = _safe_select(conn, "capitalization_review")

    # 材料
    if "material_requisition" in tables:
        ctx["materials"] = _safe_select(conn, "material_requisition")

    # 委外
    if "outsourcing_contract" in tables:
        ctx["outsourcing"] = _safe_select(conn, "outsourcing_contract")

    conn.close()

    # 汇总统计（防御式：列存在才算）
    ctx["stats"] = _compute_stats(ctx)
    return ctx


def _compute_stats(ctx: dict) -> dict:
    s: dict = {}
    s["project_count"] = len(ctx["projects"])
    s["expense_count"] = len(ctx["expenses"])
    s["personnel_count"] = len(ctx["personnel"])

    # 费用总额
    amt_col = None
    for c in ("amount", "money", "sum"):
        if ctx["expenses"] and c in ctx["expenses"][0]:
            amt_col = c
            break
    if amt_col:
        try:
            s["expense_total"] = round(sum(float(e.get(amt_col) or 0) for e in ctx["expenses"]), 2)
        except Exception:
            s["expense_total"] = None
    else:
        s["expense_total"] = None
        s.setdefault("_notes", []).append("费用表无金额列，未计算总额")

    # 按科目汇总（费用科目实际列名为 subject_name；兼容旧的 category/subject/type）
    cat_col = None
    for c in ("subject_name", "category", "subject", "type"):
        if ctx["expenses"] and c in ctx["expenses"][0]:
            cat_col = c
            break
    if cat_col and amt_col:
        by_cat: dict = {}
        for e in ctx["expenses"]:
            k = e.get(cat_col) or "未分类"
            by_cat[k] = round(by_cat.get(k, 0) + float(e.get(amt_col) or 0), 2)
        s["by_category"] = by_cat
    else:
        s["by_category"] = {}

    # 研发人员数
    rd_col = None
    for c in ("is_rd", "is_research", "rd_flag"):
        if ctx["personnel"] and c in ctx["personnel"][0]:
            rd_col = c
            break
    if rd_col:
        s["rd_personnel"] = sum(1 for p in ctx["personnel"]
                                if str(p.get(rd_col)).lower() in ("1", "true", "yes", "y"))
    else:
        s["rd_personnel"] = None

    # 证据缺口
    ev_col = None
    for c in ("evidence_id", "evidence"):
        if ctx["expenses"] and c in ctx["expenses"][0]:
            ev_col = c
            break
    if ev_col:
        s["expense_without_evidence"] = sum(
            1 for e in ctx["expenses"] if not e.get(ev_col))
    else:
        s["expense_without_evidence"] = None

    # 加计扣除 / 高企 合规测算（依赖 expense 的 caliber / subject_name / phase）
    exps = ctx.get("expenses", [])
    caliber_col = next((c for c in ("caliber",) if exps and c in exps[0]), None)
    subj_col = next((c for c in ("subject_name", "category", "subject") if exps and c in exps[0]), None)
    phase_col = next((c for c in ("phase",) if exps and c in exps[0]), None)
    if caliber_col and subj_col and amt_col:
        entrusted_kw = ("委托", "委外", "外包")
        deduc_base = other_deduct = hitech_base = other_hitech = rd_exp = 0.0
        deduc_hit = False
        for e in exps:
            cal = e.get(caliber_col) or ""
            subj = e.get(subj_col) or ""
            amt = float(e.get(amt_col) or 0)
            ph = e.get(phase_col) if phase_col else ""
            if "加计扣除" in cal:
                deduc_hit = True
                deduc_base += amt * 0.8 if any(k in subj for k in entrusted_kw) else amt
                if subj == "其他费用":
                    other_deduct += amt
            if "高企认定" in cal:
                hitech_base += amt
                if subj == "其他费用":
                    other_hitech += amt
            if ph in ("研究", "开发"):
                rd_exp += amt
        overseas = sum(float(o.get("actual_amount") or 0)
                       for o in ctx.get("outsourcing", []) if o.get("is_overseas"))
        if not deduc_hit:
            # 无任何"加计扣除"口径费用：不得给出"未超出"等合规结论
            s["deduct_base"] = None
            s["other_deduct"] = None
            s["deduct_other_limit"] = None
            s["deduct_over_limit"] = None
        else:
            s["deduct_base"] = round(deduc_base, 2)
            s["other_deduct"] = round(other_deduct, 2)
            # 其他相关费用 10% 限额（税务总局公告2017年第40号）：
            # 限额 =（可加计总额 − 其他相关费用）× 10% ÷ (1 − 10%)
            deduct_limit = (deduc_base - other_deduct) * 0.10 / 0.90 if deduc_base > other_deduct else 0.0
            s["deduct_other_limit"] = round(deduct_limit, 2)
            s["deduct_over_limit"] = bool(other_deduct > deduct_limit + 0.005)
        s["hitech_base"] = round(hitech_base, 2)
        s["other_hitech"] = round(other_hitech, 2)
        s["rd_exp_total"] = round(rd_exp, 2)
        s["overseas_entrusted"] = round(overseas, 2)
        s["domestic_rd_ratio"] = round((rd_exp - overseas) / rd_exp, 4) if rd_exp else None
        s["other_ratio_deduct"] = round(other_deduct / deduc_base, 4) if deduc_base else None
        s["other_ratio_hitech"] = round(other_hitech / hitech_base, 4) if hitech_base else None
        rd_p = s.get("rd_personnel")
        pc = s.get("personnel_count")
        s["rd_personnel_ratio"] = round(rd_p / pc, 4) if (rd_p and pc) else None
        # 科技人员占比（高企口径：科技人员 ÷ 职工总数）。人员表无科技人员标记、职工总数无外部来源，
        # 口径不可得时置 None，渲染端显示（待补），不得用研发人员占比冒充。
        s["tech_personnel"] = None
        s["tech_ratio"] = None
    return s


# ---------------------------------------------------------------------------
# 渲染（纯字符串模板，不依赖 jinja）
# ---------------------------------------------------------------------------
def _fmt(v, default="（待补）"):
    if v is None or v == "":
        return default
    return str(v)


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "（无数据 / 待补）\n"
    w = ["| " + " | ".join(headers) + " |"]
    w.append("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows:
        w.append("| " + " | ".join(_fmt(c) for c in r) + " |")
    return "\n".join(w) + "\n"


def render_package(ctx: dict) -> dict:
    """返回 {文件名: 内容}。"""
    out: dict = {}
    g = ctx.get("generated_at", "")
    dbp = ctx.get("db_path") or "（未定位）"
    stats = ctx.get("stats", {})

    # ---- 研发项目概览 ----
    proj_rows = [[_fmt(p.get("code")), _fmt(p.get("name")), _fmt(p.get("status")),
                  _fmt(p.get("budget")), _fmt(p.get("manager"))]
                 for p in ctx.get("projects", [])[:50]]
    proj_md = "# 研发项目概览\n\n" + _table(
        ["编号", "名称", "状态", "预算", "负责人"], proj_rows)

    # ---- 费用按科目 ----
    by_cat = stats.get("by_category", {})
    cat_rows = [[k, v] for k, v in by_cat.items()] or [["（无数据）", "（待补）"]]
    cat_md = "# 研发费用按科目归集\n\n" + _table(["科目", "金额"], cat_rows)

    # ---- 证据缺口提示 ----
    gap = stats.get("expense_without_evidence")
    gap_md = (f"无证据关联的费用记录数：**{_fmt(gap, '未知')}** "
              f"（evidence_id 为空属高风险，须补齐）。\n" if gap is not None
              else "（费用表无 evidence_id 列，无法判定证据缺口）\n")

    # ---- 加计扣除资料包 ----
    out["加计扣除资料包.md"] = f"""# 研发费用加计扣除资料包（草稿）

> 自动生成于 {g}　数据来源：{dbp}
> 本文件为草稿，最终以税务师口径与 A107012 申报表为准。

## 一、可加计扣除研发费用归集（财税〔2015〕119号 / 2023第7号 100%）

{cat_md}

## 二、证据齐备性
{gap_md}
其他相关费用不得超过可加计总额的 10%；委托研发按实际发生额 80% 计入（境外有限额）。

### 其他相关费用 10% 限额测算（财税〔2015〕119号 / 税务总局公告2017年第40号）
> 限额 =（可加计总额 − 其他相关费用）× 10% ÷ (1 − 10%)，按总局 2017 年第 40 号口径计算。
- 可加计基数：¥{_fmt(stats.get('deduct_base'), '（数据不足，无法测算）')}
- 其他相关费用：¥{_fmt(stats.get('other_deduct'), '（数据不足，无法测算）')}
- 10% 限额：¥{_fmt(stats.get('deduct_other_limit'), '（数据不足，无法测算）')}
- 结论：{('（数据不足，无法测算）' if stats.get('deduct_base') is None else ('（无加计口径费用，请核对归集口径）' if stats.get('deduct_base') == 0 else ('⚠ 已超出限额，超出部分不得加计' if stats.get('deduct_over_limit') else '✓ 未超出，可全额加计')))}

## 三、辅助账与申报表
- 辅助账（按项目按科目）：见 references/templates/03-forms/forms.md 表单 8，须与系统 expenses 一致。
- 申报表：A107012 研发费用加计扣除优惠明细表。

## 四、待补资料
- 立项决议、研发合同、工时记录、领料单、发票等纸质佐证（回写 /evidence 模块）。
- 其他相关费用明细（会议/差旅/检测）及其 10% 限额计算。
"""

    # ---- 高企认定资料包 ----
    rd_p = stats.get("rd_personnel")
    out["高企认定资料包.md"] = f"""# 高新技术企业认定研发费用资料包（草稿）

> 自动生成于 {g}　数据来源：{dbp}
> 本文件为草稿，最终以国科发火〔2016〕195号工作指引与专项审计为准。

## 一、研发费用归集
{cat_md}

## 二、人员结构
- 人员总数（档案）：{_fmt(stats.get('personnel_count'), '未知')}
- 研发人员数：{_fmt(rd_p, '未知（人员表无 is_rd 列）')}
- 研发人员占档案人数比（参考，非高企认定口径）：{f"{stats['rd_personnel_ratio']*100:.1f}%" if stats.get('rd_personnel_ratio') is not None else '（待补）'}
- 科技人员占比要求：≥10%

## 三、占比达标判定（国科发火〔2016〕195号）
- 销售收入≤5000万：研发费用占比≥5%
- 5000万–2亿：≥4%
- >2亿：≥3%
- 境内研发费用占比≥60%（当前测算：{f"{stats['domestic_rd_ratio']*100:.1f}%" if stats.get('domestic_rd_ratio') is not None else '（待补：未录入境外委托研发费用）'}）
- 科技人员占比≥10%（当前测算：{f"{stats['tech_ratio']*100:.1f}%" if stats.get('tech_ratio') is not None else '（待补：人员表无科技人员标记且职工总数未录入，无法测算）'}）
- 其他费用占比（高企）：≤20%（当前测算：{f"{stats['other_ratio_hitech']*100:.1f}%" if stats.get('other_ratio_hitech') is not None else '（待补）'}）

## 四、待补资料
- 近三年销售收入、研发费用专项审计数据（本系统默认取当前库，须补充历史年度）。
- 知识产权与项目关联性说明。
- 高新技术产品（服务）收入占比≥60% 证明。
"""

    # ---- IPO 申报资料包 ----
    out["IPO申报资料包.md"] = f"""# IPO 申报研发费用资料包（草稿）

> 自动生成于 {g}　数据来源：{dbp}
> 本文件为草稿，最终以保荐机构、审计师核查口径为准。

## 一、研发费用真实性（五流合一）
{cat_md}
{gap_md}

## 二、资本化合规性
- 资本化审批记录数：{_fmt(len(ctx.get('capitalization', [])))}
- 须逐项目核对《企业会计准则第6号》6 条件，留存技术可行性与测试报告。

## 三、研发人员认定
- 研发人员数：{_fmt(rd_p, '未知')}
- 须核实身份、工时、薪酬归集方法。

## 四、核查底稿（报表4）
- 合同—发票—工时—领料—验收 勾稽
- 费用跨期（截止测试）、关联方交易、同行业可比

## 五、内控制度有效性
- 引用工作流 A《研发费用内部控制制度》及执行记录（policies / risks 表）。

## 六、待补资料
- 中介机构核查程序与结论支持性文件。
- 同行业可比公司研发费用占比对比数据。
"""

    # ---- 证据清单草稿 ----
    out["证据清单草稿.md"] = f"""# 研发证据清单草稿（工作流 B）

> 自动生成于 {g}

{proj_md}

## 费用与证据关联
{gap_md}

## 三套资料证据核对（详见 references/templates/03-forms/evidence-checklist.md）
- 加计扣除：立项/合同/工时/领料/发票/辅助账/成果
- 高企：近三年归集/人员占比/知识产权关联/领域符合
- IPO：五流合一/内控有效/资本化合规/人员认定/跨期/关联方

请将缺失项回写 /evidence 模块（POST /evidence），并可导出 PDF。
"""

    # ---- 制度与规范骨架 ----
    out["内控制度骨架.md"] = f"""# 研发费用内部控制制度（自动骨架）

> 自动生成于 {g}　企业画像：项目 {_fmt(stats.get('project_count'))} 个 / 费用 {_fmt(stats.get('expense_count'))} 笔 / 人员 {_fmt(stats.get('personnel_count'))} 人
> 请基于 references/templates/01-regulations/internal-control-system.md 逐章填充并补法规引用。

## 总则 / 职责 / 立项 / 预算 / 归集核算 / 资本化 / 资产合同 / 监督考核 / 附则
（逐章模板见 references/templates/01-regulations/internal-control-system.md，本处仅列章节骨架，待人工润色定稿）
"""
    out["日常管理规范骨架.md"] = f"""# 研发费用日常管理规范（自动骨架）

> 自动生成于 {g}
> 请基于 references/templates/02-processes/daily-management-spec.md 与 references/templates/03-forms/forms.md 填充审批矩阵与归档周期。

## 表单流转 / 审批权限 / 归档周期 / 数据质量检查 / 责任追究
（逐节模板见 daily-management-spec.md，待人工润色定稿）
"""

    # ---- 政策依据与免责声明（rd-governor 红三线：引用须标注依据[文件/文号]）----
    out["政策依据与免责声明.md"] = f"""# 政策依据与免责声明

> 自动生成于 {g}

## 一、主要政策依据
- 《财政部 国家税务总局 科技部关于完善研究开发费用税前加计扣除政策的通知》（财税〔2015〕119号）
- 《国家税务总局关于研发费用税前加计扣除归集范围有关问题的公告》（国家税务总局公告2017年第40号）
- 《关于进一步完善研发费用税前加计扣除政策的公告》（财政部 税务总局公告2023年第7号，现行按100%加计）
- 《高新技术企业认定管理办法》（国科发火〔2016〕32号）
- 《高新技术企业认定管理工作指引》（国科发火〔2016〕195号）
- 《企业会计准则第6号——无形资产》（研究开发支出资本化/费用化）

## 二、免责声明
本套资料包由研发费用管理系统依据公开税收政策自动归集与测算生成，结果仅供参考，
不构成税务、审计或法律意见；最终以税务机关、科技主管部门或具备资质的会计师事务所
审核认定为准。请勿直接作为申报或披露文件提交。
"""
    return out


def save_outputs(out: dict, out_dir: str = "output") -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, content in out.items():
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(os.path.abspath(path))
    return written


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    ctx = extract(db_path)
    if not ctx["db_path"]:
        print("[rd-governor] 未找到数据库，请传入 db_path 参数。", file=sys.stderr)
        print("用法: python generate_package.py <db_path> [out_dir]", file=sys.stderr)
        return 1
    out = render_package(ctx)
    written = save_outputs(out, out_dir)
    print(f"[rd-governor] 已生成 {len(written)} 个文件到 {os.path.abspath(out_dir)}:")
    for w in written:
        print("  -", w)
    if ctx["stats"].get("expense_without_evidence"):
        print(f"[提示] 有 {ctx['stats']['expense_without_evidence']} 笔费用缺证据关联，请补齐。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
