"""importer.py — 批量导入引擎（P0 实体：工时/人员/费用/设备/物料/人工总账）。

统一导入管线：模板生成 → 上传解析 → 逐行校验 → 预检/落库。
设计原则：
- 人工上传（xlsx/csv）与 Agent 工具共用 `import_batch`，先预检后入库。
- 引用解析（人员/项目/科目/部门）统一由 `refs` 声明，复用 db 表。
- 复用 db 既有口径（工时去重、单日 24h、负面清单、阶段/资本化计算）。
- 模块自包含（仅依赖 .db），不反向 import operations，避免循环依赖。

IMPORT_MAP 每项结构：
  label    中文名
  tb       落库表
  template 中文表头列表
  fields   字段名列表（与 template 一一对应）
  required 必填字段名
  sample   模板示例行
  refs     引用解析：{字段: (解析函数, id字段名)}
  validate 行校验 (fields, ctx, resolved) -> [errs]
  writer   落库 (fields, resolved) -> record
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

from . import db


# ── 引用解析 ───────────────────────────────────────────────
def _resolve_person(name):
    name = (name or "").strip()
    if not name:
        return None, "人员姓名缺失"
    for r in db.personnel_tb():
        if r.name and r.name == name:
            return r.id, None
    for r in db.personnel_tb():
        if r.name and name in r.name:
            return r.id, None
    return None, f"未找到人员「{name}」"


def _resolve_project(code):
    code = (code or "").strip()
    if not code:
        return None, "项目编号缺失"
    for r in db.projects_tb():
        if r.code and r.code == code:
            return r.id, None
    return None, f"未找到项目「{code}」"


def _resolve_subject(name):
    name = (name or "").strip()
    if not name:
        return None, "费用科目缺失"
    for r in db.subjects_tb():
        if r.name and r.name == name:
            return r.id, None
    for r in db.subjects_tb():
        if r.name and name in r.name:
            return r.id, None
    return None, f"未找到费用科目「{name}」"


def _resolve_org(name):
    name = (name or "").strip()
    if not name:
        return None, None  # 部门可选
    for r in db.orgs_tb():
        if r.name and r.name == name:
            return r.id, None
    for r in db.orgs_tb():
        if r.name and name in r.name:
            return r.id, None
    return None, f"未找到部门「{name}」"


def _log(entity: str, entity_id: int, detail: str):
    try:
        db.log_audit("CREATE", entity, entity_id, detail=detail)
    except Exception:
        pass


# ── worktime 校验 / 落库 ──────────────────────────────────
def _worktime_exists(person_id, project_id, work_date) -> bool:
    return bool(db.work_time_tb(where=(
        f"person_id={person_id} AND project_id={project_id} AND work_date='{work_date}'")))


def _day_total(person_id, work_date) -> float:
    recs = db.work_time_tb(where=f"person_id={person_id} AND work_date='{work_date}'")
    return sum(float(r.hours or 0) for r in recs)


def _validate_worktime(fields, ctx, resolved):
    errs = []
    try:
        hours = float(fields.get("hours"))
        if hours <= 0:
            errs.append("工时必须大于0")
    except (TypeError, ValueError):
        errs.append("工时格式错误")
    pid = resolved.get("person_id")
    proj = resolved.get("project_id")
    work_date = fields.get("work_date", "")
    day_hours = ctx.setdefault("day_hours", {})
    seen = ctx.setdefault("seen_keys", set())
    key = (pid, proj, work_date)
    if key in seen:
        errs.append("同人员同项目同日已存在（批次内重复）")
    elif _worktime_exists(pid, proj, work_date):
        errs.append("同人员同项目同日已存在")
    daykey = (pid, work_date)
    day_total = day_hours.get(daykey, _day_total(pid, work_date))
    if day_total + (hours if hours > 0 else 0) > 24:
        errs.append("当日累计工时超过24小时上限")
    if not errs:
        day_hours[daykey] = day_total + hours
        seen.add(key)
    return errs


def _write_worktime(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = db.work_time_tb.insert(
        person_id=resolved["person_id"],
        project_id=resolved["project_id"],
        work_date=fields["work_date"],
        hours=float(fields["hours"]),
        task_desc=fields.get("task_desc", ""),
        created_at=now,
    )
    _log("worktime", rec.id, f"批量导入工时：{fields.get('person_name')} {fields['work_date']} {fields.get('hours')}h")
    return rec


# ── personnel 校验 / 落库 ─────────────────────────────────
def _validate_personnel(fields, ctx, resolved):
    errs = []
    try:
        d = int(fields.get("annual_rd_days") or 0)
        if d < 0 or d > 366:
            errs.append("当年研发天数需在0~366")
    except (TypeError, ValueError):
        errs.append("当年研发天数格式错误")
    try:
        r = float(fields.get("hourly_rate") or 0)
        if r < 0:
            errs.append("小时成本不能为负")
    except (TypeError, ValueError):
        errs.append("小时成本格式错误")
    return errs


def _write_personnel(fields, resolved):
    rec = db.personnel_tb.insert(
        name=fields["name"],
        org_id=resolved.get("org_id", 0),
        title=fields.get("title", ""),
        is_rd=True,
        hourly_rate=float(fields.get("hourly_rate") or 0),
        person_category=fields.get("person_category", "研究人员"),
        education=fields.get("education", ""),
        major=fields.get("major", ""),
        employment_type=fields.get("employment_type", "在职"),
        id_number=fields.get("id_number", ""),
        hire_date=fields.get("hire_date", ""),
        leave_date="",
        annual_rd_days=int(fields.get("annual_rd_days") or 0),
        social_insurance_unit=fields.get("social_insurance_unit", ""),
        certification_status="待认定",
        certification_date="",
    )
    _log("personnel", rec.id, f"批量导入人员：{fields['name']}")
    return rec


# ── expenses 校验 / 落库 ──────────────────────────────────
def _validate_expense(fields, ctx, resolved):
    errs = []
    try:
        amt = float(fields.get("amount"))
        if amt <= 0:
            errs.append("金额必须大于0")
    except (TypeError, ValueError):
        errs.append("金额格式错误")
    if db.negative_list_hit(fields.get("description", "")):
        errs.append("命中负面清单，不得归集")
    return errs


def _write_expense(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    project_id = resolved["project_id"]
    expense_date = fields.get("expense_date", "")
    phase = db.phase_for_date(project_id, expense_date)
    cap = db.capitalize_status_for_phase(phase)
    node = db.get_project_node_for_date(project_id, expense_date)
    rec = db.expenses_tb.insert(
        project_id=project_id,
        node_id=node.id if node else 0,
        subject_id=resolved.get("subject_id", 0),
        subject_name=fields.get("subject_name", ""),
        amount=float(fields["amount"]),
        expense_date=expense_date,
        phase=phase,
        capitalize_status=cap,
        caliber=fields.get("caliber", "高企认定,加计扣除"),
        person_id=resolved.get("person_id", 0),
        person_name=fields.get("person_name", ""),
        description=fields.get("description", ""),
        source="批量导入",
        created_at=now,
    )
    _log("expense", rec.id, f"批量导入费用：{fields.get('subject_name')} ¥{fields.get('amount')} 至项目{project_id}")
    return rec


# ── equipment 校验 / 落库 ─────────────────────────────────
def _validate_equipment(fields, ctx, resolved):
    errs = []
    try:
        c = float(fields.get("acquisition_cost") or 0)
        if c < 0:
            errs.append("原值不能为负")
    except (TypeError, ValueError):
        errs.append("原值格式错误")
    try:
        l = int(fields.get("useful_life") or 0)
        if l < 0:
            errs.append("使用年限不能为负")
    except (TypeError, ValueError):
        errs.append("使用年限格式错误")
    st = fields.get("status", "在用")
    if st not in ("在用", "闲置", "报废"):
        errs.append("状态需为 在用/闲置/报废")
    return errs


def _write_equipment(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = db.equipment_tb.insert(
        code=fields.get("code", ""),
        name=fields["name"],
        category=fields.get("category", "仪器设备"),
        model=fields.get("model", ""),
        acquisition_date=fields.get("acquisition_date", ""),
        acquisition_cost=float(fields.get("acquisition_cost") or 0),
        depreciation_method="年限平均法",
        useful_life=int(fields.get("useful_life") or 60),
        monthly_depreciation=float(fields.get("monthly_depreciation") or 0),
        status=fields.get("status", "在用"),
        dept_id=0,
        created_at=now,
    )
    _log("equipment", rec.id, f"批量导入设备：{fields['name']}")
    return rec


# ── materials 校验 / 落库 ─────────────────────────────────
def _validate_material(fields, ctx, resolved):
    errs = []
    try:
        q = float(fields.get("quantity"))
        if q <= 0:
            errs.append("数量必须大于0")
    except (TypeError, ValueError):
        errs.append("数量格式错误")
    try:
        p = float(fields.get("unit_price"))
        if p <= 0:
            errs.append("单价必须大于0")
    except (TypeError, ValueError):
        errs.append("单价格式错误")
    return errs


def _write_material(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    q = float(fields.get("quantity"))
    p = float(fields.get("unit_price"))
    rec = db.material_requisition_tb.insert(
        material_name=fields["material_name"],
        specification=fields.get("specification", ""),
        unit=fields.get("unit", "个"),
        quantity=q,
        unit_price=p,
        amount=round(q * p, 2),
        project_id=resolved["project_id"],
        requisition_date=fields.get("requisition_date", ""),
        requisitioner_id=resolved.get("requisitioner_id", 0),
        purpose=fields.get("purpose", ""),
        usage_status="已领用",
        collected=0,
        created_at=now,
    )
    _log("materials", rec.id, f"批量导入领料：{fields['material_name']}×{fields.get('quantity')}{fields.get('unit', '个')}")
    return rec


# ── labor_cost 校验 / 落库 ────────────────────────────────
def _validate_labor_cost(fields, ctx, resolved):
    errs = []
    try:
        s = float(fields.get("total_salary") or 0)
        if s < 0:
            errs.append("工资总额不能为负")
    except (TypeError, ValueError):
        errs.append("工资总额格式错误")
    month = fields.get("cost_month", "")
    if month and not re.match(r"^\d{4}-\d{2}$", month):
        errs.append("月份格式需为 YYYY-MM")
    return errs


def _write_labor_cost(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    salary = float(fields.get("total_salary") or 0)
    hours = float(fields.get("work_hours_total") or 0)
    hourly = round(salary / hours, 2) if hours > 0 else 0.0
    rec = db.labor_cost_tb.insert(
        person_id=resolved["person_id"],
        cost_month=fields.get("cost_month", ""),
        total_salary=salary,
        social_insurance=float(fields.get("social_insurance") or 0),
        housing_fund=float(fields.get("housing_fund") or 0),
        work_hours_total=hours,
        non_rd_hours=0,
        hourly_cost=hourly,
        status="待分摊",
        created_at=now,
    )
    _log("labor_cost", rec.id, f"批量导入人工总账：{fields.get('person_name')} {fields.get('cost_month')}")
    return rec


# ── projects 校验 / 落库 ───────────────────────────────────
_PROJECT_STATUS = {"立项中", "进行中", "已结题", "已暂停"}
_PROJECT_BOUNDARY = {"纯研发", "混合", "生产改进"}
_PROJECT_NATURE = {"自主研发", "委托研发", "受托研发"}

def _validate_project(fields, ctx, resolved):
    errs = []
    if fields.get("status") and fields["status"] not in _PROJECT_STATUS:
        errs.append("状态需为 立项中/进行中/已结题/已暂停")
    if fields.get("boundary_type") and fields["boundary_type"] not in _PROJECT_BOUNDARY:
        errs.append("边界类型需为 纯研发/混合/生产改进")
    if fields.get("rd_nature") and fields["rd_nature"] not in _PROJECT_NATURE:
        errs.append("研发性质需为 自主研发/委托研发/受托研发")
    try:
        r = float(fields.get("rd_split_ratio") or 1.0)
        if not (0 <= r <= 1):
            errs.append("混合研发占比需在0~1")
    except (TypeError, ValueError):
        errs.append("混合研发占比格式错误")
    try:
        b = float(fields.get("budget") or 0)
        if b < 0:
            errs.append("总预算不能为负")
    except (TypeError, ValueError):
        errs.append("总预算格式错误")
    return errs

def _write_project(fields, resolved):
    rec = db.projects_tb.insert(
        name=fields["name"],
        code=fields.get("code", ""),
        status=fields.get("status", "进行中"),
        budget=float(fields.get("budget") or 0),
        start_date=fields.get("start_date", ""),
        end_date=fields.get("end_date", ""),
        boundary_type=fields.get("boundary_type", "纯研发"),
        boundary_desc=fields.get("boundary_desc", ""),
        rd_split_ratio=float(fields.get("rd_split_ratio") or 1.0),
        annual_revenue=float(fields.get("annual_revenue") or 0),
        hightech_income=float(fields.get("hightech_income") or 0),
        manager=fields.get("manager", ""),
        caliber=fields.get("caliber", "高企认定,加计扣除"),
        description=fields.get("description", ""),
        rd_nature=fields.get("rd_nature", "自主研发"),
    )
    _log("projects", rec.id, f"批量导入项目：{fields['name']}")
    return rec

# ── outsourcing 校验 / 落库 ───────────────────────────────
def _validate_outsourcing(fields, ctx, resolved):
    errs = []
    for k in ("contract_amount", "actual_amount"):
        try:
            v = float(fields.get(k) or 0)
            if v < 0:
                errs.append(f"{k} 不能为负")
        except (TypeError, ValueError):
            errs.append(f"{k} 格式错误")
    if fields.get("has_tech_transfer") not in (None, "", "0", "1"):
        errs.append("成果归属约定需为 0/1")
    if fields.get("is_overseas") not in (None, "", "0", "1"):
        errs.append("境外受托方需为 0/1")
    # 基础校验有误则不累积金额，避免 fail 行干扰批次 2/3 判定
    if errs:
        return errs
    # 批次级：委托境外研发加计上限 = 境内委托实际额 × 2/3（财税〔2018〕64号）
    # 结合库内已有境内委托 + 本批次境内，境外累计超限则拦截（精确合规由 scan_compliance_risks 兜底）。
    # 注：境外在前、境内在后时境外看不到后到境内（cap 偏低），属排列边界；
    #     精确合规由服务端 scan_compliance_risks 兜底，此处为导入即时反馈。
    if fields.get("is_overseas") == "1":
        try:
            amt = float(fields.get("actual_amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt > 0:
            collect = round(amt * 0.8, 2)                      # 境外按 80% 计入（对齐一键归集）
            dom_base, _ = db.deduct_overseas_cap()            # 库内已有境内委托
            dom_base += ctx.get("outs_domestic", 0.0)         # 加本批次境内
            ov_acc = ctx.get("outs_overseas", 0.0)            # 本批次已计入境外(80%)
            cap = round(dom_base * 2.0 / 3.0, 2)
            if dom_base > 0 and ov_acc + collect > cap:
                errs.append(f"境外委托加计超境内2/3上限 ¥{cap:,.0f}（财税〔2018〕64号）")
            else:
                ctx["outs_overseas"] = ov_acc + collect
    else:
        try:
            dom = float(fields.get("actual_amount") or 0)
        except (TypeError, ValueError):
            dom = 0.0
        ctx["outs_domestic"] = ctx.get("outs_domestic", 0.0) + dom
    return errs

def _write_outsourcing(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = db.outsourcing_tb.insert(
        contract_no=fields.get("contract_no", ""),
        contractor=fields.get("contractor", ""),
        project_id=resolved["project_id"],
        contract_amount=float(fields.get("contract_amount") or 0),
        actual_amount=float(fields.get("actual_amount") or 0),
        caliber=fields.get("caliber", "高企认定,加计扣除"),
        has_tech_transfer=int(fields.get("has_tech_transfer") or 0),
        is_overseas=int(fields.get("is_overseas") or 0),
        expense_date=fields.get("expense_date", ""),
        description=fields.get("description", ""),
        created_at=now,
    )
    _log("outsourcing", rec.id, f"批量导入委托外部研发：{fields.get('contract_no')}")
    return rec

# ── others 校验 / 落库 ────────────────────────────────────
_OTHER_CATEGORIES = {"技术图书", "资料翻译", "专家咨询", "知识产权", "差旅", "会议", "其他"}

def _validate_other(fields, ctx, resolved):
    errs = []
    if fields.get("category") and fields["category"] not in _OTHER_CATEGORIES:
        errs.append("费用类别需为 技术图书/资料翻译/专家咨询/知识产权/差旅/会议/其他")
    try:
        a = float(fields.get("amount"))
        if a <= 0:
            errs.append("金额必须大于0")
    except (TypeError, ValueError):
        errs.append("金额格式错误")
    return errs

def _write_other(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = db.other_expense_tb.insert(
        project_id=resolved["project_id"],
        category=fields.get("category", "其他"),
        expense_date=fields.get("expense_date", ""),
        amount=float(fields.get("amount") or 0),
        description=fields.get("description", ""),
        caliber=fields.get("caliber", "高企认定,加计扣除"),
        created_at=now,
    )
    _log("others", rec.id, f"批量导入其他费用：{fields.get('category')} ¥{fields.get('amount')}")
    return rec

# ── special_income 校验 / 落库 ────────────────────────────
_INCOME_TYPES = {"不征税收入", "政府补助", "样品销售", "废料处置"}

_OFFSET_CALIBERS = {"加计扣除", "高企认定", "高企认定,加计扣除"}

def _validate_special_income(fields, ctx, resolved):
    errs = []
    if fields.get("income_type") and fields["income_type"] not in _INCOME_TYPES:
        errs.append("收入类型需为 不征税收入/政府补助/样品销售/废料处置")
    if fields.get("offset_caliber") and fields["offset_caliber"] not in _OFFSET_CALIBERS:
        errs.append("冲减口径需为 加计扣除/高企认定/高企认定,加计扣除")
    try:
        a = float(fields.get("amount"))
        if a <= 0:
            errs.append("金额必须大于0")
    except (TypeError, ValueError):
        errs.append("金额格式错误")
    return errs

def _write_special_income(fields, resolved):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rec = db.special_income_tb.insert(
        project_id=resolved["project_id"],
        income_type=fields.get("income_type", ""),
        amount=float(fields.get("amount") or 0),
        income_date=fields.get("income_date", ""),
        offset_caliber=fields.get("offset_caliber", "加计扣除"),
        note=fields.get("note", ""),
        created_at=now,
    )
    _log("special_income", rec.id, f"批量导入特殊收入：{fields.get('income_type')} ¥{fields.get('amount')}")
    return rec

# ── evidence 校验 / 落库 ──────────────────────────────────
_EV_TYPES = {"立项决议", "项目计划", "可行性证明", "设计评审", "交付物", "验收报告",
             "费用凭证", "合同", "发票", "领料单", "工时记录", "其他"}
_EV_PHASES = {"研究", "开发", "生产"}

def _validate_evidence(fields, ctx, resolved):
    errs = []
    if fields.get("ev_type") and fields["ev_type"] not in _EV_TYPES:
        errs.append("证据类型需为 立项决议/项目计划/可行性证明/设计评审/交付物/验收报告/费用凭证/合同/发票/领料单/工时记录/其他")
    if fields.get("phase") and fields["phase"] not in _EV_PHASES:
        errs.append("所属阶段需为 研究/开发/生产")
    return errs

def _write_evidence(fields, resolved):
    rec = db.evidence_tb.insert(
        project_id=resolved["project_id"],
        ev_type=fields.get("ev_type", "其他"),
        name=fields["name"],
        phase=fields.get("phase", ""),
        upload_date=fields.get("upload_date", ""),
        description=fields.get("description", ""),
    )
    _log("evidence", rec.id, f"批量导入证据：{fields['name']}")
    return rec

# ── 导入注册表 ─────────────────────────────────────────────
IMPORT_MAP: dict = {
    "worktime": {
        "label": "工时登记", "tb": db.work_time_tb,
        "template": ["人员姓名", "项目编号", "日期", "工时", "工作内容"],
        "fields": ["person_name", "project_code", "work_date", "hours", "task_desc"],
        "required": ["person_name", "project_code", "work_date", "hours"],
        "sample": ["张明远", "RD-2026-001", "2026-02-10", "8", "示例：研发工时"],
        "refs": {"person_name": (_resolve_person, "person_id"),
                 "project_code": (_resolve_project, "project_id")},
        "validate": _validate_worktime, "writer": _write_worktime,
    },
    "personnel": {
        "label": "研发人员档案", "tb": db.personnel_tb,
        "template": ["姓名", "人员类别", "职务", "学历", "专业", "用工方式", "所属部门",
                     "入职日期", "当年研发天数", "社保缴纳单位", "证件号", "小时成本"],
        "fields": ["name", "person_category", "title", "education", "major",
                   "employment_type", "org_name", "hire_date", "annual_rd_days",
                   "social_insurance_unit", "id_number", "hourly_rate"],
        "required": ["name"],
        "sample": ["张明远", "研究人员", "研发总监", "硕士", "计算机", "在职", "研发中心",
                   "2026-01-01", "250", "示例公司", "110101199001011234", "300"],
        "refs": {"org_name": (_resolve_org, "org_id")},
        "validate": _validate_personnel, "writer": _write_personnel,
    },
    "expenses": {
        "label": "费用记录", "tb": db.expenses_tb,
        "template": ["项目编号", "费用科目", "金额", "费用日期", "归属人员", "归集口径", "费用说明"],
        "fields": ["project_code", "subject_name", "amount", "expense_date",
                   "person_name", "caliber", "description"],
        "required": ["project_code", "subject_name", "amount", "expense_date"],
        "sample": ["RD-2026-001", "人员人工费用", "8000", "2026-02-10", "张明远",
                   "高企认定,加计扣除", "示例：研发工时对应人工费用"],
        "refs": {"project_code": (_resolve_project, "project_id"),
                 "subject_name": (_resolve_subject, "subject_id"),
                 "person_name": (_resolve_person, "person_id")},
        "validate": _validate_expense, "writer": _write_expense,
    },
    "equipment": {
        "label": "研发设备", "tb": db.equipment_tb,
        "template": ["设备编码", "设备名称", "类别", "型号", "购置日期", "原值",
                     "使用年限", "月折旧额", "状态"],
        "fields": ["code", "name", "category", "model", "acquisition_date",
                   "acquisition_cost", "useful_life", "monthly_depreciation", "status"],
        "required": ["name"],
        "sample": ["EQ-1001", "GPU训练服务器", "仪器设备", "A800", "2026-02-01",
                   "300000", "60", "5000", "在用"],
        "refs": {},
        "validate": _validate_equipment, "writer": _write_equipment,
    },
    "materials": {
        "label": "原材料领用", "tb": db.material_requisition_tb,
        "template": ["物料名称", "规格型号", "数量", "单位", "单价", "去向项目",
                     "领用人", "领用日期", "用途"],
        "fields": ["material_name", "specification", "quantity", "unit", "unit_price",
                   "project_code", "requisitioner_name", "requisition_date", "purpose"],
        "required": ["material_name", "quantity", "unit_price", "project_code"],
        "sample": ["服务器CPU", "Xeon 8480", "4", "个", "12000", "RD-2026-001",
                   "张明远", "2026-02-10", "核心模块搭建"],
        "refs": {"project_code": (_resolve_project, "project_id"),
                 "requisitioner_name": (_resolve_person, "requisitioner_id")},
        "validate": _validate_material, "writer": _write_material,
    },
    "labor_cost": {
        "label": "人工费用总账", "tb": db.labor_cost_tb,
        "template": ["人员姓名", "月份", "工资总额", "社保", "公积金", "总工时"],
        "fields": ["person_name", "cost_month", "total_salary", "social_insurance",
                   "housing_fund", "work_hours_total"],
        "required": ["person_name", "cost_month", "total_salary"],
        "sample": ["张明远", "2026-02", "24000", "4800", "2400", "176"],
        "refs": {"person_name": (_resolve_person, "person_id")},
        "validate": _validate_labor_cost, "writer": _write_labor_cost,
    },
    # ── P1 实体 ─────────────────────────────────────────────
    "projects": {
        "label": "研发项目", "tb": db.projects_tb,
        "template": ["项目名称", "项目编号", "项目经理", "研发/生产边界类型", "边界说明",
                     "总预算", "开始日期", "结束日期", "研发性质", "混合研发占比",
                     "归集口径", "状态", "项目描述"],
        "fields": ["name", "code", "manager", "boundary_type", "boundary_desc",
                   "budget", "start_date", "end_date", "rd_nature", "rd_split_ratio",
                   "caliber", "status", "description"],
        "required": ["name", "code"],
        "sample": ["智能数据分析平台研发", "RD-2026-004", "张明远", "纯研发", "",
                   "500000", "2026-01-01", "2026-12-31", "自主研发", "1",
                   "高企认定,加计扣除", "进行中", "示例：研发项目"],
        "refs": {},
        "validate": _validate_project, "writer": _write_project,
    },
    "outsourcing": {
        "label": "委托外部研发", "tb": db.outsourcing_tb,
        "template": ["合同编号", "受托方", "关联项目编号", "费用日期", "合同金额",
                     "实际发生额", "成果归属约定", "境外受托方", "归集口径", "说明"],
        "fields": ["contract_no", "contractor", "project_code", "expense_date",
                   "contract_amount", "actual_amount", "has_tech_transfer",
                   "is_overseas", "caliber", "description"],
        "required": ["contract_no", "contractor", "project_code", "actual_amount"],
        "sample": ["WT-2026-003", "某软件外包公司", "RD-2026-001", "2026-02-10",
                   "50000", "50000", "1", "0", "高企认定,加计扣除", "示例：委托研发"],
        "refs": {"project_code": (_resolve_project, "project_id")},
        "validate": _validate_outsourcing, "writer": _write_outsourcing,
    },
    "others": {
        "label": "其他费用", "tb": db.other_expense_tb,
        "template": ["关联项目编号", "费用类别", "费用日期", "金额", "归集口径", "说明"],
        "fields": ["project_code", "category", "expense_date", "amount",
                   "caliber", "description"],
        "required": ["project_code", "category", "amount", "expense_date"],
        "sample": ["RD-2026-001", "专家咨询", "2026-02-10", "3000",
                   "高企认定,加计扣除", "示例：专家咨询费"],
        "refs": {"project_code": (_resolve_project, "project_id")},
        "validate": _validate_other, "writer": _write_other,
    },
    "special_income": {
        "label": "特殊收入", "tb": db.special_income_tb,
        "template": ["关联项目编号", "收入类型", "金额", "收入日期", "冲减口径", "说明"],
        "fields": ["project_code", "income_type", "amount", "income_date",
                   "offset_caliber", "note"],
        "required": ["project_code", "income_type", "amount"],
        "sample": ["RD-2026-001", "样品销售", "5000", "2026-02-10", "加计扣除",
                   "示例：样品销售收入"],
        "refs": {"project_code": (_resolve_project, "project_id")},
        "validate": _validate_special_income, "writer": _write_special_income,
    },
    "evidence": {
        "label": "证据材料", "tb": db.evidence_tb,
        "template": ["关联项目编号", "证据类型", "证据名称", "所属阶段", "上传日期", "说明"],
        "fields": ["project_code", "ev_type", "name", "phase", "upload_date",
                   "description"],
        "required": ["project_code", "ev_type", "name"],
        "sample": ["RD-2026-001", "立项决议", "RD-2026-001 立项决议书", "研究",
                   "2026-01-05", "示例：立项决议"],
        "refs": {"project_code": (_resolve_project, "project_id")},
        "validate": _validate_evidence, "writer": _write_evidence,
    },
}


# ── 解析器（纯标准库）──────────────────────────────────────
def parse_upload(data: bytes, filename: str) -> list[list]:
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        return _parse_xlsx(data)
    return _parse_csv(data)


def _parse_xlsx(data: bytes) -> list[list]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("xl/worksheets/sheet1.xml")
    root = ET.fromstring(xml)
    rows: list[list] = []
    for row in root.findall("m:sheetData/m:row", ns):
        cells: list[str] = []
        for c in row.findall("m:c", ns):
            inline = c.find("m:is/m:t", ns)
            v = c.find("m:v", ns)
            if inline is not None:
                cells.append(inline.text or "")
            elif v is not None:
                cells.append(v.text or "")
            else:
                cells.append("")
        rows.append(cells)
    return rows


def _parse_csv(data: bytes) -> list[list]:
    text = data.decode("utf-8-sig", errors="replace")
    return [row for row in csv.reader(io.StringIO(text))]


def rows_from_sheet(sheet: list[list], entity: str) -> list[dict]:
    spec = IMPORT_MAP[entity]
    if not sheet:
        return []
    header = [str(h).strip() for h in sheet[0]]
    idx_map: dict[int, str] = {}
    for i, col in enumerate(spec["template"]):
        if col in header:
            idx_map[header.index(col)] = spec["fields"][i]
    out: list[dict] = []
    for line in sheet[1:]:
        d: dict = {}
        for j, cell in enumerate(line):
            if j in idx_map:
                d[idx_map[j]] = cell
        out.append(d)
    return out


# ── 统一导入管线 ───────────────────────────────────────────
def import_batch(entity: str, rows: list[dict], dry_run: bool = True) -> dict:
    if entity not in IMPORT_MAP:
        return {"ok": False, "error": f"未知导入实体: {entity}",
                "available": sorted(IMPORT_MAP.keys())}
    spec = IMPORT_MAP[entity]
    ok_rows: list[dict] = []
    fail_rows: list[dict] = []
    ctx: dict = {}

    for idx, raw in enumerate(rows, start=2):  # 第 1 行为表头，数据从第 2 行起
        fields = {k: (str(v).strip() if v is not None else "") for k, v in (raw or {}).items()}
        errs: list[str] = []
        resolved: dict = {}

        # 1) 必填
        for req in spec["required"]:
            if not fields.get(req):
                errs.append(f"缺少必填字段「{req}」")

        # 2) 引用解析
        if not errs:
            for fkey, (resolver, idf) in (spec.get("refs") or {}).items():
                val = fields.get(fkey)
                if val:
                    rid, e = resolver(val)
                    if e:
                        errs.append(e)
                    else:
                        resolved[idf] = rid

        # 3) 实体校验
        validate = spec.get("validate")
        if validate and not errs:
            errs += validate(fields, ctx, resolved) or []

        if errs:
            fail_rows.append({"row": idx, "error": "；".join(errs)})
            continue

        if dry_run:
            ok_rows.append({"row": idx, "data": {**fields, **resolved}})
        else:
            rec = spec["writer"](fields, resolved)
            ok_rows.append({"row": idx, "id": rec.id if hasattr(rec, "id") else None})

    return {
        "ok": True,
        "entity": entity,
        "label": spec["label"],
        "dry_run": bool(dry_run),
        "total": len(rows),
        "success": len(ok_rows),
        "failed": len(fail_rows),
        "rows": ok_rows,
        "errors": fail_rows,
    }
