"""test_importer.py — 批量导入引擎（工时登记打样）测试。

采用 Red-Green 测试驱动：先定义 import_batch / parse_upload 的契约，
再实现 rdapp/importer.py 使本文件全绿。
"""
import pytest

from rdapp import db
from rdapp import importer


@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    """种子数据（幂等）：提供人员「张明远」、项目「RD-2026-001」及种子工时。"""
    db.seed_data()
    db.seed_new_modules()
    yield


# ── 公共辅助 ───────────────────────────────────────────────
def _count_worktime():
    return len(db.work_time_tb())


def _valid_rows():
    """一条合法的工时记录（2026-02-10 无种子冲突）。"""
    return [{
        "person_name": "张明远",
        "project_code": "RD-2026-001",
        "work_date": "2026-02-10",
        "hours": "8",
        "task_desc": "打样批量导入",
    }]


# ── 用例 1：未知实体 ──────────────────────────────────────
def test_unknown_entity_rejected():
    r = importer.import_batch("nope", [])
    assert r["ok"] is False
    assert "nope" in r["error"]


# ── 用例 2：预检（dry_run=True）不落库 ────────────────────
def test_preview_dryrun_does_not_insert():
    before = _count_worktime()
    r = importer.import_batch("worktime", _valid_rows(), dry_run=True)
    assert r["ok"] is True
    assert r["success"] == 1
    assert r["failed"] == 0
    assert r["dry_run"] is True
    assert _count_worktime() == before          # 未落库


# ── 用例 3：提交（dry_run=False）落库并返回 id ───────────
def test_commit_inserts_row():
    before = _count_worktime()
    r = importer.import_batch("worktime", _valid_rows(), dry_run=False)
    assert r["ok"] is True
    assert r["success"] == 1
    assert r["failed"] == 0
    assert _count_worktime() == before + 1      # 已落库
    # 库中能找到该记录
    found = db.work_time_tb(where="work_date='2026-02-10'")
    assert len(found) == 1
    assert found[0].person_id is not None
    assert found[0].hours == 8.0


# ── 用例 4：去重（同人+同项目+同日 已存在）拒绝 ──────────
def test_duplicate_rejected():
    # 种子已有 张明远 / RD-2026-001 / 2026-01-06 / 6h
    dup = [{
        "person_name": "张明远",
        "project_code": "RD-2026-001",
        "work_date": "2026-01-06",
        "hours": "6",
        "task_desc": "重复记录",
    }]
    r = importer.import_batch("worktime", dup, dry_run=True)
    assert r["success"] == 0
    assert r["failed"] == 1
    assert "已存在" in r["errors"][0]["error"]


# ── 用例 5：单日累计超 24h 拒绝 ──────────────────────────
def test_over_24h_rejected():
    # 种子已有 张明远 2026-01-06 = 6h；再导入 20h → 累计 26h > 24 拒绝
    over = [{
        "person_name": "张明远",
        "project_code": "RD-2026-001",
        "work_date": "2026-01-06",
        "hours": "20",
        "task_desc": "超过24h",
    }]
    r = importer.import_batch("worktime", over, dry_run=True)
    assert r["success"] == 0
    assert r["failed"] == 1
    assert "24" in r["errors"][0]["error"]


# ── 用例 6：缺必填字段拒绝 ───────────────────────────────
def test_missing_required_rejected():
    # 缺 person_name
    bad = [{
        "project_code": "RD-2026-001",
        "work_date": "2026-02-11",
        "hours": "8",
    }]
    r = importer.import_batch("worktime", bad, dry_run=True)
    assert r["success"] == 0
    assert r["failed"] == 1
    assert "person_name" in r["errors"][0]["error"]


# ── 用例 7：引用解析失败（人员/项目不存在）拒绝 ──────────
def test_unresolvable_ref_rejected():
    r = importer.import_batch("worktime", [{
        "person_name": "不存在的张三",
        "project_code": "RD-2026-001",
        "work_date": "2026-02-12",
        "hours": "8",
    }], dry_run=True)
    assert r["failed"] == 1
    assert "人员" in r["errors"][0]["error"]


# ── 用例 8：中文表头二维 → 字段 dict（人工上传路径）─────
def test_rows_from_sheet_maps_headers():
    sheet = [
        ["人员姓名", "项目编号", "日期", "工时", "工作内容"],
        ["张明远", "RD-2026-001", "2026-02-13", "7", "表头映射"],
    ]
    rows = importer.rows_from_sheet(sheet, "worktime")
    assert rows == [{
        "person_name": "张明远",
        "project_code": "RD-2026-001",
        "work_date": "2026-02-13",
        "hours": "7",
        "task_desc": "表头映射",
    }]


# ── 用例 9：parse_upload 支持 csv 解析 ───────────────────
def test_parse_upload_csv():
    data = "人员姓名,项目编号,日期,工时,工作内容\n张明远,RD-2026-001,2026-02-14,7,CSV导入\n".encode("utf-8")
    sheet = importer.parse_upload(data, "导入.csv")
    assert sheet[0] == ["人员姓名", "项目编号", "日期", "工时", "工作内容"]
    assert sheet[1][0] == "张明远"
    assert sheet[1][3] == "7"


# ════════════════════════════════════════════════════════════
# 其余 P0 实体
# ════════════════════════════════════════════════════════════

def test_personnel_preview_and_commit():
    row = [{
        "name": "测试人员甲", "person_category": "研究人员", "title": "工程师",
        "education": "本科", "major": "自动化", "employment_type": "在职",
        "org_name": "研发中心", "hire_date": "2026-01-01", "annual_rd_days": "200",
        "social_insurance_unit": "示例公司", "id_number": "", "hourly_rate": "180",
    }]
    r = importer.import_batch("personnel", row, dry_run=True)
    assert r["success"] == 1 and r["failed"] == 0
    rc = importer.import_batch("personnel", row, dry_run=False)
    assert rc["success"] == 1
    found = db.personnel_tb(where="name='测试人员甲'")
    assert len(found) == 1 and found[0].org_id is not None


def test_personnel_missing_name_rejected():
    r = importer.import_batch("personnel", [{"title": "工程师"}], dry_run=True)
    assert r["failed"] == 1 and "name" in r["errors"][0]["error"]


def test_personnel_unresolvable_org_rejected():
    r = importer.import_batch("personnel", [{
        "name": "测试人员乙", "org_name": "不存在的部门",
    }], dry_run=True)
    assert r["failed"] == 1 and "部门" in r["errors"][0]["error"]


def test_expense_preview():
    row = [{
        "project_code": "RD-2026-001", "subject_name": "人员人工费用",
        "amount": "8000", "expense_date": "2026-02-10", "person_name": "张明远",
        "caliber": "高企认定,加计扣除", "description": "研发工时费用",
    }]
    r = importer.import_batch("expenses", row, dry_run=True)
    assert r["success"] == 1 and r["failed"] == 0


def test_expense_negative_amount_rejected():
    r = importer.import_batch("expenses", [{
        "project_code": "RD-2026-001", "subject_name": "人员人工费用",
        "amount": "-100", "expense_date": "2026-02-10",
    }], dry_run=True)
    assert r["failed"] == 1 and "金额" in r["errors"][0]["error"]


def test_expense_unresolvable_subject_rejected():
    r = importer.import_batch("expenses", [{
        "project_code": "RD-2026-001", "subject_name": "不存在的科目",
        "amount": "100", "expense_date": "2026-02-10",
    }], dry_run=True)
    assert r["failed"] == 1 and "科目" in r["errors"][0]["error"]


def test_equipment_preview_and_status_validation():
    ok = [{"name": "测试设备", "code": "EQ-T1", "category": "仪器设备",
           "acquisition_date": "2026-02-01", "acquisition_cost": "100000",
           "useful_life": "60", "monthly_depreciation": "1666", "status": "在用"}]
    assert importer.import_batch("equipment", ok, dry_run=True)["success"] == 1
    bad = [{"name": "测试设备2", "status": "非法状态"}]
    r = importer.import_batch("equipment", bad, dry_run=True)
    assert r["failed"] == 1 and "状态" in r["errors"][0]["error"]


def test_material_preview_and_commit():
    row = [{
        "material_name": "测试物料", "specification": "A-1", "quantity": "10",
        "unit": "个", "unit_price": "5", "project_code": "RD-2026-001",
        "requisitioner_name": "张明远", "requisition_date": "2026-02-10", "purpose": "打样",
    }]
    r = importer.import_batch("materials", row, dry_run=True)
    assert r["success"] == 1
    rc = importer.import_batch("materials", row, dry_run=False)
    assert rc["success"] == 1
    found = db.material_requisition_tb(where="material_name='测试物料'")
    assert len(found) == 1 and found[0].amount == 50.0  # 10 × 5


def test_material_zero_quantity_rejected():
    r = importer.import_batch("materials", [{
        "material_name": "M1", "quantity": "0", "unit_price": "5",
        "project_code": "RD-2026-001",
    }], dry_run=True)
    assert r["failed"] == 1 and "数量" in r["errors"][0]["error"]


def test_labor_cost_preview_and_month_format():
    ok = [{"person_name": "张明远", "cost_month": "2026-02", "total_salary": "24000",
           "social_insurance": "4800", "housing_fund": "2400", "work_hours_total": "176"}]
    assert importer.import_batch("labor_cost", ok, dry_run=True)["success"] == 1
    bad = [{"person_name": "张明远", "cost_month": "2026-2", "total_salary": "24000"}]
    r = importer.import_batch("labor_cost", bad, dry_run=True)
    assert r["failed"] == 1 and "月份" in r["errors"][0]["error"]


# ── P1 实体：项目 / 委托 / 其他 / 特殊收入 / 证据 ──────────
def _count_tb(tb):
    return len(tb())

def test_project_preview_and_commit():
    rows = [{"name": "P1测试项目", "code": "RD-P1-001", "manager": "张明远",
             "boundary_type": "纯研发", "budget": "100000", "start_date": "2026-01-01",
             "end_date": "2026-12-31", "rd_nature": "自主研发", "rd_split_ratio": "1",
             "caliber": "高企认定,加计扣除", "status": "进行中", "description": "P1 测试"}]
    before = _count_tb(db.projects_tb)
    r = importer.import_batch("projects", rows, dry_run=True)
    assert r["ok"] and r["success"] == 1 and r["failed"] == 0
    assert _count_tb(db.projects_tb) == before          # 预检不落库
    r = importer.import_batch("projects", rows, dry_run=False)
    assert r["success"] == 1
    assert _count_tb(db.projects_tb) == before + 1

def test_project_invalid_status_rejected():
    rows = [{"name": "P1项目", "code": "RD-P1-002", "status": "未知状态"}]
    r = importer.import_batch("projects", rows, dry_run=True)
    assert r["success"] == 0 and r["failed"] == 1
    assert "状态" in r["errors"][0]["error"]

def test_outsourcing_preview_and_commit():
    rows = [{"contract_no": "WT-P1-001", "contractor": "某外包公司", "project_code": "RD-2026-001",
             "expense_date": "2026-02-10", "contract_amount": "50000", "actual_amount": "50000",
             "has_tech_transfer": "1", "is_overseas": "0", "caliber": "高企认定,加计扣除",
             "description": "P1"}]
    before = _count_tb(db.outsourcing_tb)
    r = importer.import_batch("outsourcing", rows, dry_run=False)
    assert r["ok"] and r["success"] == 1 and r["failed"] == 0
    assert _count_tb(db.outsourcing_tb) == before + 1

def test_outsourcing_missing_project_rejected():
    rows = [{"contract_no": "WT-P1-002", "contractor": "某公司", "actual_amount": "100"}]
    r = importer.import_batch("outsourcing", rows, dry_run=True)
    assert r["success"] == 0 and r["failed"] == 1
    assert "project_code" in r["errors"][0]["error"]

def test_others_preview_and_commit():
    rows = [{"project_code": "RD-2026-001", "category": "专家咨询", "expense_date": "2026-02-10",
             "amount": "3000", "caliber": "高企认定,加计扣除", "description": "P1"}]
    before = _count_tb(db.other_expense_tb)
    r = importer.import_batch("others", rows, dry_run=False)
    assert r["ok"] and r["success"] == 1
    assert _count_tb(db.other_expense_tb) == before + 1

def test_others_invalid_category_rejected():
    rows = [{"project_code": "RD-2026-001", "category": "不存在类别",
             "amount": "10", "expense_date": "2026-02-10"}]
    r = importer.import_batch("others", rows, dry_run=True)
    assert r["failed"] == 1
    assert "类别" in r["errors"][0]["error"]

def test_special_income_preview_and_commit():
    rows = [{"project_code": "RD-2026-001", "income_type": "样品销售", "amount": "5000",
             "income_date": "2026-02-10", "offset_caliber": "加计扣除", "note": "P1"}]
    before = _count_tb(db.special_income_tb)
    r = importer.import_batch("special_income", rows, dry_run=False)
    assert r["ok"] and r["success"] == 1
    assert _count_tb(db.special_income_tb) == before + 1

def test_special_income_invalid_type_rejected():
    rows = [{"project_code": "RD-2026-001", "income_type": "不存在类型", "amount": "10"}]
    r = importer.import_batch("special_income", rows, dry_run=True)
    assert r["failed"] == 1
    assert "类型" in r["errors"][0]["error"]

def test_evidence_preview_and_commit():
    rows = [{"project_code": "RD-2026-001", "ev_type": "立项决议", "name": "RD-2026-001 立项决议书",
             "phase": "研究", "upload_date": "2026-01-05", "description": "P1"}]
    before = _count_tb(db.evidence_tb)
    r = importer.import_batch("evidence", rows, dry_run=False)
    assert r["ok"] and r["success"] == 1
    assert _count_tb(db.evidence_tb) == before + 1

def test_evidence_invalid_type_rejected():
    rows = [{"project_code": "RD-2026-001", "ev_type": "不存在类型", "name": "证据"}]
    r = importer.import_batch("evidence", rows, dry_run=True)
    assert r["failed"] == 1
    assert "证据类型" in r["errors"][0]["error"]


# ── P1 逐行校验对齐既有规则 ────────────────────────────────
def test_outsourcing_overseas_2of3_cap():
    """境外委托按 80% 计入，累计超境内委托 2/3 上限即拦截（财税〔2018〕64号）。
    用超大金额确保超过库内 + 批次境内 cap。"""
    rows = [{"contract_no": "WT-O-1", "contractor": "境外B", "project_code": "RD-2026-001",
             "actual_amount": "999999", "is_overseas": "1"}]
    r = importer.import_batch("outsourcing", rows, dry_run=True)
    assert r["success"] == 0 and r["failed"] == 1
    assert "2/3" in r["errors"][0]["error"]

def test_outsourcing_overseas_within_cap_ok():
    rows = [{"contract_no": "WT-O-2", "contractor": "境外C", "project_code": "RD-2026-001",
             "actual_amount": "1000", "is_overseas": "1"}]
    r = importer.import_batch("outsourcing", rows, dry_run=True)
    assert r["success"] == 1 and r["failed"] == 0

def test_special_income_invalid_offset_caliber():
    rows = [{"project_code": "RD-2026-001", "income_type": "样品销售", "amount": "100",
             "offset_caliber": "不存在口径"}]
    r = importer.import_batch("special_income", rows, dry_run=True)
    assert r["failed"] == 1
    assert "冲减口径" in r["errors"][0]["error"]
