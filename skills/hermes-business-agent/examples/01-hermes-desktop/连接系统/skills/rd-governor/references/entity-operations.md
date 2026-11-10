# 实体操作词表与高频指令剧本

> 本文件承载 `db_operation` 的精确用法与可直接照做的高频指令。加载时机：需要新建/查询实体数据、或用户指令命中下表场景时读取。

## 一、实体操作词表（db_operation 精确用法）

`db_operation` 的 `entity` 参数**只接受下表左侧键名**（不是数据库表名）。`fields` 字段名见各实体 `columns`。新增类指令请直接 `action="create"`：

| 用户意图 | entity 键 | required（必填） | 常用可选字段 | 示例 fields |
|---|---|---|---|---|
| 新建研发项目 | `projects` | `name`,`code` | `status`,`budget`,`start_date`,`end_date`,`manager`,`rd_nature` | `{"name":"智能传感研发","code":"RD2026-001","status":"进行中","rd_nature":"自主研发"}` |
| 新增研发人员 | `personnel` | `name` | `org_id`,`title`,`is_rd`,`hourly_rate` | `{"name":"张三","title":"研发工程师","is_rd":1}` |
| 新增研发设备 | `equipment` | `name` | `code`,`category`,`model`,`acquisition_date`,`acquisition_cost` | `{"name":"高精度贴片机","category":"仪器设备","acquisition_cost":580000}` |
| 新增研发活动 | `activities` | `project_id`,`node_name` | `phase`,`status`,`assignee`,`start_date`,`end_date` | `{"project_id":1,"node_name":"样机试制","phase":"开发","status":"进行中"}` |
| 新增研发工时 | `worktime` | `person_id`,`project_id`,`work_date`,`hours` | `task_desc` | `{"person_id":1,"project_id":1,"work_date":"2026-07-26","hours":8}` |
| 工资薪酬/社保/公积金 | `labor_cost` | `person_id`,`cost_month`,`total_salary` | `social_insurance`,`housing_fund`,`work_hours_total`,`non_rd_hours` | `{"person_id":1,"cost_month":"2026-07","total_salary":25000,"social_insurance":6000,"housing_fund":3000}` |

> 说明：①`activities` 映射到系统 `project_node`（研发活动/节点）表，新增时先用 `db_operation(list,"projects")` 取目标 `project_id`；②`labor_cost` 现已含 `social_insurance`（社保）、`housing_fund`（公积金）两列，工资薪酬记 `total_salary`，三类一次性记录即可；③`project_id`/`person_id` 等关联键可用 `db_operation(list,...)` 查出 id，或用引用解析键 `project_name`/`person_name` 传入名称自动解析；④entity 键与真实表名映射：`projects`→`project`、`personnel`→`personnel`、`equipment`→`equipment`、`activities`→`project_node`、`worktime`→`work_time`、`labor_cost`→`labor_cost`、`evidence`→`evidence`、`risk`→`risk`、`capitalization_review`→`capitalization_review`、`material_requisition`→`material_requisition`、`outsourcing_contract`→`outsourcing_contract`（表名一律单数，完整 schema 见 `references/schema.md`）。

## 二、高频指令剧本（直接照做）

1. **新建研发项目** → `db_operation(create,"projects",fields={name,code,...})`，code 自编 `RD{year}-{序号}`。
2. **新增研发人员** → `db_operation(create,"personnel",fields={name,title,is_rd:1,...})`。
3. **新增研发设备** → `db_operation(create,"equipment",fields={name,category,...})`。
4. **新增研发活动**（"一箱/一个研发活动"均指此）→ 先 `list,"projects"` 取 `project_id`，再 `create,"activities",fields={project_id,node_name,phase,status}`。
5. **新增研发工时登记** → 先 `list,"personnel"`/`list,"projects"` 取 id，再 `create,"worktime",fields={person_id,project_id,work_date,hours}`。
6. **新增工资薪酬、社保与公积金记录** → `create,"labor_cost",fields={person_id,cost_month,total_salary,social_insurance,housing_fund}`（三项一并写入）。
7. **对研发人员人工费用进行分配，生成分配明细表和汇总表** → 见 `03-forms/labor-cost-allocation.md`：用 `run_python` 连库，按"研发工时/总工时"分摊 `total_salary+social_insurance+housing_fund`，逐人逐月逐项目算明细，汇总写 `output/研发人员人工费用分配明细表.md` 与 `output/研发人员人工费用分配汇总明细表.md`。
8. **生成研发费用加计扣除优惠明细表** → 用 `run_python` 从 `expense`/`expense_subject` 按加计口径归集，结合 `labor_cost` 人工，套 `03-forms/reports.md` 的加计表格式，写 `output/研发费用加计扣除优惠明细表.md`（其他相关费用 ≤10% 限额、委外 80% 计入）。
9. **生成公司研发模具管理制度** → `read_file` 读 `01-regulations/mold-management-system.md`，按企业实际填充 `{{占位符}}`，写 `output/研发模具管理制度.md`（Word/PDF 交付）。
10. **根据模板生成研发流程阶段划分内控制度与内控流程** → `read_file` 读 `01-regulations/internal-control-system.md` + `02-processes/rd-process.md`，填充后写 `output/研发费用内控制度与内控流程.md`。
11. **生成研发费用预算管理制度** -> `read_file` 读 `01-regulations/budget-management-system.md`，按企业实际填充 `{{占位符}}`，写 `output/研发费用预算管理制度.md`。
12. **生成加计扣除专项申报管理制度** -> `read_file` 读 `01-regulations/super-deduction-management-system.md`，填充后写 `output/研发费用加计扣除专项申报管理制度.md`。
13. **生成研发项目档案管理制度** -> `read_file` 读 `01-regulations/project-archive-management-system.md`，填充后写 `output/研发项目档案管理制度.md`。
14. **生成研发成果管理制度** -> `read_file` 读 `01-regulations/results-management-system.md`，填充后写 `output/研发成果管理制度.md`。
15. **生成加计扣除申报操作流程** -> `read_file` 读 `02-processes/super-deduction-workflow.md`，按企业实际填充后写 `output/研发费用加计扣除申报操作流程.md`。
16. **生成研发费用报销审批流程** -> `read_file` 读 `02-processes/expense-reimbursement-workflow.md`，填充后写 `output/研发费用报销审批流程.md`。
17. **生成研发人员认定与变更流程** -> `read_file` 读 `02-processes/personnel-identification-workflow.md`，填充后写 `output/研发人员认定与变更流程.md`。
18. **生成研发差旅费及会议费管理制度** -> `read_file` 读 `01-regulations/travel-meeting-expense-system.md`，填充后写 `output/研发差旅费及会议费管理制度.md`。
19. **生成研发人员绩效考核制度** -> `read_file` 读 `01-regulations/personnel-performance-system.md`，填充后写 `output/研发人员绩效考核制度.md`。
20. **生成设备共用分摊流程** -> `read_file` 读 `02-processes/equipment-audit-workflows.md`，填充后写 `output/研发设备共用分摊流程.md`。
21. **生成预算调整与跨期调整流程** -> `read_file` 读 `02-processes/budget-adjustment-and-cross-period-workflows.md`，填充后写 `output/研发预算调整与跨期调整流程.md`。
22. **生成研发费用辅助账（AL-01~04）** -> `read_file` 读 `04-practical-tools/AL-01-auxiliary-ledger-templates.md`，按企业实际填充 `{{占位符}}`，写 `output/研发费用辅助账模板集.md`。
23. **生成研发项目流转表（AL-05~06）** -> `read_file` 读 `04-practical-tools/AL-05-project-flow-table.md`，填充后写 `output/研发项目流转表.md`。
24. **生成研发费用分配表（AL-07~11）** -> `read_file` 读 `04-practical-tools/AL-07-allocation-tables.md`，填充后写 `output/研发费用分配表集.md`。
25. **生成研发人员台账（AL-12~14）** -> `read_file` 读 `04-practical-tools/AL-12-personnel-ledger.md`，填充后写 `output/研发人员台账模板集.md`。
26. **生成研发台账底稿与凭证序时簿（AL-15~17）** -> `read_file` 读 `04-practical-tools/AL-15-ledger-working-papers.md`，填充后写 `output/研发台账底稿与凭证序时簿.md`。
27. **生成研发费用差异说明** -> `read_file` 读 `03-forms/expense-difference-explanation.md`，按企业实际填充 `{{占位符}}`，写 `output/研发费用口径差异说明.md`。
28. **生成研发费用补充表单** -> `read_file` 读 `03-forms/forms-supplement.md`，按企业实际填充 `{{占位符}}`，写 `output/研发费用补充表单集.md`。
