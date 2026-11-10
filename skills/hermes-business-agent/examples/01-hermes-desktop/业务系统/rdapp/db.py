"""db.py — 数据库模型与种子数据

研发费用管理系统数据层，使用 fastlite (SQLite) 存储。
涵盖：流程模板、费用科目、政策规则、组织架构、人员档案、
研发项目、项目流程实例、费用记录、证据材料、风险预警。
"""
import sys, os, json
from pathlib import Path
from datetime import datetime
from fastlite import database

if getattr(sys, 'frozen', False):
    # 冻结（PyInstaller onefile）模式：数据必须写到 EXE 同级目录（_MEIPASS 为只读临时目录）
    BASE_DIR = Path(sys.executable).parent
else:
    # 三层解耦：业务数据归入业务系统/data（dev 态 = 业务系统目录；
    # 独立 EXE 冻结态 = EXE 同级 data，两者一致）
    BASE_DIR = Path(__file__).parent.parent

# 允许通过环境变量覆盖数据目录（测试隔离 / 部署指定数据盘）
_env_db = os.environ.get("RD_DB_DIR")
if _env_db:
    BASE_DIR = Path(_env_db)

DB_PATH = BASE_DIR / "data" / "rd_expense.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

db = database(str(DB_PATH))


# ── 数据模型定义 ──────────────────────────────────────────────

class ProcessTemplate:
    """流程模板"""
    id: int
    name: str
    model_type: str       # 瀑布模型 / 敏捷迭代
    description: str = ""

class ProcessNode:
    """流程节点"""
    id: int
    template_id: int
    name: str
    phase: str            # 研究 / 开发 / 生产
    order_idx: int
    deliverable: str = ""
    budget_ratio: float = 0.0
    approver: str = ""

class ExpenseSubject:
    """费用科目（8大科目）"""
    id: int
    code: str
    name: str
    capitalizable: bool = False   # 是否可资本化
    description: str = ""

class PolicyRule:
    """政策规则"""
    id: int
    name: str
    caliber: str          # 高企认定 / 加计扣除 / 统计报表
    params: str = ""      # JSON 字符串
    description: str = ""
    # ── 政策规则库（缺口⑬部分）──
    version_no: int = 1          # 规则版本号（支持回滚）
    enabled: bool = True         # 是否启用
    updated_at: str = ""         # 最近更新时间

class Organization:
    """组织架构"""
    id: int
    name: str
    level: str            # 集团 / 子公司 / 部门
    parent_id: int = 0

class Personnel:
    """人员档案（含研发人员认定台账字段）

    rd-governor 人员管理10章 / 发行类第9号 要求：
    - 区分研究人员、技术人员、辅助人员（三类人员结构）
    - 记录学历专业、用工方式（在职/外聘/累计不满183天等）
    - 累计实际工作时间不满183天的研发人员不得计入（高企认定口径）
    - 社保缴纳单位与研发活动单位一致（IPO 核查要点）
    """
    id: int
    name: str
    org_id: int = 0
    title: str = ""
    is_rd: bool = True    # 是否研发人员
    hourly_rate: float = 0.0
    # ── 研发人员认定台账（AL-12）字段 ──
    person_category: str = "研究人员"   # 研究人员 / 技术人员 / 辅助人员
    education: str = ""               # 学历
    major: str = ""                   # 专业
    employment_type: str = "在职"      # 在职 / 外聘 / 劳务派遣 / 兼职
    id_number: str = ""               # 证件号（用于社保/个税比对）
    hire_date: str = ""               # 入职日期
    leave_date: str = ""              # 离职日期（空=在职）
    annual_rd_days: int = 0           # 当年累计研发工作天数（高企183天判定）
    social_insurance_unit: str = ""   # 社保缴纳单位（IPO 须与研发单位一致）
    certification_status: str = "待认定"  # 待认定 / 已认定 / 已停用
    certification_date: str = ""      # 最近一次认定/变更日期

class Project:
    """研发项目"""
    id: int
    name: str
    code: str
    status: str = "进行中"  # 立项中 / 进行中 / 已结题 / 已暂停
    template_id: int = 0
    budget: float = 0.0
    start_date: str = ""
    end_date: str = ""
    boundary_type: str = "纯研发"  # 纯研发 / 生产改进 / 混合
    boundary_desc: str = ""
    rd_split_ratio: float = 1.0    # 混合项目研发支出占比（0~1），用于分摊折算；纯研发=1
    annual_revenue: float = 0.0    # 企业年度销售收入（高企认定比例指标用）
    hightech_income: float = 0.0   # 高新技术产品（服务）收入（高企认定比例指标用）
    manager: str = ""
    caliber: str = "高企认定,加计扣除"  # 归集口径（逗号分隔）
    description: str = ""
    # ── M3 受托研发隔离 / M5 阶段精细化 ──
    rd_nature: str = "自主研发"   # 自主研发 / 委托研发 / 受托研发
    research_end: str = ""        # 研究阶段结束日（M5 手动覆盖节点判定）
    develop_end: str = ""         # 开发阶段结束日
    # ── M5 跨主体合规（缺口⑬）──
    org_id: int = 0               # 所属法人实体（关联 org_tree_tb / orgs_tb）

class ProjectNode:
    """项目流程实例节点"""
    id: int
    project_id: int
    node_id: int = 0
    node_name: str
    phase: str            # 研究 / 开发 / 生产
    status: str = "待开始"  # 待开始 / 进行中 / 已完成 / 已打回
    assignee: str = ""
    start_date: str = ""
    end_date: str = ""
    deliverable_status: str = "未提交"  # 未提交 / 待审批 / 已通过 / 已打回
    budget_ratio: float = 0.0

class Expense:
    """费用记录"""
    id: int
    project_id: int
    node_id: int = 0
    subject_id: int = 0
    subject_name: str = ""
    amount: float = 0.0
    expense_date: str = ""
    phase: str = ""           # 研究 / 开发 / 生产
    capitalize_status: str = "费用化"  # 费用化 / 待资本化 / 已资本化 / 非研发
    caliber: str = "高企认定,加计扣除"
    person_id: int = 0
    person_name: str = ""
    description: str = ""
    source: str = "手动录入"    # 手动录入 / 系统同步 / AI归集
    evidence_id: int = 0
    created_at: str = ""

class Evidence:
    """证据材料"""
    id: int
    project_id: int
    node_id: int = 0
    ev_type: str = ""     # 立项决议 / 项目计划 / 交付物 / 考勤工时 / 费用凭证 / 研发产出
    name: str = ""
    phase: str = ""       # 所属阶段
    upload_date: str = ""
    description: str = ""

class Risk:
    """风险预警"""
    id: int
    project_id: int = 0
    level: str = "中"      # 高 / 中 / 低
    risk_type: str = ""    # 阶段划分 / 边界模糊 / 资本化条件 / 预算超支 / 证据缺失
    description: str = ""
    status: str = "待处理"  # 待处理 / 已整改 / 已忽略
    suggestion: str = ""
    created_at: str = ""

class ProjectMember:
    """项目成员"""
    id: int
    project_id: int
    person_id: int
    role: str = "研发人员"  # 项目经理 / 研发人员 / 测试人员

class WorkTime:
    """研发人员工时登记"""
    id: int
    person_id: int
    project_id: int
    work_date: str = ""      # YYYY-MM-DD
    hours: float = 0.0
    task_desc: str = ""
    created_at: str = ""

class LaborCost:
    """人员人工费用总账（按月份）"""
    id: int
    person_id: int
    cost_month: str = ""      # YYYY-MM
    total_salary: float = 0.0  # 当月工资薪酬总额
    social_insurance: float = 0.0  # 当月社保费（按企业口径：个人+单位或单位部分）
    housing_fund: float = 0.0     # 当月住房公积金
    work_hours_total: float = 0.0  # 当月总工时（研发+非研发，作为分摊分母）
    non_rd_hours: float = 0.0  # 当月非研发工时（生产/管理/会议等，用于精确归集）
    hourly_cost: float = 0.0
    status: str = "待分摊"    # 待分摊 / 已分摊
    created_at: str = ""


class Equipment:
    """研发设备/资产档案"""
    id: int
    code: str = ""
    name: str
    category: str = ""        # 仪器设备 / 专用设备 / 软件 / 在用建筑物
    model: str = ""
    acquisition_date: str = ""
    acquisition_cost: float = 0.0
    depreciation_method: str = "年限平均法"
    useful_life: int = 60      # 预计使用年限（月）
    monthly_depreciation: float = 0.0  # 月折旧额
    status: str = "在用"        # 在用 / 闲置 / 报废
    dept_id: int = 0
    created_at: str = ""
    # ── 设备管理10章：来源、存放、共用、报废 ──
    source: str = "自购"        # 自购 / 融资租赁 / 经营租赁 / 接受投资 / 捐赠
    location: str = ""          # 存放地点（实物盘点依据）
    is_shared: int = 0          # 0 研发专用 / 1 研发与非研发共用（须分摊）
    residual_rate: float = 0.0  # 预计净残值率
    scrap_date: str = ""        # 报废日期
    scrap_reason: str = ""      # 报废原因
    scrap_income: float = 0.0   # 报废处置收入（应冲减研发费用）

class EquipmentWorkTime:
    """研发设备工时登记"""
    id: int
    equipment_id: int
    project_id: int
    work_date: str = ""      # YYYY-MM-DD
    hours: float = 0.0
    task_desc: str = ""
    created_at: str = ""

class EquipmentDepreciation:
    """设备折旧总账（按月）"""
    id: int
    equipment_id: int
    cost_month: str = ""      # YYYY-MM
    monthly_depreciation: float = 0.0
    rd_usage_ratio: float = 1.0  # 研发用途占比：研发工时/总工时（或按实际用途登记），用于精确归集
    allocated_hours_total: float = 0.0
    status: str = "待分摊"    # 待分摊 / 已分摊
    created_at: str = ""

class MaterialRequisition:
    """研发原材料领用与去向管理"""
    id: int
    material_name: str
    specification: str = ""
    unit: str = "个"
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0
    project_id: int = 0       # 去向项目
    requisition_date: str = ""
    requisitioner_id: int = 0
    purpose: str = ""         # 用途 / 去向说明
    usage_status: str = "已领用"  # 已领用 / 使用中 / 闲置 / 报废
    collected: int = 0        # 0 待归集 / 1 已归集
    created_at: str = ""
    # ── 物料管理9章：领料边界、试制试产、退料与废料 ──
    material_class: str = "研发专用"  # 研发专用 / 研发生产共用 / 生产用料
    rd_stage: str = "试制"          # 试制 / 中试 / 试产 / 量产
    rd_share_ratio: float = 1.0     # 研发用途占比（共用料按比例归集）
    returned_qty: float = 0.0       # 退料/余料回库数量
    returned_amount: float = 0.0    # 退料回库金额（应冲减）
    scrap_qty: float = 0.0          # 形成废料数量
    scrap_value: float = 0.0        # 废料残值/处置收入（应冲减）
    net_amount: float = 0.0         # 可归集净额 = 金额×占比 − 退料 − 废料残值
    boundary_note: str = ""         # 边界校验说明（稽查留痕）

class OutsourcingContract:
    """委托外部研发费用"""
    id: int
    contract_no: str = ""
    contractor: str = ""       # 受托方
    project_id: int = 0
    contract_amount: float = 0.0
    actual_amount: float = 0.0
    caliber: str = "高企认定,加计扣除"
    has_tech_transfer: int = 0  # 是否约定成果归属委托方（1/0）
    is_overseas: int = 0        # 是否境外受托方（1/0）：境外委托加计上限受 2/3 约束
    expense_date: str = ""
    description: str = ""
    collected: int = 0
    created_at: str = ""

class CapitalizationReview:
    """开发阶段资本化条件审批（5 条件 + 可行性证明）"""
    id: int
    project_id: int = 0
    expense_id: int = 0
    cond_tech: int = 0       # ①技术可行
    cond_intent: int = 0     # ②有意图完成并使用/出售
    cond_usable: int = 0     # ③能够使用/出售
    cond_benefit: int = 0    # ④使用寿命内带来经济利益
    cond_measure: int = 0    # ⑤支出可靠计量
    feasibility_evidence_id: int = 0  # 关联可行性证明证据
    reviewer: str = ""
    decided_at: str = ""
    status: str = "待审"      # 待审 / 通过 / 驳回
    note: str = ""


class OtherExpense:
    """其他相关费用"""
    id: int
    project_id: int = 0
    category: str = ""        # 技术图书 / 资料翻译 / 专家咨询 / 知识产权 / 差旅 / 会议 / 其他
    expense_date: str = ""
    amount: float = 0.0
    description: str = ""
    caliber: str = "高企认定,加计扣除"
    collected: int = 0
    created_at: str = ""


class EntrustedContract:
    """受托研发合同台账（我方为受托方）

    受托研发取得的收入属于「营业收入」，其对应支出若由委托方支付，
    不应重复计入我方研发费用加计扣除基数（避免双重归集）。本表用于隔离
    跟踪受托研发业务，确保受托收入不混入研发费用统计（M3）。
    """
    id: int
    contract_no: str = ""
    entrustor: str = ""        # 委托方名称
    project_id: int = 0
    contract_amount: float = 0.0
    recognized_revenue: float = 0.0   # 已确认营业收入
    our_rd_cost: float = 0.0          # 我方实际研发投入（如合同含我方研发）
    caliber: str = "高企认定"
    status: str = "进行中"      # 进行中 / 已结题
    sign_date: str = ""
    note: str = ""
    created_at: str = ""


class SpecialIncome:
    """特殊收入（需冲减研发费用加计扣除基数）（M4）

    包括：① 不征税收入用于研发的部分，其对应支出不得加计扣除；
    ② 政府补助专项用于研发，若作为不征税收入处理则需冲减；
    ③ 样品 / 副产品销售收入（见样品废料台账）冲减。
    """
    id: int
    project_id: int = 0
    income_type: str = ""     # 不征税收入 / 政府补助 / 样品销售 / 废料处置
    amount: float = 0.0
    income_date: str = ""
    offset_caliber: str = "加计扣除"   # 冲减口径
    note: str = ""
    created_at: str = ""


class SampleScrap:
    """样品、废料台账（研发产出去向）（M4/M7）

    样品销售收入应冲减研发费用（特殊收入）；废料处置残值单独记录。
    """
    id: int
    project_id: int = 0
    item_type: str = "样品"    # 样品 / 废料
    name: str = ""
    quantity: float = 0.0
    unit: str = "个"
    disposal: str = "留存"     # 留存 / 销售 / 报废 / 领回生产
    realized_amount: float = 0.0   # 销售实现收入（样品销售）/ 残值（废料）
    record_date: str = ""
    note: str = ""
    created_at: str = ""


class AuditLog:
    """审计操作日志（内控留痕）

    记录系统内所有关键写操作的"谁/何时/对什么/做了什么"，用于内控追溯与合规审计。
    动作类型 action：CREATE / UPDATE / DELETE / APPROVE / REJECT / WITHDRAW / LOGIN 等。
    """
    id: int
    ts: str = ""               # 操作时间 YYYY-MM-DD HH:MM
    actor: str = ""            # 操作人
    action: str = ""           # 动作类型
    entity: str = ""           # 实体/表名
    entity_id: int = 0         # 关联记录 id
    detail: str = ""           # 操作摘要
    before: str = ""           # 变更前（JSON，可选）
    after: str = ""            # 变更后（JSON，可选）


class ApprovalReq:
    """研发费用报销/归集审批单（审批工作流 + 审批权限矩阵）

    多级审批：经办提交 → 部门复核 → 分级批准（按金额层级）。
    强制职责分离：复核人≠提交人、批准人≠提交人且≠复核人。
    """
    id: int
    expense_id: int = 0        # 关联费用记录（0 表示独立审批事项）
    project_id: int = 0
    submitter: str = ""        # 经办人（提交人）
    amount: float = 0.0        # 金额
    subject: str = ""          # 费用类别
    description: str = ""
    status: str = "待复核"      # 待复核 / 已复核 / 已批准 / 已驳回 / 已撤回
    reviewer: str = ""         # 复核人（部门负责人）
    approver: str = ""         # 批准人（按金额分级：部门/财务总监/总经理/董事会）
    approval_level: str = ""   # 所需批准层级：部门 / 总办 / 董事会
    submitted_at: str = ""
    reviewed_at: str = ""
    decided_at: str = ""
    note: str = ""


class ControlAssessment:
    """内控成熟度自评快照（内控治理中心）

    按 rd-governor 内控制度九章节逐项评分（0-5），记录成熟度评级与差距清单。
    """
    id: int
    ts: str = ""
    assessor: str = ""
    scores: str = ""           # JSON: {章节: 0-5}
    total_score: float = 0.0   # 总分（满分 45）
    maturity: str = ""         # 成熟度评级：初创 / 基础 / 规范 / 成熟
    gaps: str = ""             # JSON list: 差距项
    note: str = ""


# ── 三大核心板块合规台账：人员 / 设备 / 材料 ──────────────

class LaborAllocation:
    """研发人员人工费用分配明细表（rd-governor 指令7 / AL-07 分配表）

    每次执行人工费用分摊时逐条落库，形成可复查、可导出的分配明细，
    满足税务稽查"人工费用分摊依据"举证要求。
    """
    id: int
    cost_month: str = ""          # YYYY-MM
    person_id: int = 0
    person_name: str = ""
    person_category: str = ""     # 研究/技术/辅助人员
    project_id: int = 0
    project_name: str = ""
    project_hours: float = 0.0    # 该人员投入该项目工时
    person_total_hours: float = 0.0   # 该人员当月总工时（分摊分母）
    rd_hours: float = 0.0         # 当月研发工时
    rd_ratio: float = 0.0         # 研发工时占比
    alloc_ratio: float = 0.0      # 项目工时占比
    salary_base: float = 0.0      # 当月人工总成本（分摊基数）
    amount: float = 0.0           # 分摊金额
    caliber: str = ""             # 归集口径
    phase: str = ""               # 研究 / 开发
    batch_no: str = ""            # 分摊批次号（同一次执行共用）
    created_at: str = ""


class EquipmentSharing:
    """共用设备研发用途分摊登记（rd-governor 指令20 / 设备管理10章）

    研发与生产共用的设备，须按合理依据（机时/工时/产量）拆分研发用途占比，
    经审批后回写当月折旧总账，避免全额计入研发费用被纳税调整。
    """
    id: int
    equipment_id: int = 0
    cost_month: str = ""
    rd_hours: float = 0.0         # 研发用途机时
    prod_hours: float = 0.0       # 生产用途机时
    other_hours: float = 0.0      # 管理/其他用途机时
    basis: str = "机时"            # 分摊依据：机时 / 产量 / 面积 / 人工工时
    computed_ratio: float = 0.0   # 计算得出的研发用途占比
    approver: str = ""            # 审批人（职责分离）
    approve_date: str = ""
    applied: int = 0              # 是否已回写折旧总账
    note: str = ""
    created_at: str = ""


class PersonnelChange:
    """研发人员认定与变更记录（rd-governor 指令17 / 人员认定流程）

    研发人员的认定、停用、类别调整全过程留痕，供高企复核与 IPO 核查。
    """
    id: int
    person_id: int = 0
    person_name: str = ""
    change_type: str = "认定"      # 认定 / 变更 / 停用 / 恢复
    before_value: str = ""
    after_value: str = ""
    reason: str = ""
    operator: str = ""
    change_date: str = ""
    created_at: str = ""


# ── M1–M6 二期新增模型（报表/凭证/数据中心/风控/工时预警/组织/分摊/专利/人事/物料/权限）──

class ReportVersion:
    """报表版本（缺口①⑭：月度版本化+锁定+多口径）

    period 形如 YYYY-MM；caliber 取值 高企认定/加计扣除/会计/R&D统计/IPO/业务管理/财务核算；
    data_hash 为报表内容 SHA256，锁定后只读可复现。
    """
    id: int
    project_id: int = 0
    period: str = ""            # YYYY-MM
    caliber: str = ""           # 高企认定 / 加计扣除 / 会计 / R&D统计 / IPO / 业务管理 / 财务核算
    data_hash: str = ""         # 报表内容 SHA256
    is_locked: bool = False
    locked_at: str = ""
    locked_by: str = ""
    created_at: str = ""


class EvidenceDoc:
    """凭证与备查文件（缺口⑦：费用-凭证-备查闭环）"""
    id: int
    expense_id: int = 0         # 关联 expense_tb
    project_id: int = 0
    ev_type: str = "凭证"       # 凭证 / 备查材料 / 辅助账附件 / 其他
    doc_name: str = ""
    file_path: str = ""
    upload_date: str = ""
    uploader: str = ""
    remark: str = ""
    created_at: str = ""


class DataCenterLog:
    """数据中心变更日志（缺口⑪：跨模块数据血缘追踪）"""
    id: int
    source_table: str = ""      # expense_tb / worktime_tb / equipment_tb ...
    source_id: int = 0
    field_key: str = ""
    old_val: str = ""
    new_val: str = ""
    sync_time: str = ""
    operator: str = ""
    created_at: str = ""


class RiskRule:
    """风控规则库（缺口⑩-a：费用/政策/管理三类风险规则）"""
    id: int
    rule_name: str = ""
    rule_type: str = "费用"     # 费用 / 政策 / 管理
    threshold: str = ""         # 阈值（JSON 字符串，按规则类型解析）
    action: str = "警告"        # 警告 / 拦截 / 提示
    description: str = ""
    enabled: bool = True
    created_at: str = ""


class RiskAlert:
    """风控预警实例（缺口⑩-a/②：规则扫描结果）"""
    id: int
    project_id: int = 0
    rule_id: int = 0
    level: str = "中"           # 高 / 中 / 低
    description: str = ""
    status: str = "未处理"      # 未处理 / 已处理 / 已忽略
    suggested_action: str = ""
    created_at: str = ""


class WorkTimeAlertRule:
    """工时预警规则（缺口②：占比过低/单日上限阈值）"""
    id: int
    project_id: int = 0         # 0=全局
    person_id: int = 0          # 0=全局
    min_rd_ratio: float = 0.3   # 最低研发工时占比
    max_single_hours: float = 12.0  # 单日最高工时上限
    enabled: bool = True
    created_at: str = ""


class OrgTree:
    """组织树节点（缺口⑬：集团-子公司-部门三级结构）"""
    id: int
    org_id: int = 0             # 关联 Organization
    name: str = ""
    level: str = "子公司"       # 集团 / 子公司 / 部门
    parent_id: int = 0
    created_at: str = ""


class DeviceSharingRatio:
    """多用途设备分摊比例（缺口⑫：研发/生产共享、跨项目分摊）"""
    id: int
    equipment_id: int = 0
    project_id: int = 0
    share_ratio: float = 1.0    # 0-1
    share_reason: str = ""
    effective_month: str = ""   # YYYY-MM，空=长期有效
    created_at: str = ""


class PatentRecord:
    """专利成果记录（缺口③：研发产出与投入关联）"""
    id: int
    project_id: int = 0
    patent_no: str = ""
    title: str = ""
    patent_type: str = "实用新型"   # 发明 / 实用新型 / 外观设计 / 软著 / 其他
    application_date: str = ""
    grant_date: str = ""
    relation_note: str = ""
    created_at: str = ""


class AttendanceRecord:
    """考勤打卡记录（缺口⑧：人事考勤一体化）"""
    id: int
    person_id: int = 0
    work_date: str = ""
    check_in: str = ""
    check_out: str = ""
    status: str = "正常"        # 正常 / 迟到 / 早退 / 缺勤 / 请假
    created_at: str = ""


class SalaryRecord:
    """月度薪酬计提记录（缺口⑧：薪资社保公积金）"""
    id: int
    person_id: int = 0
    month: str = ""             # YYYY-MM
    base_salary: float = 0.0
    social_security: float = 0.0
    housing_fund: float = 0.0
    bonus: float = 0.0
    other_allowance: float = 0.0
    total: float = 0.0
    created_at: str = ""


class MaterialSubType:
    """物料类型字典（缺口④：原料/样品/废料细分建账）"""
    id: int
    name: str = ""              # 原料 / 样品 / 废料
    code: str = ""
    is_rd_material: bool = True
    created_at: str = ""


class ProjectRole:
    """项目级角色权限（缺口⑨：项目经理/研发人员/观察员）"""
    id: int
    project_id: int = 0
    person_id: int = 0
    role: str = "研发人员"      # 项目经理 / 研发人员 / 观察员
    created_at: str = ""


# ── 建表 ──────────────────────────────────────────────

templates_tb = db.create(ProcessTemplate, pk='id', transform=True)
nodes_tb = db.create(ProcessNode, pk='id', transform=True)
subjects_tb = db.create(ExpenseSubject, pk='id', transform=True)
policies_tb = db.create(PolicyRule, pk='id', transform=True)
orgs_tb = db.create(Organization, pk='id', transform=True)
personnel_tb = db.create(Personnel, pk='id', transform=True)
projects_tb = db.create(Project, pk='id', transform=True)
project_nodes_tb = db.create(ProjectNode, pk='id', transform=True)
expenses_tb = db.create(Expense, pk='id', transform=True)
evidence_tb = db.create(Evidence, pk='id', transform=True)
risks_tb = db.create(Risk, pk='id', transform=True)
members_tb = db.create(ProjectMember, pk='id', transform=True)
work_time_tb = db.create(WorkTime, pk='id', transform=True)
labor_cost_tb = db.create(LaborCost, pk='id', transform=True)
equipment_tb = db.create(Equipment, pk='id', transform=True)
equipment_work_time_tb = db.create(EquipmentWorkTime, pk='id', transform=True)
equipment_depreciation_tb = db.create(EquipmentDepreciation, pk='id', transform=True)
material_requisition_tb = db.create(MaterialRequisition, pk='id', transform=True)
outsourcing_tb = db.create(OutsourcingContract, pk='id', transform=True)
other_expense_tb = db.create(OtherExpense, pk='id', transform=True)
capitalization_tb = db.create(CapitalizationReview, pk='id', transform=True)

# ── M1–M7 新增数据模型 ──
entrusted_tb = db.create(EntrustedContract, pk='id', transform=True)
special_income_tb = db.create(SpecialIncome, pk='id', transform=True)
sample_scrap_tb = db.create(SampleScrap, pk='id', transform=True)

# ── 内控与治理：审计日志 / 审批单 / 内控自评 ──
audit_tb = db.create(AuditLog, pk='id', transform=True)
approval_tb = db.create(ApprovalReq, pk='id', transform=True)
assessment_tb = db.create(ControlAssessment, pk='id', transform=True)

# ── 三大核心板块合规台账 ──
labor_alloc_tb = db.create(LaborAllocation, pk='id', transform=True)
equipment_sharing_tb = db.create(EquipmentSharing, pk='id', transform=True)
personnel_change_tb = db.create(PersonnelChange, pk='id', transform=True)

# ── M1–M6 二期新增表 ──
report_versions_tb = db.create(ReportVersion, pk='id', transform=True)
evidence_docs_tb = db.create(EvidenceDoc, pk='id', transform=True)
datacenter_logs_tb = db.create(DataCenterLog, pk='id', transform=True)
risk_rules_tb = db.create(RiskRule, pk='id', transform=True)
risk_alerts_tb = db.create(RiskAlert, pk='id', transform=True)
worktime_alert_rules_tb = db.create(WorkTimeAlertRule, pk='id', transform=True)
org_tree_tb = db.create(OrgTree, pk='id', transform=True)
device_sharing_ratios_tb = db.create(DeviceSharingRatio, pk='id', transform=True)
patent_records_tb = db.create(PatentRecord, pk='id', transform=True)
attendance_records_tb = db.create(AttendanceRecord, pk='id', transform=True)
salary_records_tb = db.create(SalaryRecord, pk='id', transform=True)
material_sub_types_tb = db.create(MaterialSubType, pk='id', transform=True)
project_roles_tb = db.create(ProjectRole, pk='id', transform=True)


# ── 种子数据 ──────────────────────────────────────────────

def seed_data():
    """初始化种子数据（仅首次运行时插入）"""
    if len(templates_tb()) > 0:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 费用科目（8大科目）──
    subjects_data = [
        ("01", "人员人工费用", False, "直接从事研发活动人员的工资薪金、基本养老保险等"),
        ("02", "直接投入费用", False, "研发活动直接消耗的材料、燃料和动力费用"),
        ("03", "折旧费用与长期待摊", False, "用于研发活动的仪器、设备和在用建筑物的折旧费"),
        ("04", "无形资产摊销", False, "用于研发活动的软件、专利权、非专利技术等摊销"),
        ("05", "设计费用", True, "为获得创新性创意产品，进行设计发生的费用"),
        ("06", "装备调试费用与试验", True, "工装准备过程中研发活动所发生的费用"),
        ("07", "委托外部研究费用", False, "委托外部机构或个人进行研发活动所发生的费用"),
        ("08", "其他费用", False, "与研发活动直接相关的其他费用，总额不超过可加计扣除研发费用总额的10%"),
    ]
    for code, name, cap, desc in subjects_data:
        subjects_tb.insert(code=code, name=name, capitalizable=cap, description=desc)

    # ── 流程模板 ──
    t1 = templates_tb.insert(name="瀑布模型（标准研发流程）", model_type="瀑布模型",
        description="需求调研→可行性研究→系统设计→编码实现→集成测试→用户验收→上线部署")
    t2 = templates_tb.insert(name="敏捷迭代（标准研发流程）", model_type="敏捷迭代",
        description="研究Spike→迭代开发→测试评审→版本发布")

    # 瀑布模型节点
    waterfall_nodes = [
        ("需求调研", "研究", 10, "需求调研报告", 5, "产品经理"),
        ("可行性研究", "研究", 20, "可行性研究报告", 10, "技术负责人"),
        ("技术预研", "研究", 30, "技术预研报告", 10, "技术负责人"),
        ("系统设计", "开发", 40, "系统设计文档", 15, "架构师"),
        ("编码实现", "开发", 50, "源代码+技术文档", 25, "开发团队"),
        ("集成测试", "开发", 60, "测试报告", 15, "测试团队"),
        ("用户验收", "开发", 70, "验收报告", 10, "产品经理"),
        ("上线部署", "生产", 80, "部署文档", 10, "运维团队"),
    ]
    for name, phase, order, deliv, ratio, approver in waterfall_nodes:
        nodes_tb.insert(template_id=t1.id, name=name, phase=phase, order_idx=order,
            deliverable=deliv, budget_ratio=ratio, approver=approver)

    # 敏捷迭代节点
    agile_nodes = [
        ("研究Spike", "研究", 10, "Spike研究报告", 10, "技术负责人"),
        ("迭代规划", "研究", 20, "迭代计划", 5, "产品经理"),
        ("迭代开发-1", "开发", 30, "可演示版本", 20, "开发团队"),
        ("迭代开发-2", "开发", 40, "可演示版本", 20, "开发团队"),
        ("测试评审", "开发", 50, "测试报告+评审记录", 15, "测试团队"),
        ("版本发布", "生产", 60, "发布说明", 10, "运维团队"),
    ]
    for name, phase, order, deliv, ratio, approver in agile_nodes:
        nodes_tb.insert(template_id=t2.id, name=name, phase=phase, order_idx=order,
            deliverable=deliv, budget_ratio=ratio, approver=approver)

    # ── 政策规则 ──
    policies_data = [
        ("高企认定口径", "高企认定",
         json.dumps({"other_ratio_max": 0.2, "personnel_ratio_min": 0.1, "rd_ratio_min": 0.03}),
         "高新技术企业认定研发费用归集口径，其他费用占比不超过20%"),
        ("加计扣除口径", "加计扣除",
         json.dumps({"other_ratio_max": 0.1, "deduction_rate": 1.0, "outsourcing_ratio_max": 0.8}),
         "研发费用加计扣除口径，其他费用占比不超过10%，扣除比例100%"),
        ("统计报表口径", "统计报表",
         json.dumps({"include_all": True, "report_freq": "月度"}),
         "国家统计局研发费用统计口径，全口径归集"),
    ]
    for name, caliber, params, desc in policies_data:
        policies_tb.insert(name=name, caliber=caliber, params=params, description=desc)

    # ── 组织架构 ──
    org_root = orgs_tb.insert(name="总部", level="集团")
    org_sub1 = orgs_tb.insert(name="研发中心", level="子公司", parent_id=org_root.id)
    org_sub2 = orgs_tb.insert(name="生产制造部", level="子公司", parent_id=org_root.id)
    orgs_tb.insert(name="前端研发组", level="部门", parent_id=org_sub1.id)
    orgs_tb.insert(name="后端研发组", level="部门", parent_id=org_sub1.id)
    orgs_tb.insert(name="算法研发组", level="部门", parent_id=org_sub1.id)
    orgs_tb.insert(name="质量管理组", level="部门", parent_id=org_sub2.id)

    # ── 人员档案 ──
    personnel_data = [
        ("张明远", org_sub1.id, "研发总监", True, 300),
        ("李思琪", org_sub1.id, "高级架构师", True, 250),
        ("王浩然", org_sub1.id, "前端开发工程师", True, 180),
        ("赵雪梅", org_sub1.id, "后端开发工程师", True, 180),
        ("陈志强", org_sub1.id, "算法工程师", True, 220),
        ("刘婷婷", org_sub1.id, "测试工程师", True, 150),
        ("周建国", org_sub2.id, "生产主管", False, 200),
        ("吴晓燕", org_sub1.id, "产品经理", True, 200),
    ]
    for name, org_id, title, is_rd, rate in personnel_data:
        personnel_tb.insert(name=name, org_id=org_id, title=title, is_rd=is_rd, hourly_rate=rate)

    # ── 示例项目 ──
    p1 = projects_tb.insert(
        name="智能数据分析平台研发", code="RD-2026-001",
        status="进行中", template_id=t1.id, budget=500000,
        start_date="2026-01-15", end_date="2026-09-30",
        boundary_type="纯研发",
        boundary_desc="纯研发项目，全部费用归集为研发费用",
        manager="张明远", caliber="高企认定,加计扣除",
        rd_split_ratio=1.0, annual_revenue=6000000, hightech_income=4200000,
        description="基于AI的数据分析与可视化平台，包含数据采集、清洗、分析、展示全流程"
    )
    p2 = projects_tb.insert(
        name="新一代ERP系统升级", code="RD-2026-002",
        status="进行中", template_id=t2.id, budget=800000,
        start_date="2026-02-01", end_date="2026-12-31",
        boundary_type="混合",
        boundary_desc="研发部分：核心模块重构、新功能开发；生产部分：系统部署、数据迁移、用户培训",
        manager="李思琪", caliber="高企认定,加计扣除",
        rd_split_ratio=0.7, annual_revenue=12000000, hightech_income=7800000,
        description="ERP系统核心模块重构与云端化升级，包含采购、库存、财务模块重构"
    )
    p3 = projects_tb.insert(
        name="工业物联网网关研发", code="RD-2026-003",
        status="立项中", template_id=t1.id, budget=350000,
        start_date="2026-03-01", end_date="2026-08-31",
        boundary_type="纯研发",
        boundary_desc="纯研发项目，研发工业物联网网关设备及通信协议",
        manager="陈志强", caliber="高企认定,加计扣除",
        rd_split_ratio=1.0, annual_revenue=3000000, hightech_income=2100000,
        description="面向工业场景的物联网网关设备研发，支持多协议接入和边缘计算"
    )

    # ── 项目流程实例（项目1的节点）──
    # 各节点起始日期（用于按费用发生日判定所处阶段：研究→开发→生产 单调推进）
    p1_start = ["2026-01-15", "2026-01-25", "2026-02-04", "2026-02-20",
                "2026-03-01", "2026-03-20", "2026-04-10", "2026-05-10"]
    p1_end = ["2026-01-24", "2026-02-03", "2026-02-19", "2026-03-15",
              "2026-03-28", "2026-04-09", "2026-05-05", "2026-05-30"]
    wf_nodes = nodes_tb(where=f"template_id={t1.id}", order_by="order_idx")
    for i, node in enumerate(wf_nodes):
        status = "已完成" if i < 3 else ("进行中" if i == 3 else "待开始")
        deliv_status = "已通过" if i < 3 else ("待审批" if i == 3 else "未提交")
        project_nodes_tb.insert(
            project_id=p1.id, node_id=node.id, node_name=node.name,
            phase=node.phase, status=status, assignee=node.approver,
            start_date=p1_start[i], end_date=p1_end[i],
            deliverable_status=deliv_status, budget_ratio=node.budget_ratio
        )

    # 项目2的节点（敏捷）
    p2_start = ["2026-02-01", "2026-02-12", "2026-02-25", "2026-03-10",
                "2026-03-25", "2026-04-20"]
    p2_end = ["2026-02-11", "2026-02-24", "2026-03-09", "2026-03-24",
              "2026-04-15", "2026-05-10"]
    ag_nodes = nodes_tb(where=f"template_id={t2.id}", order_by="order_idx")
    for i, node in enumerate(ag_nodes):
        status = "已完成" if i < 2 else ("进行中" if i == 2 else "待开始")
        deliv_status = "已通过" if i < 2 else ("待审批" if i == 2 else "未提交")
        project_nodes_tb.insert(
            project_id=p2.id, node_id=node.id, node_name=node.name,
            phase=node.phase, status=status, assignee=node.approver,
            start_date=p2_start[i], end_date=p2_end[i],
            deliverable_status=deliv_status, budget_ratio=node.budget_ratio
        )

    # ── 项目成员 ──
    for pid, person_id, role in [
        (p1.id, 1, "项目经理"), (p1.id, 2, "架构师"), (p1.id, 3, "前端开发"),
        (p1.id, 4, "后端开发"), (p1.id, 6, "测试"), (p1.id, 8, "产品经理"),
        (p2.id, 2, "项目经理"), (p2.id, 4, "后端开发"), (p2.id, 5, "算法工程师"),
        (p2.id, 6, "测试"), (p2.id, 8, "产品经理"),
    ]:
        members_tb.insert(project_id=pid, person_id=person_id, role=role)

    # ── 费用记录 ──
    expense_data = [
        # 项目1 - 研究阶段费用（费用化）
        (p1.id, 1, 1, "人员人工费用", 45000, "2026-01-20", "研究", "费用化", "张明远", "1月研发人员工资"),
        (p1.id, 1, 2, "直接投入费用", 12000, "2026-01-22", "研究", "费用化", "王浩然", "调研差旅及材料费"),
        (p1.id, 1, 1, "人员人工费用", 42000, "2026-02-15", "研究", "费用化", "李思琪", "2月研发人员工资"),
        (p1.id, 2, 3, "其他费用", 8000, "2026-02-18", "研究", "费用化", "吴晓燕", "专利检索及咨询费"),
        # 项目1 - 开发阶段费用（待资本化）
        (p1.id, 3, 5, "设计费用", 35000, "2026-03-10", "开发", "待资本化", "李思琪", "系统架构设计费用"),
        (p1.id, 3, 1, "人员人工费用", 48000, "2026-03-15", "开发", "待资本化", "王浩然", "3月开发人员工资"),
        (p1.id, 3, 2, "直接投入费用", 15000, "2026-03-20", "开发", "待资本化", "赵雪梅", "开发环境服务器费用"),
        (p1.id, 3, 3, "折旧费用与长期待摊", 8000, "2026-03-25", "开发", "待资本化", "", "研发设备折旧"),
        # 项目2 - 研究阶段费用
        (p2.id, 1, 1, "人员人工费用", 55000, "2026-02-10", "研究", "费用化", "李思琪", "2月研发人员工资"),
        (p2.id, 1, 4, "无形资产摊销", 6000, "2026-02-15", "研究", "费用化", "", "开发工具软件许可摊销"),
        # 项目2 - 开发阶段费用
        (p2.id, 2, 5, "设计费用", 50000, "2026-03-05", "开发", "待资本化", "李思琪", "ERP架构重构设计"),
        (p2.id, 2, 1, "人员人工费用", 60000, "2026-03-15", "开发", "待资本化", "赵雪梅", "3月开发人员工资"),
        (p2.id, 2, 7, "委托外部研究费用", 30000, "2026-03-20", "开发", "费用化", "", "委托外部UI设计（不可资本化）"),
    ]
    for proj_id, node_idx, subj_id, subj_name, amount, dt, phase, cap_status, person, desc in expense_data:
        # 找到对应的项目节点
        pn = project_nodes_tb(where=f"project_id={proj_id}", order_by="id")
        node_id = pn[node_idx - 1].id if node_idx <= len(pn) else 0
        person_obj = personnel_tb(where=f"name='{person}'") if person else None
        person_id = person_obj[0].id if person_obj else 0
        expenses_tb.insert(
            project_id=proj_id, node_id=node_id, subject_id=subj_id,
            subject_name=subj_name, amount=amount, expense_date=dt,
            phase=phase, capitalize_status=cap_status,
            caliber="高企认定,加计扣除", person_id=person_id, person_name=person,
            description=desc, source="手动录入", created_at=now
        )

    # ── 证据材料 ──
    evidence_data = [
        (p1.id, 1, "立项决议", "RD-2026-001立项决议书", "研究", "2026-01-15"),
        (p1.id, 1, "项目计划", "智能数据分析平台项目计划书", "研究", "2026-01-16"),
        (p1.id, 1, "交付物", "需求调研报告v1.0", "研究", "2026-01-25"),
        (p1.id, 2, "交付物", "可行性研究报告", "研究", "2026-02-05"),
        (p1.id, 3, "交付物", "技术预研报告", "研究", "2026-02-20"),
        (p1.id, 4, "交付物", "系统设计文档v1.0", "开发", "2026-03-10"),
        (p1.id, 1, "费用凭证", "1月工资发放表", "研究", "2026-01-31"),
        (p1.id, 3, "费用凭证", "3月研发人员工资表", "开发", "2026-03-31"),
        (p2.id, 1, "立项决议", "RD-2026-002立项决议书", "研究", "2026-02-01"),
        (p2.id, 1, "项目计划", "ERP升级项目计划书", "研究", "2026-02-02"),
        (p2.id, 1, "交付物", "Spike研究报告", "研究", "2026-02-15"),
    ]
    for proj_id, node_idx, ev_type, name, phase, dt in evidence_data:
        pn = project_nodes_tb(where=f"project_id={proj_id}", order_by="id")
        node_id = pn[node_idx - 1].id if node_idx <= len(pn) else 0
        evidence_tb.insert(
            project_id=proj_id, node_id=node_id, ev_type=ev_type,
            name=name, phase=phase, upload_date=dt, description=""
        )

    # ── 风险预警 ──
    risks_data = [
        (p2.id, "高", "边界模糊",
         "项目RD-2026-002为混合类型，生产部分（系统部署、数据迁移）费用未明确划分规则",
         "待处理", "建议在项目立项中补充研发与生产的费用划分规则，明确哪些环节属于研发费用归集范围"),
        (p1.id, "中", "阶段划分",
         "项目RD-2026-001研究阶段费用占比偏低（38%），请确认研究/开发阶段划分是否合理",
         "待处理", "建议核查各流程节点的阶段标记是否准确，必要时调整阶段边界（需技术总监审批）"),
        (p2.id, "中", "资本化条件",
         "项目RD-2026-002开发阶段资本化条件未完全满足，缺少市场可行性证明",
         "待处理", "建议补充市场可行性分析报告，否则开发阶段费用需费用化处理"),
        (p1.id, "低", "证据缺失",
         "项目RD-2026-001研究阶段缺少2份调研报告",
         "已整改", "已补充提交相关调研报告"),
    ]
    for proj_id, level, rtype, desc, status, suggestion in risks_data:
        risks_tb.insert(
            project_id=proj_id, level=level, risk_type=rtype,
            description=desc, status=status, suggestion=suggestion,
            created_at=now
        )

    # ── 工时登记（示例：2026-01 项目1研究阶段，2026-03 项目1/2 开发阶段）──
    worktime_data = [
        # 2026-01 研究阶段
        (1, p1.id, "2026-01-06", 6, "需求调研与可行性分析"),
        (1, p1.id, "2026-01-13", 6, "可行性研究报告撰写"),
        (2, p1.id, "2026-01-14", 7, "技术预研方案设计"),
        (3, p1.id, "2026-01-15", 4, "原型交互设计"),
        (8, p1.id, "2026-01-16", 5, "产品需求文档整理"),
        # 2026-03 开发阶段
        (2, p1.id, "2026-03-02", 8, "系统架构设计"),
        (3, p1.id, "2026-03-03", 8, "前端框架搭建"),
        (4, p1.id, "2026-03-04", 8, "后端接口开发"),
        (2, p2.id, "2026-03-05", 6, "ERP架构重构"),
        (4, p2.id, "2026-03-06", 7, "ERP核心模块开发"),
        (5, p2.id, "2026-03-07", 6, "算法模型训练"),
        (6, p1.id, "2026-03-08", 5, "集成测试用例编写"),
        (6, p2.id, "2026-03-09", 4, "测试评审准备"),
        (8, p2.id, "2026-03-10", 5, "迭代规划与需求澄清"),
    ]
    for person_id, proj_id, dt, hours, desc in worktime_data:
        work_time_tb.insert(
            person_id=person_id, project_id=proj_id, work_date=dt,
            hours=hours, task_desc=desc, created_at=now
        )

    # ── 人工费用总账（示例：2026-01/03 两个月）──
    labor_cost_data = [
        (1, "2026-01", 24000, 168, 0),   # 张明远
        (2, "2026-01", 28000, 160, 0),   # 李思琪
        (3, "2026-01", 18000, 168, 0),   # 王浩然
        (2, "2026-03", 30000, 176, 0),   # 李思琪
        (3, "2026-03", 19000, 176, 0),   # 王浩然
        (4, "2026-03", 19000, 176, 0),   # 赵雪梅
        (5, "2026-03", 22000, 168, 0),   # 陈志强
        (6, "2026-03", 14000, 160, 0),   # 刘婷婷
        (8, "2026-03", 18000, 168, 0),   # 吴晓燕
    ]
    for person_id, month, salary, total_hours, non_rd in labor_cost_data:
        hourly = round(salary / total_hours, 2) if total_hours > 0 else 0.0
        labor_cost_tb.insert(
            person_id=person_id, cost_month=month, total_salary=salary,
            work_hours_total=total_hours, non_rd_hours=non_rd,
            hourly_cost=hourly,
            status="待分摊", created_at=now
        )


# ── 共享业务辅助函数（供各路由模块复用）───────────────────

def get_active_project_node(project_id: int):
    """返回项目当前进行中节点；无则首个节点；无节点返回 None"""
    nodes = project_nodes_tb(where=f"project_id={project_id}", order_by="id")
    active = [n for n in nodes if n.status == "进行中"]
    return active[0] if active else (nodes[0] if nodes else None)


def get_project_node_for_date(project_id: int, expense_date: str):
    """返回项目在指定日期(YYYY-MM-DD)【当时】所处的流程节点。

    用于按费用发生日（而非“当前进度”）判定阶段与资本化状态。
    做法：取各节点起始日期，找到 start_date <= 费用日期 中起始最晚的节点，
    其阶段即为当时所处阶段（研究→开发→生产 单调推进，故“最近开始的节点”
    即当时进行中的节点；日期早于所有节点则从首节点起算）。
    无法解析日期时回退到“当前进行中节点”。
    """
    nodes = project_nodes_tb(where=f"project_id={project_id}", order_by="id")
    if not nodes:
        return None

    def _pd(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    exp = _pd(expense_date)
    if exp is None:
        active = [n for n in nodes if n.status == "进行中"]
        return active[0] if active else nodes[0]

    dated = [(n, _pd(n.start_date)) for n in nodes if _pd(n.start_date)]
    dated.sort(key=lambda x: x[1])
    candidate = None
    for n, sd in dated:
        if sd <= exp:
            candidate = n
        else:
            break
    return candidate if candidate else nodes[0]


def phase_for_date(project_id: int, expense_date: str):
    """返回项目在指定日期所处的阶段（研究/开发/生产）"""
    node = get_project_node_for_date(project_id, expense_date)
    return node.phase if node else "研究"


def capitalize_status_for_phase(phase: str):
    """根据阶段返回资本化状态"""
    if phase == "研究":
        return "费用化"
    if phase == "生产":
        return "非研发"
    return "待资本化"


def subject_by_code(code: str):
    """按科目编码取科目记录"""
    rows = subjects_tb(where=f"code='{code}'")
    return rows[0] if rows else None


# 加计扣除口径下，折旧费用只允许“仪器、设备”的折旧费计入；
# 在用建筑物 / 房屋折旧 不属于可加计扣除的折旧范围（财税[2015]119号）。
# 软件授权资本化的摊销计入“无形资产摊销”，属可加计范围，故一并允许。
_EQUIPMENT_DEDUCTIBLE_CATEGORIES = {"仪器设备", "专用设备", "软件"}


def equipment_caliber_for_category(category: str, proj_caliber: str) -> str:
    """根据设备类别返回折旧分摊应写入的归集口径。

    加计扣除口径仅接受仪器、设备折旧及软件摊销；建筑物/房屋类资产
    折旧只能进入“高企认定”口径（高企认定允许房屋建筑物折旧计入），
    不得计入加计扣除，避免高估加计扣除基数。
    """
    if category and category.strip() in ("在用建筑物", "房屋", "房屋建筑物", "建筑物"):
        # 从口径中剔除“加计扣除”，仅保留高企认定（若原本就没有则维持）
        parts = [p for p in proj_caliber.split(",") if p.strip() and p.strip() != "加计扣除"]
        return ",".join(parts) if parts else "高企认定"
    return proj_caliber



def add_expense(**kwargs):
    """统一写入 expense 表，自动补全 created_at 与 node_id（未提供时）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    proj_id = kwargs.get("project_id", 0)
    exp_date = kwargs.get("expense_date", "")
    if "node_id" not in kwargs or not kwargs["node_id"]:
        if proj_id and exp_date:
            node = get_project_node_for_date(proj_id, exp_date)
        else:
            node = get_active_project_node(proj_id) if proj_id else None
        kwargs["node_id"] = node.id if node else 0
    kwargs.setdefault("caliber", "高企认定,加计扣除")
    kwargs.setdefault("person_id", 0)
    kwargs.setdefault("person_name", "")
    kwargs.setdefault("evidence_id", 0)
    kwargs.setdefault("created_at", now)
    row = expenses_tb.insert(**kwargs)
    # 内控留痕：每笔费用归集均记录操作日志（谁/何时/归集到哪个项目）
    try:
        log_audit(
            "CREATE", "expense", row.id,
            detail=f"归集研发费用 ¥{row.amount:,.0f}（{row.subject_name}）至项目 {row.project_id}",
            actor=row.person_name or "系统",
            after=json.dumps({"project_id": row.project_id, "subject": row.subject_name,
                              "amount": row.amount, "phase": row.phase}, ensure_ascii=False),
        )
    except Exception:
        pass
    return row


# ════════════════════════════════════════════════════════════════
# 内控与治理：审计留痕 + 合规红线扫描
# ════════════════════════════════════════════════════════════════

def log_audit(action: str, entity: str, entity_id: int = 0, detail: str = "",
              actor: str = "系统", before: str = "", after: str = ""):
    """写入一条审计操作日志（内控留痕）。失败静默，不影响业务流程。"""
    try:
        audit_tb.insert(
            ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
            actor=actor, action=action, entity=entity, entity_id=entity_id,
            detail=detail, before=before, after=after,
        )
    except Exception:
        pass


def approval_level_for_amount(amount: float, subject: str = ""):
    """审批权限矩阵：按金额分级 + 费用类型，返回所需批准层级。

    依据 rd-governor 工作流 A《研发费用报销审批流程》：
      - 材料费/试制费/差旅费/会议费/其他费用：预算内 ≤1万 部门；>1万 +财务总监
      - 委外研发费/设备购置费：部门+财务总监；>1万 +总经理；>10万 +董事会
    返回 (层级, 说明)。
    """
    heavy = subject in ("委托外部研究费用", "设备购置费", "研发设备", "委外研发费")
    if amount > 100000:
        level = "董事会" if heavy else "总办"
        note = f"金额 >10万，需{'董事会（委外/设备）' if heavy else '总经理/总办'}审批"
    elif amount > 10000:
        level = "总办" if heavy else "财务总监"
        note = f"金额 >1万，需财务总监{'+总经理' if heavy else ''}审批"
    else:
        level = "部门"
        note = "金额 ≤1万，部门负责人审批"
    return level, note


def scan_compliance_risks():
    """实时合规红线扫描（内控治理中心用）。

    汇总全库可计算的合规风险，返回 list[dict]：
      level(高/中/低) / type / project / description / citation / suggestion
    覆盖：加计扣除其他费用10%限额、高企其他费用20%限额、境内研发占比≥60%、
          委托境外2/3上限、预算超支、负面清单行业、特殊收入冲减。
    """
    risks = []
    projects = projects_tb()

    # ① 其他相关费用限额（按项目，分加计10% / 高企20%）
    for p in projects:
        proj_exp = [e for e in expenses_tb() if e.project_id == p.id]
        deduct_base = sum(e.amount for e in proj_exp if "加计扣除" in (e.caliber or "")) or 0
        hitech_base = sum(e.amount for e in proj_exp if "高企认定" in (e.caliber or "")) or 0
        other_deduct = sum(e.amount for e in proj_exp
                           if e.subject_name == "其他费用" and "加计扣除" in (e.caliber or ""))
        other_hitech = sum(e.amount for e in proj_exp
                           if e.subject_name == "其他费用" and "高企认定" in (e.caliber or ""))
        if deduct_base > 0 and other_deduct > deduct_base * 0.10:
            over = other_deduct - deduct_base * 0.10
            risks.append(dict(level="高", type="其他费用超限额(加计)", project=p.name,
                description=f"其他相关费用 ¥{other_deduct:,.0f} 超可加计基数 ¥{deduct_base:,.0f} 的10%限额，超限 ¥{over:,.0f}",
                citation="财税〔2015〕119号 / 国家税务总局公告2017年第40号",
                suggestion="将超限部分剔除加计扣除基数，或补充其他可加计科目稀释占比"))
        if hitech_base > 0 and other_hitech > hitech_base * 0.20:
            over = other_hitech - hitech_base * 0.20
            risks.append(dict(level="中", type="其他费用超限额(高企)", project=p.name,
                description=f"其他费用 ¥{other_hitech:,.0f} 超高企归集基数 ¥{hitech_base:,.0f} 的20%限额，超限 ¥{over:,.0f}",
                citation="国科发火〔2016〕195号",
                suggestion="高企认定口径其他费用不得超过20%，请核减"))

    # ② 境内研发占比 ≥60%（委托境外加计上限受 2/3 约束）
    domestic_base, overseas_cap = deduct_overseas_cap()
    overseas = [o for o in outsourcing_tb() if o.is_overseas]
    overseas_actual = sum(o.actual_amount for o in overseas)
    if domestic_base > 0 and overseas_actual > overseas_cap:
        risks.append(dict(level="高", type="委托境外超限(2/3)", project="企业级",
            description=f"委托境外研发费用 ¥{overseas_actual:,.0f} 超过境内委托实际额 ¥{domestic_base:,.0f} 的2/3（上限 ¥{overseas_cap:,.0f}），超限 ¥{overseas_actual - overseas_cap:,.0f}",
            citation="财税〔2018〕64号（委托境外研发费用加计扣除）",
            suggestion="超限部分不得加计扣除，须从加计基数剔除"))

    # ③ 预算超支（执行率 >100% 高 / >90% 中）
    for p in projects:
        if not p.budget or p.budget <= 0:
            continue
        used = sum(e.amount for e in expenses_tb() if e.project_id == p.id)
        ratio = used / p.budget
        if ratio > 1.0:
            risks.append(dict(level="高", type="预算超支", project=p.name,
                description=f"已使用 ¥{used:,.0f} 超预算 ¥{p.budget:,.0f}（执行率 {ratio*100:.1f}%）",
                citation="研发费用预算管理制度（工作流A）",
                suggestion="超预算须先走预算调整审批流程，审批通过后方可继续归集"))
        elif ratio > 0.9:
            risks.append(dict(level="中", type="预算临界", project=p.name,
                description=f"预算执行率 {ratio*100:.1f}%，临近上限",
                citation="研发费用预算管理制度（工作流A）",
                suggestion="关注后续归集，必要时提前启动预算调整"))

    # ④ 负面清单行业（企业级，依赖 settings 行业字段）
    try:
        from .biz_config import get_rd_settings
        industry = ((get_rd_settings().get("enterprise", {}) or {}).get("industry", "") or "")
    except Exception:
        industry = ""
    NEGATIVE_LIST = ("烟草", "住宿和餐饮", "批发和零售", "房地产", "租赁和商务服务", "娱乐")
    if industry and any(k in industry for k in NEGATIVE_LIST):
        risks.append(dict(level="高", type="负面清单行业", project="企业级",
            description=f"企业所属行业「{industry}」属研发费用加计扣除负面清单行业",
            citation="财税〔2015〕119号第四条",
            suggestion="该行业不得享受研发费用加计扣除，请核实行业归类"))

    # ⑤ 特殊收入冲减提示（存在未冲减的特殊收入）
    offset_total, _ = special_income_offset("加计扣除")
    if offset_total > 0:
        risks.append(dict(level="中", type="特殊收入待冲减", project="企业级",
            description=f"存在特殊收入合计 ¥{offset_total:,.0f} 需冲减研发费用加计扣除基数",
            citation="财税〔2015〕119号 / 国家税务总局公告2017年第40号",
            suggestion="不征税收入/政府补助/样品销售对应支出不得加计，须冲减基数"))

    return risks


# ════════════════════════════════════════════════════════════════
# 负面清单与边界校验（P1：不得归集支出识别，财税口径）
# ════════════════════════════════════════════════════════════════
# (关键词, 原因) —— 命中即判定为「不属于研发费用归集范围」的支出。
NEGATIVE_PATTERNS = [
    ("业务招待", "业务招待费不属于研发费用归集范围"),
    ("招待费", "业务招待费不属于研发费用归集范围"),
    ("市场推广", "市场推广/广告费不属于研发费用归集范围"),
    ("广告费", "市场推广/广告费不属于研发费用归集范围"),
    ("常规升级", "常规性产品升级、商业化后改型不属于研发活动"),
    ("批量生产", "批量生产用工装模具费用不属于研发活动"),
    ("一般测试", "产品商业化后的常规性一般测试不属于研发活动"),
    ("生产成本", "生产成本（直接材料/人工用于量产）不属于研发费用"),
    ("非研发管理费", "非研发相关的管理费用不应计入研发费用"),
]


def negative_list_hit(description: str):
    """返回命中的负面清单原因；未命中返回 None。"""
    if not description:
        return None
    for kw, reason in NEGATIVE_PATTERNS:
        if kw in description:
            return reason
    return None


def rd_personnel_ratio():
    """研发人员占比 = 研发人员 / 总人员（Personnel 表）。"""
    people = personnel_tb()
    if not people:
        return None
    rd = [p for p in people if p.is_rd]
    return len(rd) / len(people)


def deduct_overseas_cap():
    """委托境外研发加计扣除上限 = 境内委托实际发生额之和 × 2/3（财税口径）。

    返回 (domestic_base, cap)。domestic_base 为全部境内委托实际发生额合计。
    """
    domestic = [o for o in outsourcing_tb() if not o.is_overseas]
    domestic_base = sum(o.actual_amount for o in domestic)
    return domestic_base, round(domestic_base * 2.0 / 3.0, 2)


def capitalizable_ready(expense_id: int):
    """判断某笔「待资本化」费用是否已通过 5 条件审批。

    返回 (passed: bool, review_or_None)。
    """
    rows = capitalization_tb(where=f"expense_id={expense_id} AND status='通过'")
    return (len(rows) > 0, rows[0] if rows else None)


def metrics_for_project(project_id: int):
    """计算单个项目（及企业口径）的高企认定比例指标。

    返回 dict：各指标含 value / threshold / ok / note。
    依赖 Project.annual_revenue / hightech_income；缺失时 ok=None（待录入）。
    """
    p = projects_tb[project_id]
    proj_exp = [e for e in expenses_tb() if e.project_id == project_id]
    rd_exp = sum(e.amount for e in proj_exp if e.phase in ("研究", "开发"))

    # 其他费用占比（按口径分别算 10% 加计 / 20% 高企）
    other_deduct = sum(e.amount for e in proj_exp
                       if e.subject_name == "其他费用" and "加计扣除" in e.caliber)
    deduct_base = sum(e.amount for e in proj_exp if "加计扣除" in e.caliber) or 1
    other_hitech = sum(e.amount for e in proj_exp
                       if e.subject_name == "其他费用" and "高企认定" in e.caliber)
    hitech_base = sum(e.amount for e in proj_exp if "高企认定" in e.caliber) or 1
    other_ratio_deduct = other_deduct / deduct_base
    other_ratio_hitech = other_hitech / hitech_base

    out = {
        "rd_expense": rd_exp,
        "other_ratio_deduct": other_ratio_deduct,      # 应 ≤ 0.10
        "other_ratio_hitech": other_ratio_hitech,      # 应 ≤ 0.20
    }
    # 企业级比例指标（依赖年度收入数据）
    rev = p.annual_revenue or 0.0
    hi = p.hightech_income or 0.0
    if rev > 0:
        out["rd_ratio"] = rd_exp / rev                 # 高企：按收入档 3/4/5%
        out["hightech_income_ratio"] = hi / rev        # 应 ≥ 0.60
    else:
        out["rd_ratio"] = None
        out["hightech_income_ratio"] = None
    # 研发人员占比（企业级，跨项目）
    out["rd_personnel_ratio"] = rd_personnel_ratio()  # 应 ≥ 0.10
    return out


# ── 新增模块种子数据（幂等：仅当表为空时插入）────────────

def seed_new_modules():
    """为设备折旧 / 原材料 / 委托外部 / 其他费用四个模块填充示例数据。
    幂等：每个表独立判断，已存在数据则不重复插入，从而保证在既有
    （含 WorkTime/LaborCost 种子）的生产库上重跑 import 时不报错。
    """
    if len(equipment_tb()) > 0:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 研发设备档案
    eq1 = equipment_tb.insert(name="高性能计算服务器", code="EQ-001", category="仪器设备",
                               model="Dell R750", acquisition_date="2025-09-01",
                               acquisition_cost=300000, depreciation_method="年限平均法",
                               useful_life=60, monthly_depreciation=5000, status="在用",
                               dept_id=0, created_at=now)
    eq2 = equipment_tb.insert(name="研发测试工作站", code="EQ-002", category="专用设备",
                               model="联想 ThinkStation", acquisition_date="2025-11-15",
                               acquisition_cost=120000, depreciation_method="年限平均法",
                               useful_life=60, monthly_depreciation=2000, status="在用",
                               dept_id=0, created_at=now)
    eq3 = equipment_tb.insert(name="EDA 设计软件授权", code="EQ-003", category="软件",
                               model="Cadence 年度授权", acquisition_date="2026-01-10",
                               acquisition_cost=180000, depreciation_method="年限平均法",
                               useful_life=36, monthly_depreciation=5000, status="在用",
                               dept_id=0, created_at=now)

    # 设备工时登记（2026-01 研究 / 2026-03 开发）
    eq_worktime = [
        (eq1.id, 1, "2026-01-08", 40, "需求仿真与可行性计算"),
        (eq1.id, 1, "2026-03-12", 60, "开发环境训练与建模"),
        (eq2.id, 1, "2026-03-13", 50, "集成测试与压测"),
        (eq3.id, 1, "2026-03-14", 30, "电路设计仿真"),
        (eq1.id, 2, "2026-03-15", 55, "ERP 性能基准测试"),
        (eq3.id, 2, "2026-03-16", 25, "ERP 拓扑仿真"),
    ]
    for eid, pid, dt, hrs, desc in eq_worktime:
        equipment_work_time_tb.insert(equipment_id=eid, project_id=pid, work_date=dt,
                                      hours=hrs, task_desc=desc, created_at=now)

    # 设备折旧总账（2026-01 / 2026-03）；rd_usage_ratio=研发用途占比（默认1.0，
    # 兼产设备需按实际用途登记，如 EQ-001 同时服务生产，登记 0.8）
    eq_depr = [
        (eq1.id, "2026-01", 5000, 0.8),
        (eq2.id, "2026-01", 2000, 1.0),
        (eq3.id, "2026-01", 5000, 1.0),
        (eq1.id, "2026-03", 5000, 0.8),
        (eq2.id, "2026-03", 2000, 1.0),
        (eq3.id, "2026-03", 5000, 1.0),
    ]
    for eid, month, dep, ratio in eq_depr:
        equipment_depreciation_tb.insert(equipment_id=eid, cost_month=month,
                                        monthly_depreciation=dep,
                                        rd_usage_ratio=ratio,
                                        allocated_hours_total=0.0, status="待分摊",
                                        created_at=now)

    # 原材料领用与去向（归集到直接投入费用 科目02）
    mat = [
        ("服务器 CPU", "Xeon 8480", "颗", 4, 12000, 1, "2026-01-18", 1, "核心模块搭建", "使用中", 0),
        ("研发用内存条", "DDR5 64G", "条", 16, 1500, 1, "2026-01-20", 1, "仿真环境扩容", "使用中", 0),
        ("FPGA 开发板", "Xilinx VU9P", "块", 2, 8000, 2, "2026-03-05", 2, "算法硬件验证", "使用中", 0),
        ("工业传感器", "温湿度模块", "个", 20, 300, 3, "2026-03-08", 3, "网关联调", "已领用", 0),
    ]
    for name, spec, unit, qty, price, pid, dt, rid, purpose, usage, collected in mat:
        material_requisition_tb.insert(
            material_name=name, specification=spec, unit=unit, quantity=qty,
            unit_price=price, amount=round(qty * price, 2), project_id=pid,
            requisition_date=dt, requisitioner_id=rid, purpose=purpose,
            usage_status=usage, collected=collected, created_at=now
        )

    # 委托外部研发费用（按实际发生额 80% 归集到科目07）
    out = [
        ("WT-2026-001", "某软件外包公司", 1, 50000, 50000, "高企认定,加计扣除", 1, "2026-03-20", "UI 设计外包", 0),
        ("WT-2026-002", "某算法研究院", 2, 80000, 80000, "高企认定,加计扣除", 1, "2026-03-22", "专用算法委托研发", 0),
    ]
    for cno, contractor, pid, camt, amt, caliber, htt, dt, desc, collected in out:
        outsourcing_tb.insert(
            contract_no=cno, contractor=contractor, project_id=pid,
            contract_amount=camt, actual_amount=amt, caliber=caliber,
            has_tech_transfer=htt, expense_date=dt, description=desc,
            collected=collected, created_at=now
        )

    # 其他相关费用（归集到科目08，注意 10% 上限）
    oth = [
        (1, "技术图书", "2026-01-25", 3000, "研发专业书籍采购", "高企认定,加计扣除"),
        (1, "专家咨询", "2026-03-18", 6000, "外部专家技术评审", "高企认定,加计扣除"),
        (2, "差旅", "2026-03-21", 4000, "客户现场联调差旅", "高企认定,加计扣除"),
    ]
    for pid, cat, dt, amt, desc, caliber in oth:
        other_expense_tb.insert(project_id=pid, category=cat, expense_date=dt,
                                amount=amt, description=desc, caliber=caliber,
                                collected=0, created_at=now)


# ── 二期新增表种子（幂等：各表独立判断，仅当表为空时插入）──

def seed_extended_tables():
    """为 M1–M6 二期新增表填充基础字典与示例数据。

    幂等：每个表独立判断 len()==0 才插入，保证在既有生产库上重跑 import 不报错。
    依赖 seed_data() 已先执行（orgs_tb / projects_tb / personnel_tb 已有数据）。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 物料类型字典（缺口④：原料/样品/废料）
    if len(material_sub_types_tb()) == 0:
        material_sub_types_tb.insert(name="原料", code="01", is_rd_material=True, created_at=now)
        material_sub_types_tb.insert(name="样品", code="02", is_rd_material=True, created_at=now)
        material_sub_types_tb.insert(name="废料", code="03", is_rd_material=False, created_at=now)

    # 风控规则库（缺口⑩-a：费用/政策/管理三类）
    if len(risk_rules_tb()) == 0:
        risk_rules_tb.insert(rule_name="研发费用环比异常增长", rule_type="费用",
                             threshold='{"metric":"monthly_expense_growth_pct","op":">","value":50}',
                             action="警告", description="某项目当月研发费用环比增幅>50%触发预警", enabled=True, created_at=now)
        risk_rules_tb.insert(rule_name="研发人员占比过低", rule_type="费用",
                             threshold='{"metric":"rd_personnel_ratio","op":"<","value":0.3}',
                             action="警告", description="某项目研发人员占比<30%触发预警", enabled=True, created_at=now)
        risk_rules_tb.insert(rule_name="其他相关费用超10%限额", rule_type="政策",
                             threshold='{"metric":"other_expense_pct","op":">","value":10}',
                             action="拦截", description="其他相关费用超过加计扣除10%限额", enabled=True, created_at=now)
        risk_rules_tb.insert(rule_name="负面清单支出混入", rule_type="政策",
                             threshold='{"metric":"negative_list","op":"in","value":1}',
                             action="拦截", description="业务招待/市场推广等负面清单支出混入研发费用", enabled=True, created_at=now)
        risk_rules_tb.insert(rule_name="建筑物折旧计入加计", rule_type="政策",
                             threshold='{"metric":"building_depreciation","op":">","value":0}',
                             action="拦截", description="建筑物折旧计入加计扣除", enabled=True, created_at=now)
        risk_rules_tb.insert(rule_name="开发阶段未完成立项", rule_type="管理",
                             threshold='{"metric":"dev_without_approval","op":"==","value":1}',
                             action="警告", description="项目进入开发阶段但未完成立项审批", enabled=True, created_at=now)
        risk_rules_tb.insert(rule_name="节点通过30天无归集", rule_type="管理",
                             threshold='{"metric":"approve_no_collect_days","op":">","value":30}',
                             action="警告", description="节点审批通过超过30天无费用归集记录", enabled=True, created_at=now)

    # 工时预警规则（缺口②：全局默认规则）
    if len(worktime_alert_rules_tb()) == 0:
        worktime_alert_rules_tb.insert(project_id=0, person_id=0,
                                       min_rd_ratio=0.3, max_single_hours=12.0,
                                       enabled=True, created_at=now)

    # 组织树（缺口⑬：关联 orgs_tb 现有组织）
    if len(org_tree_tb()) == 0 and len(orgs_tb()) > 0:
        root = orgs_tb()[0]
        subs = [o for o in orgs_tb() if o.parent_id == root.id]
        org_tree_tb.insert(org_id=root.id, name=root.name, level=root.level, parent_id=0, created_at=now)
        for s in subs:
            org_tree_tb.insert(org_id=s.id, name=s.name, level=s.level, parent_id=root.id, created_at=now)
            for d in [o for o in orgs_tb() if o.parent_id == s.id]:
                org_tree_tb.insert(org_id=d.id, name=d.name, level=d.level, parent_id=s.id, created_at=now)

    # 项目级角色权限（缺口⑨：示例）
    if len(project_roles_tb()) == 0 and len(projects_tb()) > 0 and len(personnel_tb()) > 0:
        p0 = projects_tb()[0]
        pm = personnel_tb()[0]
        project_roles_tb.insert(project_id=p0.id, person_id=pm.id, role="项目经理", created_at=now)


# 执行种子数据初始化
seed_data()
seed_new_modules()
seed_extended_tables()

# 兼容旧库：EquipmentDepreciation 可能缺少 rd_usage_ratio 列（2026-07-18 合规修复新增）
_tbl = equipment_depreciation_tb
_try_cols = [c[1] for c in _tbl.db.execute(
    f"PRAGMA table_info({_tbl.name})").fetchall()]
if "rd_usage_ratio" not in _try_cols:
    try:
        _tbl.db.execute(
            f"ALTER TABLE {_tbl.name} ADD COLUMN rd_usage_ratio FLOAT DEFAULT 1.0")
        _tbl.db.execute(
            f"UPDATE {_tbl.name} SET rd_usage_ratio = 1.0 WHERE rd_usage_ratio IS NULL")
    except Exception:
        pass

# 兼容旧库：新增列在既有生产库上缺失时补全（与 rd_usage_ratio 同模式）
for _tbl, _cols in [
    (projects_tb, ["rd_split_ratio", "annual_revenue", "hightech_income"]),
    (outsourcing_tb, ["is_overseas"]),
]:
    _try_cols = [c[1] for c in _tbl.db.execute(
        f"PRAGMA table_info({_tbl.name})").fetchall()]
    for _col in _cols:
        if _col not in _try_cols:
            try:
                _tbl.db.execute(
                    f"ALTER TABLE {_tbl.name} ADD COLUMN {_col} FLOAT DEFAULT 0")
            except Exception:
                pass
    try:
        _tbl.db.execute(
            f"UPDATE {_tbl.name} SET {_cols[0]} = 0 WHERE {_cols[0]} IS NULL")
    except Exception:
        pass

# 兼容旧库：M3 项目属性扩展（受托研发隔离 / 阶段精细化手动覆盖）
for _col, _ddl in [
    ("rd_nature", "VARCHAR DEFAULT '自主研发'"),
    ("research_end", "VARCHAR DEFAULT ''"),
    ("develop_end", "VARCHAR DEFAULT ''"),
]:
    _try_cols = [c[1] for c in projects_tb.db.execute(
        f"PRAGMA table_info({projects_tb.name})").fetchall()]
    if _col not in _try_cols:
        try:
            projects_tb.db.execute(
                f"ALTER TABLE {projects_tb.name} ADD COLUMN {_col} {_ddl}")
        except Exception:
            pass

# 兼容旧库：三大核心板块（人员认定 / 设备共用报废 / 材料边界）新增列
for _t, _defs in [
    (personnel_tb, [
        ("person_category", "VARCHAR DEFAULT '研究人员'"),
        ("education", "VARCHAR DEFAULT ''"),
        ("major", "VARCHAR DEFAULT ''"),
        ("employment_type", "VARCHAR DEFAULT '在职'"),
        ("id_number", "VARCHAR DEFAULT ''"),
        ("hire_date", "VARCHAR DEFAULT ''"),
        ("leave_date", "VARCHAR DEFAULT ''"),
        ("annual_rd_days", "INTEGER DEFAULT 0"),
        ("social_insurance_unit", "VARCHAR DEFAULT ''"),
        ("certification_status", "VARCHAR DEFAULT '待认定'"),
        ("certification_date", "VARCHAR DEFAULT ''"),
    ]),
    (equipment_tb, [
        ("source", "VARCHAR DEFAULT '自购'"),
        ("location", "VARCHAR DEFAULT ''"),
        ("is_shared", "INTEGER DEFAULT 0"),
        ("residual_rate", "FLOAT DEFAULT 0"),
        ("scrap_date", "VARCHAR DEFAULT ''"),
        ("scrap_reason", "VARCHAR DEFAULT ''"),
        ("scrap_income", "FLOAT DEFAULT 0"),
    ]),
    (material_requisition_tb, [
        ("material_class", "VARCHAR DEFAULT '研发专用'"),
        ("rd_stage", "VARCHAR DEFAULT '试制'"),
        ("rd_share_ratio", "FLOAT DEFAULT 1.0"),
        ("returned_qty", "FLOAT DEFAULT 0"),
        ("returned_amount", "FLOAT DEFAULT 0"),
        ("scrap_qty", "FLOAT DEFAULT 0"),
        ("scrap_value", "FLOAT DEFAULT 0"),
        ("net_amount", "FLOAT DEFAULT 0"),
        ("boundary_note", "VARCHAR DEFAULT ''"),
    ]),
]:
    try:
        _exist = [c[1] for c in _t.db.execute(
            f"PRAGMA table_info({_t.name})").fetchall()]
        for _col, _ddl in _defs:
            if _col not in _exist:
                try:
                    _t.db.execute(
                        f"ALTER TABLE {_t.name} ADD COLUMN {_col} {_ddl}")
                except Exception:
                    pass
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# M1–M7 合规辅助函数（供各路由模块复用）
# ════════════════════════════════════════════════════════════════


def special_income_offset(caliber: str = "加计扣除"):
    """M4：特殊收入合计（需冲减研发费用加计扣除基数）。

    仅计入 offset_caliber 包含指定口径的特殊收入（不征税收入 / 政府补助 /
    样品销售 / 废料处置）。返回 (total, rows)。
    """
    rows = [r for r in special_income_tb() if caliber in (r.offset_caliber or "")]
    return sum(r.amount for r in rows), rows


def entrusted_isolated_total():
    """M3：受托研发合同已确认营业收入合计（隔离，不计入我方研发费用）。"""
    return sum(r.recognized_revenue for r in entrusted_tb())


def phase_for_date_m5(project_id: int, expense_date: str):
    """M5：阶段精细化判定。

    优先使用项目 research_end / develop_end 手动指定的阶段边界；
    未指定时回退到基于流程节点起始日的自动判定（phase_for_date）。
    研究 < research_end 且未到 develop_end → 研究；
    research_end ≤ 日期 < develop_end → 开发；
    ≥ develop_end → 生产（常规化/量产）。
    """
    p = projects_tb[project_id]

    def _pd(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    re_end = _pd(p.research_end)
    de_end = _pd(p.develop_end)
    exp = _pd(expense_date)
    if exp is None:
        return phase_for_date(project_id, expense_date)
    if re_end and exp < re_end:
        return "研究"
    if de_end and exp < de_end:
        return "开发"
    if de_end and exp >= de_end:
        return "生产"
    return phase_for_date(project_id, expense_date)


def deduct_base_after_offset(project_id: int, caliber: str = "加计扣除"):
    """M4：加计扣除口径下，扣除特殊收入后的研发费用净额。

    返回 (gross, offset, net)。gross 为该项目加计扣除口径费用合计；
    offset 为企业级特殊收入冲减额（特殊收入按企业整体冲减，不分摊到项目）。
    """
    proj_exp = [e for e in expenses_tb() if e.project_id == project_id]
    gross = sum(e.amount for e in proj_exp if caliber in (e.caliber or ""))
    offset, _ = special_income_offset(caliber)
    return gross, offset, max(gross - offset, 0.0)


# ════════════════════════════════════════════════════════════════
# 三大核心板块合规引擎：研发人员 / 研发设备 / 研发原材料
# 依据：rd-governor 人员管理10章、设备管理10章、物料管理9章；
#      《监管规则适用指引——发行类第9号：研发人员及研发投入》；
#      高企认定管理办法（科技人员累计工作满183天规则）。
# ════════════════════════════════════════════════════════════════

# 高企认定：科技人员当年累计实际工作时间须满 183 天
HIGHTECH_MIN_WORK_DAYS = 183

PERSON_CATEGORIES = ["研究人员", "技术人员", "辅助人员"]
EMPLOYMENT_TYPES = ["在职", "外聘", "劳务派遣", "兼职"]
CERT_STATUSES = ["待认定", "已认定", "已停用"]

MATERIAL_CLASSES = ["研发专用", "研发生产共用", "生产用料"]
RD_STAGES = ["试制", "中试", "试产", "量产"]
NON_RD_STAGES = ["量产"]   # 量产阶段材料属正常生产耗用，不得计入研发费用

EQUIPMENT_SHARE_BASIS = ["机时", "产量", "面积", "人工工时"]


def _safe(obj, attr, default=None):
    """兼容旧库缺列：安全取属性"""
    v = getattr(obj, attr, default)
    return default if v is None else v


# ── 研发人员合规体检 ───────────────────────────────────────

def check_personnel_compliance():
    """扫描研发人员台账的合规问题。

    返回 [(级别, 人员名, 问题, 建议)]，级别为 高/中/低。
    """
    issues = []
    persons = [p for p in personnel_tb() if p.is_rd]

    for p in persons:
        name = p.name
        days = int(_safe(p, "annual_rd_days", 0) or 0)
        emp = _safe(p, "employment_type", "在职") or "在职"
        cert = _safe(p, "certification_status", "待认定") or "待认定"
        cat = _safe(p, "person_category", "") or ""
        si_unit = (_safe(p, "social_insurance_unit", "") or "").strip()
        leave = (_safe(p, "leave_date", "") or "").strip()

        # ① 高企 183 天规则
        if days and days < HIGHTECH_MIN_WORK_DAYS:
            issues.append(("高", name,
                f"当年累计研发工作 {days} 天，不足 {HIGHTECH_MIN_WORK_DAYS} 天",
                "高企认定口径下不得计入科技人员，请核实考勤或调出研发人员名单"))
        elif not days:
            issues.append(("中", name, "未登记当年累计研发工作天数",
                "高企认定需据实统计累计工作时间，请补登考勤天数"))

        # ② 认定状态
        if cert != "已认定":
            issues.append(("高", name, f"研发人员认定状态为「{cert}」",
                "未经认定的人员其人工费用不得归集，请走人员认定流程"))

        # ③ 人员类别（三类人员结构）
        if cat not in PERSON_CATEGORIES:
            issues.append(("中", name, "未划分人员类别（研究/技术/辅助）",
                "高企与 IPO 均要求区分三类人员结构，请补充"))

        # ④ 社保缴纳单位
        if emp == "在职" and not si_unit:
            issues.append(("中", name, "未登记社保缴纳单位",
                "IPO 核查要求社保、个税缴纳单位与研发活动主体一致"))

        # ⑤ 外聘 / 劳务派遣
        if emp in ("外聘", "劳务派遣"):
            issues.append(("低", name, f"用工方式为「{emp}」",
                "外聘研发人员费用须有劳务合同与派遣协议支撑，高企口径需单独统计"))

        # ⑥ 已离职仍标记为研发人员
        if leave:
            issues.append(("高", name, f"已登记离职日期 {leave}，仍标记为研发人员",
                "请停用其研发人员认定，避免离职后继续归集人工费用"))

    # ⑦ 非研发人员却登记了研发工时
    try:
        rd_ids = {p.id for p in persons}
        seen = set()
        for w in work_time_tb():
            if w.person_id and w.person_id not in rd_ids and w.person_id not in seen:
                seen.add(w.person_id)
                try:
                    pn = personnel_tb[w.person_id].name
                except Exception:
                    pn = f"#{w.person_id}"
                issues.append(("高", pn,
                    f"非研发人员登记了研发工时（{w.work_date}）",
                    "请核实：或补充认定为研发人员，或删除该工时记录"))
    except Exception:
        pass

    return issues


def personnel_structure():
    """三类人员结构统计，返回 ({类别: 人数}, 未分类数, 研发人员总数)。"""
    stat = {c: 0 for c in PERSON_CATEGORIES}
    others = 0
    for p in personnel_tb():
        if not p.is_rd:
            continue
        cat = _safe(p, "person_category", "") or ""
        if cat in stat:
            stat[cat] += 1
        else:
            others += 1
    total = sum(stat.values()) + others
    return stat, others, total


def record_personnel_change(person_id: int, change_type: str, before: str,
                            after: str, reason: str = "", operator: str = "系统"):
    """写入研发人员认定 / 变更记录（rd-governor 指令17 留痕）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        pname = personnel_tb[person_id].name
    except Exception:
        pname = f"#{person_id}"
    personnel_change_tb.insert(
        person_id=person_id, person_name=pname, change_type=change_type,
        before_value=before, after_value=after, reason=reason,
        operator=operator, change_date=now[:10], created_at=now)
    return pname


# ── 研发原材料领料边界校验 ─────────────────────────────────

def material_net_amount(rec):
    """可归集净额 = 领用金额 × 研发占比 − 退料金额 − 废料残值"""
    amount = float(_safe(rec, "amount", 0.0) or 0.0)
    ratio = float(_safe(rec, "rd_share_ratio", 1.0) or 1.0)
    ratio = max(0.0, min(1.0, ratio))
    returned = float(_safe(rec, "returned_amount", 0.0) or 0.0)
    scrap = float(_safe(rec, "scrap_value", 0.0) or 0.0)
    return round(max(amount * ratio - returned - scrap, 0.0), 2)


def material_boundary_check(rec):
    """领料边界校验：判断该笔领料能否计入研发费用。

    返回 (可归集?, 级别, 提示)。级别：ok / warn / block。
    对应稽查高发点「生产材料混入研发费用」。
    """
    mclass = _safe(rec, "material_class", "研发专用") or "研发专用"
    stage = _safe(rec, "rd_stage", "试制") or "试制"
    ratio = float(_safe(rec, "rd_share_ratio", 1.0) or 1.0)
    amount = float(_safe(rec, "amount", 0.0) or 0.0)
    qty = float(_safe(rec, "quantity", 0.0) or 0.0)
    returned = float(_safe(rec, "returned_amount", 0.0) or 0.0)
    scrap = float(_safe(rec, "scrap_value", 0.0) or 0.0)

    # ① 生产用料：直接禁止归集
    if mclass == "生产用料":
        return False, "block", "生产用料不得计入研发费用（稽查高发：生产材料混入研发）"

    # ② 量产阶段：禁止归集
    if stage in NON_RD_STAGES:
        return False, "block", f"「{stage}」阶段材料属正常生产耗用，不得计入研发费用"

    # ③ 试产阶段：可归集但高风险
    if stage == "试产":
        return True, "warn", "试产阶段材料易与量产混淆，须有试产方案与产出记录佐证，否则可能被纳税调整"

    # ④ 共用料未拆分占比
    if mclass == "研发生产共用" and ratio >= 1.0:
        return True, "warn", "研发生产共用材料未拆分研发占比（当前100%），将高估研发费用，请据实登记"

    # ⑤ 大额领料未登记退料与废料
    if amount >= 50000 and returned <= 0 and scrap <= 0:
        return True, "warn", "单笔领料金额较大但未登记退料余料与废料残值，请核实是否全部实际耗用"

    # ⑥ 数量异常
    if qty <= 0:
        return True, "warn", "领用数量为 0，请核实领料单据"

    return True, "ok", "符合研发领料边界要求"


def scan_material_boundary():
    """全量扫描材料领用边界问题，返回 [(级别, 记录, 提示)]"""
    out = []
    for r in material_requisition_tb():
        ok, level, msg = material_boundary_check(r)
        if level != "ok":
            out.append((level, r, msg))
    return out


# ── 共用设备研发用途占比 ───────────────────────────────────

def compute_sharing_ratio(rd_hours: float, prod_hours: float, other_hours: float):
    """按机时口径计算共用设备的研发用途占比"""
    total = (rd_hours or 0) + (prod_hours or 0) + (other_hours or 0)
    if total <= 0:
        return 0.0
    return round((rd_hours or 0) / total, 4)


def check_equipment_compliance():
    """研发设备合规体检，返回 [(级别, 设备名, 问题, 建议)]"""
    issues = []
    for e in equipment_tb():
        name = f"{e.code} {e.name}".strip()
        shared = int(_safe(e, "is_shared", 0) or 0)
        cat = e.category or ""
        status = e.status or ""
        cost = float(e.acquisition_cost or 0)
        dep = float(e.monthly_depreciation or 0)
        life = int(e.useful_life or 0)
        loc = (_safe(e, "location", "") or "").strip()

        # ① 共用设备未登记用途分摊
        if shared == 1:
            try:
                recs = equipment_sharing_tb(where=f"equipment_id={e.id}")
            except Exception:
                recs = []
            if not recs:
                issues.append(("高", name, "标记为研发 / 非研发共用设备，但未登记用途分摊",
                    "请在「共用设备分摊」中按机时登记研发用途占比并经审批"))

        # ② 建筑物类资产
        if "建筑" in cat or "房屋" in cat:
            issues.append(("中", name, "属在用建筑物类资产",
                "其折旧不得计入加计扣除口径，仅可计入高企认定口径"))

        # ③ 折旧额与原值 / 年限测算值偏离
        if cost > 0 and life > 0 and dep > 0:
            expect = cost / life
            if abs(dep - expect) / max(expect, 1) > 0.2:
                issues.append(("中", name,
                    f"月折旧额 ¥{dep:,.0f} 与「原值÷年限」测算值 ¥{expect:,.0f} 偏离超 20%",
                    "请核实折旧方法、净残值率与税会差异（加速折旧须单独台账）"))

        # ④ 报废设备处理
        if status == "报废":
            if not (_safe(e, "scrap_date", "") or "").strip():
                issues.append(("高", name, "状态为报废但未登记报废日期",
                    "请补登报废日期与原因；报废当月次月起停止计提折旧"))
            if dep > 0:
                issues.append(("高", name, "报废设备仍设置了月折旧额",
                    "请将月折旧额清零，避免继续归集研发费用"))

        # ⑤ 存放地点缺失
        if not loc and status != "报废":
            issues.append(("低", name, "未登记存放地点",
                "实物盘点与税务现场核查需要设备存放地点信息"))

    return issues
