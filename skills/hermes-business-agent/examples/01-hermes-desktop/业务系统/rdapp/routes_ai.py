"""routes_ai.py — AI 助手（缺口⑩-b）

功能：
- 面向研发费用归集场景的对话式 AI 助手
- 基于 Hermes AIAgent + DeepSeek API，注入当前业务数据快照作为上下文
- 提供快捷问答入口（政策口径、风险预警、报表解读等）
"""
from fasthtml.common import *
from fasthtml.core import APIRouter
from urllib.parse import quote
import os

from .components import page_layout, alert_box

ar = APIRouter()

QUICK_QUESTIONS = [
    ("加计扣除政策要点", "研发费用加计扣除的口径要点和归集注意事项有哪些？"),
    ("高企认定口径", "高新技术企业认定中研发费用占比的要求是什么？"),
    ("费用归集风险", "当前系统数据中可能存在哪些费用归集合规风险？"),
    ("三类口径差异", "高企认定、加计扣除、会计三类口径的主要差异是什么？"),
    ("证据链要求", "研发费用辅助账需要保留哪些证据链材料？"),
]


def _make_agent():
    """创建 Hermes AIAgent（DeepSeek /v1 + OpenAI provider）。"""
    from run_agent import AIAgent
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    return AIAgent(
        base_url="https://api.deepseek.com/v1",
        api_key=api_key,
        provider="openai",
        model="deepseek-v4-flash",
        disabled_toolsets=["terminal"],
        quiet_mode=True,
        max_iterations=30,
        max_tokens=2048,
    )


def _ask(question: str) -> str:
    """调用 AI 助手回答问题，返回回答文本。"""
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
    if not api_key:
        return "AI 助手未配置 API Key：请设置环境变量 ANTHROPIC_AUTH_TOKEN（DeepSeek API Key）后重启服务，即可启用问答。"
    try:
        from .app import get_business_snapshot
        snapshot = get_business_snapshot()
    except Exception:
        snapshot = ""
    try:
        agent = _make_agent()
        system = (
            "你是研发费用管理系统的 AI 助手，请结合以下系统数据快照回答用户问题。"
            "回答要简洁、专业、可执行，涉及金额时引用快照中的实际数据。\n\n"
            + snapshot
        )
        resp = agent.run_conversation(question, system_message=system)
        if isinstance(resp, dict):
            text = resp.get("final_response") or resp.get("response") or ""
        else:
            text = str(resp)
        return text.strip() or "（AI 助手未返回有效回答，请重试。）"
    except Exception as e:
        return f"AI 助手调用失败：{e}"


@ar("/ai-assistant")
def ai_assistant(q: str = ""):
    """AI 助手对话页"""
    answer = ""
    error = ""
    if q.strip():
        answer = _ask(q.strip())
        if answer.startswith("AI 助手调用失败"):
            error = answer
            answer = ""

    body = []
    body.append(Div(
        Div(
            Span("研发费用 AI 助手", style="font-size:15px;font-weight:600;"),
            Div("基于系统实时数据快照，回答政策口径、归集风险、报表解读等问题",
                style="font-size:12px;color:var(--text-muted);margin-top:4px;"),
            cls="card-title"
        ),
        Form(
            Div(
                Input(name="q", cls="input", placeholder="输入你的问题，例如：本月加计扣除口径费用总额是多少？",
                      value=q, style="flex:1;padding:10px 12px;"),
                Button("提问", cls="btn btn-primary", type="submit", style="padding:10px 20px;"),
                style="display:flex;gap:10px;align-items:center;"
            ),
            method="get", action="/ai-assistant",
            cls="nat-form"
        ),
        cls="card"
    ))

    if error:
        body.append(Div(alert_box(error, "danger"), cls="card"))
    if answer:
        body.append(Div(
            Div("回答", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
            Div(answer, cls="ai-answer", style="white-space:pre-wrap;line-height:1.7;font-size:13.5px;"),
            cls="card"
        ))

    # 快捷问题
    quick = []
    for label, text in QUICK_QUESTIONS:
        quick.append(
            A(label, href=f"/ai-assistant?q={quote(text)}",
              cls="btn btn-outline btn-sm", style="text-decoration:none;")
        )
    body.append(Div(
        Div("快捷提问", style="font-size:14px;font-weight:600;margin-bottom:10px;"),
        Div(*quick, style="display:flex;gap:8px;flex-wrap:wrap;"),
        cls="card"
    ))

    body.append(Script("""
    // 让回答区保留换行与代码块样式
    (function(){
      var blocks = document.querySelectorAll('.ai-answer');
      blocks.forEach(function(b){
        b.querySelectorAll('pre').forEach(function(p){
          p.style.background = '#f6f8fa';
          p.style.padding = '10px 12px';
          p.style.borderRadius = '8px';
          p.style.overflow = 'auto';
        });
      });
    })();
    """))

    return page_layout("AI 助手", "首页 / AI 助手", "/ai-assistant", *body)
