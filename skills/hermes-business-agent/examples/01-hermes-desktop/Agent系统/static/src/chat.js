// @ts-check
/* =====================================================================
 * chat.js — 对话核心：会话 / 历史 / 气泡 / 发送(SSE) / 工具卡 / 消息操作 /
 *           审批 / 附件 / 语音 / 用量 / 上下文 / 指令补全 / 全局搜索 / 尺寸拖拽
 * 本模块自包含：仅依赖叶子模块（dom/state/api/util），不反向依赖视图模块。
 * 导出：所有交互函数供入口 app.js 与面板模块按需调用。
 * ===================================================================== */
import { $, $$, el, esc, toast, postProcessBubble } from "./dom.js";
import { State } from "./state.js";
import { api, getJSON, postJSON, delJSON, parseSSE } from "./api.js";
import { convDateGroup, estimateTokens, formatUsage, toolIcon, extractFilePath, CONTEXT_CAP } from "./util.js";
import { getCompletions, executeCommand, CATEGORIES } from "./commands.js";

// ------------------------------------------------------------------ 健康自检
// ------------------------------------------------------------------ 多会话并行：快照管理
// 每个后台会话的 DOM 节点 + 流式状态保存于此；切换会话时卸载/挂载。
const _chatSnapshots = new Map(); // conv_id -> { nodes: Node[], streaming: boolean, phase: {text, cls} }
let _phaseState = { text: '就绪', cls: '' };

function _snapshotAndDetach() {
  const cid = State.conv_id;
  if (!cid) return;
  const chat = $('#chat');
  const nodes = Array.from(chat.childNodes);
  if (!nodes.length && !State.streaming) return;
  _chatSnapshots.set(cid, { nodes, streaming: State.streaming, phase: { ..._phaseState } });
  for (const n of nodes) chat.removeChild(n);
}

function _restoreSnapshot(cid) {
  const snap = _chatSnapshots.get(cid);
  if (!snap) return false;
  const chat = $('#chat');
  chat.innerHTML = '';
  for (const n of snap.nodes) chat.appendChild(n);
  _chatSnapshots.delete(cid);
  State.streaming = snap.streaming;
  _updateStreamButtons(snap.streaming);
  _phaseState = snap.phase;
  _applyPhaseDOM(snap.phase.text, snap.phase.cls);
  return true;
}

function _updateStreamButtons(streaming) {
  $('#btnSend').classList.toggle('hidden', streaming);
  $('#btnStop').classList.toggle('hidden', !streaming);
}

function _applyPhaseDOM(text, cls) {
  const p = $('#agentPhase'); if (!p) return;
  p.classList.remove('hidden', 'ok', 'err', 'thinking', 'busy', 'warn');
  if (cls) p.classList.add(cls);
  $('#agentPhaseText').textContent = text;
}

async function loadHealth() {
  const chip = $("#healthChip");
  try {
    const info = await getJSON("/healthz");
    const ok = info.importable && info.callbacks_ok;
    let cls = ok ? "ok" : "bad", txt;
    if (ok) txt = "内核就绪";
    else txt = "内核未安装（离线）";
    if (info.model) txt += ` · ${info.model}`;
    chip.className = "health " + cls;
    chip.textContent = txt;
    chip.title = JSON.stringify(info, null, 2);
  } catch (e) {
    chip.className = "health bad";
    chip.textContent = "健康自检失败";
  }
}

// ------------------------------------------------------------------ 会话列表
async function loadConversations(selectId) {
  const list = $("#convList");
  const q = ($("#convSearch") || {}).value || "";
  let data;
  try { data = await getJSON("/api/conversations?q=" + encodeURIComponent(q) + "&include_archived=true"); }
  catch (e) { list.innerHTML = ""; return; }
  const items = (data.items || []).filter((s) => s && s.id);
  State.visibleConvIds = items.map((s) => s.id);
  // 仅保留可见且仍存在的选中项（避免搜索过滤后残留不可见勾选项）
  const visibleSet = new Set(State.visibleConvIds);
  for (const id of [...State.selectedConvs]) if (!visibleSet.has(id)) State.selectedConvs.delete(id);
  list.innerHTML = "";
  if (!items.length) {
    list.appendChild(el("div", { class: "muted", style: "padding:14px;",
      text: q ? "无匹配会话" : "暂无会话" }));
    return;
  }
  // 分组：置顶 → 今天 → 昨天 → 更早（置顶不进日期组）
  const groups = [{ key: "__pin", label: "置顶" }];
  const seen = new Set();
  for (const s of items) {
    const g = s.pinned ? "__pin" : convDateGroup(s.updated_at);
    if (!seen.has(g)) { seen.add(g); groups.push({ key: g, label: g === "__pin" ? "置顶" : g }); }
  }
  let lastGroup = null;
  for (const s of items) {
    const g = s.pinned ? "__pin" : convDateGroup(s.updated_at);
    if (g !== lastGroup) {
      const meta = groups.find((x) => x.key === g);
      list.appendChild(el("div", { class: "conv-group", text: meta ? meta.label : g }));
      lastGroup = g;
    }
    const tagEls = (s.tags && s.tags.length)
      ? [el("div", { class: "conv-tags" }, s.tags.slice(0, 3).map((t) => el("span", { class: "tg", text: "#" + t })))]
      : [];
    const checked = State.selectedConvs.has(s.id);
    const checkAttrs = {
      type: "checkbox", class: "conv-check", "data-id": s.id,
      onclick: (ev) => { ev.stopPropagation(); toggleConvSelect(s.id, ev.target.checked); },
    };
    if (checked) checkAttrs.checked = true;
    const item = el("div", {
      class: "conv-item" + (s.id === State.conv_id ? " active" : "") + (checked ? " selected" : ""),
      onclick: () => openConversation(s.id),
    }, [
      el("input", checkAttrs),
      s.pinned ? el("span", { class: "pin", text: "📌" }) : null,
      el("div", { style: "flex:1 1 auto;min-width:0;" }, [
        el("span", { class: "title", text: (s.archived ? "📦 " : "") + (s.title || "新对话") }),
        ...tagEls,
      ]),
      el("div", { class: "c-actions" }, [
        el("button", { title: "复制", text: "⧉", onclick: (ev) => { ev.stopPropagation(); copyConv(s.id); } }),
        el("button", { title: s.archived ? "取消归档" : "归档", text: s.archived ? "📂" : "📦",
          onclick: (ev) => { ev.stopPropagation(); archiveConv(s.id, !s.archived); } }),
        el("button", { title: "导出", text: "⭳", onclick: (ev) => { ev.stopPropagation(); exportConv(s.id, "md"); } }),
        el("button", { title: "复制内容", text: "📋", onclick: (ev) => { ev.stopPropagation(); copyConvContent(s.id); } }),
        el("button", { title: "置顶", text: s.pinned ? "📌" : "📍",
          onclick: (ev) => { ev.stopPropagation(); pinConv(s.id, !s.pinned); } }),
        el("button", { title: "重命名", text: "✎",
          onclick: (ev) => { ev.stopPropagation(); renameConv(s.id, s.title); } }),
        el("button", { title: "标签", text: "#",
          onclick: (ev) => { ev.stopPropagation(); tagConv(s.id, s); } }),
        el("button", { title: "删除", text: "🗑",
          onclick: (ev) => { ev.stopPropagation(); delConv(s.id); } }),
        el("button", { title: "移动到分组", text: "📁",
          onclick: (ev) => {
            ev.stopPropagation();
            const cur = s.group || "";
            const existing = [...new Set(items.map((x) => x.group).filter(Boolean))];
            const g = prompt("移动到分组（留空=清除分组；现有分组：" + (existing.join("、") || "无") + "）：", cur);
            if (g === null) return;
            postJSON(`/api/conversations/${encodeURIComponent(s.id)}/group`, { group: g.trim() })
              .then((r) => { if (r && r.ok) { toast("已移动到：" + (g.trim() || "（无分组）"), "ok"); loadConversations(); } else toast("移动失败：" + ((r && r.error) || ""), "err"); })
              .catch((e) => toast("移动失败：" + e.message, "err"));
          } }),
      ]),
    ]);
    list.appendChild(item);
  }
  syncConvToolbar();
  if (selectId && items.some((s) => s.id === selectId)) openConversation(selectId, true);
}

async function copyConv(id) {
  const r = await postJSON(`/api/conversations/${encodeURIComponent(id)}/copy`).catch((e) => ({ ok: false, error: e.message }));
  if (r.ok) { toast("已复制会话", "ok"); await loadConversations(); }
  else toast("复制失败：" + (r.error || ""), "err");
}
async function archiveConv(id, archived) {
  await postJSON(`/api/conversations/${encodeURIComponent(id)}/archive`, { archived });
  await loadConversations();
}
async function tagConv(id, s) {
  const cur = (s && s.tags ? s.tags : []).join(", ");
  const v = prompt("设置标签（逗号分隔，如 工作, 研究）：", cur);
  if (v == null) return;
  const tags = v.split(",").map((t) => t.trim()).filter(Boolean);
  await postJSON(`/api/conversations/${encodeURIComponent(id)}/tags`, { tags });
  await loadConversations();
}
async function exportConv(id, fmt) {
  let r;
  try { r = await getJSON(`/api/conversations/${encodeURIComponent(id)}/export?fmt=${fmt}`); }
  catch (e) { toast("导出失败：" + e.message, "err"); return; }
  if (!r.ok) { toast("导出失败：" + (r.error || ""), "err"); return; }
  const blob = new Blob([r.text], { type: fmt === "md" ? "text/markdown" : "application/json" });
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: (r.title || "conversation") + "." + (fmt === "md" ? "md" : "json") });
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  toast("已导出 " + fmt.toUpperCase(), "ok");
}

async function copyConvContent(id) {
  try {
    const r = await getJSON(`/api/conversations/${encodeURIComponent(id)}/export?fmt=md`);
    if (!r.ok) { toast("获取内容失败：" + (r.error || ""), "err"); return; }
    const ok = await copyToClipboard(r.text, true);
    if (ok) toast("已复制会话内容", "ok"); else toast("复制失败", "err");
  } catch (e) { toast("复制失败：" + e.message, "err"); }
}

async function batchExportConvs(fmt) {
  const ids = [...State.selectedConvs];
  if (!ids.length) { toast("请先选择要导出的会话", "err"); return; }
  let exported = 0;
  for (const id of ids) {
    try {
      const r = await getJSON(`/api/conversations/${encodeURIComponent(id)}/export?fmt=${fmt}`);
      if (r.ok) {
        const blob = new Blob([r.text], { type: fmt === "md" ? "text/markdown" : "application/json" });
        const url = URL.createObjectURL(blob);
        const a = el("a", { href: url, download: (r.title || "conversation") + "." + (fmt === "md" ? "md" : "json") });
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
        exported++;
      }
    } catch (_) {}
  }
  toast("已导出 " + exported + " 个会话（共 " + ids.length + " 个）", exported > 0 ? "ok" : "err");
}
function bindImportConv() {
  const btn = $("#btnImportConv"); const inp = $("#importFile");
  if (!btn || !inp) return;
  btn.addEventListener("click", () => inp.click());
  inp.addEventListener("change", async () => {
    const f = inp.files[0]; if (!f) return;
    try {
      const payload = JSON.parse(await f.text());
      const r = await postJSON("/api/conversations/import", { payload }).catch((e) => ({ ok: false, error: e.message }));
      if (r.ok) { toast("已导入会话", "ok"); await loadConversations(r.id); }
      else toast("导入失败：" + (r.error || ""), "err");
    } catch (e) { toast("导入失败：" + e.message, "err"); }
    inp.value = "";
  });
}

// 切回对话视图（不依赖 Views 模块，避免循环依赖）
function _showChatView() {
  State.currentView = 'chat';
  document.querySelectorAll('#sideNav .nav').forEach((b) => b.classList.toggle('active', b.dataset.view === 'chat'));
  const chat = document.getElementById('chat');
  const comp = document.getElementById('composerWrap');
  if (chat) chat.style.display = '';
  if (comp) comp.style.display = '';
  document.querySelectorAll('.app-view').forEach((v) => v.classList.add('hidden'));
}

async function newConversation() {
  _showChatView();
  _snapshotAndDetach();
  State.streaming = false;
  const data = await postJSON("/api/conversations", { title: "" });
  State.conv_id = data.item.id;
  resetUsage();                  // 新会话清空 token 累计
  await loadConversations(State.conv_id);
  resetChat();
  $("#prompt").focus();
}

async function openConversation(id) {
  _showChatView();
  _snapshotAndDetach();
  State.conv_id = id;
  syncConvActions();
  State.streaming = State.activeStreams.has(id);
  _updateStreamButtons(State.streaming);
  if (_restoreSnapshot(id)) {
    try {
      const data = await getJSON("/api/conversations/" + encodeURIComponent(id));
      $("#convTitle").textContent = data.title || "新对话";
      await loadConversations();
      closeSidebarNarrow();
    } catch (e) { toast("打开会话失败：" + e.message, "err"); }
    return;
  }
  try {
    const data = await getJSON("/api/conversations/" + encodeURIComponent(id));
    $("#convTitle").textContent = data.title || "新对话";
    renderHistory(data.messages || []);
    recomputeUsage(data.messages || []);
    await loadConversations();
    closeSidebarNarrow();
  } catch (e) { toast("打开会话失败：" + e.message, "err"); }
}

async function renameConv(id, oldTitle) {
  const name = prompt("重命名会话：", oldTitle || "");
  if (name == null) return;
  await postJSON(`/api/conversations/${encodeURIComponent(id)}/rename`, { title: name });
  await loadConversations();
}
async function pinConv(id, pinned) {
  await postJSON(`/api/conversations/${encodeURIComponent(id)}/pin`, { pinned });
  await loadConversations();
}
async function delConv(id) {
  if (!confirm("确定删除该会话？")) return;
  await delJSON(`/api/conversations/${encodeURIComponent(id)}`);
  if (State.conv_id === id) { State.conv_id = null; resetChat(); }
  await loadConversations();
}

// ── 批量选择 / 全选 / 批量删除 ────────────────────────────────
function toggleConvSelect(id, checked) {
  if (checked) State.selectedConvs.add(id);
  else State.selectedConvs.delete(id);
  syncConvToolbar();
}

async function batchCopyConvs() {
  const ids = [...State.selectedConvs];
  if (!ids.length) { toast("请先选择要复制的会话", "err"); return; }
  let copied = 0;
  for (const id of ids) {
    const r = await postJSON("/api/conversations/" + encodeURIComponent(id) + "/copy").catch(() => ({ ok: false }));
    if (r.ok) copied++;
  }
  toast("已复制 " + copied + " 个会话（共 " + ids.length + " 个）", "ok");
  if (copied > 0) await loadConversations();
}

function selectAllConvs(checked) {
  State.selectedConvs = checked ? new Set(State.visibleConvIds) : new Set();
  for (const cb of $$("#convList .conv-check")) cb.checked = checked;
  syncConvToolbar();
}

function syncConvToolbar() {
  const total = State.visibleConvIds.length;
  const n = State.selectedConvs.size;
  const selAll = $("#convSelectAll");
  const btnDel = $("#btnBatchDelete");
  const btnCopy = $("#btnBatchCopy");
  const btnExport = $("#btnBatchExport");
  if (selAll) {
    selAll.checked = total > 0 && n === total;
    selAll.indeterminate = n > 0 && n < total;
  }
  if (btnDel) {
    btnDel.classList.toggle("hidden", n === 0);
    btnDel.textContent = n > 0 ? `🗑 删除选中 (${n})` : "🗑 删除选中";
  }
  if (btnCopy) {
    btnCopy.classList.toggle("hidden", n === 0);
    btnCopy.textContent = n > 0 ? `⧉ 复制选中 (${n})` : "⧉ 复制选中";
  }
  if (btnExport) {
    btnExport.classList.toggle("hidden", n === 0);
    btnExport.textContent = n > 0 ? `⭳ 导出选中 (${n})` : "⭳ 导出选中";
  }
}

async function batchDelConvs() {
  const ids = [...State.selectedConvs];
  if (!ids.length) return;
  if (!confirm(`确定删除选中的 ${ids.length} 个会话？此操作不可撤销。`)) return;
  const r = await postJSON("/api/conversations/batch-delete", { ids })
    .catch((e) => ({ ok: false, error: e.message }));
  if (!r || !r.ok) { toast("批量删除失败：" + (r && r.error || ""), "err"); return; }
  if (State.conv_id && State.selectedConvs.has(State.conv_id)) { State.conv_id = null; resetChat(); }
  State.selectedConvs = new Set();
  toast(`已删除 ${r.deleted} 个会话`, "ok");
  await loadConversations();
}

function bindConvToolbar() {
  const selAll = $("#convSelectAll");
  const btnDel = $("#btnBatchDelete");
  const btnCopy = $("#btnBatchCopy");
  const btnExport = $("#btnBatchExport");
  if (selAll) selAll.addEventListener("change", () => selectAllConvs(selAll.checked));
  if (btnDel) btnDel.addEventListener("click", batchDelConvs);
  if (btnCopy) btnCopy.addEventListener("click", batchCopyConvs);
  if (btnExport) btnExport.addEventListener("click", () => batchExportConvs("md"));

  // G2.5：对话区就地「立即压缩」（引擎压缩 /api/context/compress，与上下文视图一致）
  const qc = document.getElementById("btnQuickCompress");
  if (qc) {
    qc.addEventListener("click", async () => {
      if (!State.conv_id) { toast("请先选择会话", "err"); return; }
      qc.disabled = true; qc.textContent = "压缩中…";
      const r = await postJSON("/api/context/compress", { conv_id: State.conv_id }).catch(e => ({ ok: false, error: e.message }));
      qc.disabled = false; qc.textContent = "🗜 压缩";
      if (!r.ok) { toast("压缩失败：" + (r.error || ""), "err"); return; }
      if (r.compressed) toast("已压缩：" + r.original_count + " → " + r.compressed_count + " 条", "ok");
      else toast("未压缩：" + (r.reason || ""), "info");
      updateContextIndicator();
      if (State.conv_id) openConversation(State.conv_id);
    });
  }

  // G2：压缩历史上下文按钮（接入已有 /api/conversations/{cid}/compress）
  const ca = document.getElementById("convActions");
  if (ca && !ca.querySelector("#btnConvCompress")) {
    ca.appendChild(el("button", { class: "btn icon", id: "btnConvCompress", title: "压缩历史上下文（节省 token）", text: "🗜", onclick: async () => {
      if (!State.conv_id) { toast("请先选择一个会话", "err"); return; }
      if (!confirm("压缩当前会话的历史上下文？将用摘要替换较早的消息以节省 token，此操作不可撤销。")) return;
      const r = await postJSON(`/api/conversations/${encodeURIComponent(State.conv_id)}/compress`, {}).catch(e => ({ ok: false, error: e.message }));
      if (r && r.ok) {
        const saved = (r.compressed_count ? `（压缩 ${r.compressed_count} 条）` : "");
        toast("已压缩" + saved, "ok");
        if (State.conv_id) openConversation(State.conv_id);
      } else toast("压缩失败：" + ((r && r.error) || ""), "err");
    } }));
  }

  // G4：预览服务状态指示灯 + 停止按钮（轮询 /api/preview）
  const tb = document.querySelector(".topbar");
  if (tb && !document.getElementById("previewStatusBox")) {
    const refreshPreviewStatus = async () => {
      const st = await getJSON("/api/preview").catch(() => null);
      const dot = document.getElementById("previewDot");
      if (!dot) return;
      if (st && st.running) { dot.style.background = "#27c93f"; dot.title = "预览服务运行中：" + (st.url || ""); }
      else { dot.style.background = "#bbb"; dot.title = "预览服务未运行"; }
    };
    const pbox = el("div", { class: "preview-status", id: "previewStatusBox" }, [
      el("span", { class: "preview-dot", id: "previewDot",
        style: "display:inline-block;width:9px;height:9px;border-radius:50%;background:#bbb;margin:0 4px;vertical-align:middle;",
        title: "预览服务未运行" }),
      el("button", { class: "btn ghost sm", id: "btnPreviewStop", text: "停止预览", title: "停止预览服务", onclick: async () => {
        const r = await postJSON("/api/preview/stop", {}).catch(e => ({ ok: false, error: e.message }));
        if (r && r.ok) { toast("预览服务已停止", "ok"); } else toast("停止失败：" + ((r && r.error) || ""), "err");
        refreshPreviewStatus();
      } }),
    ]);
    tb.appendChild(pbox);
    refreshPreviewStatus();
    if (!window.__previewTimer) window.__previewTimer = setInterval(refreshPreviewStatus, 5000);
  }
}

/** 根据当前是否有会话，显隐标题栏「会话操作」按钮组 */
function syncConvActions() {
  const box = document.getElementById("convActions");
  if (!box) return;
  box.classList.toggle("hidden", !State.conv_id);
}

function resetChat() {
  syncConvActions();
  $("#chat").innerHTML = "";
  clearToolCallsPanel(); // 切换/新建对话时同步清空「工具调用信息」面板
  $("#emptyHint") && $("#emptyHint").remove();
  const empty = el("div", { class: "empty", id: "emptyHint" }, [
    el("div", { class: "empty-title", text: "开始一段对话" }),
    el("div", { class: "empty-sub", text: "输入 / 可查看原生指令；工具调用与参数会汇总在右上角「工具调用信息」面板中。" }),
    el("div", { class: "chips", id: "starterChips" }),
  ]);
  $("#chat").appendChild(empty);
  renderStarterChips();
}

function renderStarterChips() {
  const box = $("#starterChips");
  if (!box) return;
  const chips = ["帮我写一个快速排序", "用 Python 读这个目录的文件", "总结当前目录结构", "/HELP"];
  box.innerHTML = "";
  for (const c of chips) {
    box.appendChild(el("div", { class: "chip", text: c,
      onclick: () => { $("#prompt").textContent = c; sendMessage(); } }));
  }
}

// ------------------------------------------------------------------ 历史渲染
function renderHistory(messages) {
  const chat = $("#chat");
  chat.innerHTML = "";
  const empty = $("#emptyHint");
  if (empty) empty.remove();
  for (const m of messages) {
    if (m.role === "user") addUserBubble(m.text);
    else addAssistantBubble(m.html || esc(m.text), false);
  }
  window.__ctxText = (messages || []).map((m) => m.text || m.html || "").join("\n");
  updateContextIndicator();
  scrollChat();
}

function addUserBubble(text) {
  const chat = $("#chat");
  const empty = $("#emptyHint"); if (empty) empty.remove();
  const msg = el("div", { class: "msg user" }, [
    el("div", { class: "avatar", text: "你" }),
    el("div", { class: "bubble", text: text }),
  ]);
  chat.appendChild(msg);
  attachMsgActions(msg, "user");
  scrollChat();
  return msg;
}

function addAssistantBubble(html, live) {
  const chat = $("#chat");
  const empty = $("#emptyHint"); if (empty) empty.remove();
  const bubble = el("div", { class: "bubble" });
  if (html) bubble.innerHTML = html;
  const msg = el("div", { class: "msg assistant" }, [
    el("div", { class: "avatar", text: "H" }),
    bubble,
  ]);
  chat.appendChild(msg);
  postProcessBubble(bubble);
  attachMsgActions(msg, "assistant");
  scrollChat();
  return { msg, bubble };
}

function scrollChat() {
  const chat = $("#chat");
  chat.scrollTop = chat.scrollHeight;
}

// ------------------------------------------------------------------ 阶段状态条
function setPhase(text, cls, convId) {
  _phaseState = { text, cls };
  if (convId && convId !== State.conv_id) return;
  _applyPhaseDOM(text, cls);
}
function hidePhase(convId) {
  _phaseState = { text: "", cls: "hidden" };
  if (convId && convId !== State.conv_id) return;
  const p = $("#agentPhase"); if (p) p.classList.add("hidden");
}

// ------------------------------------------------------------------ 高级搜索语法解析
// 支持：AND / OR / NOT / "精确匹配" / -排除
function parseSearchQuery(q) {
  const tokens = [];
  let i = 0, s = q.trim();
  while (i < s.length) {
    if (s[i] === " ") { i++; continue; }
    if (s[i] === "-" && i + 1 < s.length && s[i + 1] !== " ") {
      // 排除词
      let j = i + 1;
      while (j < s.length && s[j] !== " ") j++;
      tokens.push({ type: "not", val: s.slice(i + 1, j).toLowerCase() });
      i = j;
    } else if (s[i] === '"' || s[i] === "“") {
      // 精确匹配（支持英文引号 " 和中文引号 "）
      const close = s[i] === '"' ? '"' : "”";
      let j = i + 1;
      while (j < s.length && s[j] !== close) j++;
      tokens.push({ type: "exact", val: s.slice(i + 1, j).toLowerCase() });
      i = j + 1;
    } else {
      let j = i;
      while (j < s.length && s[j] !== " " && s[j] !== "-" && s[j] !== '"' && s[j] !== "“") j++;
      tokens.push({ type: "word", val: s.slice(i, j).toLowerCase() });
      i = j;
    }
  }
  // 检查是否有 AND/OR 操作符
  const hasOr = tokens.some(t => t.type === "word" && (t.val === "or" || t.val === "||"));
  const hasAnd = tokens.some(t => t.type === "word" && (t.val === "and" || t.val === "&&"));
  const hasNot = tokens.some(t => t.type === "not");
  const keywords = tokens.filter(t => t.type !== "word" || (t.val !== "or" && t.val !== "||" && t.val !== "and" && t.val !== "&&"));
  const orMode = hasOr;
  return function(text) {
    const lower = (text || "").toLowerCase();
    const matches = keywords.filter(t => {
      if (t.type === "not") return !lower.includes(t.val);
      if (t.type === "exact") return lower.includes(t.val);
      if (t.type === "word") {
        if (t.val === "or" || t.val === "||" || t.val === "and" || t.val === "&&") return true;
        return lower.includes(t.val);
      }
      return true;
    });
    if (orMode) return matches.length === keywords.length || keywords.some(k => k.type === "not" ? false : lower.includes(k.val));
    return matches.length === keywords.length;
  };
}

// ------------------------------------------------------------------ 对话内搜索
let _convSearch = { q: "", matches: [], idx: -1 };
function convSearchClear() {
  document.querySelectorAll("#chat mark.hl").forEach((m) => {
    const t = m.parentNode;
    t.replaceChild(document.createTextNode(m.textContent), m);
    t.normalize();
  });
  _convSearch.matches = []; _convSearch.idx = -1;
  const c = $("#convSearchCount"); if (c) c.textContent = "";
}
function convSearchLive(v) {
  convSearchClear();
  const q = (v || "").trim().toLowerCase();
  if (!q) return;
  const walker = document.createTreeWalker($("#chat"), NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (n.textContent && n.textContent.toLowerCase().includes(q)) nodes.push(n);
  }
  for (const n of nodes) {
    const lower = n.textContent.toLowerCase();
    const at = lower.indexOf(q);
    if (at === -1) continue;
    const span = document.createElement("mark"); span.className = "hl";
    span.textContent = n.textContent.substring(at, at + q.length);
    const head = document.createTextNode(n.textContent.substring(0, at));
    const tail = document.createTextNode(n.textContent.substring(at + q.length));
    n.parentNode.replaceChild(span, n);
    n.parentNode.insertBefore(head, span);
    n.parentNode.insertBefore(tail, span.nextSibling);
  }
  _convSearch.matches = Array.from(document.querySelectorAll("#chat mark.hl"));
  _convSearch.idx = _convSearch.matches.length ? 0 : -1;
  const c = $("#convSearchCount");
  if (c) c.textContent = _convSearch.matches.length ? `1/${_convSearch.matches.length}` : "无匹配";
  convSearchJump(0, true);
}

// ------------------------------------------------------------------ 附件上传
async function uploadFiles(files) {
  if (!files || !files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const r = await fetch("/api/upload", { method: "POST", body: fd })
    .then((res) => res.json()).catch(() => ({ ok: false }));
  if (!r.ok || !r.attachments) { toast("上传失败", "err"); return; }
  State.attachments = State.attachments.concat(r.attachments);
  renderAttachments();
  toast(`已上传 ${r.attachments.length} 个附件`, "ok");
}
function renderAttachments() {
  const area = $("#attachmentsArea");
  const list = $("#attachmentsList");
  const chip = $("#attachChip");
  if (!State.attachments || !State.attachments.length) {
    area.classList.add("hidden");
    if (chip) chip.classList.add("hidden");
    return;
  }
  area.classList.remove("hidden");
  list.innerHTML = "";
  for (const a of State.attachments) {
    list.appendChild(el("span", { class: "attach-item", title: a.path },
      el("span", { text: "📎 " + a.name + " (" + (a.size || 0) + "B)" })));
  }
  if (chip) { chip.textContent = `📎 ${State.attachments.length}`; chip.classList.remove("hidden"); }
}

// ------------------------------------------------------------------ 输入框高度拖拽
function initResize() {
  const handle = $("#resizeHandle");
  const ta = $("#prompt");
  if (!handle || !ta) return;
  try { const s = localStorage.getItem("lx_input_h"); if (s) ta.style.height = s + "px"; } catch (e) {}
  let startY = 0, startH = 0, dragging = false;
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault(); dragging = true; startY = e.clientY; startH = ta.offsetHeight;
    handle.classList.add("active"); document.body.style.userSelect = "none";
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const h = Math.min(500, Math.max(60, startH + (startY - e.clientY)));
    ta.style.height = h + "px";
  });
  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false; handle.classList.remove("active"); document.body.style.userSelect = "";
    try { localStorage.setItem("lx_input_h", String(ta.offsetHeight)); } catch (e) {}
  });
}

// ------------------------------------------------------------------ 侧栏宽度拖拽
function initSideResize() {
  const handle = $("#sideResize");
  const sb = $("#sidebar");
  if (!handle || !sb) return;
  try { const s = localStorage.getItem("lx_sbw"); if (s) sb.style.setProperty("--sbw", s + "px"); } catch (e) {}
  let startX = 0, startW = 0, dragging = false;
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault(); dragging = true; startX = e.clientX; startW = sb.offsetWidth;
    handle.classList.add("active"); document.body.style.userSelect = "none";
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const w = Math.min(380, Math.max(190, startW + (e.clientX - startX)));
    sb.style.setProperty("--sbw", w + "px");
  });
  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false; handle.classList.remove("active"); document.body.style.userSelect = "";
    try { localStorage.setItem("lx_sbw", String(sb.offsetWidth)); } catch (e) {}
  });
}

// ------------------------------------------------------------------ 拖拽文件上传
function initDropUpload() {
  const wrap = $("#composerWrap");
  if (!wrap) return;
  wrap.addEventListener("dragover", (e) => { e.preventDefault(); wrap.classList.add("drag-over"); });
  wrap.addEventListener("dragleave", () => wrap.classList.remove("drag-over"));
  wrap.addEventListener("drop", (e) => {
    e.preventDefault(); wrap.classList.remove("drag-over");
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) uploadFiles(files);
  });
}

function convSearchJump(dir, noAdvance) {
  if (!_convSearch.matches.length) return;
  if (!noAdvance) _convSearch.idx += (dir || 1);
  if (_convSearch.idx >= _convSearch.matches.length) _convSearch.idx = 0;
  if (_convSearch.idx < 0) _convSearch.idx = _convSearch.matches.length - 1;
  _convSearch.matches.forEach((x, i) => x.classList.toggle("current", i === _convSearch.idx));
  const m = _convSearch.matches[_convSearch.idx];
  m.scrollIntoView({ block: "center" });
  const c = $("#convSearchCount");
  if (c) c.textContent = `${_convSearch.idx + 1}/${_convSearch.matches.length}`;
}

// A2：跨会话全文检索（Ctrl+K 全局搜索）
let _gsTimer = null;
let _gsIdx = -1;
// 搜索历史（localStorage 持久化，最多 10 条）
function _gsLoadHistory() { try { return JSON.parse(localStorage.getItem("_gsHistory") || "[]"); } catch { return []; } }
function _gsSaveHistory(q) { if (!q) return; const h = _gsLoadHistory().filter(x => x !== q); h.unshift(q); if (h.length > 10) h.length = 10; try { localStorage.setItem("_gsHistory", JSON.stringify(h)); } catch {} }
function openGlobalSearch() {
  let mask = $("#globalSearchMask");
  if (!mask) {
    const input = el("input", { id: "gsInput", class: "gs-input", type: "text",
      placeholder: "跨所有会话搜索消息内容…（Ctrl+K）" });
    const suggestions = el("div", { class: "gs-suggestions hidden" });
    function showSuggestions() {
      const h = _gsLoadHistory();
      suggestions.innerHTML = "";
      if (!h.length || input.value.trim()) { suggestions.classList.add("hidden"); return; }
      suggestions.classList.remove("hidden");
      suggestions.appendChild(el("div", { class: "gs-sug-head", text: "最近搜索" }));
      for (const q of h) {
        suggestions.appendChild(el("div", { class: "gs-sug-item", text: q, onclick: () => {
          input.value = q;
          suggestions.classList.add("hidden");
          run();
        } }));
      }
    }
    input.addEventListener("focus", showSuggestions);
    input.addEventListener("blur", () => setTimeout(() => suggestions.classList.add("hidden"), 200));
    const results = el("div", { id: "gsResults", class: "gs-results" });
    const panel = el("div", { class: "gs-panel" }, [
      el("div", { class: "gs-head" }, [
        el("span", { text: "🔍 跨会话搜索" }),
        el("button", { class: "gs-close", text: "✕", onclick: () => mask.classList.add("hidden") }),
      ]),
      input, suggestions, results,
    ]);
    mask = el("div", { id: "globalSearchMask", class: "gs-mask hidden" }, [panel]);
    mask.addEventListener("click", (e) => { if (e.target === mask) mask.classList.add("hidden"); });
    document.body.appendChild(mask);

    const run = () => {
      const q = input.value.trim();
      if (!q) { results.innerHTML = ''; _gsIdx = -1; return; }
      _gsSaveHistory(q);
      getJSON("/api/conversations/search?q=" + encodeURIComponent(q))
        .then((d) => {
          const items = (d && d.items) || [];
          results.innerHTML = "";
          if (!items.length) {
            results.appendChild(el("div", { class: "gs-empty muted", text: "无匹配会话" }));
            return;
          }
          _gsIdx = 0;
          for (const it of items) {
            const row = el("div", { class: "gs-item" + (_gsIdx === 0 ? " sel" : ""), onclick: () => {
              mask.classList.add("hidden");
              const qq = input.value.trim();
              openConversation(it.id).then(() => { if (qq) convSearchLive(qq); });
            } }, [
              el("div", { class: "gs-title" }, [
                el("span", { text: (it.archived ? "📦 " : "") + (it.title || "新对话") }),
                el("span", { class: "gs-badge", text: it.matches + " 处" }),
              ]),
              el("div", { class: "gs-snippet", text: it.snippet || "" }),
            ]);
            results.appendChild(row);
            _gsIdx++;
          }
          _gsIdx = 0;
        })
        .catch(() => { results.innerHTML = ""; });
    };
    input.addEventListener("input", () => { clearTimeout(_gsTimer); _gsTimer = setTimeout(run, 200); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { mask.classList.add("hidden"); return; }
      const items = results.querySelectorAll(".gs-item");
      if (!items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (_gsIdx < items.length - 1) _gsIdx++;
        items.forEach((x, i) => x.classList.toggle("sel", i === _gsIdx));
        items[_gsIdx].scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (_gsIdx > 0) _gsIdx--;
        items.forEach((x, i) => x.classList.toggle("sel", i === _gsIdx));
        items[_gsIdx].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (_gsIdx >= 0 && _gsIdx < items.length) items[_gsIdx].click();
      }
    });
  }
  mask.classList.remove("hidden");
}

// A3：统一搜索入口（Ctrl+Shift+F 跨所有内容源搜索）
let _usTimer = null;
function openUnifiedSearch() {
  let mask = $("#unifiedSearchMask");
  if (!mask) {
    const input = el("input", { id: "usInput", class: "gs-input", type: "text",
      placeholder: "跨所有内容搜索（会话/Wiki/记忆/看板/定时任务）…（Ctrl+Shift+F）" });
    const results = el("div", { id: "usResults", class: "us-results" });
    const panel = el("div", { class: "gs-panel us-panel" }, [
      el("div", { class: "gs-head" }, [
        el("span", { text: "🔍 统一搜索" }),
        el("button", { class: "gs-close", text: "✕", onclick: () => mask.classList.add("hidden") }),
      ]),
      input, results,
    ]);
    mask = el("div", { id: "unifiedSearchMask", class: "gs-mask hidden" }, [panel]);
    mask.addEventListener("click", (e) => { if (e.target === mask) mask.classList.add("hidden"); });
    document.body.appendChild(mask);

    const run = () => {
      const q = input.value.trim();
      if (!q) { results.innerHTML = ""; return; }
      results.innerHTML = el("div", { class: "gs-empty muted", text: "搜索中…" }).outerHTML;
      getJSON("/api/search/all?q=" + encodeURIComponent(q))
        .then((d) => {
          const src = (d && d.ok && d.sources) || {};
          results.innerHTML = "";
          let hasAny = false;
          const order = ["conversations", "wiki", "memory", "kanban", "cron"];
          const labels = { conversations: "会话", wiki: "Wiki 知识库", memory: "记忆", kanban: "看板", cron: "定时任务" };
          const icons = { conversations: "💬", wiki: "📖", memory: "🧠", kanban: "📋", cron: "⏰" };
          for (const key of order) {
            const items = src[key] || [];
            if (!items.length) continue;
            hasAny = true;
            const sec = el("div", { class: "us-section" });
            sec.appendChild(el("div", { class: "us-section-title" }, [
              el("span", { text: (icons[key] || "") + " " + (labels[key] || key) }),
              el("span", { class: "badge", text: items.length + " 条" }),
            ]));
            for (const it of items) {
              sec.appendChild(el("div", { class: "us-item" }, [
                el("div", { class: "us-item-title", text: it.title || it.name || "" }),
                it.snippet ? el("div", { class: "us-item-snippet", text: it.snippet }) : null,
                it.schedule ? el("div", { class: "us-item-meta", text: "⏰ " + it.schedule }) : null,
              ]));
            }
            results.appendChild(sec);
          }
          if (!hasAny) {
            results.appendChild(el("div", { class: "gs-empty muted", text: "无匹配内容" }));
          }
        })
        .catch(() => { results.innerHTML = el("div", { class: "gs-empty muted", text: "搜索失败" }).outerHTML; });
    };
    input.addEventListener("input", () => { clearTimeout(_usTimer); _usTimer = setTimeout(run, 300); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") mask.classList.add("hidden");
    });
  }
  mask.classList.remove("hidden");
  setTimeout(() => $("#usInput").focus(), 100);
}

// ------------------------------------------------------------------ 发送 / SSE
function setStreaming(on) {
  State.streaming = on;
  $("#btnSend").classList.toggle("hidden", on);
  $("#btnStop").classList.toggle("hidden", !on);
}

// 工具调用信息面板：全局登记当前对话的所有 turn，便于清空时重置 FIFO 队列；
// 每张工具卡渲染进 #toolCallsList（而非对话区时间线）。
const ConvTurns = [];
let _toolCallCount = 0;

function buildTurn() {
  const chat = $("#chat");
  const empty = $("#emptyHint"); if (empty) empty.remove();
  const turn = (function () {
  const thinking = el("details", { class: "thinking" }, [
    el("summary", {}, [el("span", { text: "🧠 思考过程" })]),
    el("div", { class: "body" }),
  ]);
  const moa = el("details", { class: "moa-refs" }, [
    el("summary", {}, [el("span", { text: "🔄 MOA 参考模型" })]),
    el("div", { class: "body" }),
  ]);
  const timeline = el("div", { class: "timeline" });
  const bubble = el("div", { class: "bubble" });
  const live = el("span", {});
  bubble.appendChild(live);
  const msg = el("div", { class: "msg assistant" }, [
    el("div", { class: "avatar", text: "H" }),
    el("div", { style: "flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:8px;" }, [
      thinking, moa, timeline, bubble,
    ]),
  ]);
  chat.appendChild(msg);
  return { thinking, thinkingBody: thinking.querySelector(".body"),
           moa, moaBody: moa.querySelector(".body"),
           timeline, bubble, live, msg };
  })();
  ConvTurns.push(turn);
  return turn;
}

// C1：每个「工具调用实例」一张独立卡（同名工具多次调用各自成卡，互不覆盖）。
// 后端 action/action_result 事件不带调用 id，故按「每工具 FIFO 等待队列」匹配。
function openToolCard(turn, tool, preview) {
  turn._toolSeq = turn._toolSeq || {};
  const seq = (turn._toolSeq[tool] = (turn._toolSeq[tool] || 0) + 1);
  const label = seq > 1 ? ` ${seq}` : "";
  const head = el("div", { class: "t-head" }, [
    el("div", { class: "t-ico", text: toolIcon(tool) }),
    el("div", { class: "t-name", text: tool + label }),
    el("div", { class: "t-state run", text: "运行中…" }),
  ]);
  // A3：参数（调用输入）与结果分区，各自独立；结果区用 <pre> 保留格式且不注入 HTML
  const args = el("div", { class: "t-args", text: preview || "" });
  const result = el("pre", { class: "t-result-body" });
  const card = el("div", { class: "tool-card", onclick: () => card.classList.toggle("open") }, [
    head,
    el("div", { class: "t-sec" }, [el("div", { class: "t-label", text: "参数" }), args]),
    el("div", { class: "t-sec" }, [el("div", { class: "t-label", text: "结果" }), result]),
  ]);
  // 工具卡写入「工具调用信息」面板（#toolCallsList），不再内联进对话区时间线
  const list = document.getElementById("toolCallsList");
  if (list) list.appendChild(card);
  else turn.timeline.appendChild(card); // 兜底：面板缺失时退回时间线，避免丢失
  _toolCallCount += 1;
  updateToolCallsBadge();
  updateToolCallsEmpty();
  const ref = { tool, head, args, result, state: head.querySelector(".t-state"), card, previewBtn: null, previewBox: null };
  turn._cardRefs = turn._cardRefs || [];
  turn._cardRefs.push(ref);
  turn._pendingByTool = turn._pendingByTool || {};
  (turn._pendingByTool[tool] = turn._pendingByTool[tool] || []).push(ref);
  return ref;
}

// 工具调用信息面板：更新右上角按钮的计数徽标
function updateToolCallsBadge() {
  const badge = document.getElementById("toolCallsBadge");
  if (!badge) return;
  badge.textContent = _toolCallCount > 0 ? String(_toolCallCount) : "";
  badge.classList.toggle("hidden", _toolCallCount === 0);
}

// 工具调用信息面板：无记录时显示空提示
export function updateToolCallsEmpty() {
  const list = document.getElementById("toolCallsList");
  const empty = document.getElementById("toolCallsEmpty");
  if (empty) empty.classList.toggle("hidden", !!(list && list.children.length));
}

// 工具调用信息面板：清空本对话的全部工具卡与计数，并重置各 turn 的 FIFO 队列，
// 避免后续结果事件错配到已被移除的卡片。
export function clearToolCallsPanel() {
  const list = document.getElementById("toolCallsList");
  if (list) list.innerHTML = "";
  ConvTurns.forEach((t) => { t._pendingByTool = {}; t._cardRefs = []; t._toolSeq = {}; });
  _toolCallCount = 0;
  updateToolCallsBadge();
  updateToolCallsEmpty();
}

// C1：匹配该工具最早尚未完成的实例（FIFO）；无对应 action 时兜底新建，避免结果丢失。
function closeToolCard(turn, tool) {
  const q = turn._pendingByTool && turn._pendingByTool[tool];
  let ref = q && q.shift();
  if (!ref) ref = openToolCard(turn, tool, "");
  return ref;
}

// 子目录上下文渐进发现：低调、非侵入、防 HTML 注入的信息陈列。
// 仅把发现的相对路径以 muted 文本追加到消息容器（done 事件只替换 turn.bubble.innerHTML，
// 该节点是 turn.msg 的兄弟，故不会被覆盖）。同一路径在本轮去重。
function showContextHint(turn, rel, tool) {
  if (!turn || !turn.msg) return;
  turn._ctxHints = turn._ctxHints || new Set();
  if (turn._ctxHints.has(rel)) return;
  turn._ctxHints.add(rel);
  const note = el("div", { class: "ctx-hint muted",
    text: "🔍 在 " + rel + " 发现子目录上下文提示（已并入工具结果，供本轮参考）" });
  turn.msg.appendChild(note);
}

// A4：从工具结果里抽取可预览的文件路径（优先 dict.path，其次字符串里的绝对/盘符路径）
// （实现见 util.extractFilePath；此处保留透明调用）

// A4：工具结果含文件路径时，挂一个「预览」按钮；点击在沙箱化容器里渲染
function attachFilePreview(turn, ref, res) {
  if (ref.previewBtn) return;          // 已挂过，避免重复
  const fp = extractFilePath(res);
  if (!fp) return;
  const btn = el("button", { class: "t-preview-btn", text: "📄 预览文件" });
  btn.addEventListener("click", async () => {
    if (ref.previewBox) { ref.previewBox.classList.toggle("hidden"); return; }
    const box = el("div", { class: "t-preview-box hidden" });
    ref.previewBox = box;
    ref.card.appendChild(box);
    box.classList.remove("hidden");
    box.textContent = "加载中…";
    try {
      const d = await getJSON("/api/file/preview?path=" + encodeURIComponent(fp));
      if (!d || !d.ok) { box.textContent = "无法预览：" + ((d && d.error) || "未知"); return; }
      box.textContent = "";
      if (d.type === "image") {
        const img = el("img"); img.src = d.data_url; box.appendChild(img);
      } else if (d.type === "pdf") {
        const f = el("iframe"); f.src = d.data_url; box.appendChild(f);
      } else if (d.type === "html") {
        // 沙箱化：sandbox="" 禁用脚本/表单/同源，内容无法逃逸或执行
        const f = el("iframe", { sandbox: "", srcdoc: d.text });
        box.appendChild(f);
      } else {  // text
        const pre = el("pre"); pre.textContent = d.text; box.appendChild(pre);
      }
    } catch (e) { box.textContent = "预览失败：" + e.message; }
  });
  ref.previewBtn = btn;
  ref.card.appendChild(btn);
}

async function sendMessage() {
  if (State.streaming) return;
  const myConvId = State.conv_id || "";
  const ta = $("#prompt");
  const text = (ta.textContent || "").trim();
  if (!text) return;

  // 斜杠命令：优先走 CommandRegistry（前端本地命令），再走后端原生指令
  if (text.startsWith("/")) {
    // 先尝试 CommandRegistry
    const result = await executeCommand(text);
    if (result !== null) {
      addUserBubble(text);
      // 记录命令历史
      _cmdHistory.push(text);
      if (_cmdHistory.length > 50) _cmdHistory.shift();
      _cmdHistoryIdx = _cmdHistory.length;
      _cmdHistoryTemp = "";
      ta.textContent = "";
      const pop = document.getElementById("cmdPop");
      if (pop) { pop.classList.add("hidden"); pop.innerHTML = ""; }
      // 有结果文本时显示气泡，无结果文本时仅 Toast（如 /help 模态框）
      if (result) {
        addAssistantBubble(`<pre>${esc(result)}</pre>`, false);
      }
      return;
    }
    // 再尝试后端原生指令
    try {
      const r = await postJSON("/api/command", { text });
      if (r.ok && r.name) {
        addUserBubble(text);
        // 记录命令历史
        _cmdHistory.push(text);
        if (_cmdHistory.length > 50) _cmdHistory.shift();
        _cmdHistoryIdx = _cmdHistory.length;
        _cmdHistoryTemp = "";
        const out = r.result && typeof r.result === "object"
          ? JSON.stringify(r.result, null, 2) : String(r.result || "");
        addAssistantBubble(`<pre>${esc(out)}</pre>`, false);
        ta.textContent = "";
        toast("⚡ 已执行后端指令: " + r.name, "ok");
        return;
      }
    } catch (e) { /* 落到普通对话 */ }
    // 未知命令 — 提示帮助
    addUserBubble(text);
    // 记录命令历史（即使是未知命令）
    _cmdHistory.push(text);
    if (_cmdHistory.length > 50) _cmdHistory.shift();
    _cmdHistoryIdx = _cmdHistory.length;
    _cmdHistoryTemp = "";
    ta.textContent = "";
    const pop = document.getElementById("cmdPop");
    if (pop) { pop.classList.add("hidden"); pop.innerHTML = ""; }
    toast("❓ 未知命令，输入 /help 查看可用命令", "warn");
    addAssistantBubble(`<pre>${esc("未知命令。输入 /help 查看可用命令列表。")}</pre>`, false);
    return;
  }

  // —— 非斜杠消息：发往后端并消费 SSE 流 ——
  addUserBubble(text);
  addUsage(text, true);            // 累计输入 token（估算）
  ta.textContent = "";
  setStreaming(true);
  State.activeStreams.set(myConvId, true);
  setPhase("正在处理…", "busy");

  if (!State.conv_id) {
    // 让后端新建会话（conv_id 留空，done 后从 meta 拿）
    State.conv_id = "";
  }

  const turn = buildTurn();
  turn.live.textContent = "…";

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        conv_id: State.conv_id,
        model_id: State.model_id,
        deep_think: State.deep_think,
        web_search: State.web_search,
        attachments: State.attachments,
        skill_id: State.skill_id || null,
        replace_index: State.replace_index != null ? State.replace_index : undefined,
      }),
    });
    // 附件随本轮提交后清空
    if (State.attachments && State.attachments.length) { State.attachments = []; renderAttachments(); }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      // D1：标准 SSE 累积器——按 \n\n 切分事件，事件内按 field:value 解析
      const { events, rest } = parseSSE(buf);
      buf = rest;
      for (const obj of events) {
        handleEvent(obj, turn, (v) => { turn.live.textContent = v; }, myConvId);
      }
    }
    if (!turn._hasEvent && !turn.thinkingBody.textContent) {
      turn.live.textContent = "（无输出）";
    }
  } catch (e) {
    turn.live.textContent = "";
    turn.bubble.appendChild(el("div", { class: "muted", text: "⚠ " + e.message }));
    toast("对话出错：" + e.message, "err");
  } finally {
    State.replace_index = null;
    State.activeStreams.delete(myConvId);
    // 修复按钮卡「停止」：新会话首轮 myConvId=""，done 事件已把 State.conv_id 更新为新值，
    // 旧判断 State.conv_id === myConvId 永不成立 → setStreaming(false) 被跳过，按钮残留「停止」。
    // 改为：本轮流已结束且无其他活跃流时无条件复位发送按钮。
    if (!myConvId || State.conv_id === myConvId || State.activeStreams.size === 0) {
      setStreaming(false);
    }
    await loadConversations(State.conv_id || undefined);
  }
}

function handleEvent(obj, turn, appendDelta, myConvId) {
  const visible = (myConvId === undefined || myConvId === "" || myConvId === State.conv_id);
  if (obj.type === "meta") {
    if (obj.conv_id) {
      if (visible) State.conv_id = obj.conv_id;
    }
    if (obj.model && visible) State.model = obj.model;
    return;
  }
  turn._hasEvent = true;   // C2：任何「内容」事件都算有产出；仅 meta 不算
  if (obj.choices && obj.choices[0] && obj.choices[0].delta && obj.choices[0].delta.content != null) {
    setPhase("生成中…", "busy", myConvId);
    appendDelta(obj.choices[0].delta.content);
    addUsage(obj.choices[0].delta.content, false);   // 累计输出 token（估算）
    return;
  }
  if (obj.type === "reasoning") {
    setPhase("思考中…", "thinking", myConvId);
    turn.thinking.style.display = "";
    turn.thinkingBody.textContent += obj.text || "";
    return;
  }
  if (obj.type === "action") {
    setPhase("执行工具：" + (obj.tool || ""), "busy", myConvId);
    const ref = openToolCard(turn, obj.tool, obj.preview);
    ref.state.className = "t-state run";
    ref.state.textContent = "运行中…";
    if (obj.preview) ref.args.textContent = obj.preview;   // A3：参数区 = 调用输入
    return;
  }
  if (obj.type === "action_result") {
    const ref = closeToolCard(turn, obj.tool);
    ref.state.className = "t-state ok";
    ref.state.textContent = "完成";
    const res = obj.result;
    if (res != null) {
      let txt;
      if (typeof res === "string") txt = res;
      else { try { txt = JSON.stringify(res, null, 2); } catch (_) { txt = String(res); } }
      ref.result.textContent = txt;   // A3：结果区纯文本，保留格式且无 HTML 注入风险
    }
    attachFilePreview(turn, ref, res);   // A4：结果含文件路径时挂「预览」按钮
    return;
  }
  if (obj.type === "tool_progress") {
    // MoA 参考模型事件（agent_init._moa_reference_relay → tool_progress_callback → SSE）
    const name = obj.name;
    const args = obj.args || [];
    if (name === "moa.reference") {
      const label = args[0] || "参考模型";
      const text = args[1] || "";
      const block = el("div", { class: "moa-ref" }, [
        el("div", { class: "moa-ref-label", text: "· " + label }),
        el("div", { class: "moa-ref-text", text: text }),
      ]);
      turn.moaBody.appendChild(block);
      turn.moa.open = true;
      setPhase("MOA 参考模型作答中…", "thinking", myConvId);
    } else if (name === "moa.aggregating") {
      const agg = args[0] || "聚合模型";
      turn.moaBody.appendChild(el("div", { class: "moa-agg", text: "⏳ " + agg + " 正在综合最终回答…" }));
      turn.moa.open = true;
      setPhase("MOA 聚合模型综合中…", "busy", myConvId);
    }
    return;
  }
  if (obj.type === "context_hint") {
    // 子目录上下文渐进发现提示：纯信息陈列，不改动注入、防 HTML 注入（用 text 而非 innerHTML）
    const raw = obj.hint || "";
    const m = raw.match(/\[Subdirectory context discovered:\s*([^\]]+)\]/);
    const rel = m ? m[1].trim() : "(未知位置)";
    showContextHint(turn, rel, obj.tool);
    return;
  }
  if (obj.type === "cancelled") {
    setPhase("已停止", "warn", myConvId);
    turn.live.textContent += "\n（已停止）";
    toast("已停止生成本轮", "ok");
    return;
  }
  if (obj.type === "done") {
    if (turn._errored) return;   // D2：错误路径下的 done 直接忽略
    setPhase("完成", "ok", myConvId); setTimeout(() => hidePhase(myConvId), 1200);
    if (obj.html) {
      turn.bubble.innerHTML = obj.html; postProcessBubble(turn.bubble);
    } else if (obj.final != null) {
      // C3：无 html 时保留流式累积文本（已是最终内容）
      turn.live.textContent = obj.final;
    }
    if (obj.title && visible) $("#convTitle").textContent = obj.title;
    if (obj.conv_id && visible) State.conv_id = obj.conv_id;
    if (obj.approval) showApproval(obj.approval);
    attachMsgActions(turn.msg, "assistant");
    window.__ctxText = (window.__ctxText || "") + "\n" + (obj.final || "");
    updateContextIndicator();
    scrollChat();
    // 破除「AI 声称改成功但界面无变化」：本轮 Agent 若改了文件，按类型转成可见动作
    if (obj.changed_files && obj.changed_files.length) {
      applyChangedFiles(obj.changed_files);
    }
    if (obj.conv_id && State.usage) {
      postJSON("/api/conversations/" + obj.conv_id + "/usage", {
        input: State.usage.input, output: State.usage.output, model: State.model,
      }).catch(() => {});
    }
    // Goals：本轮完成且本会话有常驻目标 → 服务端已跑裁判循环（obj.goal）。
    // 透明可控：仅当用户显式点「继续目标」才推进下一轮，绝不自动连跑。
    if (obj.goal && obj.goal.active && obj.goal.judge_available && obj.goal.decision && obj.goal.decision.should_continue) {
      showGoalContinueBar(obj.goal);
    } else {
      hideGoalContinueBar();
    }
    return;
  }
  if (obj.error) {
    turn._errored = true;   // D2：标记错误，后续 done（若有）直接忽略（防御性）
    setPhase("失败", "err", myConvId);
    turn.live.textContent = "";
    turn.bubble.appendChild(el("div", { class: "muted", text: "⚠ " + (obj.error.message || "错误") }));
    toast("对话出错：" + (obj.error.message || "错误"), "err");
    return;
  }
}

// 破除「AI 改了文件但界面无变化」的假成功：把 changed_files 转成可见/可验证的动作
function applyChangedFiles(files) {
  if (!files || !files.length) return;
  const norm = (p) => (p || "").replace(/\\/g, "/");
  const isStatic = (p) => /\/static\//.test(norm(p));
  const staticChanged = files.filter(isStatic);
  const serverChanged = files.filter((p) => !isStatic(p));
  if (staticChanged.length) {
    // 静态文件（前端源码 / 样式）：浏览器刷新即生效——直接重载，让用户看到改动
    toast("AI 已修改前端文件，正在重新加载以应用更改…", "ok");
    setTimeout(() => { location.reload(); }, 800);
  }
  if (serverChanged.length) {
    // 服务端代码（.py 等）：FastHTML 不热重载，必须重启进程——诚实提示，不假装已生效
    showServerRestartBanner(serverChanged);
  }
}

function showServerRestartBanner(files) {
  let bar = document.getElementById("srvRestartBar");
  if (!bar) {
    bar = el("div", { id: "srvRestartBar" });
    Object.assign(bar.style, {
      position: "fixed", left: "0", right: "0", bottom: "0", zIndex: "9999",
      display: "flex", gap: "12px", alignItems: "center", justifyContent: "center",
      padding: "10px 16px", background: "#7c2d12", color: "#fff",
      fontSize: "13px", boxShadow: "0 -2px 10px rgba(0,0,0,.3)",
    });
    document.body.appendChild(bar);
  }
  bar.innerHTML = "";
  const names = files.map((f) => f.split(/[\\/]/).pop()).slice(0, 6).join("、");
  const more = files.length > 6 ? ` 等 ${files.length} 个` : "";
  // 诚实提示：服务端代码（.py）FastHTML 不热重载，必须手动重启才能生效，
  // 不再假装「已改成功」。前端/样式类改动已由上方自动重载处理。
  bar.appendChild(el("span", {
    text: `⚠ AI 修改了服务端代码（${names}${more}），需手动重启应用才能生效（关闭后重新运行）。`,
  }));
}

// 破除「目标悄悄停在某轮」：常驻目标未满足时，在底部给出显式「继续目标」按钮，
// 由用户决定是否推进下一轮（绝不自动连跑）。
function hideGoalContinueBar() {
  const bar = document.getElementById("goalContinueBar");
  if (bar) bar.remove();
}

function showGoalContinueBar(goal) {
  let bar = document.getElementById("goalContinueBar");
  if (!bar) {
    bar = el("div", { id: "goalContinueBar" });
    Object.assign(bar.style, {
      position: "fixed", left: "0", right: "0", bottom: "0", zIndex: "9998",
      display: "flex", gap: "12px", alignItems: "center", justifyContent: "center",
      padding: "10px 16px", background: "#1e3a5f", color: "#fff",
      fontSize: "13px", boxShadow: "0 -2px 10px rgba(0,0,0,.3)",
    });
    document.body.appendChild(bar);
  }
  bar.innerHTML = "";
  const reason = (goal.decision && goal.decision.reason) || "目标尚未完成";
  bar.appendChild(el("span", { text: "🎯 目标进行中：" + reason }));
  bar.appendChild(el("button", {
    class: "btn primary sm", text: "继续目标 ▶",
    onclick: () => {
      const prompt = goal.decision && goal.decision.continuation_prompt;
      const fallback = "请继续朝着以下目标工作直到完成：\n" + ((goal.state && goal.state.goal) || "");
      const text = (prompt && prompt.trim()) ? prompt : fallback;
      const ta = $("#prompt");
      if (ta) ta.textContent = text;
      hideGoalContinueBar();
      sendMessage();
    },
  }));
}

function stopStream() {
  if (!State.streaming) return;
  const cid = State.conv_id;
  postJSON("/api/chat/stop", { conv_id: cid }).catch(() => {});
  State.activeStreams.delete(cid);
  toast("正在停止…");
  setTimeout(() => setStreaming(false), 300);
}

// ------------------------------------------------------------------ 语音输入（Web Speech API，纯前端）
let _recognizer = null, _recognizing = false;
function initVoice() {
  const btn = $("#btnMic");
  if (!btn) return;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { btn.title = "当前浏览器不支持语音输入（请用 Chrome/Edge）"; btn.style.opacity = "0.4"; return; }
  const ta = $("#prompt");
  btn.addEventListener("click", () => {
    if (_recognizing) { try { _recognizer.stop(); } catch (_) {} return; }
    _recognizer = new SR();
    _recognizer.lang = navigator.language || "zh-CN";
    _recognizer.interimResults = true;
    _recognizer.continuous = false;
    const vs = $("#voiceState");
    _recognizer.onstart = () => { _recognizing = true; vs.classList.remove("hidden"); vs.classList.add("listening"); vs.textContent = "● 聆听中…（约 2 秒静音自动停止）"; btn.classList.add("on"); };
    _recognizer.onend = () => { _recognizing = false; vs.classList.add("hidden"); vs.classList.remove("listening"); btn.classList.remove("on"); };
    _recognizer.onerror = (e) => { if (e.error !== "no-speech") toast("语音识别：" + (e.error || "错误"), "err"); };
    _recognizer.onresult = (e) => {
      let txt = "";
      for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
      ta.textContent = txt;
      placeCaretEnd(ta);
      updateCmdPop();
    };
    try { _recognizer.start(); } catch (_) { /* 已启动 */ }
  });
}

// ------------------------------------------------------------------ 上下文使用指示器（对接 /api/context/status 真实水位；接口不可用时静默降级）
async function updateContextIndicator() {
  const ind = $("#ctxIndicator");
  if (!ind) return;
  const cid = State.conv_id;
  if (!cid) { ind.innerHTML = ""; ind.style.color = ""; return; }
  const d = await getJSON("/api/context/status?cid=" + encodeURIComponent(cid)).catch(() => ({ ok: false }));
  if (!d.ok) { ind.innerHTML = ""; ind.style.color = ""; return; }
  const up = d.usage_percent;
  const cw = d.context_window;
  const sc = d.should_compress;
  if (up == null) {
    const reason = (d.diagnostics && d.diagnostics.reason) || "模型窗口未知";
    ind.innerHTML = `上下文 未知（${reason}）`;
    ind.style.color = "";
    return;
  }
  const cwTxt = cw ? `（${(cw / 1000).toFixed(1)}K 窗口）` : "";
  const need = up > 85 ? ' <span class="warn">需压缩⚠️</span>' : (sc === true ? ' <span class="warn">达阈值⚠️</span>' : "");
  ind.innerHTML = `上下文 ${up}%${cwTxt}${need}`;
  ind.style.color = up > 85 ? "#e53935" : (up > 60 ? "#fb8c00" : "");
}

// ------------------------------------------------------------------ token 用量累计（估算）
function addUsage(text, isInput) {
  const n = estimateTokens(text || "");
  if (isInput) State.usage.input += n; else State.usage.output += n;
  updateUsageChip();
}
function resetUsage() { State.usage = { input: 0, output: 0 }; updateUsageChip(); }
function recomputeUsage(messages) {
  let inp = 0, out = 0;
  for (const m of (messages || [])) {
    const t = m.text || "";
    if (m.role === "user") inp += estimateTokens(t);
    else out += estimateTokens(t);
  }
  State.usage = { input: inp, output: out };
  updateUsageChip();
}
function fmtUsage() {
  const { total, cny } = formatUsage(State.usage);
  return { total, cny };
}
function updateUsageChip() {
  const chip = $("#usageChip");
  if (!chip) return;
  const { total, cny } = fmtUsage();
  // 空态弱化：0 消耗时不展示无意义的 "¥0.0000（估算）" 精确计费
  chip.textContent = `📊 ${total.toLocaleString()} tok` + (total ? ` · ¥${cny.toFixed(4)}（估算）` : "");
}

// ------------------------------------------------------------------ 消息悬停操作（编辑 / 重生成）
// 右键上下文菜单
function _showCtxMenu(x, y, msgEl, role) {
  _hideCtxMenu();
  const menu = document.getElementById("ctxMenu");
  if (!menu) return;
  menu.innerHTML = "";
  const bubble = msgEl.querySelector(".bubble");
  const text = bubble ? bubble.textContent : msgEl.textContent;
  const html = bubble ? bubble.innerHTML : "";

  function item(label, action, danger) {
    const btn = el("button", { class: "ctx-item" + (danger ? " ctx-del" : ""), text: label });
    btn.addEventListener("click", () => { _hideCtxMenu(); action(); });
    menu.appendChild(btn);
  }

  item("复制", () => {
    copyToClipboard(text).then(ok => { if (ok) toast("已复制消息", "ok"); else toast("复制失败", "err"); });
  });
  if (role !== "user") {
    item("复制为 Markdown", () => {
      const md = htmlToMarkdown(html);
      copyToClipboard(md).then(ok => { if (ok) toast("已复制为 Markdown", "ok"); else toast("复制失败", "err"); });
    });
  }
  if (role === "user") {
    item("编辑", () => editUserMessage(msgEl));
  } else {
    item("重新生成", () => regenerateFrom(msgEl));
  }
  item("删除该消息", () => {
    if (!confirm("确定删除这条消息？")) return;
    msgEl.remove();
  }, true);

  menu.style.display = "block";
  // 防止菜单超出视口
  const rect = menu.getBoundingClientRect();
  if (x + rect.width > window.innerWidth) x = window.innerWidth - rect.width - 4;
  if (y + rect.height > window.innerHeight) y = window.innerHeight - rect.height - 4;
  menu.style.left = x + "px";
  menu.style.top = y + "px";
}

function _hideCtxMenu() {
  const menu = document.getElementById("ctxMenu");
  if (menu) menu.style.display = "none";
}

function attachMsgActions(msgEl, role) {
  if (msgEl.querySelector(".msg-actions")) return;
  const actions = el("div", { class: "msg-actions" });
  // 复制按钮（所有消息通用）
  actions.appendChild(el("button", { text: "复制", title: "复制消息内容到剪贴板", onclick: (ev) => {
    ev.stopPropagation();
    const bubble = msgEl.querySelector(".bubble");
    const txt = bubble ? bubble.textContent : msgEl.textContent;
    copyToClipboard(txt).then(ok => { if (ok) toast("已复制消息", "ok"); else toast("复制失败", "err"); });
  } }));
  // 复制为 Markdown（仅助手消息，保留格式）
  if (role !== "user") {
    actions.appendChild(el("button", { text: "MD", class: "md-copy", title: "复制为 Markdown（保留格式）", onclick: (ev) => {
      ev.stopPropagation();
      const bubble = msgEl.querySelector(".bubble");
      const html = bubble ? bubble.innerHTML : "";
      const md = htmlToMarkdown(html);
      copyToClipboard(md).then(ok => { if (ok) toast("已复制为 Markdown", "ok"); else toast("复制失败", "err"); });
    } }));
  }
  if (role === "user") {
    actions.appendChild(el("button", { text: "编辑", title: "编辑后作为新轮发送", onclick: (ev) => { ev.stopPropagation(); editUserMessage(msgEl); } }));
  } else {
    actions.appendChild(el("button", { text: "重生成", title: "用上一条用户消息重新生成", onclick: (ev) => { ev.stopPropagation(); regenerateFrom(msgEl); } }));
  }
  msgEl.appendChild(actions);

  // 右键上下文菜单
  msgEl.addEventListener("contextmenu", (ev) => {
    ev.preventDefault();
    _showCtxMenu(ev.clientX, ev.clientY, msgEl, role);
  });
}

// 简单 HTML 转 Markdown（无外部依赖，覆盖常用标签）
function htmlToMarkdown(html) {
  if (!html) return "";
  let text = html;
  text = text.replace(/<br\s*\/?>/gi, "\n");
  text = text.replace(/<\/p>/gi, "\n\n");
  text = text.replace(/<\/div>/gi, "\n");
  text = text.replace(/<\/li>/gi, "\n");
  text = text.replace(/<li[^>]*>/gi, "- ");
  text = text.replace(/<h1[^>]*>/gi, "# "); text = text.replace(/<\/h1>/gi, "\n\n");
  text = text.replace(/<h2[^>]*>/gi, "## "); text = text.replace(/<\/h2>/gi, "\n\n");
  text = text.replace(/<h3[^>]*>/gi, "### "); text = text.replace(/<\/h3>/gi, "\n\n");
  text = text.replace(/<h4[^>]*>/gi, "#### "); text = text.replace(/<\/h4>/gi, "\n\n");
  text = text.replace(/<pre><code[^>]*>/gi, "```\n");
  text = text.replace(/<\/code><\/pre>/gi, "\n```\n");
  text = text.replace(/<code[^>]*>/gi, "`"); text = text.replace(/<\/code>/gi, "`");
  text = text.replace(/<strong[^>]*>/gi, "**"); text = text.replace(/<\/strong>/gi, "**");
  text = text.replace(/<b[^>]*>/gi, "**"); text = text.replace(/<\/b>/gi, "**");
  text = text.replace(/<em[^>]*>/gi, "*"); text = text.replace(/<\/em>/gi, "*");
  text = text.replace(/<i[^>]*>/gi, "*"); text = text.replace(/<\/i>/gi, "*");
  text = text.replace(/<a[^>]*href="([^"]*)"[^>]*>([^<]*)<\/a>/gi, "[$2]($1)");
  text = text.replace(/<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*\/?>/gi, "![$2]($1)");
  text = text.replace(/<img[^>]*src="([^"]*)"[^>]*\/?>/gi, "![]($1)");
  text = text.replace(/<table[^>]*>/gi, "\n"); text = text.replace(/<\/table>/gi, "\n");
  text = text.replace(/<tr[^>]*>/gi, "| "); text = text.replace(/<\/tr>/gi, "|\n");
  text = text.replace(/<th[^>]*>/gi, ""); text = text.replace(/<\/th>/gi, " | ");
  text = text.replace(/<td[^>]*>/gi, ""); text = text.replace(/<\/td>/gi, " | ");
  text = text.replace(/<[^>]+>/g, "");
  text = text.replace(/&amp;/g, "&");
  text = text.replace(/&lt;/g, "<");
  text = text.replace(/&gt;/g, ">");
  text = text.replace(/&quot;/g, '"');
  text = text.replace(/&#39;/g, "'");
  text = text.replace(/&nbsp;/g, " ");
  text = text.replace(/\n{3,}/g, "\n\n");
  return text.trim();
}

// 通用剪贴板写入（带 fallback）
async function copyToClipboard(text, skipHistory) {
  try {
    await navigator.clipboard.writeText(text);
    if (!skipHistory) _saveCopyHistory(text);
    return true;
  } catch (_) {
    // fallback：使用 textarea + execCommand
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed"; ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok && !skipHistory) _saveCopyHistory(text);
      return ok;
    } catch (_2) {
      return false;
    }
  }
}

// 复制历史（localStorage 持久化，最多 10 条）
function _saveCopyHistory(text) {
  if (!text || text.length > 500) return;
  try {
    const h = JSON.parse(localStorage.getItem("_copyHistory") || "[]");
    h.unshift({ text: text.slice(0, 200), time: Date.now() });
    if (h.length > 10) h.length = 10;
    localStorage.setItem("_copyHistory", JSON.stringify(h));
  } catch (_) {}
}
function _loadCopyHistory() {
  try { return JSON.parse(localStorage.getItem("_copyHistory") || "[]"); } catch { return []; }
}
// B1：重生成 / 编辑的共用逻辑
function replaceAndResend(text, targetUserEl) {
  if (State.streaming) return;
  if (!text) { toast("内容为空", "err"); return; }
  const chat = $("#chat");
  const all = Array.from(chat.querySelectorAll(".msg"));
  const users = Array.from(chat.querySelectorAll(".msg.user"));
  const startIdx = all.indexOf(targetUserEl);
  const ordinal = users.indexOf(targetUserEl);
  if (startIdx < 0 || ordinal < 0) {
    // 找不到目标（异常分支）：退化为普通发送，不做替换
    State.replace_index = null;
  } else {
    for (let i = startIdx; i < all.length; i++) chat.removeChild(all[i]);
    State.replace_index = ordinal;
  }
  $("#prompt").textContent = text;
  sendMessage();
}
function editUserMessage(msgEl) {
  const bubble = msgEl.querySelector(".bubble");
  const old = bubble.textContent;
  const ta = el("textarea", { class: "edit-ta", text: old });
  bubble.replaceWith(ta);
  ta.focus();
  const commit = () => {
    const v = ta.value.trim();
    if (!v) return;
    replaceAndResend(v, msgEl);
  };
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); }
    else if (e.key === "Escape") { e.preventDefault(); bubble.textContent = old; ta.replaceWith(bubble); }
  });
}
function regenerateFrom(msgEl) {
  let cur = msgEl.previousElementSibling;
  while (cur && !(cur.classList.contains("msg") && cur.classList.contains("user"))) cur = cur.previousElementSibling;
  const text = cur ? cur.querySelector(".bubble").textContent : "";
  if (!cur) { toast("找不到上一条用户消息", "err"); return; }
  replaceAndResend(text, cur);
}

// ------------------------------------------------------------------ 审批弹窗
function showApproval(command) {
  $("#approvalBody").innerHTML = "";
  $("#approvalBody").appendChild(el("div", { class: "note", text: "Agent 请求执行以下删除操作（纯进程内，无 shell）：" }));
  $("#approvalBody").appendChild(el("pre", { text: command }));
  $("#approvalMask").classList.remove("hidden");
  $("#btnApproveCmd").onclick = async () => {
    $("#approvalMask").classList.add("hidden");
    const r = await postJSON("/api/approve", { command }).catch((e) => ({ ok: false, error: e.message }));
    const out = r.ok ? (r.stdout || "执行成功") : ("拒绝/失败：" + (r.error || ""));
    addAssistantBubble(`<pre>${esc(out)}</pre>`, false);
  };
  $("#btnRejectCmd").onclick = () => $("#approvalMask").classList.add("hidden");
  $("#btnCloseApproval").onclick = () => $("#approvalMask").classList.add("hidden");
}

// ------------------------------------------------------------------ 模型 / 技能下拉
async function loadToolbarSelects() {
  // 模型下拉：按 vendor 分组（>1 家才分组，避免单家时多余层级），标注无密钥，默认选中 active；
  // 加载失败/无数据时恢复占位项并给出明确反馈，杜绝静默空白下拉。
  const msel = $("#modelSelect");
  if (msel) {
    const data = await getJSON("/api/models").catch(() => null);
    msel.innerHTML = "";
    if (data && Array.isArray(data.items) && data.items.length) {
      State.model_cache = data;
      const active = data.active || data.items[0].id;
      const groups = {};
      for (const m of data.items) (groups[m.vendor || "其他"] ||= []).push(m);
      const vendors = Object.keys(groups);
      const useGroup = vendors.length > 1;
      for (const v of vendors) {
        const parent = useGroup ? el("optgroup", { label: v }) : msel;
        for (const m of groups[v]) {
          const opt = el("option", { value: m.id });
          opt.textContent = (m.model || m.id) + (m.has_key ? "" : " ⚠无密钥") + (m.id === active ? "（当前）" : "");
          opt.title = [m.vendor, m.base_url].filter(Boolean).join(" · ") || (m.model || m.id);
          if (m.id === active) opt.selected = true;
          parent.appendChild(opt);
        }
        if (useGroup) msel.appendChild(parent);
      }
      State.model_id = State.model_id || active || null;
      // 底部模型指示器：初始即显示当前模型（避免空框）
      const _m0 = data.items.find(m => m.id === State.model_id);
      State.model = (_m0 && (_m0.model || _m0.id)) || State.model_id || null;
      const _mchip = document.getElementById("modelChip");
      if (_mchip) _mchip.textContent = State.model || "未选择";
      State.model_label = State.model_id || "默认模型";
      // 恢复此前用户选择（避免切换视图返回 chat 后下拉与 State 脱节）
      msel.value = State.model_id || "";
    } else if (data) {
      const opt = el("option", { value: "", disabled: true });
      opt.textContent = "（无可用模型）";
      opt.title = "llm.json 未配置任何模型";
      msel.appendChild(opt);
      State.model_id = State.model_id || null;
    } else {
      const opt = el("option", { value: "", disabled: true });
      opt.textContent = "（模型加载失败）";
      opt.title = "请检查服务或 llm.json 配置";
      msel.appendChild(opt);
      toast("模型列表加载失败", "err");
      State.model_id = State.model_id || null;
    }
    // 操作入口：只要服务可达就提供「去配置」捷径（value 为哨兵，选中后跳转并恢复原值）
    if (data) {
      const act = el("optgroup", { label: "操作" });
      const o = el("option", { value: "__manage_models__" });
      o.textContent = "➕ 新增 / 管理模型…";
      o.title = "打开模型配置界面";
      act.appendChild(o);
      msel.appendChild(act);
    }
  }

  // 技能下拉：首项保留「默认（不指定技能）」反选；按 category 分组（>1 类才分）；
  // 禁用项标注「（禁用）」并用 data-disabled 标记，选择时由 change 处理器警告（服务端会拒绝）。
  const ssel = $("#skillSelect");
  if (ssel) {
    const data = await getJSON("/api/skills").catch(() => null);
    ssel.innerHTML = "";
    const none = el("option", { value: "" });
    none.textContent = "默认（不指定技能）";
    none.title = "不注入任何原生技能，走默认对话";
    none.selected = true;
    ssel.appendChild(none);
    if (data && Array.isArray(data.items) && data.items.length) {
      const groups = {};
      for (const s of data.items) (groups[s.category || "未分类"] ||= []).push(s);
      const cats = Object.keys(groups).sort();
      const useGroup = cats.length > 1;
      for (const c of cats) {
        const parent = useGroup ? el("optgroup", { label: c }) : ssel;
        for (const s of groups[c]) {
          const opt = el("option", { value: s.id });
          opt.textContent = (s.name || s.id) + (s.enabled === false ? "（禁用）" : "");
          opt.title = s.description || (s.name || s.id);
          if (s.enabled === false) opt.dataset.disabled = "1";
          parent.appendChild(opt);
        }
        if (useGroup) ssel.appendChild(parent);
      }
    } else if (!data) {
      const opt = el("option", { value: "", disabled: true });
      opt.textContent = "（技能加载失败）";
      opt.title = "请检查服务或 skills 目录";
      ssel.appendChild(opt);
      toast("技能列表加载失败", "err");
    }
    State.skill_id = State.skill_id || null;
    // 恢复此前用户选择（默认项 value="" 与 skill_id=null 一致）
    ssel.value = State.skill_id || "";
    // 操作入口：只要服务可达就提供「去管理」捷径（value 为哨兵，选中后跳转并恢复原值）
    if (data) {
      const act = el("optgroup", { label: "操作" });
      const o = el("option", { value: "__manage_skills__" });
      o.textContent = "➕ 新增 / 管理技能…";
      o.title = "打开技能管理界面";
      act.appendChild(o);
      ssel.appendChild(act);
    }
  }
}

// ------------------------------------------------------------------ 原生指令自动补全
function loadCommandsCache() {
  if (State.commands) return Promise.resolve(State.commands);
  return getJSON("/api/commands").then((d) => { State.commands = d; return d; }).catch(() => ({ items: [], count: {} }));
}

let _cmdPopIndex = 0;
let _cmdPopItems = [];
// 命令历史（↑ 回溯）
let _cmdHistory = [];
let _cmdHistoryIdx = -1;
let _cmdHistoryTemp = "";

async function updateCmdPop() {
  const ta = $("#prompt");
  const text = ta.textContent || "";
  const pop = $("#cmdPop");
  if (!text.startsWith("/") || text.includes("\n")) {
    pop.classList.add("hidden"); pop.innerHTML = ""; _cmdPopItems = []; return;
  }
  const completions = getCompletions(text);
  if (!completions.length) {
    pop.classList.add("hidden"); pop.innerHTML = ""; _cmdPopItems = []; return;
  }
  _cmdPopItems = completions;
  _cmdPopIndex = 0;
  pop.classList.remove("hidden"); pop.innerHTML = "";
  const catOrder = ["session", "model", "tool", "info", "manage"];
  let lastCat = "";
  completions.forEach((c, i) => {
    if (c.category !== lastCat) {
      lastCat = c.category;
      const cat = CATEGORIES[c.category];
      if (cat) {
        pop.appendChild(el("div", { class: "cat-label" }, [
          el("span", { text: cat.icon + " " + cat.label }),
        ]));
      }
    }
    pop.appendChild(el("div", { class: "row" + (i === 0 ? " sel" : ""), "data-idx": i, onclick: () => {
      cmdPopSelect(i);
    } }, [
      el("span", { class: "cname", text: "/" + c.id }),
      el("span", { class: "cdesc", text: c.desc }),
      c.usage ? el("span", { class: "cusage", text: c.usage }) : null,
    ]));
  });
}

function cmdPopSelect(idx) {
  const pop = $("#cmdPop");
  const ta = $("#prompt");
  if (!pop || !ta) return;
  if (idx < 0 || idx >= _cmdPopItems.length) return;
  _cmdPopIndex = idx;
  pop.querySelectorAll(".row").forEach((r, i) => r.classList.toggle("sel", i === idx));
  const cmd = _cmdPopItems[idx];
  ta.textContent = "/" + cmd.id + " ";
  placeCaretEnd(ta);
  pop.classList.add("hidden"); pop.innerHTML = ""; _cmdPopItems = [];
}

// 命令历史（↑ 回溯）
function cmdHistoryBack(ta) {
  if (_cmdHistory.length === 0) return false;
  if (_cmdHistoryIdx <= 0) return false;
  if (_cmdHistoryIdx === _cmdHistory.length) {
    _cmdHistoryTemp = ta.textContent || "";
  }
  _cmdHistoryIdx--;
  ta.textContent = _cmdHistory[_cmdHistoryIdx];
  placeCaretEnd(ta);
  return true;
}
function cmdHistoryForward(ta) {
  if (_cmdHistoryIdx >= _cmdHistory.length - 1) {
    _cmdHistoryIdx = _cmdHistory.length;
    ta.textContent = _cmdHistoryTemp;
    placeCaretEnd(ta);
    return true;
  }
  if (_cmdHistoryIdx < _cmdHistory.length - 1) {
    _cmdHistoryIdx++;
    ta.textContent = _cmdHistory[_cmdHistoryIdx];
    placeCaretEnd(ta);
    return true;
  }
  return false;
}
function cmdHistoryClear() {
  _cmdHistory = [];
  _cmdHistoryIdx = -1;
  _cmdHistoryTemp = "";
}

function cmdPopNavigate(direction) {
  if (!_cmdPopItems.length) return false;
  const newIdx = _cmdPopIndex + direction;
  if (newIdx < 0 || newIdx >= _cmdPopItems.length) return false;
  _cmdPopIndex = newIdx;
  const pop = $("#cmdPop");
  if (pop) {
    pop.querySelectorAll(".row").forEach((r, i) => r.classList.toggle("sel", i === _cmdPopIndex));
    const sel = pop.querySelector(".row.sel");
    if (sel) sel.scrollIntoView({ block: "nearest" });
  }
  return true;
}
function placeCaretEnd(node) {
  const r = document.createRange(); r.selectNodeContents(node); r.collapse(false);
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
}

function closeSidebarNarrow() { if (window.innerWidth <= 720) $("#sidebar").classList.remove("open"); }


// ------------------------------------------------------------------ 侧栏纵向拖拽（调整导航区/会话区分割）
function initSideVResize() {
  const list = document.getElementById("convList");
  const sidebar = document.getElementById("sidebar");
  const sideNav = document.getElementById("sideNav");
  if (!list || !sidebar || !sideNav) return;

  // 在「对话列表上边界」插入专用拖拽手柄
  let handle = document.getElementById("convResizeTop");
  if (!handle) {
    handle = el("div", { id: "convResizeTop", class: "conv-resize-top", title: "拖动调整导航区/会话区高度" });
    list.parentNode.insertBefore(handle, list);
  }

  const head = sidebar.querySelector(".side-head");
  const handleH = () => handle.offsetHeight || 6;
  const minListH = 80;
  const minNavH = 120;

  function availableNavMax() {
    const sbh = sidebar.getBoundingClientRect().height;
    const hh = head ? head.offsetHeight : 0;
    return Math.max(minNavH, sbh - hh - handleH() - minListH);
  }

  // 恢复上次记忆的导航区高度；若无记忆，则按内容自然高度（最多 220px）初始化。
  // 下方 conv-list 使用 flex:1 自动填满剩余空间，彻底消灭底部「留白吸收区」。
  try {
    const saved = parseInt(localStorage.getItem("lx_navh") || "", 10);
    const maxNavH = availableNavMax();
    const naturalH = Math.max(minNavH, Math.min(sideNav.scrollHeight, maxNavH));
    const h = saved > 0 ? Math.max(minNavH, Math.min(saved, maxNavH)) : Math.min(220, naturalH);
    sidebar.style.setProperty("--snh", h + "px");
    // 清除旧版可能遗留的 conv-list 固定高度，避免与 flex:1 冲突
    list.style.height = "";
    list.style.flex = "";
  } catch (e) {}

  let startY = 0, startNavH = 0, dragging = false;

  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragging = true;
    startY = e.clientY;
    startNavH = sideNav.offsetHeight;
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
    handle.classList.add("active");
  });

  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    // 向上拖（delta < 0）应缩小导航区、放大对话列表；向下拖则相反
    const delta = e.clientY - startY;
    const maxNavH = availableNavMax();
    const newNavH = Math.max(minNavH, Math.min(maxNavH, startNavH + delta));
    sidebar.style.setProperty("--snh", newNavH + "px");
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    handle.classList.remove("active");
    try { localStorage.setItem("lx_navh", String(sideNav.offsetHeight)); } catch (ex) {}
  });
}

// ------------------------------------------------------------------ 文件夹上传
async function uploadFolder(fileList) {
  if (!fileList || !fileList.length) return;
  const files = Array.from(fileList);
  for (const f of files) {
    const relPath = f.webkitRelativePath || f.name;
    State.attachments.push({ name: relPath, size: f.size, path: relPath, file: f });
  }
  renderAttachments();
  toast("已添加 " + files.length + " 个文件（文件夹上传）", "ok");
}

// ------------------------------------------------------------------ 固定文件夹上下文
function renderContextFolder(folder) {
  const bar = document.getElementById("ctxFolderBar");
  const path = document.getElementById("ctxFolderPath");
  if (!bar) return;
  if (folder && folder.display) {
    bar.classList.remove("hidden");
    if (path) {
      path.textContent = folder.display;
      path.title = folder.root || folder.display;
    }
  } else {
    bar.classList.add("hidden");
  }
}

async function unbindContextFolder() {
  if (!State.conv_id) { toast("当前没有会话可解绑", "warn"); return; }
  try {
    const r = await fetch("/api/context-folder?conv_id=" + encodeURIComponent(State.conv_id), { method: "DELETE" })
      .then(r => r.json()).catch(() => ({ ok: false }));
    if (r.ok) {
      State.context_folder = null;
      renderContextFolder(null);
      toast("已解绑固定文件夹", "ok");
    } else {
      toast("解绑失败", "err");
    }
  } catch (e) { toast("解绑失败：" + e.message, "err"); }
}


// 点击其他区域关闭右键菜单
document.addEventListener("click", () => _hideCtxMenu());
document.addEventListener("contextmenu", (e) => {
  // 只在 #chat 区域外的右键不阻止默认行为
  const chat = document.getElementById("chat");
  if (chat && !chat.contains(e.target)) _hideCtxMenu();
});

// 供入口与面板模块导入
export {
  loadHealth, loadConversations, copyConv, archiveConv, tagConv, exportConv, bindImportConv, batchCopyConvs,
  newConversation, openConversation, renameConv, pinConv, delConv, resetChat, renderStarterChips,
  bindConvToolbar, batchDelConvs, selectAllConvs, toggleConvSelect, syncConvToolbar, batchExportConvs, copyConvContent,
  renderHistory, addUserBubble, addAssistantBubble, scrollChat, setPhase, hidePhase,
  convSearchClear, convSearchLive, convSearchJump, copyToClipboard, _loadCopyHistory, htmlToMarkdown, uploadFiles, uploadFolder, renderAttachments, renderContextFolder, unbindContextFolder,
  initResize, initSideResize, initSideVResize, initDropUpload, openGlobalSearch, openUnifiedSearch, setStreaming, buildTurn,
  openToolCard, closeToolCard, attachFilePreview, sendMessage, handleEvent, stopStream,
  initVoice, updateContextIndicator, addUsage, resetUsage, recomputeUsage, fmtUsage, updateUsageChip,
  attachMsgActions, replaceAndResend, editUserMessage, regenerateFrom, showApproval,
  loadToolbarSelects, loadCommandsCache, updateCmdPop, cmdPopNavigate, cmdPopSelect, cmdHistoryBack, cmdHistoryForward, cmdHistoryClear, placeCaretEnd, closeSidebarNarrow,
};
