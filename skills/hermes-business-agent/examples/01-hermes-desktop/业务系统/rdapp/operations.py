"""operations.py — Agent 可执行的系统操作层

把「研发费用管理系统」的全部数据操作暴露为一组结构化工具，供 Agent 在对话中
自主调用（工具调用 / function calling）。设计原则：

- 单一通用工具 `db_operation` 覆盖所有实体的 增删改查（list/get/create/update/delete），
  避免为 17 张表各写一套 schema；`fields` / `filters` 为自由对象，由调度器按实体
  白名单过滤后安全落库。
- 引用解析：调用方可传 `project_code` / `project_name` / `person_name` / `subject_name`
  等人性化键，调度器自动解析为对应 id，降低模型出错率。
- 费用归集走 `db.add_expense`，自动补全 节点 / 阶段 / 资本化状态，保证口径正确。
- 合规分析工具（`analyze_project` / `analyze_metrics` / `analyze_capitalization` /
  `dashboard_summary`）复用 db.py 既有计算逻辑，给出结构化结论。
- 所有写操作均返回人类可读的摘要，便于模型向用户复述「执行结果」。

工具 schemas 通过 `AGENT_TOOLS` 导出，直接随 /v1/chat/completions 下发。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from . import db


# ── 实体注册表 ──────────────────────────────────────────────
# 每个实体：表对象 + 中文名 + 创建必需字段 + 可写字段（白名单）+ 摘要函数
def _proj_label(r):
    return f"研发项目 #{r.id}「{r.name}」({r.code})"


def _exp_label(r):
    return f"费用记录 #{r.id}：{r.expense_date} {r.subject_name} ¥{r.amount:,.0f}（{r.phase}/{r.capitalize_status}）"


def _wt_label(r):
    return f"工时 #{r.id}：人员 {r.person_id} 项目 {r.project_id} {r.work_date} {r.hours}h"


def _eq_label(r):
    return f"设备 #{r.id}「{r.name}」({r.code})"


def _mat_label(r):
    return f"材料领用 #{r.id}「{r.material_name}」×{r.quantity}{r.unit} ¥{r.amount:,.0f}"


def _out_label(r):
    return f"委托研发 #{r.id}（{r.contract_no}）受托方 {r.contractor} ¥{r.actual_amount:,.0f}"


def _oth_label(r):
    return f"其他费用 #{r.id}：{r.category} ¥{r.amount:,.0f}"


def _risk_label(r):
    return f"风险 #{r.id}（{r.level}）{r.risk_type}"


def _ev_label(r):
    return f"证据 #{r.id}：{r.ev_type}「{r.name}」"


def _cap_label(r):
    return f"资本化审批 #{r.id}（项目 {r.project_id}/费用 {r.expense_id}）状态 {r.status}"


def _si_label(r):
    return f"特殊收入 #{r.id}：{r.income_type} ¥{r.amount:,.0f}"


def _ss_label(r):
    return f"样品废料 #{r.id}：{r.item_type}「{r.name}」"


def _en_label(r):
    return f"受托研发 #{r.id}（{r.contract_no}）委托方 {r.entrustor} ¥{r.contract_amount:,.0f}"


def _per_label(r):
    return f"人员 #{r.id}「{r.name}」（{r.title}）"


def _lc_label(r):
    return f"人工总账 #{r.id}：人员 {r.person_id} {r.cost_month} ¥{r.total_salary:,.0f}"


def _act_label(r):
    return f"研发活动 #{r.id}：「{getattr(r, 'node_name', '')}」项目{r.project_id}（{getattr(r, 'phase', '')}/{getattr(r, 'status', '')}）"


def _ed_label(r):
    return f"设备折旧 #{r.id}：设备 {r.equipment_id} {r.cost_month} ¥{r.monthly_depreciation:,.0f}"


def _ewt_label(r):
    return f"设备工时 #{r.id}：设备 {r.equipment_id} 项目 {r.project_id} {r.work_date} {r.hours}h"


ENTITY_MAP = {
    "projects":             {"tb": db.projects_tb,            "label": "研发项目",     "required": ["name", "code"],
                             "columns": ["name","code","status","template_id","budget","start_date","end_date","boundary_type","boundary_desc","rd_split_ratio","annual_revenue","hightech_income","manager","caliber","description","rd_nature","research_end","develop_end"],
                             "summary": _proj_label},
    "expenses":             {"tb": db.expenses_tb,            "label": "费用记录",     "required": ["project_id", "amount", "expense_date"],
                             "columns": ["project_id","node_id","subject_id","subject_name","amount","expense_date","phase","capitalize_status","caliber","person_id","person_name","description","source"],
                             "brief": ["expense_date","amount","project_id","subject_name","phase","capitalize_status"],
                             "summary": _exp_label},
    "worktime":             {"tb": db.work_time_tb,           "label": "工时登记",     "required": ["person_id", "project_id", "work_date", "hours"],
                             "columns": ["person_id","project_id","work_date","hours","task_desc"],
                             "summary": _wt_label},
    "equipment":            {"tb": db.equipment_tb,           "label": "研发设备",     "required": ["name"],
                             "columns": ["code","name","category","model","acquisition_date","acquisition_cost","depreciation_method","useful_life","monthly_depreciation","status","dept_id"],
                             "summary": _eq_label},
    "materials":            {"tb": db.material_requisition_tb,"label": "原材料领用",   "required": ["material_name", "quantity", "unit_price", "project_id"],
                             "columns": ["material_name","specification","unit","quantity","unit_price","amount","project_id","requisition_date","requisitioner_id","purpose","usage_status"],
                             "summary": _mat_label},
    "outsourcing":          {"tb": db.outsourcing_tb,         "label": "委托外部研发", "required": ["contract_no", "contractor", "project_id", "actual_amount"],
                             "columns": ["contract_no","contractor","project_id","contract_amount","actual_amount","caliber","has_tech_transfer","is_overseas","expense_date","description"],
                             "summary": _out_label},
    "others":               {"tb": db.other_expense_tb,       "label": "其他费用",     "required": ["project_id", "category", "amount", "expense_date"],
                             "columns": ["project_id","category","expense_date","amount","description","caliber"],
                             "summary": _oth_label},
    "risks":                {"tb": db.risks_tb,               "label": "风险预警",     "required": ["project_id", "level", "risk_type", "description"],
                             "columns": ["project_id","level","risk_type","description","status","suggestion"],
                             "summary": _risk_label},
    "evidence":             {"tb": db.evidence_tb,            "label": "证据材料",     "required": ["project_id", "ev_type", "name"],
                             "columns": ["project_id","node_id","ev_type","name","phase","upload_date","description"],
                             "summary": _ev_label},
    "capitalization":       {"tb": db.capitalization_tb,      "label": "资本化审批",   "required": ["project_id", "expense_id"],
                             "columns": ["project_id","expense_id","cond_tech","cond_intent","cond_usable","cond_benefit","cond_measure","feasibility_evidence_id","reviewer","decided_at","status","note"],
                             "summary": _cap_label},
    "special_income":       {"tb": db.special_income_tb,      "label": "特殊收入",     "required": ["project_id", "income_type", "amount"],
                             "columns": ["project_id","income_type","amount","income_date","offset_caliber","note"],
                             "summary": _si_label},
    "sample_scrap":         {"tb": db.sample_scrap_tb,        "label": "样品废料",     "required": ["project_id", "name", "item_type"],
                             "columns": ["project_id","item_type","name","quantity","unit","disposal","realized_amount","record_date","note"],
                             "summary": _ss_label},
    "entrusted":            {"tb": db.entrusted_tb,           "label": "受托研发",     "required": ["contract_no", "entrustor", "project_id", "contract_amount"],
                             "columns": ["contract_no","entrustor","project_id","contract_amount","recognized_revenue","our_rd_cost","caliber","status","sign_date","note"],
                             "summary": _en_label},
    "personnel":            {"tb": db.personnel_tb,           "label": "人员档案",     "required": ["name"],
                             "columns": ["name","org_id","title","is_rd","hourly_rate"],
                             "summary": _per_label},
    "labor_cost":           {"tb": db.labor_cost_tb,          "label": "人工费用总账", "required": ["person_id", "cost_month", "total_salary"],
                             "columns": ["person_id","cost_month","total_salary","social_insurance","housing_fund","work_hours_total","non_rd_hours","hourly_cost","status"],
                             "summary": _lc_label},
    "activities":           {"tb": db.project_nodes_tb,       "label": "研发活动",     "required": ["project_id", "node_name"],
                             "columns": ["project_id","node_id","node_name","phase","status","assignee","start_date","end_date","deliverable_status","budget_ratio"],
                             "summary": _act_label},
    "equipment_depreciation":{"tb": db.equipment_depreciation_tb,"label": "设备折旧总账","required": ["equipment_id", "cost_month", "monthly_depreciation"],
                             "columns": ["equipment_id","cost_month","monthly_depreciation","rd_usage_ratio","allocated_hours_total","status"],
                             "summary": _ed_label},
    "equipment_worktime":   {"tb": db.equipment_work_time_tb,"label": "设备工时",     "required": ["equipment_id", "project_id", "work_date", "hours"],
                             "columns": ["equipment_id","project_id","work_date","hours","task_desc"],
                             "summary": _ewt_label},
}

# 需经 db.add_expense 落库、自动补阶段/资本化的实体
_EXPENSE_AUTO_ENTITIES = {"expenses"}

# 引用解析键 → (表, id字段, 名称字段)
_REF_RESOLVERS = {
    "project_code": (db.projects_tb, "code", "project_id"),
    "project_name": (db.projects_tb, "name", "project_id"),
    "person_name":  (db.personnel_tb, "name", "person_id"),
    "subject_name": (db.subjects_tb, "name", "subject_id"),
}


def _resolve_refs(fields: dict) -> list[str]:
    """把 project_code/name、person_name、subject_name 解析为对应 id。

    返回解析说明列表（用于结果回显）。解析失败的键会从 fields 中剔除并提示。
    """
    notes = []
    for key, (tb, match_col, id_col) in _REF_RESOLVERS.items():
        if key in fields:
            val = fields.pop(key)
            if val in (None, ""):
                continue
            rows = tb()
            match = None
            for r in rows:
                cell = getattr(r, match_col, None)
                if cell is not None and str(cell) == str(val):
                    match = r
                    break
            if match is None and match_col == "name":
                # 名称允许包含匹配（更宽松）
                for r in rows:
                    cell = getattr(r, match_col, None)
                    if cell and val in str(cell):
                        match = r
                        break
            if match is not None:
                fields[id_col] = match.id
                if id_col == "subject_id":
                    fields["subject_name"] = getattr(match, "name", "")
                notes.append(f"已解析 {key}={val!r} → {id_col}={match.id}")
            else:
                notes.append(f"⚠️ 未找到 {key}={val!r} 的对应记录，请确认后重试")
    return notes


def _clean_fields(entity: str, fields: dict) -> tuple[dict, list[str]]:
    """按实体白名单过滤字段，自动解析引用，并对 materials 自动算金额。

    注意：引用键（project_code / project_name / person_name / subject_name）可能不在
    可写字段白名单中，因此必须先解析引用（会写入对应 *_id 并剔除引用键），再按白名单过滤。
    """
    meta = ENTITY_MAP[entity]
    allowed = set(meta["columns"])
    # 1) 先解析引用（直接作用于原始 fields，写入 *_id 并剔除引用键）
    notes = _resolve_refs(fields)
    # 2) 再按白名单过滤
    cleaned = {k: v for k, v in (fields or {}).items() if k in allowed}
    if entity == "materials" and "amount" not in cleaned:
        q = cleaned.get("quantity")
        p = cleaned.get("unit_price")
        if isinstance(q, (int, float)) and isinstance(p, (int, float)):
            cleaned["amount"] = round(q * p, 2)
    return cleaned, notes


def _row_to_dict(row) -> dict:
    d = {}
    for k in dir(row):
        if k.startswith("_"):
            continue
        try:
            v = getattr(row, k)
        except Exception:
            continue
        if callable(v):
            continue
        d[k] = v
    return d


def db_operation(action: str, entity: str, id: int = None, fields: dict = None,
                 filters: dict = None) -> dict:
    """通用数据操作：list / get / create / update / delete。

    返回统一结构：{"ok": bool, "action", "entity", "id"?, "summary"?, "rows"?, "count"?, "notes"?}
    """
    if entity not in ENTITY_MAP:
        return {"ok": False, "error": f"未知实体：{entity}", "available": sorted(ENTITY_MAP.keys())}
    meta = ENTITY_MAP[entity]
    tb = meta["tb"]
    action = (action or "").lower()

    if action == "list":
        rows = tb()
        if filters:
            rows = [r for r in rows if _match_filters(r, filters)]
        total_matched = len(rows)
        rows = rows[:300]
        brief_cols = meta.get("brief") or []
        out = []
        for r in rows:
            item = {"id": r.id, "summary": meta["summary"](r)}
            for c in brief_cols:
                try:
                    item[c] = getattr(r, c, None)
                except Exception:
                    item[c] = None
            out.append(item)
        return {"ok": True, "action": "list", "entity": entity, "count": len(out),
                "total_matched": total_matched, "rows": out}

    if action == "get":
        if not id:
            return {"ok": False, "error": "get 操作需要 id"}
        try:
            r = tb[id]
        except Exception:
            return {"ok": False, "error": f"未找到 {entity} id={id}"}
        return {"ok": True, "action": "get", "entity": entity, "id": id,
                "summary": meta["summary"](r), "data": _row_to_dict(r)}

    if action == "create":
        cleaned, notes = _clean_fields(entity, fields or {})
        missing = [c for c in meta["required"] if c not in cleaned or cleaned.get(c) in (None, "")]
        if missing:
            return {"ok": False, "error": f"缺少必填字段：{missing}", "required": meta["required"], "notes": notes}
        try:
            if entity in _EXPENSE_AUTO_ENTITIES:
                # 自动补全阶段 / 资本化状态（无显式给定时）
                if not cleaned.get("phase") and cleaned.get("project_id") and cleaned.get("expense_date"):
                    cleaned["phase"] = db.phase_for_date(cleaned["project_id"], cleaned["expense_date"])
                if not cleaned.get("capitalize_status") and cleaned.get("phase"):
                    cleaned["capitalize_status"] = db.capitalize_status_for_phase(cleaned["phase"])
                row = db.add_expense(**cleaned)
            else:
                row = tb.insert(**cleaned)
        except Exception as e:
            return {"ok": False, "error": f"创建失败：{e}", "notes": notes}
        return {"ok": True, "action": "create", "entity": entity, "id": row.id,
                "summary": meta["summary"](row), "notes": notes}

    if action == "update":
        if not id:
            return {"ok": False, "error": "update 操作需要 id"}
        cleaned, notes = _clean_fields(entity, fields or {})
        if not cleaned:
            return {"ok": False, "error": "update 没有任何可写字段", "notes": notes}
        try:
            row = tb[id]
            if row is None:
                return {"ok": False, "error": f"未找到 {entity} id={id}"}
            for k, v in cleaned.items():
                setattr(row, k, v)
            tb.update(row)
            r = tb[id]
        except Exception as e:
            return {"ok": False, "error": f"更新失败：{e}", "notes": notes}
        return {"ok": True, "action": "update", "entity": entity, "id": id,
                "summary": meta["summary"](r), "notes": notes}

    if action == "delete":
        if not id:
            return {"ok": False, "error": "delete 操作需要 id"}
        try:
            before = tb[id]
            label = meta["summary"](before) if before else f"{entity}#{id}"
        except Exception:
            before = None
            label = f"{entity}#{id}"
        if before is None:
            return {"ok": False, "error": f"未找到 {entity} id={id}"}
        try:
            tb.delete(id)
        except Exception as e:
            return {"ok": False, "error": f"删除失败：{e}"}
        return {"ok": True, "action": "delete", "entity": entity, "id": id,
                "summary": f"已删除：{label}"}

    return {"ok": False, "error": f"不支持的 action：{action}", "supported": ["list", "get", "create", "update", "delete"]}


def _match_filters(row, filters: dict) -> bool:
    for k, v in filters.items():
        rv = getattr(row, k, None)
        if rv is None:
            if v in (None, "", "null"):
                continue
            return False
        if isinstance(v, str) and isinstance(rv, str):
            if v.lower() not in rv.lower():
                return False
        elif str(rv) != str(v):
            return False
    return True


# ── 合规分析工具 ──────────────────────────────────────────────

def _resolve_project(pid):
    """支持 id / code / name 解析为项目对象。"""
    if pid is None:
        return None
    if isinstance(pid, int):
        try:
            return db.projects_tb[pid]
        except Exception:
            return None
    s = str(pid)
    for p in db.projects_tb():
        if p.code == s or p.id == s or (s and s in p.name):
            return p
    return None


def analyze_project(pid) -> dict:
    """预算执行分析：归集额、阶段分布、科目分布、预算执行率。"""
    p = _resolve_project(pid)
    if not p:
        return {"ok": False, "error": f"未找到项目：{pid}"}
    exps = [e for e in db.expenses_tb() if e.project_id == p.id]
    total = sum(e.amount for e in exps)
    by_phase = {}
    by_subject = {}
    for e in exps:
        by_phase[e.phase] = by_phase.get(e.phase, 0) + e.amount
        by_subject[e.subject_name] = by_subject.get(e.subject_name, 0) + e.amount
    rate = (total / p.budget) if p.budget else None
    return {
        "ok": True,
        "project": {"id": p.id, "name": p.name, "code": p.code, "budget": p.budget,
                    "status": p.status, "boundary_type": p.boundary_type},
        "collected_total": round(total, 2),
        "budget_execution_rate": round(rate, 4) if rate is not None else None,
        "by_phase": {k: round(v, 2) for k, v in by_phase.items()},
        "by_subject": {k: round(v, 2) for k, v in by_subject.items()},
        "expense_count": len(exps),
    }


def analyze_metrics(pid) -> dict:
    """高企认定 / 加计扣除比例指标（复用 db.metrics_for_project）。"""
    p = _resolve_project(pid)
    if not p:
        return {"ok": False, "error": f"未找到项目：{pid}"}
    try:
        m = db.metrics_for_project(p.id)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "project": {"id": p.id, "name": p.name, "code": p.code}, "metrics": m}


def analyze_capitalization(expense_id: int) -> dict:
    """某笔「待资本化」费用是否满足 5 条件审批（复用 db.capitalizable_ready）。"""
    if not expense_id:
        return {"ok": False, "error": "需要 expense_id"}
    try:
        passed, review = db.capitalizable_ready(int(expense_id))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "expense_id": int(expense_id),
        "capitalizable": passed,
        "review": _row_to_dict(review) if review else None,
    }


def dashboard_summary() -> dict:
    """企业级总览。"""
    projects = db.projects_tb()
    expenses = db.expenses_tb()
    risks = db.risks_tb()
    return {
        "ok": True,
        "project_count": len(projects),
        "expense_count": len(expenses),
        "expense_total": round(sum(e.amount for e in expenses), 2),
        "unhandled_risks": len([r for r in risks if r.status == "待处理"]),
        "projects": [{"id": p.id, "name": p.name, "code": p.code, "budget": p.budget,
                      "status": p.status} for p in projects],
    }


def analyze_expense_trend(start_month: str = None, end_month: str = None,
                          project=None, subject: str = None) -> dict:
    """费用月度趋势与异常波动分析。

    - 按 expense_date 前 7 位（YYYY-MM）聚合每月费用总额 / 笔数 / 科目分布；
    - 计算环比变化率（MoM）与均值/标准差 z-score；
    - 异常判定：|z| ≥ 2（显著偏离历史均值）或 |环比| ≥ 50%（且金额非微小）。
    支持按项目（id/code/名称）与科目名称过滤，支持 start_month/end_month 截取区间。
    """
    proj = None
    if project not in (None, ""):
        proj = _resolve_project(project)
        if not proj:
            return {"ok": False, "error": f"未找到项目：{project}"}

    exps = list(db.expenses_tb())
    if proj:
        exps = [e for e in exps if e.project_id == proj.id]
    if subject:
        exps = [e for e in exps if subject in (e.subject_name or "")]

    monthly: dict[str, dict] = {}
    for e in exps:
        d = (e.expense_date or "")[:7]
        if len(d) != 7:
            continue
        if start_month and d < start_month[:7]:
            continue
        if end_month and d > end_month[:7]:
            continue
        m = monthly.setdefault(d, {"month": d, "total": 0.0, "count": 0, "by_subject": {}})
        m["total"] += e.amount
        m["count"] += 1
        sn = e.subject_name or "未分类"
        m["by_subject"][sn] = m["by_subject"].get(sn, 0.0) + e.amount

    if not monthly:
        return {"ok": True, "months": [], "anomalies": [],
                "note": "指定范围内没有费用记录（请检查月份区间 / 项目 / 科目过滤条件）"}

    months = sorted(monthly.keys())
    series = []
    totals = []
    for i, mk in enumerate(months):
        m = monthly[mk]
        total = round(m["total"], 2)
        totals.append(total)
        prev = round(monthly[months[i - 1]]["total"], 2) if i > 0 else None
        mom = round((total - prev) / prev, 4) if prev else None
        top_subjects = sorted(m["by_subject"].items(), key=lambda kv: -kv[1])[:5]
        series.append({
            "month": mk, "total": total, "count": m["count"],
            "mom_change": mom,
            "by_subject": {k: round(v, 2) for k, v in top_subjects},
        })

    n = len(totals)
    mean = sum(totals) / n
    std = (sum((t - mean) ** 2 for t in totals) / n) ** 0.5 if n > 1 else 0.0

    anomalies = []
    for i, item in enumerate(series):
        reasons = []
        z = (item["total"] - mean) / std if std > 0 else 0.0
        if n >= 3 and abs(z) >= 2:
            reasons.append(f"金额 ¥{item['total']:,.0f} 偏离 {n} 个月均值 ¥{mean:,.0f} 达 {z:+.1f} 个标准差")
        mom = item["mom_change"]
        if mom is not None and abs(mom) >= 0.5 and max(item["total"], series[i - 1]["total"]) >= mean * 0.2:
            reasons.append(f"环比{'激增' if mom > 0 else '骤降'} {mom:+.0%}")
        if reasons:
            anomalies.append({"month": item["month"], "total": item["total"],
                              "z_score": round(z, 2), "mom_change": mom,
                              "reasons": reasons,
                              "top_subjects": item["by_subject"]})

    return {
        "ok": True,
        "scope": {
            "project": ({"id": proj.id, "name": proj.name, "code": proj.code} if proj else "全部项目"),
            "subject": subject or "全部科目",
            "start_month": months[0], "end_month": months[-1],
        },
        "months": series,
        "stat": {"month_count": n, "mean": round(mean, 2), "std": round(std, 2),
                 "grand_total": round(sum(totals), 2)},
        "anomalies": anomalies,
        "latest_month": series[-1],
    }


def generate_packages(out_dir: str | None = None, db_path: str | None = None) -> dict:
    """运行 rd-governor 自动化生成引擎。

    从 rd_expense.db 抽取真实项目 / 费用 / 人员 / 工时 / 证据数据，套用 rd-governor
    模板，生成三套资料包草稿（研发费用加计扣除 / 高新技术企业认定 / IPO 申报）+ 证据清单
    + 内控制度与日常管理规范骨架，写入 output/ 目录。对应技能 SKILL.md 的「自动化引擎」。

    注意：rd-governor 目录含连字符，无法作为 Python 模块名直接 import，故用
    importlib 按文件路径加载其 scripts/generate_package.py（函数式可导入）。
    """
    script = (Path(__file__).resolve().parent
              / "default_skills" / "rd-governor" / "scripts" / "generate_package.py")
    if not script.exists():
        return {"ok": False, "error": f"未找到生成引擎脚本：{script}"}
    try:
        spec = importlib.util.spec_from_file_location("rdgov_genpkg", str(script))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"加载生成引擎失败：{e}"}
    try:
        ctx = mod.extract(db_path)
        if not ctx.get("db_path"):
            return {"ok": False, "error": "未定位到 rd_expense.db（请提供 db_path）",
                    "missing": ctx.get("missing", [])}
        out = mod.render_package(ctx)
        if not out_dir:
            out_dir = str(Path(__file__).resolve().parents[1] / "output")
        written = mod.save_outputs(out, out_dir)
        stats = ctx.get("stats", {})
        return {
            "ok": True,
            "db_path": ctx["db_path"],
            "out_dir": str(Path(out_dir).resolve()),
            "written": written,
            "file_count": len(written),
            "stats": {
                "project_count": stats.get("project_count"),
                "expense_count": stats.get("expense_count"),
                "expense_total": stats.get("expense_total"),
                "expense_without_evidence": stats.get("expense_without_evidence"),
            },
            "missing": ctx.get("missing", []),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"生成失败：{e}"}


def _rd_governor_dir() -> Path:
    """定位 rd-governor 技能目录（含模板），目录含连字符故用绝对路径读取。"""
    return (Path(__file__).resolve().parent
            / "default_skills" / "rd-governor")


def _read_policy_template(policy_type: str) -> tuple[str, str]:
    """返回 (标题, 模板正文)。policy_type: process / internal_control。"""
    gov = _rd_governor_dir()
    tpl_dir = gov / "references" / "templates"
    if policy_type == "process":
        p = tpl_dir / "02-processes" / "rd-process.md"
        title = "研发流程管理制度"
    elif policy_type == "internal_control":
        p = tpl_dir / "01-regulations" / "internal-control-system.md"
        title = "研发费用内部控制制度"
    else:
        raise ValueError(f"未知制度类型：{policy_type}")
    if not p.exists():
        raise FileNotFoundError(f"模板不存在：{p}")
    return title, p.read_text(encoding="utf-8")


def _enterprise_context_text() -> str:
    """读取设置中心企业资料（rd_settings.json），渲染为可读上下文。"""
    try:
        from rdapp.biz_config import get_rd_settings
        rd = get_rd_settings()
    except Exception:
        rd = {}
    ent = rd.get("enterprise", {}) or {}
    tax = rd.get("tax", {}) or {}
    cap = rd.get("capitalization", {}) or {}
    lines = [
        f"- 企业名称：{ent.get('name') or '（未填写）'}",
        f"- 统一社会信用代码：{ent.get('credit_code') or '（未填写）'}",
        f"- 所属行业：{ent.get('industry') or '（未填写）'}",
        f"- 高新技术企业：{'是' if ent.get('is_high_tech') else '否'}；"
        f"科技型中小企业：{'是' if ent.get('is_sci_sme') else '否'}",
        f"- 会计准则：{ent.get('accounting_standard') or '企业会计准则'}",
        f"- 加计扣除比例：{tax.get('super_deduction_rate', 100)}%（依据 {tax.get('policy_basis') or '未填写'}）",
        f"- 研究阶段支出：{'全部费用化' if cap.get('research_expense', True) else '按企业政策'}",
        f"- 开发阶段：{'满足条件资本化' if cap.get('dev_capitalize', True) else '费用化'}",
        f"- 资本化条件：{('；'.join(cap.get('criteria', []) or [])) or '（未填写）'}",
    ]
    return "\n".join(lines)


def generate_rd_policy(policy_type: str = "process",
                       enterprise_materials: str = "",
                       out_dir: str | None = None) -> dict:
    """智能制度生成工具（内化能力）：读取制度模板 + 企业资料，产出一份制度生成工作底稿。

    policy_type: process=研发流程管理制度 / internal_control=研发费用内部控制制度。
    enterprise_materials: 用户提供的企业资料文本（如上传文件内容、企业描述），可选。

    说明：本工具是「装配器」——把 企业资料 + 制度模板 + 生成指引 组装成一份工作底稿
    返回给 Agent；Agent 据此生成完整制度并用 write_file 落盘 output/。
    """
    try:
        title, template = _read_policy_template(policy_type)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"读取制度模板失败：{e}"}
    ent_ctx = _enterprise_context_text()

    try:
        if not out_dir:
            out_dir = str(Path(__file__).resolve().parents[1] / "output")
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        fname = "研发流程管理制度工作底稿.md" if policy_type == "process" else "研发费用内控制度工作底稿.md"
        out_path = Path(out_dir) / fname
        work = (
            f"# {title} · 智能生成工作底稿\n\n"
            f"> 由 rd-policy-builder 技能 + generate_rd_policy 工具生成。\n"
            f"> 原则：不改变企业现有研发管理，在此基础上嵌入财税合规要求。\n\n"
            f"## 一、企业资料\n{ent_ctx}\n\n"
            f"## 二、用户补充资料\n{enterprise_materials or '（无）'}\n\n"
            f"## 三、制度模板骨架\n\n{template}\n"
        )
        out_path.write_text(work, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        out_path_s = f"（写入失败：{e}）"
    else:
        out_path_s = str(out_path)

    return {
        "ok": True,
        "policy_type": policy_type,
        "title": title,
        "workfile": out_path_s,
        "enterprise_context": ent_ctx,
        "user_materials": enterprise_materials or "（无）",
        "template": template,
        "generate_note": (
            "请基于以上企业资料与模板骨架，生成完整制度正文。"
            "必须用 write_file 写入 output/ 目录的正式制度文件"
            f"（如 output/{'研发流程管理制度.md' if policy_type == 'process' else '研发费用内控制度.md'}），"
            "并保持『不改变企业研发管理』原则。"
        ),
    }
# ── 工具 schema（OpenAI 兼容） ─────────────────────────────────

def _entity_columns_str() -> str:
    parts = []
    for name, meta in ENTITY_MAP.items():
        parts.append(f"- {name}（{meta['label']}）：{', '.join(meta['columns'])}")
    return "\n".join(parts)


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "db_operation",
            "description": (
                "研发费用管理系统的通用数据操作工具，可对任意业务实体执行 增删改查。"
                "支持实体：projects(研发项目)、expenses(费用记录)、worktime(工时)、"
                "equipment(研发设备)、materials(原材料领用)、outsourcing(委托外部研发)、"
                "others(其他费用)、risks(风险预警)、evidence(证据材料)、capitalization(资本化审批)、"
                "special_income(特殊收入)、sample_scrap(样品废料)、entrusted(受托研发)、"
                "personnel(人员档案)、labor_cost(人工费用总账)、equipment_depreciation(设备折旧总账)、"
                "equipment_worktime(设备工时)。\n"
                "action 取值：list(列表/查询)、get(按id取详情)、create(新建)、update(按id更新)、delete(按id删除)。\n"
                "引用简化：create/update 时可传 project_code 或 project_name（自动解析 project_id）、"
                "person_name（解析 person_id）、subject_name（解析 subject_id 并补 subject_name），无需先查 id。\n"
                "费用归集（expenses）建议由系统自动判定阶段与资本化状态，只需给 project_id/code、amount、expense_date、subject_name 等。\n"
                "各实体可写字段如下：\n" + _entity_columns_str()
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "get", "create", "update", "delete"],
                                "description": "操作类型"},
                    "entity": {"type": "string",
                                "enum": list(ENTITY_MAP.keys()),
                                "description": "目标业务实体"},
                    "id": {"type": "integer", "description": "get/update/delete 时的记录 id"},
                    "fields": {"type": "object", "description": "create/update 的字段对象（键为实体字段名）",
                                "additionalProperties": True},
                    "filters": {"type": "object", "description": "list 时的过滤条件（键为字段名，值精确/包含匹配）",
                                "additionalProperties": True},
                },
                "required": ["action", "entity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_project",
            "description": "分析某研发项目的预算执行情况：已归集费用总额、预算执行率、按阶段（研究/开发/生产）与按科目分布。便于向用户汇报预算差异。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string",
                                "description": "项目 id、项目编号(code，如 RD-2026-001) 或项目名称"},
                },
                "required": ["project"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_metrics",
            "description": "计算某项目（及企业口径）的高企认定与加计扣除比例指标：研发费用占收入比、高新技术收入占比、其他费用占比、研发人员占比等，并给出是否达标。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string",
                                "description": "项目 id、项目编号(code) 或项目名称"},
                },
                "required": ["project"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_capitalization",
            "description": "判断某笔「待资本化」费用是否已通过开发阶段资本化 5 条件审批；返回是否满足及审批详情。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expense_id": {"type": "integer", "description": "费用记录 id"},
                },
                "required": ["expense_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dashboard_summary",
            "description": "企业级总览：项目数、费用记录数、费用总额、未处理风险数、项目清单。用于一句话掌握系统整体状况。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_expense_trend",
            "description": (
                "研发费用月度趋势与异常波动分析：按月聚合费用总额/笔数/科目分布，"
                "计算环比变化率与 z-score，自动识别异常波动月份并给出原因"
                "（如金额显著偏离历史均值、环比激增/骤降）。"
                "用户问「本月/近几个月费用趋势」「有没有异常波动」「哪个月费用暴涨」时必须调用本工具。"
                "可选按项目（id/编号/名称）或科目名称过滤，可用 start_month/end_month 截取区间（YYYY-MM）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_month": {"type": "string", "description": "起始月份，格式 YYYY-MM，缺省为最早有数据的月份"},
                    "end_month": {"type": "string", "description": "结束月份，格式 YYYY-MM，缺省为最新有数据的月份"},
                    "project": {"type": "string", "description": "可选：项目 id、编号(code) 或名称，缺省分析全部项目"},
                    "subject": {"type": "string", "description": "可选：费用科目名称（如 人员人工、直接投入），缺省分析全部科目"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_packages",
            "description": (
                "运行「研发费用管理系统首席合规官(rd-governor)」自动化生成引擎："
                "从真实数据库 rd_expense.db 抽取项目 / 费用 / 人员 / 工时 / 证据数据，"
                "套用 rd-governor 模板，一键生成三套资料包草稿（研发费用加计扣除 / "
                "高新技术企业认定 / IPO 申报）+ 证据清单草稿 + 内控制度与日常管理规范骨架，"
                "写入 output/ 目录。\n"
                "当用户说「生成研发费用资料包 / 加计扣除资料 / 高企认定资料 / IPO 申报资料 / "
                "全套研发资料 / 帮我做一套完整的研发费用管理体系」时调用本工具。"
                "生成后向用户说明产出文件清单与仍需人工补录的待补项。无需参数即可运行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "out_dir": {"type": "string", "description": "可选：输出目录（绝对或相对项目根），缺省为项目根/output"},
                    "db_path": {"type": "string", "description": "可选：数据库路径，缺省自动探测 data/rd_expense.db"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_rd_policy",
            "description": (
                "智能制度生成（内化能力，rd-policy-builder 技能）：根据企业资料（含上传的制度文件、"
                "设置中心企业信息、业务数据），在不改变企业现有研发管理的前提下，生成合乎财税规范的制度。\n"
                "policy_type 取值：\n"
                "  - process=研发流程管理制度（区分研究/开发阶段、资本化/费用化、研发/生产三对边界）\n"
                "  - internal_control=研发费用内部控制制度（九章节骨架 + 完整证据链设计）\n"
                "当用户说「梳理研发流程管理制度 / 编制研发费用内控制度 / 帮我做一套研发管理制度 / "
                "完善研发制度 / 生成研发制度 / 制度生成」时调用本工具。\n"
                "调用后工具返回企业资料 + 制度模板骨架 + 生成指引，请据此生成完整制度正文，"
                "并用 write_file 写入 output/ 目录的正式制度文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "policy_type": {"type": "string", "enum": ["process", "internal_control"],
                                    "description": "制度类型：process=研发流程管理制度 / internal_control=研发费用内部控制制度"},
                    "enterprise_materials": {"type": "string",
                                             "description": "用户提供的企业资料文本（如上传制度文件内容、企业研发管理模式描述），可选"},
                    "out_dir": {"type": "string", "description": "可选：输出目录，缺省为项目根/output"},
                },
                "required": ["policy_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_batch",
            "description": "批量导入某实体数据（人员/工时/费用/设备/物料/人工总账/项目/委托外部研发/其他费用/特殊收入/证据等）。rows 为字段对象列表，字段名见实体导入模板；dry_run=True 预检不落库，False 落库并留痕。返回成功/失败行数与逐行错误原因。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "enum": ["worktime","personnel","expenses","equipment","materials","labor_cost","projects","outsourcing","others","special_income","evidence"], "description": "待导入实体"},
                    "rows": {"type": "array", "items": {"type": "object"}, "description": "数据行列表"},
                    "dry_run": {"type": "boolean", "default": True},
                },
                "required": ["entity", "rows"],
            },
        },
    },
]




# ── 调度 ──────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> dict:
    """把工具调用分发到对应实现，统一返回 dict。"""
    args = args or {}
    try:
        if name == "import_batch":
            from .importer import import_batch as _ib
            return _ib(
                entity=args.get("entity"),
                rows=args.get("rows") or [],
                dry_run=bool(args.get("dry_run", True)),
            )
        if name == "db_operation":
            return db_operation(
                action=args.get("action"),
                entity=args.get("entity"),
                id=args.get("id"),
                fields=args.get("fields"),
                filters=args.get("filters"),
            )
        if name == "analyze_project":
            return analyze_project(args.get("project"))
        if name == "analyze_metrics":
            return analyze_metrics(args.get("project"))
        if name == "analyze_capitalization":
            return analyze_capitalization(args.get("expense_id"))
        if name == "dashboard_summary":
            return dashboard_summary()
        if name == "analyze_expense_trend":
            return analyze_expense_trend(
                start_month=args.get("start_month"),
                end_month=args.get("end_month"),
                project=args.get("project"),
                subject=args.get("subject"),
            )
        if name == "generate_packages":
            return generate_packages(
                out_dir=args.get("out_dir"),
                db_path=args.get("db_path"),
            )
        if name == "generate_rd_policy":
            return generate_rd_policy(
                policy_type=args.get("policy_type") or "process",
                enterprise_materials=args.get("enterprise_materials") or "",
                out_dir=args.get("out_dir"),
            )
    except Exception as e:
        return {"ok": False, "error": f"工具执行异常：{e}"}
    return {"ok": False, "error": f"未知工具：{name}"}


# ════════════════════════════════════════════════════════════════
# P0 核心缺口修复：流程 → 费用 → 证据 打通
# 由 process_node_approve 审批通过后调用，保证三套数据同源可追溯。
# ════════════════════════════════════════════════════════════════

def expense_collect_from_node(project_id: int, node_id: int) -> list:
    """根据流程节点审批通过触发费用归集。

    策略：
    1. 优先归集该项目下尚未归集（collected=0）的真实业务数据
       （材料领用 / 委托外部 / 其他费用 / 设备折旧）；
    2. 若节点关联无可归集数据，则按节点预算占比估算里程碑费用，
       生成一条 source='系统自动归集' 的记录，保证流程→费用链路可见。

    返回本次新增的 Expense 记录列表（元素为 dict 摘要）。
    """
    from .db import (
        expenses_tb, projects_tb, project_nodes_tb,
        material_requisition_tb, outsourcing_tb, other_expense_tb,
        equipment_depreciation_tb, add_expense, get_project_node_for_date,
        log_audit,
    )
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    created = []
    node = project_nodes_tb[node_id] if node_id else None
    phase = getattr(node, "phase", "") or "研究"
    node_name = getattr(node, "node_name", "") or "流程节点"
    exp_date = getattr(node, "end_date", "") or now[:10]

    # ── 1) 真实未归集业务数据（按节点交付物关键词匹配，找不到则全项目兜底）──
    pending = []
    for tb, kw in [
        (material_requisition_tb, ("材料", "物料", "领用", "原料", "样品", "废料")),
        (outsourcing_tb, ("委托", "外包", "外部", "合作")),
        (other_expense_tb, ("其他", "咨询", "差旅", "图书", "测试", "认证")),
    ]:
        for r in tb(where=f"project_id={project_id}"):
            if getattr(r, "collected", 0):
                continue
            desc = getattr(r, "description", "") or ""
            name = getattr(r, "material_name", "") or getattr(r, "contractor", "") or getattr(r, "category", "")
            if kw and not any(k in node_name or k in desc or k in str(name) for k in kw):
                continue
            pending.append((tb, r))

    # 设备折旧归集（当月存在"待分摊"折旧记录时触发）
    for d in equipment_depreciation_tb():
        if getattr(d, "status", "") != "待分摊":
            continue
        # 设备归属项目：从设备工时登记推断
        try:
            from .db import equipment_work_time_tb
            wt = equipment_work_time_tb(where=f"equipment_id={d.equipment_id} AND project_id={project_id}")
            if not wt:
                continue
            amt = getattr(d, "monthly_depreciation", 0) * getattr(d, "rd_usage_ratio", 1.0)
            row = add_expense(
                project_id=project_id, node_id=node_id,
                subject_name="折旧费用与长期待摊",
                amount=round(amt, 2), expense_date=exp_date, phase=phase,
                description=f"设备折旧归集（节点：{node_name}）",
                source="系统自动归集",
            )
            d.status = "已分摊"
            try:
                tb_u = equipment_depreciation_tb
                d2 = tb_u[d.id]
                d2.status = "已分摊"
                tb_u.update(d2)
            except Exception:
                pass
            created.append(row)
        except Exception:
            continue

    for tb, r in pending:
        try:
            if tb is material_requisition_tb:
                subject_name = "直接投入费用"
                amt = getattr(r, "amount", 0)
            elif tb is outsourcing_tb:
                subject_name = "委托外部研究费用"
                amt = getattr(r, "actual_amount", 0)
            else:
                subject_name = "其他费用"
                amt = getattr(r, "amount", 0)
            row = add_expense(
                project_id=project_id, node_id=node_id,
                subject_name=subject_name, amount=round(amt, 2),
                expense_date=exp_date, phase=phase,
                description=f"{node_name} 关联归集：{getattr(r, 'description', '') or getattr(r, 'material_name', '') or getattr(r, 'contractor', '')}",
                source="系统自动归集",
            )
            try:
                r.collected = 1
                tb.update(r)
            except Exception:
                pass
            created.append(row)
        except Exception:
            continue

    # ── 2) 无可归集数据时：按节点预算占比估算里程碑费用 ──
    if not created:
        try:
            p = projects_tb[project_id]
            ratio = getattr(node, "budget_ratio", 0) or 0
            if ratio > 0 and getattr(p, "budget", 0) > 0:
                amt = round(p.budget * ratio / 100.0, 2)
                row = add_expense(
                    project_id=project_id, node_id=node_id,
                    subject_name="其他费用",
                    amount=amt, expense_date=exp_date, phase=phase,
                    description=f"节点里程碑费用估算（{node_name}，预算占比 {ratio}%）",
                    source="系统自动归集",
                )
                created.append(row)
        except Exception:
            pass

    # 审计留痕
    try:
        log_audit(
            "APPROVE", "process_node", node_id,
            detail=f"节点审批通过，触发费用归集：{node_name}（新增 {len(created)} 笔费用）",
            actor="系统",
            after=f'{{"project_id":{project_id},"node_id":{node_id},"created":{len(created)}}}',
        )
    except Exception:
        pass

    return [{"id": getattr(r, "id", 0), "amount": getattr(r, "amount", 0),
             "subject_name": getattr(r, "subject_name", "")} for r in created]


def evidence_create_snapshot(project_id: int, node_id: int, phase: str = ""):
    """节点审批通过后生成证据快照（写入 evidence_tb）。

    快照包含：节点名称、交付物、完成时间、阶段、关联费用汇总。
    返回新创建的 Evidence 记录 dict；失败返回 None。
    """
    from .db import (
        evidence_tb, project_nodes_tb, expenses_tb, log_audit,
    )
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        node = project_nodes_tb[node_id]
    except Exception:
        node = None
    node_name = getattr(node, "node_name", "") if node else "流程节点"
    deliverable = getattr(node, "deliverable", "") or getattr(node, "deliverable_status", "") or ""
    end_date = getattr(node, "end_date", "") or now[:10]
    phase = phase or getattr(node, "phase", "") or "研究"

    # 关联费用汇总
    try:
        node_exp = [e for e in expenses_tb(where=f"node_id={node_id}") if e.project_id == project_id]
    except Exception:
        node_exp = []
    total = sum(getattr(e, "amount", 0) for e in node_exp)
    desc = (f"节点完成快照：{node_name}（{end_date}），阶段：{phase}，"
            f"交付物：{deliverable or '—'}，关联费用 {len(node_exp)} 笔合计 ¥{total:,.2f}")

    snap = evidence_tb.insert(
        project_id=project_id, node_id=node_id,
        ev_type="节点完成快照", name=f"节点完成快照：{node_name}",
        phase=phase, upload_date=now[:10], description=desc,
    )
    try:
        log_audit(
            "CREATE", "evidence", snap.id,
            detail=f"节点审批通过自动生成证据快照：{node_name}",
            actor="系统",
            after=f'{{"project_id":{project_id},"node_id":{node_id},"ev_type":"节点完成快照"}}',
        )
    except Exception:
        pass
    return {"id": snap.id, "name": snap.name, "ev_type": snap.ev_type,
            "description": snap.description, "total": total}
