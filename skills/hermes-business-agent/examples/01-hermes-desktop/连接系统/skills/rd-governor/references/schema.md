# 数据库 Schema 对照表（单一事实源）

> 本清单以真实数据库 `PRAGMA table_info` 实测为准（复核日期：2026-09-30，生产库 `业务系统\data\rd_expense.db`，43 张业务表 + 2 张 SQLite 内部统计表（sqlite_stat1/sqlite_stat4），共 45 个表对象）。**所有表名一律以本清单为准**；`SKILL.md` 4.2 词表、`integration.md` 数据底座、`generate_package.py` 抽取逻辑均引用本清单，不另设口径。
>
> entity 键 = `scripts/generate_package.py` / `db_operation` 使用的上下文键名；表名 = 数据库真实表名。

## 一、核心业务表（脚本抽取对象）

| 真实表名 | 业务含义 | entity 键 | 关键列 |
|---|---|---|---|
| `project` | 研发项目 | `projects` | id, code, name, status, budget, manager, caliber, rd_nature, annual_revenue, hightech_income, boundary_type, org_id |
| `expense` | 研发费用记录 | `expenses` | id, project_id, subject_name, amount, expense_date, phase, capitalize_status, caliber, person_id, person_name, evidence_id |
| `personnel` | 人员档案 | `personnel` | id, name, org_id, title, is_rd, hourly_rate, person_category, education, employment_type, hire_date, annual_rd_days |
| `work_time` | 工时登记 | `worktime` | person_id, project_id, work_date, hours, task_desc |
| `evidence` | 证据材料 | `evidence` | 证据类型、关联项目/费用、文件与状态 |
| `risk` | 风险预警 | `risk` | id, project_id, level, risk_type, description, status, suggestion |
| `capitalization_review` | 资本化审批 | `capitalization_review` | 6 条件判定记录、项目、结论 |
| `material_requisition` | 原材料领用 | `materials` | 项目、材料、数量、金额、领用人 |
| `outsourcing_contract` | 委托外部研发合同 | `outsourcing` | 委托方、金额、是否境外、成果归属 |
| `labor_cost` | 人工费用总账（含社保/公积金） | `labor_cost` | person_id, cost_month, total_salary, social_insurance, housing_fund, work_hours_total, non_rd_hours |

## 二、其他业务表

| 真实表名 | 业务含义 | 说明 |
|---|---|---|
| `organization` / `org_tree` | 组织/组织树 | 部门层级 |
| `expense_subject` | 费用科目 | 一/二级科目树 |
| `other_expense` | 其他费用明细 | 10% 限额测算明细 |
| `labor_allocation` | 人工费用分配 | 按工时/项目分摊 |
| `equipment` / `equipment_depreciation` / `equipment_work_time` | 设备及折旧/工时 | 折旧分摊依据 |
| `process_template` / `process_node` / `project_node` | 流程模板/节点/项目节点 | 研发活动节点（`db_operation` 的 `activities` 映射 `project_node`） |
| `project_member` / `project_role` | 项目成员/角色 | 项目—人员关联 |
| `policy_rule` | 政策/制度规则 | 内控与政策规则库 |
| `risk_rule` / `risk_alert` | 风险规则/预警 | 风险引擎 |
| `audit_log` | 审计日志 | 系统操作留痕 |
| `approval_req` / `attendance_record` / `salary_record` / `patent_record` / `sample_scrap` / `special_income` / `device_sharing_ratio` / `equipment_sharing` / `evidence_doc` / `personnel_change` / `data_center_log` / `report_version` / `control_assessment` / `work_time_alert_rule` / `entrusted_contract` / `material_sub_type` | 其他业务辅助表 | 按需使用 |

## 三、非业务表（勿当业务数据）

| 表名 | 说明 |
|---|---|
| `sqlite_stat1` / `sqlite_stat4` | SQLite 自动统计表，非业务数据 |

## 四、命名规则

- 表名一律**单数**（`project`、`expense`、`work_time`、`risk`），不用复数（`projects`、`expenses`、`risks`）。
- 时间类表名用下划线连接（`work_time`、`capitalization_review`）。
- `risk` 历史曾误写 `risks`，脚本已做兼容（`risk` 优先）；**新写代码与文档一律用 `risk`**。
