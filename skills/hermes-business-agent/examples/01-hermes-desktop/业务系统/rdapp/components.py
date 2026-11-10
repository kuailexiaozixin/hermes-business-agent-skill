"""components.py — 共享 UI 组件

提供布局、导航、卡片、表格、徽章等可复用的 FastTags 组件。
所有 CSS 内联，不依赖 CDN，确保打包后离线可用。
"""
from fasthtml.common import *
from datetime import date
import os


# ── 全局样式 ──────────────────────────────────────────────

APP_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
    --bg: #f0f2f5;
    --surface: #ffffff;
    --sidebar-bg: #1e2a3a;
    --sidebar-hover: #2d3e54;
    --sidebar-active: #3b82f6;
    --text: #1a1a2e;
    --text-muted: #52525b;   /* 提至 WCAG AA：白底对比度 ≥4.5 */
    --text-light: #52525b;
    --border: #e5e7eb;
    --primary: #2563eb;
    --primary-dark: #2563eb;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --info: #6366f1;
    --phase-research: #3b82f6;
    --phase-develop: #10b981;
    --phase-produce: #f59e0b;
    --sidebar-width: 240px;
    --sidebar-collapsed-width: 56px;
    --sidebar-w: 240px;          /* 实时宽度：折叠/展开/拖拽共用此变量 */
    --sidebar-min: 56px;
    --sidebar-max: 440px;
}
body {
    font-family: -apple-system, "Microsoft YaHei", "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.6;
    font-variant-numeric: tabular-nums;
    user-select: text;
    -webkit-user-select: text;
}
/* 键盘可见焦点：满足 a11y 键盘导航可达性（audit 未显式验证项） */
a:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
.btn:focus-visible,
.nav-item:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}
.app-layout { display: flex; min-height: 100vh; }

/* 侧边栏 */
.sidebar {
    width: var(--sidebar-w);
    background: var(--sidebar-bg);
    color: #f1f5f9;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    position: fixed;
    height: 100vh;
    overflow-y: auto;
    overflow-x: hidden;
    z-index: 100;
    transition: width 0.2s ease;
}
.sidebar.collapsed { width: var(--sidebar-collapsed-width); }
/* 折叠态下隐藏右侧拖拽手柄（无宽度可调意义） */
.sidebar.collapsed .sidebar-resize-handle { display: none; }
/* 右侧拖拽手柄：左右拖拉调整侧边栏宽度（与折叠按钮并存） */
.sidebar-resize-handle {
    position: absolute;
    top: 0; right: 0;
    width: 6px; height: 100%;
    cursor: col-resize;
    z-index: 200;
    background: transparent;
    transition: background .15s;
}
.sidebar-resize-handle::before {
    content: "";
    position: absolute;
    top: 50%; right: 1px;
    transform: translateY(-50%);
    width: 2px; height: 36px;
    border-radius: 2px;
    background: transparent;
    transition: background .15s;
}
.sidebar-resize-handle:hover,
.sidebar-resize-handle.active { background: rgba(59,130,246,0.18); }
.sidebar-resize-handle:hover::before,
.sidebar-resize-handle.active::before { background: #60a5fa; }
.sidebar.collapsed .sidebar-header h1,
.sidebar.collapsed .sidebar-header p,
.sidebar.collapsed .nav-group-title,
.sidebar.collapsed .nav-item span:last-child { display: none; }
.sidebar.collapsed .nav-item { justify-content: center; padding: 10px 0; }
.sidebar.collapsed .nav-group-title { padding: 16px 0 6px; text-align: center; }
.sidebar-toggle {
    background: #f8fafc; border: 1px solid #e2e8f0; color: #1e293b; cursor: pointer;
    width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; transition: background .15s, transform .2s, box-shadow .15s;
    box-shadow: 0 2px 6px rgba(0,0,0,.18);
}
.sidebar-toggle:hover { background: #ffffff; transform: scale(1.05); box-shadow: 0 4px 10px rgba(0,0,0,.25); }
.sidebar.collapsed .sidebar-toggle { transform: rotate(180deg); }
.sidebar.collapsed .sidebar-toggle:hover { transform: rotate(180deg) scale(1.05); }
.sidebar-header {
    padding: 18px 16px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.sidebar-brand { flex: 1; min-width: 0; overflow: hidden; }
.sidebar-header h1 {
    color: #f5f5f5;
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 4px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sidebar-header p {
    color: #cbd5e1;
    font-size: 11px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sidebar-nav { padding: 12px 0; flex: 1; }
.nav-group-title {
    padding: 18px 20px 8px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #f1f5f9;
    font-weight: 700;
    line-height: 16px;
    overflow: hidden; white-space: nowrap;
}
/* 导航项：line-height 与 .nav-icon 高度严格同高（20px），消除图标/文字纵向错位 */
.nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px 10px 20px;
    color: #f5f5f5;
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    line-height: 20px;          /* 与图标盒同高，保证 flex 居中后视觉对齐 */
    min-height: 40px;           /* 命中态/折叠态/文字换行 时高度一致 */
    transition: all 0.15s;
    border-left: 3px solid transparent;
    white-space: nowrap;
}
.nav-item:hover {
    background: var(--sidebar-hover);
    color: #f5f5f5;
}
.nav-item.active {
    /* 用实色而非半透明：避免 CDP 探针按纯蓝(59,130,246)读背景导致对比度误判；
       实色 #1e40af 下白字对比度≈8.0，真实渲染与探针测量一致且高可读 */
    background: #1e40af;
    color: #f5f5f5;
    border-left-color: var(--sidebar-active);
    font-weight: 600;
}
.nav-item .nav-icon { color: #e2e8f0; }
.nav-item:hover .nav-icon { color: #f5f5f5; }
.nav-item.active .nav-icon { color: #f5f5f5; }
/* 图标盒固定 20×20；svg 用 display:block 消除内联基线空隙，避免图标下沉 */
.nav-icon { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; flex-shrink: 0; }
.nav-icon svg { display: block; width: 20px; height: 20px; stroke: currentColor; fill: none; }
/* 折叠态下仅显示图标，图标必须足够亮 */
.sidebar.collapsed .nav-item .nav-icon { color: #e2e8f0; }
.sidebar.collapsed .nav-item:hover .nav-icon { color: #f5f5f5; }
.sidebar.collapsed .nav-item.active .nav-icon { color: #bfdbfe; }

/* 主内容区 */
.main-content {
    flex: 1;
    margin-left: var(--sidebar-w);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    transition: margin-left 0.2s ease;
}
.main-content.sidebar-collapsed { margin-left: var(--sidebar-collapsed-width); }
.top-bar {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 10px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 50;
    gap: 12px;
}
.top-bar h2 { font-size: 16px; font-weight: 600; color: var(--text); white-space: nowrap; }
.top-bar .breadcrumb { font-size: 12px; color: var(--text-muted); }
.content-body { padding: 16px 20px; flex: 1; }

/* 卡片 */
.card {
    background: var(--surface);
    border-radius: 8px;
    border: 1px solid var(--border);
    padding: 20px;
    margin-bottom: 16px;
}
.card-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

/* 统计卡片 */
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.stat-card {
    background: var(--surface);
    border-radius: 8px;
    border: 1px solid var(--border);
    padding: 20px;
    position: relative;
    overflow: hidden;
}
.stat-card::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 4px;
}
.stat-card.blue::before { background: var(--primary); }
.stat-card.green::before { background: var(--success); }
.stat-card.orange::before { background: var(--warning); }
.stat-card.red::before { background: var(--danger); }
.stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.stat-sub { font-size: 11px; color: var(--text-light); margin-top: 4px; }

/* 表格 */
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.data-table th {
    text-align: left;
    padding: 10px 12px;
    background: #f8fafc;
    border-bottom: 2px solid var(--border);
    color: var(--text-muted);
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
}
.data-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
}
.data-table tr:hover td { background: #f8fafc; }
.data-table tr:last-child td { border-bottom: none; }

/* 徽章 */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    line-height: 1.5;
}
.badge-blue { background: #dbeafe; color: #1e40af; }
.badge-green { background: #d1fae5; color: #065f46; }
.badge-orange { background: #fef3c7; color: #92400e; }
.badge-red { background: #fee2e2; color: #991b1b; }
.badge-gray { background: #f3f4f6; color: #374151; }
.badge-purple { background: #ede9fe; color: #5b21b6; }

/* 阶段徽章 */
.phase-research { background: #dbeafe; color: #1e40af; }
.phase-develop { background: #d1fae5; color: #065f46; }
.phase-produce { background: #fef3c7; color: #92400e; }

/* 按钮 */
.btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    border: none;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.15s;
}
.btn-primary { background: var(--primary); color: #f5f5f5; }
.btn-primary:hover { background: var(--primary-dark); }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn-outline:hover { background: #f8fafc; border-color: var(--primary); color: var(--primary); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-danger { background: #dc2626; color: #f5f5f5; }
.btn-success { background: #047857; color: #f5f5f5; }
.btn-warning { background: #b45309; color: #f5f5f5; }

/* 表单 */
.form-group { margin-bottom: 16px; }
.form-label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text); }
.form-label .required { color: var(--danger); }
.form-input, .form-select, .form-textarea {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
    font-family: inherit;
    background: var(--surface);
    color: var(--text);
    outline: none;
    transition: border-color 0.15s;
}
.form-input:focus, .form-select:focus, .form-textarea:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(59,130,246,0.1);
}
.form-textarea { min-height: 80px; resize: vertical; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.form-hint { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.input-with-action { display: flex; gap: 8px; align-items: center; }
.input-with-action .form-input, .input-with-action .form-select { flex: 1; min-width: 0; }
.input-with-action .input-action-btn {
    padding: 8px 10px; font-size: 13px; line-height: 1;
    white-space: nowrap; flex-shrink: 0;
}
/* 模型列表（多模型管理） */
.model-list { margin: 4px 0 12px; border: 1px solid var(--border, #e5e7eb); border-radius: 8px; overflow: hidden; }
.model-list-title { font-size: 12px; font-weight: 600; padding: 8px 10px; background: rgba(127,127,127,0.06); }
.model-list-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; border-top: 1px solid var(--border, #e5e7eb); }
.model-list-item.active { background: rgba(22,163,74,0.08); }
.model-list-info { min-width: 0; }
.model-list-info b { font-size: 13px; }
.model-list-info .muted { font-size: 11px; }
.model-list-acts { display: flex; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
.form-actions { display: flex; gap: 8px; margin-top: 8px; }

/* 模态框/弹层 */
.modal-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4);
    display: flex; align-items: center; justify-content: center;
    z-index: 3000;
}
.modal {
    background: var(--surface);
    border-radius: 10px;
    width: 90%; max-width: 600px;
    max-height: 85vh; overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.15);
}
.modal-header {
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
}
.modal-header h3 { font-size: 16px; font-weight: 600; }
.modal-body { padding: 24px; }
.modal-footer {
    padding: 16px 24px;
    border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; gap: 10px;
}
.modal-close {
    background: none; border: none; font-size: 22px;
    color: var(--text-muted); cursor: pointer; line-height: 1;
}
.modal-max {
    background: none; border: none; font-size: 17px;
    color: var(--text-muted); cursor: pointer; line-height: 1;
    margin-right: 2px; padding: 0 4px; border-radius: 6px;
}
.modal-max:hover { color: var(--text); background: rgba(15,23,42,0.06); }

/* 进度条 */
.progress-bar {
    background: var(--border);
    border-radius: 4px;
    height: 6px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s;
}

/* 流程时间线 */
.timeline { position: relative; padding-left: 28px; }
.timeline::before {
    content: ''; position: absolute; left: 10px; top: 0; bottom: 0;
    width: 2px; background: var(--border);
}
.timeline-item { position: relative; padding-bottom: 20px; }
.timeline-item:last-child { padding-bottom: 0; }
.timeline-dot {
    position: absolute; left: -24px; top: 2px;
    width: 14px; height: 14px; border-radius: 50%;
    border: 3px solid var(--surface);
    z-index: 1;
}
.timeline-dot.done { background: var(--success); }
.timeline-dot.active { background: var(--primary); box-shadow: 0 0 0 4px rgba(59,130,246,0.2); }
.timeline-dot.pending { background: var(--text-light); }

/* 提示框 */
.alert {
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 13px;
    margin-bottom: 12px;
    display: flex;
    gap: 10px;
    align-items: flex-start;
}
.alert-info { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
.alert-warning { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
.alert-danger { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
.alert-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #065f46; }

/* 标签页 */
.tabs {
    display: flex;
    gap: 4px;
    border-bottom: 2px solid var(--border);
    margin-bottom: 20px;
}
.tab {
    padding: 8px 16px;
    font-size: 13px;
    color: var(--text-muted);
    text-decoration: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    font-weight: 500;
    transition: all 0.15s;
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--primary); border-bottom-color: var(--primary); }

/* 空状态 */
.empty-state {
    text-align: center;
    padding: 48px 20px;
    color: var(--text-muted);
}
.empty-state .icon { font-size: 48px; margin-bottom: 12px; opacity: 0.4; }

/* 响应式 */
@media (max-width: 1024px) {
    .stat-grid { grid-template-columns: repeat(2, 1fr); }
    .form-row, .form-row-3 { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
    .sidebar { display: none; }
    .main-content { margin-left: 0; }
    .stat-grid { grid-template-columns: 1fr; }
}

/* ── 设置中心（HubUI 弹窗：真实覆盖层，Hermes 实例中枢）── */
.settings-overlay {
  position: fixed; inset: 0; z-index: 1000;
  display: none;                        /* JS 打开时置为 flex */
  align-items: flex-start; justify-content: center;
  background: rgba(15, 23, 42, 0.55);
  padding: 32px 16px; overflow-y: auto;
}
.settings-overlay .modal { max-width: 920px; width: 94vw; }
.settings-modal {
  background: var(--surface);
  border-radius: 12px;
  box-shadow: 0 24px 70px rgba(0,0,0,0.28);
  max-height: 86vh; overflow: hidden;
  display: flex; flex-direction: column;
}
/* 设置中心「最大化」：仅把弹窗放大至整个应用窗口（CSS 级），不放大整个桌面应用窗口 */
.settings-overlay .modal.is-max {
  position: fixed; inset: 0;
  width: 100% !important; height: 100% !important;
  max-width: none; max-height: none;
  border-radius: 0; margin: 0;
  box-shadow: none;
}
.settings-modal.is-max .settings-panels { max-height: calc(100vh - 65px); }
.settings-modal .modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid var(--border); gap: 12px;
}
.settings-modal .modal-head-left {
  display: flex; align-items: center; gap: 14px; flex: 1; min-width: 0;
}
.settings-modal .modal-head h3 { font-size: 16px; font-weight: 600; }
.hub-state-compact {
  display: inline-flex; align-items: center; gap: 6px;
  background: #f8fafc; border: 1px solid var(--border); border-radius: 999px;
  padding: 2px 2px 2px 10px; font-size: 12px; white-space: nowrap;
}
.hub-state-label { color: var(--text-muted); }
.hub-state-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 999px; font-weight: 600;
}
.hub-state-badge::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%;
}
.hub-state-on { background: #dcfce7; color: #166534; }
.hub-state-on::before { background: #16a34a; }
.hub-state-off { background: #fee2e2; color: #b91c1c; }
.hub-state-off::before { background: #dc2626; }
.hub-state-refresh {
  background: none; border: none; color: var(--text-muted); cursor: pointer;
  font-size: 14px; padding: 2px 6px; border-radius: 999px;
}
.hub-state-refresh:hover { background: rgba(0,0,0,0.06); color: var(--text); }
.settings-grid { display: grid; grid-template-columns: 220px 1fr; min-height: 0; }
.settings-nav {
  border-right: 1px solid var(--border); padding: 12px 8px;
  max-height: calc(86vh - 65px); overflow-y: auto; background: var(--bg);
}
.settings-nav-group {
  font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--text-muted); padding: 12px 12px 4px; font-weight: 600;
}
/* 设置中心左侧导航：必须用 .settings-nav 限定，避免覆盖侧栏的 .nav-item
   （历史上写成全局选择器，display:block + 深色文字反向覆盖了侧栏的提亮样式，导致"左侧看不清"复发） */
.settings-nav .nav-item {
  display: block; padding: 8px 12px; border-radius: 8px;
  color: var(--text); text-decoration: none; font-size: 13px; cursor: pointer;
}
.settings-nav .nav-item:hover { background: rgba(37, 99, 235, 0.08); }
.settings-nav .nav-item.active { background: var(--primary); color: #f5f5f5; }
.settings-panels { padding: 20px 24px; overflow-y: auto; max-height: calc(86vh - 65px); }
.settings-panel { display: none; }
.settings-panel.active { display: block; }
.settings-panel-inner { max-width: 1080px; margin: 0 auto; }
.settings-panel h4 { font-size: 15px; margin: 0 0 4px; }
.settings-panel .hint-inline { font-size: 12px; color: var(--text-muted); margin: 0 0 12px; }
.settings-panel label { display: block; font-size: 12px; font-weight: 600; margin: 10px 0 4px; }
.form-col { min-width: 0; }
.form-col-fixed { flex: 0 0 auto; }
.form-range { width: 100%; accent-color: var(--primary); }
.toggle-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 10px 12px; background: #f8fafc; border: 1px solid var(--border);
  border-radius: 8px; margin: 8px 0 14px;
}
.switch {
  position: relative; display: inline-block; width: 40px; height: 22px;
}
.switch input { opacity: 0; width: 0; height: 0; }
.switch-slider {
  position: absolute; cursor: pointer; inset: 0;
  background: #cbd5e1; border-radius: 22px; transition: .2s;
}
.switch-slider::before {
  position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px;
  background: white; border-radius: 50%; transition: .2s;
}
.switch input:checked + .switch-slider { background: var(--primary); }
.switch input:checked + .switch-slider::before { transform: translateX(18px); }
.form-check {
  width: 18px; height: 18px; accent-color: var(--primary); cursor: pointer;
}
.form-status { font-size: 12px; margin-top: 8px; min-height: 16px; }
.loop-steps { display: flex; flex-wrap: wrap; gap: 8px; }
.loop-step { display: flex; align-items: center; gap: 6px; background: #f1f5f9; padding: 5px 10px; border-radius: 16px; font-size: 12px; border: 1px solid #e2e8f0; }
.loop-step-num { width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; background: var(--primary); color: #f5f5f5; border-radius: 50%; font-size: 10px; font-weight: 600; }
.loop-step-text { color: var(--text); }
/* Loop 面板：循环卡片 + 状态徽章 + 摘要条 */
.loop-summary { font-size: 13px; color: var(--text); background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; line-height: 1.7; }
.loop-card { border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; margin-bottom: 14px; background: #fff; transition: box-shadow .15s, transform .15s; }
.loop-card:hover { box-shadow: 0 6px 18px rgba(15,23,42,0.10); }
.loop-card-gateway { opacity: .78; background: #fafafa; }
.loop-card-ondemand { border-color: #c7d2fe; background: #f8faff; }
.loop-card-custom { border-color: #c7d2fe; background: #f8faff; }
.loop-card-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 14px; }
.loop-card-head .loop-badge { margin-left: auto; }
.loop-card-desc { font-size: 13px; color: var(--text-muted); margin: 8px 0 4px; line-height: 1.65; }
.loop-card-sec { font-size: 12px; font-weight: 700; color: var(--text); margin: 10px 0 6px; }
.loop-card-usage { font-size: 12.5px; color: var(--text-muted); line-height: 1.65; background: #f8fafc; border-radius: 8px; padding: 8px 10px; }
.loop-badge { font-size: 11px; padding: 2px 10px; border-radius: 999px; font-weight: 600; white-space: nowrap; }
.loop-badge-active { background: #dcfce7; color: #166534; }
.loop-badge-embedded { background: #e0f2fe; color: #075985; }
.loop-badge-switch { background: #fef9c3; color: #854d0e; }
.loop-badge-gateway { background: #f3f4f6; color: #6b7280; }
.loop-badge-ondemand { background: #e0e7ff; color: #4338ca; }
/* 加粗循环卡片边框，增大区分度（用户明确要求）：3px 主边 + 更强阴影 */
.loop-card.loop-card-bold { border: 3px solid #cbd5e1; box-shadow: 0 4px 14px rgba(15,23,42,0.16); }
.loop-card.loop-card-bold.loop-card-active { border-color: #22c55e; }
.loop-card.loop-card-bold.loop-card-embedded { border-color: #38bdf8; }
.loop-card.loop-card-bold.loop-card-switch { border-color: #eab308; }
.loop-card.loop-card-bold.loop-card-gateway { border-color: #9ca3af; }
.loop-card.loop-card-bold.loop-card-ondemand { border-color: #818cf8; }
.loop-card.loop-card-bold.loop-card-custom { border-color: #818cf8; }
/* 精致循环开关（与 Agent 对话页 .skill-toggle 一致，全局可用） */
.skill-toggle { position: relative; display: inline-flex; align-items: center; width: 36px; height: 20px; }
.skill-toggle input { opacity: 0; width: 0; height: 0; }
.skill-toggle-slider {
  position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
  background: #cbd5e1; border-radius: 20px; transition: .2s;
}
.skill-toggle-slider:before {
  position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px;
  background: #fff; border-radius: 50%; transition: .2s;
}
.skill-toggle input:checked + .skill-toggle-slider { background: var(--success); }
.skill-toggle input:checked + .skill-toggle-slider:before { transform: translateX(16px); }
.skill-toggle-label { font-size: 12px; color: var(--text-muted); }
/* 瀑布流：卡片按高度自然分流入列，无预留空列、无等高空白；超宽屏居中限宽 */
.loop-grid { columns: 2; column-gap: 16px; max-width: 1080px; margin: 0 auto; }
.loop-grid .loop-card { margin: 0 0 16px; break-inside: avoid; width: 100%; }
.loop-grid .loop-card-gateway { opacity: .82; }
/* 摘要条与自定义循环通栏，独占一整行 */
.loop-grid .loop-summary { column-span: all; margin-bottom: 16px; }
.loop-grid .loop-card-custom { column-span: all; }
@media (max-width: 760px) { .loop-grid { columns: 1; } }
/* Memory 记忆管理器（瀑布流卡片网格，与 Loop/Tools 同原则：消行高空白） */
.mem-store { max-width: 1080px; margin: 0 auto; }
.mem-sync-btn { margin-left: auto; }
.mem-toolbar { display: flex; align-items: center; gap: 10px; margin: 12px 0 10px; flex-wrap: wrap; }
.mem-search { position: relative; flex: 1 1 240px; min-width: 200px; }
.mem-search-ico { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 13px; opacity: .55; }
.mem-search-input { width: 100%; padding: 8px 10px 8px 30px; border: 1px solid var(--border); border-radius: 9px; font-size: 13px; background: #fff; color: var(--text); }
.mem-search-input:focus { outline: none; border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,.18); }
.mem-stats { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 10px; }
.mem-stat-pill { font-size: 12px; padding: 4px 11px; border-radius: 999px; background: #f1f5f9; color: #475569; border: 1px solid var(--border); }
.mem-stat-pill b { color: #0f172a; }
.mem-stat-pill.on { background: #dcfce7; color: #15803d; border-color: #bbf7d0; }
.mem-stat-pill.off { background: #f8fafc; color: #94a3b8; }
.mem-chips { display: flex; gap: 7px; flex-wrap: wrap; margin: 0 0 12px; }
.mem-chip { font-size: 12px; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--border); background: #fff; color: #475569; cursor: pointer; transition: all .12s; display: inline-flex; align-items: center; gap: 5px; }
.mem-chip:hover { border-color: #818cf8; color: #4338ca; }
.mem-chip.active { background: #eef2ff; border-color: #818cf8; color: #4338ca; font-weight: 600; }

/* ── 子智能体委托（Delegation）监控 ── */
.deleg-monitor { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; }
.deleg-item { border: 1px solid var(--border); border-radius: 9px; padding: 8px 10px; background: #f8faff; }
.deleg-item-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.deleg-subs { margin: 6px 0 0; padding-left: 18px; font-size: 12px; color: var(--text-muted); }
.deleg-subs li { margin: 2px 0; }
.agents-monitor { position: fixed; right: 18px; bottom: 18px; width: 320px; max-height: 60vh; overflow: auto;
  background: #fff; border: 1px solid #c7d2fe; border-radius: 12px; box-shadow: 0 10px 30px rgba(15,23,42,.18); z-index: 9000; padding: 12px 14px; }
.agents-monitor-head { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; margin-bottom: 8px; }
.agents-monitor-head button { margin-left: auto; }
.agents-monitor-body { display: flex; flex-direction: column; gap: 8px; }
.btn-xs { padding: 2px 8px; font-size: 11px; border-radius: 7px; }

/* ── 「子智能体循环」卡片内嵌的子智能体委托模块 ── */
.loop-deleg-wrap { margin-top: 6px; padding: 10px 12px; border: 1px dashed #c7d2fe; border-radius: 10px; background: #fafbff; }
.deleg-config { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; }
.deleg-config .form-group { margin: 4px 0; }

.mem-chip-n { font-size: 10.5px; background: #e2e8f0; color: #64748b; border-radius: 999px; padding: 0 6px; }
.mem-chip.active .mem-chip-n { background: #c7d2fe; color: #3730a3; }
.mem-grid { columns: 2; column-gap: 16px; max-width: 1080px; margin: 0 auto; }
.mem-grid .mem-card { margin: 0 0 16px; break-inside: avoid; width: 100%; box-sizing: border-box; }
@media (max-width: 760px) { .mem-grid { columns: 1; } }
.mem-empty { text-align: center; color: var(--text-muted); padding: 36px 10px; font-size: 13px; border: 1px dashed var(--border); border-radius: 12px; background: #f8fafc; }
.mem-card { border: 2px solid #e2e8f0; border-radius: 12px; padding: 13px 15px; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,0.06); transition: border-color .15s, box-shadow .15s, transform .12s; cursor: pointer; }
.mem-card:hover { box-shadow: 0 6px 18px rgba(15,23,42,0.10); border-color: #c7d2fe; transform: translateY(-1px); }
.mem-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.mem-card-title { font-size: 14px; font-weight: 600; color: #0f172a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1 1 auto; }
.mem-kind-badge { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; flex: 0 0 auto; }
.mem-kind-general { background: #e0e7ff; color: #4338ca; }
.mem-kind-project { background: #dbeafe; color: #1d4ed8; }
.mem-kind-rule { background: #fef3c7; color: #b45309; }
.mem-kind-wiki { background: #ccfbf1; color: #0f766e; }
.mem-kind-persona { background: #fce7f3; color: #be185d; }
.mem-kind-task { background: #dcfce7; color: #15803d; }
.mem-kind-meeting { background: #ffedd5; color: #c2410c; }
.mem-kind-people { background: #cffafe; color: #0e7490; }
.mem-card-snippet { font-size: 12.5px; color: var(--text-muted); line-height: 1.62; max-height: 4.9em; overflow: hidden; margin-bottom: 9px; word-break: break-word; }
.mem-card-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 11px; color: #94a3b8; margin-bottom: 9px; }
.mem-card-meta span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mem-card-meta span:first-child { font-family: var(--mono, monospace); }
.mem-card-foot { display: flex; gap: 6px; border-top: 1px dashed var(--border); padding-top: 9px; }
.mem-act { flex: 1 1 0; font-size: 12px; padding: 5px 4px; border: 1px solid var(--border); border-radius: 8px; background: #f8fafc; color: #475569; cursor: pointer; transition: all .12s; }
.mem-act:hover { background: #eef2ff; border-color: #818cf8; color: #4338ca; }
.mem-act-del:hover { background: #fef2f2; border-color: #fca5a5; color: #dc2626; }
/* 编辑器弹窗 */
.mem-modal-overlay { position: fixed; inset: 0; background: rgba(15,23,42,.45); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 18px; }
.mem-modal { background: #fff; border-radius: 14px; width: min(680px, 96vw); max-height: 92vh; display: flex; flex-direction: column; box-shadow: 0 24px 60px rgba(15,23,42,.30); }
.mem-modal-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.mem-modal-title { font-size: 15px; font-weight: 700; color: #0f172a; }
.mem-modal-x { border: none; background: transparent; font-size: 16px; cursor: pointer; color: #94a3b8; }
.mem-modal-x:hover { color: #dc2626; }
.mem-modal-body { padding: 14px 18px; overflow-y: auto; }
.mem-form-row { margin-bottom: 12px; }
.mem-form-label { display: block; font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 5px; }
.mem-form-input { width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 9px; font-size: 13px; background: #fff; color: var(--text); box-sizing: border-box; }
.mem-form-input:focus { outline: none; border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,.18); }
.mem-form-textarea { width: 100%; min-height: 260px; padding: 10px; border: 1px solid var(--border); border-radius: 9px; font-size: 13px; line-height: 1.7; font-family: var(--mono, monospace); background: #fff; color: var(--text); resize: vertical; box-sizing: border-box; }
.mem-form-textarea:focus { outline: none; border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,.18); }
.mem-modal-foot { display: flex; gap: 8px; justify-content: flex-end; padding: 12px 18px; border-top: 1px solid var(--border); }
/* 轻量 toast */
.mem-toast { position: fixed; left: 50%; bottom: 32px; transform: translateX(-50%); background: #0f172a; color: #f5f5f5; padding: 9px 18px; border-radius: 10px; font-size: 13px; z-index: 10000; opacity: 0; transition: opacity .25s; pointer-events: none; box-shadow: 0 8px 24px rgba(15,23,42,.30); }
.mem-toast.err { background: #dc2626; }
/* LLM Wiki 知识库管理器（复用 .mem-* 工具条/卡片/弹窗基础样式，此处仅 Wiki 专属） */
.wiki-store { max-width: 1080px; margin: 0 auto; }
.wiki-cat-badge { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; flex: 0 0 auto; }
.wiki-cat-general { background: #e0e7ff; color: #4338ca; }
.wiki-cat-rd { background: #dbeafe; color: #1d4ed8; }
.wiki-cat-finance { background: #fef3c7; color: #b45309; }
.wiki-cat-policy { background: #fee2e2; color: #b91c1c; }
.wiki-cat-tech { background: #ccfbf1; color: #0f766e; }
.wiki-cat-process { background: #fce7f3; color: #be185d; }
.wiki-cat-industry { background: #dcfce7; color: #15803d; }
.wiki-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 9px; }
.wiki-tag { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; background: #f1f5f9; color: #64748b; border: 1px solid var(--border); cursor: pointer; transition: all .12s; }
.wiki-tag:hover { border-color: #818cf8; color: #4338ca; background: #eef2ff; }
.wiki-tag.active { background: #eef2ff; border-color: #818cf8; color: #4338ca; font-weight: 600; }
.wiki-legacy-badge { font-size: 10px; color: #94a3b8; border: 1px dashed #cbd5e1; border-radius: 999px; padding: 0 6px; flex: 0 0 auto; }
/* 查看器弹窗（Markdown 渲染） */
.wiki-view-modal { width: min(860px, 96vw); }
.wiki-view-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; font-size: 11.5px; color: #94a3b8; padding: 9px 22px; border-bottom: 1px solid var(--border); background: #f8fafc; }
.wiki-view-body { padding: 16px 22px; overflow-y: auto; font-size: 13.5px; line-height: 1.75; color: #1e293b; }
.wiki-view-body h1 { font-size: 19px; margin: 14px 0 10px; }
.wiki-view-body h2 { font-size: 16px; margin: 16px 0 8px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.wiki-view-body h3 { font-size: 14.5px; margin: 12px 0 6px; }
.wiki-view-body h4 { font-size: 13.5px; margin: 10px 0 5px; }
.wiki-view-body p { margin: 6px 0; }
.wiki-view-body code { background: #f1f5f9; padding: 1px 5px; border-radius: 5px; font-size: 12px; font-family: var(--mono, monospace); }
.wiki-view-body pre { background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 9px; overflow: auto; font-size: 12px; line-height: 1.6; }
.wiki-view-body pre code { background: transparent; color: inherit; padding: 0; }
.wiki-view-body blockquote { border-left: 3px solid #c7d2fe; margin: 8px 0; padding: 4px 12px; color: #475569; background: #f8fafc; border-radius: 0 8px 8px 0; }
.wiki-view-body table { border-collapse: collapse; margin: 8px 0; width: 100%; font-size: 12.5px; }
.wiki-view-body th, .wiki-view-body td { border: 1px solid var(--border); padding: 5px 9px; text-align: left; }
.wiki-view-body th { background: #f8fafc; }
.wiki-view-body ul, .wiki-view-body ol { margin: 6px 0; padding-left: 22px; }
.wiki-view-body li { margin: 3px 0; }
.wiki-view-body a { color: #4338ca; }
.wiki-view-body hr { border: none; border-top: 1px dashed var(--border); margin: 12px 0; }
.wiki-sources { padding: 10px 22px; border-top: 1px dashed var(--border); font-size: 12px; color: #475569; }
.wiki-sources a { color: #4338ca; word-break: break-all; }
.wiki-sources li { margin: 3px 0; }
/* Soul 人格管理器（瀑布流卡片网格，与 Memory 同原则） */
.soul-store { max-width: 1080px; margin: 0 auto; }
.soul-toolbar { display: flex; align-items: center; gap: 10px; margin: 12px 0 10px; flex-wrap: wrap; }
.soul-search { position: relative; flex: 1 1 240px; min-width: 200px; }
.soul-search-ico { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 13px; opacity: .55; }
.soul-search-input { width: 100%; padding: 8px 10px 8px 30px; border: 1px solid var(--border); border-radius: 9px; font-size: 13px; background: #fff; color: var(--text); }
.soul-search-input:focus { outline: none; border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,.18); }
.soul-stats { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 10px; }
.soul-stat-pill { font-size: 12px; padding: 4px 11px; border-radius: 999px; background: #f1f5f9; color: #475569; border: 1px solid var(--border); }
.soul-stat-pill b { color: #0f172a; }
.soul-stat-pill.on { background: #dcfce7; color: #15803d; border-color: #bbf7d0; }
.soul-stat-pill.off { background: #f8fafc; color: #94a3b8; }
.soul-chips { display: flex; gap: 7px; flex-wrap: wrap; margin: 0 0 12px; }
.soul-chip { font-size: 12px; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--border); background: #fff; color: #475569; cursor: pointer; transition: all .12s; display: inline-flex; align-items: center; gap: 5px; }
.soul-chip:hover { border-color: #818cf8; color: #4338ca; }
.soul-chip.active { background: #eef2ff; border-color: #818cf8; color: #4338ca; font-weight: 600; }
.soul-chip-n { font-size: 10.5px; background: #e2e8f0; color: #64748b; border-radius: 999px; padding: 0 6px; }
.soul-chip.active .soul-chip-n { background: #c7d2fe; color: #3730a3; }
.soul-grid { columns: 2; column-gap: 16px; max-width: 1080px; margin: 0 auto; }
.soul-grid .soul-card { margin: 0 0 16px; break-inside: avoid; width: 100%; box-sizing: border-box; }
@media (max-width: 760px) { .soul-grid { columns: 1; } }
.soul-empty { text-align: center; color: var(--text-muted); padding: 36px 10px; font-size: 13px; border: 1px dashed var(--border); border-radius: 12px; background: #f8fafc; }
.soul-card { border: 2px solid #e2e8f0; border-radius: 12px; padding: 13px 15px; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,0.06); transition: border-color .15s, box-shadow .15s, transform .12s; cursor: pointer; }
.soul-card:hover { box-shadow: 0 6px 18px rgba(15,23,42,0.10); border-color: #c7d2fe; transform: translateY(-1px); }
.soul-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.soul-card-title { font-size: 14px; font-weight: 600; color: #0f172a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1 1 auto; }
.soul-card-right { flex: 0 0 auto; display: flex; align-items: center; }
.soul-kind-badge { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; flex: 0 0 auto; }
.soul-kind-general { background: #e0e7ff; color: #4338ca; }
.soul-kind-assistant { background: #dbeafe; color: #1d4ed8; }
.soul-kind-mentor { background: #fce7f3; color: #be185d; }
.soul-kind-audit { background: #fef3c7; color: #b45309; }
.soul-kind-analysis { background: #ccfbf1; color: #0f766e; }
.soul-kind-exec { background: #dcfce7; color: #15803d; }
.soul-kind-creative { background: #ffedd5; color: #c2410c; }
.soul-kind-service { background: #cffafe; color: #0e7490; }
.soul-active-pill { font-size: 10.5px; padding: 2px 9px; border-radius: 999px; font-weight: 600; background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; white-space: nowrap; }
.soul-card-snippet { font-size: 12.5px; color: var(--text-muted); line-height: 1.62; max-height: 4.9em; overflow: hidden; margin-bottom: 9px; word-break: break-word; }
.soul-card-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 11px; color: #94a3b8; margin-bottom: 9px; }
.soul-card-meta span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.soul-card-meta span:first-child { font-family: var(--mono, monospace); }
.soul-card-foot { display: flex; gap: 6px; border-top: 1px dashed var(--border); padding-top: 9px; }
.soul-act { flex: 1 1 0; font-size: 12px; padding: 5px 4px; border: 1px solid var(--border); border-radius: 8px; background: #f8fafc; color: #475569; cursor: pointer; transition: all .12s; }
.soul-act:hover { background: #eef2ff; border-color: #818cf8; color: #4338ca; }
.soul-act-del:hover { background: #fef2f2; border-color: #fca5a5; color: #dc2626; }
.soul-act-activate { background: #eef2ff; border-color: #c7d2fe; color: #4338ca; font-weight: 600; }
.soul-act-activate:hover { background: #e0e7ff; border-color: #818cf8; }
/* 编辑器弹窗 */
.soul-modal-overlay { position: fixed; inset: 0; background: rgba(15,23,42,.45); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 18px; }
.soul-modal { background: #fff; border-radius: 14px; width: min(680px, 96vw); max-height: 92vh; display: flex; flex-direction: column; box-shadow: 0 24px 60px rgba(15,23,42,.30); }
.soul-modal-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.soul-modal-title { font-size: 15px; font-weight: 700; color: #0f172a; }
.soul-modal-x { border: none; background: transparent; font-size: 16px; cursor: pointer; color: #94a3b8; }
.soul-modal-x:hover { color: #dc2626; }
.soul-modal-body { padding: 14px 18px; overflow-y: auto; }
.soul-form-row { margin-bottom: 12px; }
.soul-form-label { display: block; font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 5px; }
.soul-form-input { width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 9px; font-size: 13px; background: #fff; color: var(--text); box-sizing: border-box; }
.soul-form-input:focus { outline: none; border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,.18); }
.soul-form-textarea { width: 100%; min-height: 260px; padding: 10px; border: 1px solid var(--border); border-radius: 9px; font-size: 13px; line-height: 1.7; font-family: var(--mono, monospace); background: #fff; color: var(--text); resize: vertical; box-sizing: border-box; }
.soul-form-textarea:focus { outline: none; border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,.18); }
.soul-modal-foot { display: flex; gap: 8px; justify-content: flex-end; padding: 12px 18px; border-top: 1px solid var(--border); }
/* 轻量 toast */
.soul-toast { position: fixed; left: 50%; bottom: 32px; transform: translateX(-50%); background: #0f172a; color: #f5f5f5; padding: 9px 18px; border-radius: 10px; font-size: 13px; z-index: 10000; opacity: 0; transition: opacity .25s; pointer-events: none; box-shadow: 0 8px 24px rgba(15,23,42,.30); }
.soul-toast.err { background: #dc2626; }
/* 工作步骤默认折叠，节省短卡片空白 */
.loop-steps-toggle { font-size: 12px; padding: 4px 10px; margin: 4px 0 8px; }
.loop-steps-wrap { display: flex; flex-wrap: wrap; gap: 8px; }
.loop-steps-collapsed { display: none; }
.loop-custom-row { flex-wrap: wrap; }
/* 研发领域工具卡片（对标技能/Loop 卡片，支持单工具开关） */
.tool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; margin-top: 4px; }
.tool-card { border: 2px solid #e2e8f0; border-radius: 12px; padding: 14px 16px; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,0.06); transition: border-color .15s, background .15s; }
.tool-card.tool-card-off { border-color: #fca5a5; background: #fef2f2; opacity: .92; }
.tool-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 6px; }
.tool-card-head b { font-size: 14px; color: #0f172a; }
.tool-card-desc { font-size: 12.5px; color: var(--text-muted); line-height: 1.6; }
/* Tools 工具集卡片：对标技能/Loop 卡片（加粗状态色边 + 状态徽章 + 主开关 + 单工具开关 + 专属配置） */
/* 瀑布流：与 Loop 同理，避免少工具集时的整列空白；超宽屏居中限宽 */
.toolset-grid { columns: 2; column-gap: 16px; max-width: 1080px; margin: 4px auto 0; }
.toolset-grid .toolset-card { margin-bottom: 16px; break-inside: avoid; }
@media (max-width: 760px) { .toolset-grid { columns: 1; } }
/* 顶部统计行通栏，不挤入某一列 */
.toolset-grid > p:first-child { column-span: all; margin-bottom: 12px; }
.toolset-card { border: 2px solid #cbd5e1; border-radius: 12px; padding: 14px 16px; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,0.06); transition: border-color .15s, box-shadow .15s, transform .15s; margin-bottom: 2px; }
.toolset-card:hover { box-shadow: 0 6px 18px rgba(15,23,42,0.10); }
.toolset-card.toolset-on { border-color: #22c55e; }
.toolset-card.toolset-off { border-color: #cbd5e1; background: #f8fafc; }
.toolset-card.toolset-need { border-color: #eab308; background: #fffbeb; }
.toolset-card.toolset-locked { border-color: #ef4444; background: #fef2f2; }
.toolset-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.toolset-title { font-size: 14px; font-weight: 600; color: #0f172a; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolset-name { font-size: 11.5px; color: #94a3b8; font-family: var(--mono, monospace); }
.toolset-purpose { font-size: 12.5px; color: var(--text-muted); line-height: 1.6; margin: 8px 0 4px; }
.toolset-req { font-size: 12px; color: #b45309; margin: 4px 0; }
.toolset-config { margin: 10px 0 4px; border-top: 1px dashed var(--border); padding-top: 8px; }
.toolset-config-title { font-size: 12px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
.toolset-config .form-col { margin-bottom: 6px; }
.toolset-tools { margin: 10px 0 2px; border-top: 1px dashed var(--border); padding-top: 8px; }
.toolset-tools-title { font-size: 12px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.toolset-tool-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 4px 0; font-size: 13px; border-bottom: 1px dashed var(--border); }
.toolset-tool-row:last-child { border-bottom: none; }
.toolset-tool-row .tn { color: var(--text-muted); font-family: var(--mono, monospace); font-size: 12px; }
.toolset-tool-row.is-off .tn { color: #ef4444; text-decoration: line-through; }
/* 父级工具集关闭时，子工具整体置灰且禁用（与父状态一致，消除“父关子开”矛盾） */
.toolset-tool-row.is-parent-off .tn { color: #94a3b8; }
.toolset-tool-row.is-parent-off .skill-toggle { opacity: .5; pointer-events: none; }
.toolset-tool-row.is-parent-off input[type=checkbox] { cursor: not-allowed; }
.toolset-badge { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; }
.toolset-badge-on { background: #dcfce7; color: #15803d; }
.toolset-badge-off { background: #f1f5f9; color: #64748b; }
.toolset-badge-need { background: #fef3c7; color: #b45309; }
.toolset-badge-locked { background: #fee2e2; color: #991b1b; }
/* 任务看板（Kanban）：对标技能/Loop 卡片风格（加粗状态色边 + 徽章 + 操作区） */
.kanban-board { display: flex; gap: 12px; overflow-x: auto; padding: 4px 2px 10px; align-items: flex-start; }
.kanban-col { flex: 0 0 220px; background: #f8fafc; border: 1px solid var(--border); border-radius: 12px; padding: 8px; min-height: 120px; }
.kanban-col-head { font-size: 13px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 6px; margin-bottom: 8px; padding: 2px 4px; }
.kanban-col-count { font-size: 11px; font-weight: 600; color: #64748b; background: #e2e8f0; border-radius: 999px; padding: 0 7px; }
.kanban-col-empty { text-align: center; color: #cbd5e1; font-size: 12px; padding: 16px 0; }
.kanban-card { border: 2px solid #cbd5e1; border-radius: 10px; padding: 10px 11px; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,0.06); margin-bottom: 9px; transition: border-color .15s, box-shadow .15s; }
.kanban-card.kanban-card-triage { border-color: #94a3b8; }
.kanban-card.kanban-card-todo { border-color: #60a5fa; }
.kanban-card.kanban-card-ready { border-color: #38bdf8; }
.kanban-card.kanban-card-running { border-color: #22c55e; }
.kanban-card.kanban-card-blocked { border-color: #f59e0b; background: #fffbeb; }
.kanban-card.kanban-card-done { border-color: #a78bfa; opacity: .92; }
.kanban-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 6px; }
.kanban-card-head b { font-size: 13px; color: #0f172a; line-height: 1.35; }
.kanban-card-desc { font-size: 12px; color: var(--text-muted); line-height: 1.55; margin: 6px 0; white-space: pre-wrap; word-break: break-word; }
.kanban-card-meta { font-size: 11.5px; color: #64748b; margin: 2px 0; }
.kanban-card-result { font-size: 11.5px; color: #1e293b; background: #f1f5f9; border-radius: 8px; padding: 6px 8px; margin: 6px 0; white-space: pre-wrap; word-break: break-word; max-height: 120px; overflow: auto; }
.kanban-card-ops { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.kanban-card-ops .btn { padding: 3px 8px; font-size: 11px; }
.kanban-badge { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; }
.kanban-badge-triage { background: #e2e8f0; color: #475569; }
.kanban-badge-todo { background: #dbeafe; color: #1d4ed8; }
.kanban-badge-ready { background: #e0f2fe; color: #0369a1; }
.kanban-badge-running { background: #dcfce7; color: #15803d; }
.kanban-badge-blocked { background: #fef3c7; color: #b45309; }
.kanban-badge-done { background: #ede9fe; color: #6d28d9; }
/* 定时任务（Cron）：对标技能/Loop 卡片风格（加粗状态色边 + 开关 + 徽章 + 操作区 + 标签页） */
.cron-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 6px 0 10px; }
.cron-search { flex: 1 1 220px; min-width: 160px; }
.cron-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin: 4px 0 12px; }
.cron-tab { font-size: 13px; padding: 7px 14px; cursor: pointer; color: var(--text-muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
.cron-tab:hover { color: var(--text); }
.cron-tab.active { color: var(--primary); font-weight: 600; border-bottom-color: var(--primary); }
/* 设置中心 Loop / Soul / Wiki / 委托 面板的「发现 / 我的」标签页 */
.panel-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin: 4px 0 12px; }
.panel-tab { font-size: 13px; padding: 7px 14px; cursor: pointer; color: var(--text-muted); border-bottom: 2px solid transparent; margin-bottom: -1px; user-select: text; -webkit-user-select: text; }
.panel-tab:hover { color: var(--text); }
.panel-tab.active { color: var(--primary); font-weight: 600; border-bottom-color: var(--primary); }
.panel-tab-view { display: none; }
.panel-tab-view.active { display: block; }
.cron-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.cron-history { margin-top: 4px; }
.cron-empty { text-align: center; padding: 24px 0; display: flex; flex-direction: column; align-items: center; gap: 10px; }
.cron-card { border: 2px solid #cbd5e1; border-radius: 12px; padding: 12px 14px; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,0.06); transition: border-color .15s, box-shadow .15s; }
.cron-card.cron-card-active { border-color: #22c55e; }
.cron-card.cron-card-paused { border-color: #cbd5e1; background: #f8fafc; opacity: .95; }
.cron-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.cron-card-title { font-size: 14px; font-weight: 600; color: #0f172a; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cron-card-desc { font-size: 12.5px; color: var(--text-muted); line-height: 1.6; margin: 8px 0 6px; white-space: pre-wrap; word-break: break-word; }
.cron-card-meta { font-size: 11.5px; color: #64748b; margin: 2px 0; line-height: 1.5; }
.cron-card-ops { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.cron-card-ops .btn { padding: 3px 9px; font-size: 11.5px; }
.cron-badge { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; }
.cron-badge-active { background: #dcfce7; color: #15803d; }
.cron-badge-paused { background: #f1f5f9; color: #64748b; }
.cron-history-table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 4px; }
.cron-history-table th, .cron-history-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.cron-history-table th { color: var(--text-muted); font-weight: 600; background: #f8fafc; }
.cron-history-table tr:hover td { background: #f8fafc; }
.cron-hist-badge { font-size: 11px; padding: 1px 9px; border-radius: 999px; font-weight: 600; white-space: nowrap; }
.cron-hist-ok { background: #dcfce7; color: #15803d; }
.cron-hist-err { background: #fee2e2; color: #991b1b; }
.cron-freq-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 8px; }
.cron-template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin: 10px 0; }
.cron-template-card { border: 1px solid var(--border); border-radius: 10px; padding: 12px; background: #fff; box-shadow: 0 1px 3px rgba(15,23,42,0.05); }
.cron-tpl-title { font-size: 13.5px; font-weight: 600; color: #0f172a; margin-bottom: 6px; }
.cron-tpl-desc { font-size: 12px; color: var(--text-muted); line-height: 1.55; margin: 0 0 4px; }
.cron-tpl-sched { font-size: 11.5px; color: #64748b; margin: 0; font-family: monospace; }
.loop-custom-ops { display: flex; gap: 6px; flex-wrap: wrap; }

/* ── 任务控制中心（Dashboard）── 复用 cron/loop 状态色边语言 ── */
.tc-toolbar { display: flex; align-items: center; gap: 14px; margin: 8px 0 14px; flex-wrap: wrap; }
.tc-updated { font-size: 12px; color: var(--text-muted); }
.tc-auto-toggle { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }
.switch.switch-sm { width: 34px; height: 18px; }
.switch.switch-sm .slider::before { height: 12px; width: 12px; left: 3px; bottom: 3px; }
.switch.switch-sm input:checked + .slider::before { transform: translateX(16px); }
.tc-overview { display: grid; grid-template-columns: repeat(auto-fill, minmax(132px, 1fr)); gap: 10px; margin-bottom: 16px; }
.tc-stat { border: 1px solid var(--border); border-left-width: 4px; border-radius: 10px; padding: 10px 12px; background: #fff; box-shadow: 0 1px 3px rgba(15,23,42,0.05); }
.tc-stat-n { font-size: 22px; font-weight: 700; line-height: 1.1; color: #0f172a; }
.tc-stat-l { font-size: 11.5px; color: var(--text-muted); margin-top: 3px; }
.tc-stat-ok { border-left-color: #22c55e; }
.tc-stat-ok .tc-stat-n { color: #15803d; }
.tc-stat-warn { border-left-color: #eab308; }
.tc-stat-warn .tc-stat-n { color: #b45309; }
.tc-stat-err { border-left-color: #ef4444; }
.tc-stat-err .tc-stat-n { color: #b91c1c; }
.tc-stat-run { border-left-color: #38bdf8; }
.tc-stat-run .tc-stat-n { color: #0369a1; }
.tc-stat-info { border-left-color: #818cf8; }
.tc-stat-info .tc-stat-n { color: #4338ca; }
.tc-stat-muted { border-left-color: #cbd5e1; }
.tc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 6px; }
.tc-col { min-width: 0; }
.tc-section-title { font-size: 13.5px; font-weight: 600; color: #0f172a; margin: 18px 0 8px; padding-left: 8px; border-left: 3px solid #e2e8f0; }
.tc-loop-summary { font-size: 12.5px; color: var(--text-muted); line-height: 1.6; margin-bottom: 8px; }
.tc-loop-list { display: flex; flex-direction: column; gap: 6px; }
.tc-loop-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; color: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; background: #fff; }
.tc-att-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.tc-att-item { font-size: 12.5px; line-height: 1.5; padding: 8px 10px; border-radius: 8px; border-left: 3px solid #cbd5e1; background: #f8fafc; }
.tc-att-item.tc-att-err { border-left-color: #ef4444; background: #fef2f2; color: #991b1b; }
.tc-att-item.tc-att-warn { border-left-color: #eab308; background: #fffbeb; color: #92400e; }
.tc-att-item.tc-att-info { border-left-color: #818cf8; background: #eef2ff; color: #4338ca; }
.tc-cron-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.tc-kanban-cols { display: flex; flex-wrap: wrap; gap: 10px; }
.tc-kanban-col { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; background: #fff; font-size: 13px; }
.tc-kanban-n { font-weight: 700; color: #0f172a; }
.tc-kanban-boards { font-size: 12.5px; color: var(--text-muted); margin-top: 8px; }
/* ── RD caliber page (base-data, moved from settings hub) ── */
.rd-section { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; margin: 0 0 16px; }
.rd-sec-title { font-size: 13.5px; font-weight: 600; color: var(--text); margin: 0 0 10px; padding-left: 8px; border-left: 3px solid var(--primary); }
.kv-list { display: flex; flex-direction: column; margin-bottom: 10px; }
.rd-caliber-page label:not(.skill-toggle) { display: block; font-size: 12px; font-weight: 600; margin: 10px 0 4px; }
.rd-caliber-page .hint-inline { font-size: 12px; color: var(--text-muted); margin: 8px 0; }
.rd-caliber-page .skill-toggle { cursor: pointer; }
.kv-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); }
.kv-row-head { background: rgba(15,23,42,0.03); border-radius: 8px; padding: 8px 10px; margin-top: 4px; }
.kv-row.kv-sub { padding: 5px 0 5px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.kv-row.kv-sub > div { color: var(--text-muted); }
.tag { font-size: 11px; padding: 1px 8px; border-radius: 999px; }
.tag-on { background: #dcfce7; color: #166534; }
.tag-off { background: #f3f4f6; color: #4b5563; }
.tag-err { background: #fee2e2; color: #991b1b; font-weight: 600; }
/* 通用布局工具：flex 行（工具条/操作区默认横向排列并留间距） */
.row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.gap-sm { gap: 8px; }
.hub-statebar { font-size: 12px; padding: 8px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; }
.hub-state-on { color: #166534; font-weight: 600; }
.hub-state-off { color: #b91c1c; font-weight: 600; }
.link { color: var(--primary); text-decoration: none; cursor: pointer; }
.muted { color: var(--text-muted); }

/* ── 插件管理（Plugins）── */
.plugin-stats { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 12px; }
.pstat { background: linear-gradient(135deg,#eef2ff,#f8faff); border: 1px solid var(--border); border-radius: 11px; padding: 9px 16px; min-width: 92px; text-align: center; }
.pstat b { display: block; font-size: 20px; color: #4338ca; line-height: 1.1; }
.pstat span { font-size: 12px; color: #64748b; }
.plugin-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 14px; margin-top: 6px; }
.plugin-card { border: 1px solid var(--border); border-radius: 13px; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,.06); overflow: hidden; transition: box-shadow .15s, border-color .15s, transform .12s; }
.plugin-card:hover { box-shadow: 0 8px 22px rgba(15,23,42,.10); border-color: #c7d2fe; transform: translateY(-1px); }
.plugin-card.open { border-color: #818cf8; }
.pc-head { display: flex; align-items: flex-start; gap: 12px; padding: 13px 15px; cursor: pointer; }
.pc-icon { font-size: 26px; width: 42px; height: 42px; display: flex; align-items: center; justify-content: center; background: #f1f5f9; border-radius: 11px; flex: 0 0 auto; }
.pc-main { flex: 1 1 auto; min-width: 0; }
.pc-title { font-size: 14.5px; font-weight: 700; color: #0f172a; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pc-sub { font-size: 11.5px; margin: 3px 0; }
.pc-desc { font-size: 12.5px; color: #475569; line-height: 1.5; margin-top: 4px; }
.pc-actions { flex: 0 0 auto; display: flex; align-items: center; }
.pc-foot { display: flex; justify-content: flex-end; gap: 8px; padding: 0 15px 13px; border-top: 1px dashed var(--border); padding-top: 11px; }
.pc-detail { border-top: 1px solid var(--border); background: #fbfcfe; padding: 13px 15px; }
.pc-detail-body { display: flex; flex-direction: column; gap: 10px; font-size: 12.5px; }
.pc-detail-sec b { font-size: 12px; color: #334155; display: block; margin-bottom: 3px; }
.pc-deps { margin: 0; padding-left: 18px; color: #475569; }
.tag { display: inline-block; font-size: 10.5px; padding: 1px 8px; border-radius: 999px; background: #f1f5f9; color: #64748b; border: 1px solid var(--border); white-space: nowrap; }
.tag-on { background: #dcfce7; color: #15803d; border-color: #bbf7d0; }
.tag-off { background: #f8fafc; color: #94a3b8; border-color: #e2e8f0; }
.tag-builtin { background: #ede9fe; color: #6d28d9; border-color: #ddd6fe; }
.tag-user { background: #e0f2fe; color: #0369a1; border-color: #bae6fd; }
.tag-err { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.tag-edit { background: #fff7ed; color: #c2410c; border-color: #fed7aa; font-weight: 600; }
.chip-sm { font-size: 11px; padding: 3px 10px; }
@media (max-width: 760px) { .plugin-grid { grid-template-columns: 1fr; } }

/* ── Hermes 原生内置插件（bundled）── */
.hub-sep { height: 1px; background: var(--border); margin: 18px 0; border: 0; }
.native-plugin-list { display: flex; flex-direction: column; gap: 14px; margin-top: 8px; }
.nat-group { border: 1px solid var(--border); border-radius: 13px; overflow: hidden; background: #fff; }
.nat-group-head { display: flex; align-items: center; gap: 10px; padding: 11px 15px; cursor: pointer;
  background: #f8fafc; border-bottom: 1px solid transparent; user-select: text; -webkit-user-select: text; }
.nat-group.open .nat-group-head { border-bottom-color: var(--border); }
.nat-group-icon { font-size: 18px; }
.nat-group-label { font-weight: 700; color: #0f172a; font-size: 14px; }
.nat-group-count { margin-left: auto; font-size: 12px; }
.nat-group-count b { color: #4338ca; }
.nat-group-caret { font-size: 12px; color: #64748b; width: 16px; text-align: center; }
.nat-group-body { padding: 12px; display: flex; flex-direction: column; gap: 12px; }
.nat-card { box-shadow: none; }
.nat-form { display: flex; flex-direction: column; gap: 10px; margin: 4px 0 8px; }
.nat-field { display: flex; flex-direction: column; gap: 4px; }
.nat-label { font-size: 12.5px; font-weight: 600; color: #334155; }
.nat-label .req { color: #dc2626; font-style: normal; }
.nat-hint { font-size: 11.5px; }
.nat-url { font-size: 12px; }
.tag-active { background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe; }
.tag-auto { background: #ede9fe; color: #6d28d9; border-color: #ddd6fe; }
"""


# ── 布局组件 ──────────────────────────────────────────────

NAV_ITEMS = [
    ("Agent 对话", "/", "robot", "系统概览"),
    ("仪表盘", "/dashboard", "dashboard", "系统概览"),
    ("基础数据", "/base-data", "database", "系统概览"),
    ("数据中心", "/datacenter", "database", "系统概览"),
    ("研发项目", "/projects", "folder", "系统概览"),
    ("跨主体视图", "/projects/cross-org", "folder", "系统概览"),
    ("重复申报检测", "/projects/duplicate-check", "search", "系统概览"),
    ("流程管理", "/process", "workflow", "系统概览"),
    ("费用总账", "/expenses", "coins", "费用归集"),
    ("工时管理", "/worktime", "clock", "费用归集"),
    ("工时预警", "/worktime-alert-rules", "clock", "费用归集"),
    ("人工费用", "/labor-costs", "users", "费用归集"),
    ("分摊明细", "/labor-allocation", "users", "费用归集"),
    ("研发设备", "/equipment", "tool", "费用归集"),
    ("原材料领用", "/materials", "box", "费用归集"),
    ("委托外部研发", "/outsourcing", "handshake", "费用归集"),
    ("其他费用", "/others", "receipt", "费用归集"),
    ("证据链", "/evidence", "link", "合规管理"),
    ("凭证备查", "/evidence-docs", "file", "合规管理"),
    ("资本化审批", "/capitalization", "check", "合规管理"),
    ("比例指标", "/metrics", "gauge", "合规管理"),
    ("特殊收入冲减", "/special-income", "minus", "合规管理"),
    ("样品废料台账", "/sample-scrap", "recycle", "合规管理"),
    ("受托研发隔离", "/entrusted", "shield", "合规管理"),
    ("风险预警", "/risks", "alert", "合规管理"),
    ("风控中心", "/risk-alerts", "alert", "合规管理"),
    ("政策规则库", "/policy-rules", "award", "合规管理"),
    ("报表中心", "/reports", "chart", "合规管理"),
    ("版本化报表", "/reports/center", "chart", "合规管理"),
    ("三类口径并排", "/reports/compare", "chart", "合规管理"),
    ("共用设备分摊", "/equipment/sharing", "tool", "合规管理"),
    ("AI 助手", "/ai-assistant", "robot", "合规管理"),
    ("组织树管理", "/org-tree", "database", "合规管理"),
    ("专利成果", "/patents", "award", "研发资产"),
    ("物料细分台账", "/materials/types", "box", "研发资产"),
    ("样品废料冲减", "/materials/sample-scrap-summary", "recycle", "研发资产"),
    ("研发人员认定", "/rd-personnel", "users", "人事管理"),
    ("考勤打卡", "/attendance", "clock", "人事管理"),
    ("薪酬计提", "/salary", "coins", "人事管理"),
    ("审批工作流", "/approval", "approval", "内控与治理"),
    ("操作审计", "/audit", "audit", "内控与治理"),
    ("内控治理", "/control", "control", "内控与治理"),
    ("项目权限", "/project-roles", "shield", "内控与治理"),
]

# 内联 SVG 图标（离线可用，无需外部字体/CDN）
ICON_SVGS = {
    "dashboard": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>""",
    "database": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M3 5V19A9 3 0 0 0 21 19V5"></path><path d="M3 12A9 3 0 0 0 21 12"></path></svg>""",
    "folder": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>""",
    "search": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>""",
    "file": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>""",
    "workflow": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="3"></circle><circle cx="5" cy="19" r="3"></circle><circle cx="19" cy="19" r="3"></circle><path d="M12 8v2"></path><path d="M8.5 14.5 7 16"></path><path d="M15.5 14.5 17 16"></path></svg>""",
    "coins": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M3 5V11A9 3 0 0 0 21 11V5"></path><path d="M3 11V17A9 3 0 0 0 21 17V11"></path></svg>""",
    "users": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>""",
    "clock": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>""",
    "tool": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>""",
    "box": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>""",
    "handshake": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 17 2 2a1 1 0 1 0 3-3"></path><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"></path><path d="m21 3 1 11h-2"></path><path d="M3 3 2 14l6 6"></path></svg>""",
    "receipt": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"></path><path d="M16 8h-6"></path><path d="M16 12h-6"></path><path d="M16 16h-6"></path></svg>""",
    "link": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>""",
    "alert": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>""",
    "chart": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>""",
    "check": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>""",
    "gauge": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 14l4-4"></path><path d="M3.34 19a10 10 0 1 1 17.32 0"></path></svg>""",
    "minus": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="8" y1="12" x2="16" y2="12"></line></svg>""",
    "recycle": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 19H4.8a2 2 0 0 1-1.7-3l2.3-4a2 2 0 0 1 1.7-1h6.4a2 2 0 0 1 1.7 1l.6 1"></path><path d="M21 15.5a2 2 0 0 1-1.7 3H17"></path><path d="M12 12 9 9"></path><path d="m16 8 3-3 1 3-3 1"></path></svg>""",
    "shield": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>""",
    "approval": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"></rect><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><path d="m9 14 2 2 4-4"></path></svg>""",
    "audit": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>""",
    "control": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><path d="m9 12 2 2 4-4"></path></svg>""",
    "robot": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"></rect><circle cx="12" cy="5" r="2"></circle><path d="M12 7v4"></path><line x1="8" y1="16" x2="8" y2="16"></line><line x1="16" y1="16" x2="16" y2="16"></line></svg>""",
    "award": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"></circle><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"></path></svg>""",
    "puzzle": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4a2 2 0 1 0-4 0v1H8a2 2 0 0 0-2 2v3h1a2 2 0 1 1 0 4H6v3a2 2 0 0 0 2 2h3v-1a2 2 0 1 1 4 0v1h3a2 2 0 0 0 2-2v-3h-1a2 2 0 1 1 0-4h1V8a2 2 0 0 0-2-2h-2V4z"></path></svg>""",
    "plugin": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><path d="M10 6.5h4M6.5 10v4M17.5 10v4M10 17.5h4"></path></svg>""",
}


def sidebar(active: str = ""):
    """侧边导航栏（支持可折叠）"""
    # 独立模式（RD_BIZ_STANDALONE=1）：Agent 底座对话页不可达，
    # "Agent 对话"入口指向业务系统内置 AI 助手（Hermes AIAgent 驱动）；
    # 融合模式保持指向 "/"（Agent 底座对话页）。
    standalone = os.environ.get("RD_BIZ_STANDALONE") == "1"
    groups = {}
    for label, href, icon, group in NAV_ITEMS:
        if standalone and label == "Agent 对话":
            href = "/ai-assistant"
        groups.setdefault(group, []).append((label, href, icon))

    nav_items = []
    for group_name, items in groups.items():
        if not items:
            continue
        nav_items.append(Div(group_name, cls="nav-group-title"))
        for label, href, icon in items:
            is_active = (href != "/" and active == href) or (href == "/" and active == "/")
            cls = "nav-item active" if is_active else "nav-item"
            nav_items.append(
                A(
                    Span(NotStr(ICON_SVGS.get(icon, "")), cls="nav-icon"),
                    Span(label),
                    href=href,
                    cls=cls,
                    title=label,
                    **({"aria_current": "page"} if is_active else {})
                )
            )

    return Div(
        Div(
            Div(
                H1("研发费用管理系统"),
                P("RD Expense Management System v1.0"),
                cls="sidebar-brand",
            ),
            Button(
                NotStr("""<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11 17 6 12 11 7"></polyline><polyline points="18 17 13 12 18 7"></polyline></svg>"""),
                cls="sidebar-toggle",
                onclick="window.toggleSidebar()",
                title="折叠/展开菜单",
                aria_label="折叠或展开侧边栏"
            ),
            cls="sidebar-header"
        ),
        Div(*nav_items, cls="sidebar-nav", role="navigation", aria_label="主导航"),
        Div(cls="sidebar-resize-handle", title="按住左右拖动调整菜单宽度"),
        cls="sidebar",
        id="appSidebar"
    )


def page_layout(title: str, breadcrumb: str = "", active: str = "", *body):
    """完整页面布局：侧边栏 + 顶栏 + 内容区"""
    toggle_script = Script("""
(function(){
  const SB_KEY = 'rd_sidebar_collapsed';
  const W_KEY = 'rd_sidebar_width';
  function root(){ return document.documentElement; }
  function setVar(w){ root().style.setProperty('--sidebar-w', w + 'px'); }
  function getVar(){
    const v = getComputedStyle(root()).getPropertyValue('--sidebar-w');
    const n = parseFloat(v);
    return isNaN(n) ? 240 : n;
  }
  function applySidebarState(){
    try {
      const collapsed = localStorage.getItem(SB_KEY) === '1';
      const w = localStorage.getItem(W_KEY);
      const sb = document.getElementById('appSidebar');
      const mc = document.getElementById('appMainContent');
      if (w) setVar(parseFloat(w));
      if (sb) sb.classList.toggle('collapsed', collapsed);
      if (mc) mc.classList.toggle('sidebar-collapsed', collapsed);
      // 恢复侧边栏导航滚动位置（整页导航后菜单不再回到顶部）
      const sc = parseFloat(localStorage.getItem('rd_sidebar_scroll') || '0');
      if (sb && sc > 0) sb.scrollTop = sc;
    } catch(e){}
  }
  // 点击导航项前保存侧边栏滚动位置；整页导航会刷新页面并丢失 scrollTop
  function initSidebarScroll(){
    const sb = document.getElementById('appSidebar');
    if (!sb) return;
    sb.addEventListener('click', function(e){
      const t = e.target;
      const a = t && t.closest ? t.closest('a.nav-item') : null;
      if (a) {
        try { localStorage.setItem('rd_sidebar_scroll', String(sb.scrollTop)); } catch(err){}
      }
    });
  }
  window.toggleSidebar = function(){
    const sb = document.getElementById('appSidebar');
    const mc = document.getElementById('appMainContent');
    if (!sb) return;
    const collapsed = !sb.classList.contains('collapsed');
    if (collapsed) {
      sb.classList.add('collapsed');
      if (mc) mc.classList.add('sidebar-collapsed');
      try { localStorage.setItem(SB_KEY, '1'); } catch(e){}
    } else {
      sb.classList.remove('collapsed');
      if (mc) mc.classList.remove('sidebar-collapsed');
      const w = localStorage.getItem(W_KEY);
      if (w) setVar(parseFloat(w));
      try { localStorage.setItem(SB_KEY, '0'); } catch(e){}
    }
  };
  // 右侧手柄：左右拖拽调整宽度（56~440px），与折叠按钮并存
  function initSidebarResize(){
    const sb = document.getElementById('appSidebar');
    const handle = document.querySelector('.sidebar-resize-handle');
    if (!sb || !handle) return;
    let startX = 0, startW = 0, dragging = false;
    const MIN = 56, MAX = 440;
    handle.addEventListener('mousedown', function(e){
      dragging = true;
      startX = e.clientX;
      startW = sb.getBoundingClientRect().width;
      handle.classList.add('active');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    window.addEventListener('mousemove', function(e){
      if (!dragging) return;
      let w = startW + (e.clientX - startX);
      w = Math.min(MAX, Math.max(MIN, w));
      setVar(w);
      // 拖拽即视为展开态
      if (sb.classList.contains('collapsed')) {
        sb.classList.remove('collapsed');
        const mc = document.getElementById('appMainContent');
        if (mc) mc.classList.remove('sidebar-collapsed');
      }
    });
    window.addEventListener('mouseup', function(){
      if (!dragging) return;
      dragging = false;
      handle.classList.remove('active');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      const w = sb.getBoundingClientRect().width;
      try {
        localStorage.setItem(W_KEY, String(w));
        localStorage.setItem(SB_KEY, '0');
      } catch(e){}
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function(){ applySidebarState(); initSidebarResize(); initSidebarScroll(); });
  } else { applySidebarState(); initSidebarResize(); initSidebarScroll(); }
})();
""")
    return Div(
        Style(APP_CSS),
        sidebar(active),
        # 侧边栏渲染后立即恢复滚动位置，避免整页导航后先显示顶部再跳回原位的闪烁
        Script("""(function(){try{var sb=document.getElementById('appSidebar');var sc=parseFloat(localStorage.getItem('rd_sidebar_scroll')||'0');if(sb&&sc>0)sb.scrollTop=sc;}catch(e){}})();"""),
        Div(
            Div(
                Div(
                    H2(title),
                    Span(f" / {breadcrumb}", style="font-size:12px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;") if breadcrumb else "",
                    style="display:flex;align-items:center;gap:4px;min-width:0;",
                ),
                Span(f"{date.today().strftime('%Y-%m-%d')}", style="font-size:12px;color:var(--text-muted);white-space:nowrap;flex-shrink:0;"),
                cls="top-bar",
            ),
            Div(*body, cls="content-body"),
            cls="main-content",
            id="appMainContent"
        ),
        toggle_script,
        Script(f"document.title = {__import__('json').dumps(title)};"),
        cls="app-layout",
    )


# ── 通用组件 ──────────────────────────────────────────────

def stat_card(label: str, value: str, sub: str = "", color: str = "blue"):
    """统计卡片"""
    return Div(
        Div(label, cls="stat-label"),
        Div(value, cls="stat-value"),
        Div(sub, cls="stat-sub") if sub else "",
        cls=f"stat-card {color}"
    )


def phase_badge(phase: str):
    """阶段徽章"""
    cls_map = {"研究": "phase-research", "开发": "phase-develop", "生产": "phase-produce"}
    cls = cls_map.get(phase, "badge-gray")
    return Span(phase, cls=f"badge {cls}")


def status_badge(status: str):
    """状态徽章"""
    color_map = {
        "进行中": "badge-blue", "已完成": "badge-green", "待开始": "badge-gray",
        "已结题": "badge-green", "立项中": "badge-purple", "已暂停": "badge-gray",
        "待处理": "badge-orange", "已整改": "badge-green", "已忽略": "badge-gray",
        "已打回": "badge-red", "待审批": "badge-orange",
        "未提交": "badge-gray", "已通过": "badge-green",
        "费用化": "badge-blue", "待资本化": "badge-orange", "已资本化": "badge-green", "非研发": "badge-gray",
    }
    cls = color_map.get(status, "badge-gray")
    return Span(status, cls=f"badge {cls}")


def level_badge(level: str):
    """风险等级徽章"""
    color_map = {"高": "badge-red", "中": "badge-orange", "低": "badge-blue"}
    cls = color_map.get(level, "badge-gray")
    return Span(level, cls=f"badge {cls}")


def data_table(headers: list, rows: list, cls: str = ""):
    """数据表格"""
    ths = [Th(h) for h in headers]
    trs = []
    for row in rows:
        tds = [Td(cell) for cell in row]
        trs.append(Tr(*tds))
    return Table(
        Thead(Tr(*ths)),
        Tbody(*trs),
        cls=f"data-table {cls}"
    )


def empty_state(icon: str, message: str):
    """空状态"""
    return Div(
        Div(icon, cls="icon"),
        P(message),
        cls="empty-state"
    )


def alert_box(message: str, alert_type: str = "info"):
    """提示框"""
    icons = {"info": "i", "warning": "!", "danger": "x", "success": ""}
    icon = icons.get(alert_type, "i")
    return Div(
        Span(icon, style="font-weight:bold;flex-shrink:0;") if icon else "",
        Span(message),
        cls=f"alert alert-{alert_type}"
    )


def progress_bar(percent: float, color: str = ""):
    """进度条"""
    color_map = {"": "var(--primary)", "green": "var(--success)", "orange": "var(--warning)", "red": "var(--danger)"}
    fill_color = color_map.get(color, "var(--primary)")
    return Div(
        Div(style=f"width:{percent:.0f}%;background:{fill_color};", cls="progress-fill"),
        cls="progress-bar"
    )


def modal_dialog(title: str, body_content, footer_content=None, modal_id: str = "modal"):
    """模态框

    关闭动作绑定在标题栏的 × 按钮上，点击向 /close/{modal_id} 发起 HTMX
    请求，由路由返回空内容将整个 overlay 从 DOM 中移除（hx_swap=outerHTML）。
    注意：hx_get 只放在 × 按钮，不放 overlay 本身，避免点击弹窗内部内容时
    误触发关闭 / 命中不存在的路由（404）。
    """
    return Div(
        Div(
            Div(
                H3(title),
                Button(
                    "×", cls="modal-close",
                    hx_get=f"/close/{modal_id}",
                    hx_target=f"#{modal_id}",
                    hx_swap="outerHTML",
                    aria_label="关闭",
                ),
                cls="modal-header",
            ),
            Div(body_content, cls="modal-body"),
            Div(footer_content or "", cls="modal-footer"),
            cls="modal",
        ),
        cls="modal-overlay",
        id=modal_id,
        role="dialog",
        aria_modal="true",
        aria_label=title,
    )


# ── 表单/统计辅助（原散落各 routes_*.py 的重复实现，统一归位）──

def project_options(selected="", placeholder="— 请选择项目 —", status="进行中"):
    """项目下拉选项。status 可为 '进行中' 或 '进行中 OR 已结题'（受托隔离/特殊收入用）。"""
    from .db import projects_tb
    opts = [Option(placeholder, value="")]
    for p in projects_tb(where=f"status='{status}'"):
        opts.append(Option(f"{p.code} {p.name}", value=p.id, selected=str(p.id) == str(selected)))
    return opts


def org_options(selected=0):
    """法人实体下拉选项（orgs_tb），含 0=未分配。"""
    from .db import orgs_tb
    opts = [Option("— 未分配主体 —", value="0", selected=(str(selected) == "0"))]
    for o in orgs_tb():
        opts.append(Option(f"{o.name}（{o.level}）", value=o.id, selected=str(o.id) == str(selected)))
    return opts


def month_options(selected=""):
    """月份下拉选项（2025-01 到当前月）"""
    opts = [Option("— 请选择月份 —", value="")]
    today = date.today()
    for y in range(2025, today.year + 1):
        for m in range(1, 13):
            if y == today.year and m > today.month:
                break
            val = f"{y}-{m:02d}"
            opts.append(Option(val, value=val, selected=val == selected))
    return opts


def person_options(selected="", placeholder="— 请选择人员 —", show_title=False):
    """研发人员下拉选项。show_title=True 时显示 姓名（职务）。"""
    from .db import personnel_tb
    opts = [Option(placeholder, value="")]
    for p in personnel_tb(where="is_rd=1"):
        text = f"{p.name}（{p.title}）" if show_title else p.name
        opts.append(Option(text, value=p.id, selected=str(p.id) == str(selected)))
    return opts


def stat_block(label: str, value: str, color: str):
    """简化统计块（卡片式）。color 支持 blue/green/orange/red/purple。"""
    color_map = {"blue": "var(--primary)", "green": "var(--success)",
                 "orange": "var(--warning)", "red": "var(--danger)", "purple": "var(--info)"}
    c = color_map.get(color, "var(--primary)")
    return Div(
        Div(label, style="font-size:12px;color:var(--text-muted);margin-bottom:6px;"),
        Div(value, style=f"font-size:22px;font-weight:700;color:{c};"),
        cls="card"
    )
