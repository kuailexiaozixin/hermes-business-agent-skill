// @ts-check
/* =====================================================================
 * app.js — 入口（原生 ES 模块，零构建 / 零运行时依赖）
 * 仅负责装配：导入各模块、绑定事件、启动。所有业务逻辑已拆分到 ./src/*。
 *
 * 契约：SSE 事件形如
 *   {"choices":[{"delta":{"content":".."}}]}   文本增量（OpenAI chunk 形状）
 *   {"type":"reasoning","text":".."}
 *   {"type":"action","tool":"..","preview":".."}
 *   {"type":"action_result","tool":"..","preview":"..","result":{..}}
 *   {"type":"done","conv_id","final","html","approval","title"}
 *   {"type":"cancelled"} / {"error":{"message":".."}}
 * ===================================================================== */
import { $, el, toast } from "./src/dom.js";
import { State, applyTheme, applySkin, toggleTheme, openSkinMenu } from "./src/state.js";
import * as Chat from "./src/chat.js";
import * as Panels from "./src/panels.js";
import * as Views from "./src/views.js";

// 解构常用引用，保持与旧代码调用形式一致
const {
  newConversation, loadConversations, sendMessage, stopStream, loadToolbarSelects,
  initResize, initDropUpload, initSideResize, initSideVResize, updateCmdPop, cmdPopNavigate, cmdPopSelect, updateContextIndicator,
  updateUsageChip, openGlobalSearch, openUnifiedSearch, htmlToMarkdown, convSearchClear, convSearchLive, convSearchJump,
  initVoice, loadHealth, uploadFiles, uploadFolder, renderAttachments, bindConvToolbar,
  cmdHistoryBack, cmdHistoryForward, cmdHistoryClear,
  copyToClipboard, _loadCopyHistory, renameConv, exportConv, archiveConv, delConv,
} = Chat;

function bindEvents() {
  $("#btnNew").addEventListener("click", newConversation);
  const sb = $("#convSearch");
  if (sb) sb.addEventListener("input", () => loadConversations());
  $("#btnSend").addEventListener("click", sendMessage);
  $("#btnStop").addEventListener("click", stopStream);
  $("#btnTheme").addEventListener("click", toggleTheme);
  $("#btnSkin").addEventListener("click", openSkinMenu);
  // 产物按钮：改为客户端渲染到「对话区右上角」（原为左侧栏，改服务端需重启进程；
  // 移到前端后，Agent 编辑前端文件即可经自动重载生效，且契合「对话界面右上方」需求）。
  const _topbar = document.querySelector(".topbar");
  if (_topbar) {
    // 工具调用信息按钮：对话区右上角，点击打开「工具调用信息」抽屉
    let _tc = document.getElementById("btnToolCalls");
    if (!_tc) {
      _tc = el("button", { class: "btn ghost", id: "btnToolCalls",
        title: "工具调用信息（对话过程中的工具调用与参数配置）" });
      _tc.appendChild(document.createTextNode("🔧"));
      _tc.appendChild(el("span", { class: "tc-badge hidden", id: "toolCallsBadge" }));
      const _ab0 = document.getElementById("btnArtifacts");
      if (_ab0) _topbar.insertBefore(_tc, _ab0);
      else _topbar.appendChild(_tc);
    }
    _tc.addEventListener("click", Panels.openToolCalls);
    // 产物按钮
    let _ab = document.getElementById("btnArtifacts");
    if (!_ab) {
      _ab = el("button", { class: "btn icon", id: "btnArtifacts", title: "产物（output/ 列表）" });
      _ab.textContent = "📁";
      const _skin = document.getElementById("btnSkin");
      if (_skin) _topbar.insertBefore(_ab, _skin);
      else _topbar.appendChild(_ab);
    }
    _ab.addEventListener("click", Panels.openArtifacts);
  }
  $("#btnCloseToolCalls").addEventListener("click", Panels.closeToolCalls);
  $("#btnClearToolCalls").addEventListener("click", Panels.clearToolCalls);
  $("#btnConfig").addEventListener("click", Panels.openConfigDialog);
  $("#btnFullExport").addEventListener("click", Panels.fullExport);
  $("#btnAnalytics").addEventListener("click", Panels.openAnalytics);
  $("#btnCloseAnalytics").addEventListener("click", Panels.closeAnalytics);
  $("#analyticsMask").addEventListener("click", (e) => { if (e.target.id === "analyticsMask") Panels.closeAnalytics(); });
  $("#btnCloseArtifacts").addEventListener("click", () => $("#artifactDrawer").classList.add("hidden"));
  $("#btnRefreshArtifacts").addEventListener("click", Panels.openArtifacts);
  $("#modelSelect").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v === "__manage_models__") { Views.showView("models"); e.target.value = State.model_id || ""; return; }
    State.model_id = v || null;
    State.model_label = v || "默认模型";
    const _mc0 = State.model_cache && State.model_cache.items ? State.model_cache.items.find(m => m.id === v) : null;
    State.model = (_mc0 && (_mc0.model || _mc0.id)) || v || null;
    const chip = document.getElementById("modelChip");
    if (chip) chip.textContent = State.model || "未选择";
    toast("🤖 已切换模型: " + (State.model || "默认"), "ok");
  });
  $("#skillSelect").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v === "__manage_skills__") { Views.showView("skills"); e.target.value = State.skill_id || ""; return; }
    const opt = e.target.selectedOptions && e.target.selectedOptions[0];
    State.skill_id = v || null;
    if (opt && opt.dataset && opt.dataset.disabled) toast("该技能已禁用，发送时将被服务端拒绝", "warn");
  });
  loadToolbarSelects();
  initResize();
  initDropUpload();
  initSideResize();
  initSideVResize();
  bindConvToolbar();
  $("#btnDeep").addEventListener("click", () => {
    State.deep_think = !State.deep_think;
    $("#btnDeep").classList.toggle("on", State.deep_think);
    toast("⚡ " + (State.deep_think ? "深度思考（更强推理）" : "常规模式"), "ok");
  });
  $("#btnWeb").addEventListener("click", () => {
    State.web_search = !State.web_search;
    $("#btnWeb").classList.toggle("on", State.web_search);
    toast("🌐 " + (State.web_search ? "已启用联网搜索" : "已禁用联网搜索"), "ok");
  });
  $("#btnUpload").addEventListener("click", () => $("#fileInput").click());
  $("#fileInput").addEventListener("change", (e) => { uploadFiles(e.target.files); e.target.value = ""; });
  $("#btnUploadFolder").addEventListener("click", () => $("#folderInput").click());
  $("#folderInput").addEventListener("change", (e) => { uploadFolder(e.target.files); e.target.value = ""; });
  $("#btnClearAttach").addEventListener("click", () => { State.attachments = []; renderAttachments(); });
  $("#btnUnbindCtx").addEventListener("click", () => Chat.unbindContextFolder());
  // 会话操作按钮组（重命名/导出/归档/删除当前会话）
  const convId = () => State.conv_id;
  $("#btnConvRename").addEventListener("click", () => {
    const t = $("#convTitle") ? $("#convTitle").textContent : "";
    renameConv(convId(), t);
  });
  $("#btnConvExport").addEventListener("click", () => exportConv(convId(), "md"));
  $("#btnConvArchive").addEventListener("click", () => archiveConv(convId(), true));
  $("#btnConvDelete").addEventListener("click", () => delConv(convId()));

  $("#btnConvSearch").addEventListener("click", () => {
    const bar = $("#convSearchBar");
    bar.classList.toggle("hidden");
    if (bar.classList.contains("hidden")) { convSearchClear(); }
    else { const i = $("#convSearchInput"); i.focus(); convSearchLive(i.value); }
  });
  $("#convSearchInput").addEventListener("input", (e) => convSearchLive(e.target.value));
  $("#convSearchInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); convSearchJump(1); }
    else if (e.key === "Escape") { $("#convSearchBar").classList.add("hidden"); convSearchClear(); }
  });
  $("#btnToggleSide").addEventListener("click", () => $("#sidebar").classList.toggle("collapsed"));

  $("#sideNav").addEventListener("click", (e) => {
    const b = e.target.closest(".nav");
    if (b && b.dataset.view) { Views.showView(b.dataset.view); if (b.dataset.view === "chat") loadToolbarSelects(); }
  });
  $("#approvalMask").addEventListener("click", (e) => { if (e.target.id === "approvalMask") e.currentTarget.classList.add("hidden"); });

  const ta = $("#prompt");
  ta.addEventListener("keydown", (e) => {
    const pop = $("#cmdPop");
    const isCmdOpen = pop && !pop.classList.contains("hidden");
    if (isCmdOpen) {
      if (e.key === "ArrowDown") { e.preventDefault(); cmdPopNavigate(1); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); cmdPopNavigate(-1); return; }
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const sel = pop.querySelector(".row.sel"); if (sel) { const idx = parseInt(sel.dataset.idx); if (!isNaN(idx)) cmdPopSelect(idx); } else { cmdPopSelect(0); } return; }
      if (e.key === "Escape") { pop.classList.add("hidden"); pop.innerHTML = ""; return; }
    }
    // Tab 补全：输入 / 开头的部分命令时自动补全
    if (e.key === "Tab") {
      const text = ta.textContent || "";
      if (text.startsWith("/")) {
        e.preventDefault();
        const partial = text.slice(1).toLowerCase();
        if (partial && window.__cmdCompletions) {
          const cmds = window.__cmdCompletions(partial);
          if (cmds.length === 1) {
            ta.textContent = "/" + cmds[0].id + " ";
            const r = document.createRange(); r.selectNodeContents(ta); r.collapse(false);
            const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
          }
        }
      }
      return;
    }
    // 命令历史：↑ 回溯，↓ 前进（仅在 cmdPop 关闭时）
    if (e.key === "ArrowUp" && !e.shiftKey && !isCmdOpen) {
      const text = ta.textContent || "";
      if (!text || text.startsWith("/")) {
        if (cmdHistoryBack(ta)) { e.preventDefault(); return; }
      }
    }
    if (e.key === "ArrowDown" && !e.shiftKey && !isCmdOpen) {
      const text = ta.textContent || "";
      if (text.startsWith("/")) {
        if (cmdHistoryForward(ta)) { e.preventDefault(); return; }
      }
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
// 输入防抖：原实现每敲一个字符都同步发 /api/context/status 请求，输入/粘贴明显卡顿。
let _ctxDebounce = null;
function scheduleContextIndicator() {
  clearTimeout(_ctxDebounce);
  _ctxDebounce = setTimeout(updateContextIndicator, 400);
}
ta.addEventListener("input", () => { updateCmdPop(); scheduleContextIndicator(); });
ta.addEventListener("paste", async (e) => {
  const items = e.clipboardData.items;
  let hasImage = false;
  for (const item of items) {
    if (item.type.startsWith("image/")) {
      e.preventDefault();
      hasImage = true;
      const file = item.getAsFile();
      if (file) await uploadFiles([file]);
      break;
    }
  }
  if (hasImage) return;
  const html = e.clipboardData.getData("text/html");
  if (html) {
    e.preventDefault();
    const md = htmlToMarkdown(html);
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      range.insertNode(document.createTextNode(md));
      range.collapse(false);
    }
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  }
});
  window.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "c" || e.key === "C")) {
      e.preventDefault(); showCopyHistory();
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "f" || e.key === "F")) {
      e.preventDefault(); openUnifiedSearch();
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault(); openGlobalSearch();
    }
  });
}

// 命令补全辅助：给 Tab 键用
function showCopyHistory() {
  const h = _loadCopyHistory();
  if (!h.length) { toast("暂无复制历史", "err"); return; }
  let mask = document.getElementById("copyHistoryMask");
  if (!mask) {
    const list = el("div", { class: "ch-list" });
    const panel = el("div", { class: "ch-panel" }, [
      el("div", { class: "ch-head", text: "复制历史" }),
      el("button", { class: "ch-close", text: "✕", onclick: () => mask.classList.add("hidden") }),
      list,
    ]);
    mask = el("div", { id: "copyHistoryMask", class: "ch-mask hidden" }, [panel]);
    mask.addEventListener("click", (e) => { if (e.target === mask) mask.classList.add("hidden"); });
    document.body.appendChild(mask);
  }
  const list = mask.querySelector(".ch-list");
  list.innerHTML = "";
  for (const item of h) {
    list.appendChild(el("div", { class: "ch-item", onclick: () => {
      copyToClipboard(item.text);
      toast("已重新复制", "ok");
    } }, [
      el("div", { class: "ch-item-text", text: item.text.slice(0, 120) }),
      el("div", { class: "ch-item-time", text: new Date(item.time).toLocaleString() }),
    ]));
  }
  mask.classList.remove("hidden");
}

async function _initCmdCompletions() {
  try {
    const mod = await import("./src/commands.js");
    window.__cmdCompletions = (prefix) => mod.getCompletions(prefix);
  } catch (_) { window.__cmdCompletions = null; }
}

async function init() {
  _initCmdCompletions();
  applyTheme();
  applySkin();
  bindEvents();
  initVoice();
  await Promise.all([loadHealth(), loadConversations(), loadToolbarSelects()]);
  updateContextIndicator();
  updateUsageChip();
  initContextChip();
  $("#prompt").focus();
}

// 上下文水位徽标：轮询 /api/context/status（tips 文档对齐的 token 跟踪），
// 按占用率着色；点击触发主动压缩（/api/context/compress）。全部自包含，
// 不改动 ./src/* 内部逻辑。
function initContextChip() {
  if (!document.getElementById("ctxChipStyle")) {
    const st = document.createElement("style");
    st.id = "ctxChipStyle";
    st.textContent =
      ".ctx-chip{font-variant-numeric:tabular-nums;min-width:54px;text-align:center;opacity:.92}" +
      ".ctx-chip.ok{color:var(--ok)}" +
      ".ctx-chip.warn{color:var(--warn)}" +
      ".ctx-chip.danger{color:var(--danger);font-weight:600}" +
      ".ctx-chip.compress{outline:1px solid var(--danger);outline-offset:1px}" +
      "html[data-theme='dark'] .ctx-chip.ok{color:#51cf66}" +
      "html[data-theme='dark'] .ctx-chip.warn{color:#ffa94d}" +
      "html[data-theme='dark'] .ctx-chip.danger{color:#ff6b6b}";
    document.head.appendChild(st);
  }
  const topbar = document.querySelector(".topbar");
  if (!topbar) return;
  let chip = document.getElementById("ctxChip");
  if (!chip) {
    chip = el("button", { class: "btn ghost ctx-chip", id: "ctxChip",
      title: "上下文水位（token 占用 / 压缩状态）；点击主动压缩" });
    chip.textContent = "🧠 —";
    const skin = document.getElementById("btnSkin");
    if (skin) topbar.insertBefore(chip, skin);
    else topbar.appendChild(chip);
    chip.addEventListener("click", async () => {
      const cid = State.conv_id;
      if (!cid) { toast("请先选择会话", "warn"); return; }
      try {
        const r = await fetch("/api/context/compress", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ conv_id: cid }),
        });
        const j = await r.json();
        if (j.ok) {
          toast(j.compressed ? `已压缩：${j.original_count} → ${j.compressed_count} 条`
                              : (j.reason || "无需压缩"), j.compressed ? "ok" : "warn");
        } else {
          toast("压缩失败：" + (j.error || r.status), "err");
        }
      } catch (e) { toast("压缩请求失败：" + e, "err"); }
    });
  }
  const update = async () => {
    const cid = State.conv_id;
    const chipEl = document.getElementById("ctxChip");
    if (!chipEl) return;
    if (!cid) { chipEl.textContent = "🧠 —"; chipEl.className = "btn ghost ctx-chip"; return; }
    try {
      const r = await fetch("/api/context/status?conv_id=" + encodeURIComponent(cid));
      const j = await r.json();
      if (!j.ok) return;
      const pct = Math.round(j.usage_percent || 0);
      chipEl.textContent = "🧠 " + pct + "%";
      let cls = "btn ghost ctx-chip";
      if (pct >= 85) cls += " danger";
      else if (pct >= 60) cls += " warn";
      else cls += " ok";
      if (j.should_compress) cls += " compress";
      chipEl.className = cls;
      chipEl.title = `上下文水位 ${pct}% / 阈值 ${Math.round((j.threshold_percent || 0) * 100)}% · 引擎 ${j.active_engine || "-"}` +
        (j.should_compress ? " · 建议压缩（点击执行）" : "");
    } catch (_) { /* 轮询失败静默，不影响对话 */ }
  };
  update();
  setInterval(update, 8000);
  // 发消息后稍候刷新（会话可能刚创建/追加）
  const _send = document.getElementById("btnSend");
  if (_send) _send.addEventListener("click", () => setTimeout(update, 2500));
}

document.addEventListener("DOMContentLoaded", init);
