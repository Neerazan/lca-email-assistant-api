"""
agent/prompt_builder.py
------------------------
Builds structured, well-engineered prompts for the email assistant agent
and prepares safe message history for each LangGraph turn.

Design decisions:
  - ChatPromptTemplate + SystemMessagePromptTemplate for type-safe, testable
    prompt construction instead of raw f-strings.
  - Prompt is structured with XML-like section tags — LLMs follow delimited
    instructions more reliably than flat prose.
  - Explicit per-tool usage guidance so the agent knows when/how to use each tool.
  - <reasoning_approach> section encourages the agent to think before acting.
  - trim_messages: protects against context window overflow on long threads.
  - filter_messages: removes stale SystemMessages persisted by the checkpointer
    so the fresh one we inject is never duplicated.
  - Images go into HumanMessage as vision blocks (LLM sees them).
  - Text files go into the system prompt as <uploaded_files> (LLM reads them).
  - Memories are shown with their key so the agent knows what to pass to delete_memory.
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    filter_messages,
    trim_messages,
)
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_openai import ChatOpenAI

from services.attachment_extractor import AttachmentKind, ExtractedAttachment
from services.preferences import get_user_preferences
from services.store import get_memories
from utils.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Truncate very large extracted file text to protect context window
_MAX_TEXT_CHARS = 12_000

# Safety ceiling for trimmed message history.
# Leaves ~4 000 token headroom for model output on a 32 k context model.
# Raise this if you switch to a larger context model (e.g. 100 000 for gpt-4.1).
_MAX_HISTORY_TOKENS = 28_000

# Cheap model used only as a token counter for trim_messages — never generates output.
_token_counter = ChatOpenAI(
    model="gpt-4.1-nano",
    api_key=settings.OPENAI_API_KEY,
)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
<role>
You are an expert AI email assistant with full access to the user's Gmail account.
Your job is to help the user read, draft, send, search, and manage their emails \
efficiently, accurately, and professionally.
Always act on behalf of the user — match their preferred tone, style, and language exactly.
Your goal is to be helpful but invisible. Do not be conversational or chatty. Execute tasks in as few turns as possible.
</role>

<capabilities>
You have access to the following tools. Use them proactively and intelligently:

search_emails
  • Search Gmail using standard query syntax: "is:unread", "from:alice@example.com",
    "subject:invoice after:2024/01/01", etc.
  • Use this FIRST when the user asks about emails without specifying a message ID.
  • Returned message IDs and thread IDs should be passed to get_email / get_thread.

get_email
  • Retrieve the FULL body of a specific email by its Gmail message ID.
  • ONLY use Gmail message IDs returned by search_emails — never use session UUIDs,
    attachment IDs, or thread IDs here.

get_thread
  • Retrieve a full email conversation thread by its Gmail thread ID.
  • Use when the user asks about a reply chain or conversation history.

send_email
  • Send an email immediately on the user's behalf.
  • ALWAYS trigger a human-in-the-loop approval before calling this tool.
  • Never send without explicit user confirmation, no matter how clear the request.
  • Pass attachment IDs exactly as shown in <uploaded_files> if the user wants to attach files.

create_draft
  • Save a composed email as a Gmail draft without sending it.
  • This is the DEFAULT action unless the user explicitly says "send" or "send it now".
  • Prefer this over send_email when there is any ambiguity about intent.
  • Pass attachment IDs exactly as shown in <uploaded_files> if files should be attached.

save_memory
  • Persist a durable fact about the user for use in FUTURE sessions.
  • Use sparingly — only for facts that are stable, reusable, and not already saved.
  • Good candidates: preferred contacts, recurring tasks, tone preferences, relationships.
  • Bad candidates: one-off requests, email content, temporary decisions.
  • Key format: short snake_case noun (e.g. "boss_name", "weekly_report_recipient").

delete_memory
  • Remove an outdated or incorrect saved memory by its key.
  • Use immediately when the user corrects something you previously saved.
</capabilities>

<reasoning_approach>
Before taking any action on a request, briefly think through:
  1. What is the user actually asking for? (read / search / write / send / organise)
  2. Do I have all the information I need, or is something ambiguous?
  3. Which tool(s) do I need, and in what order?
  4. Are there any risks? (wrong recipient, wrong attachment, unintended send)

If the request is ambiguous AND the user has ask_clarifying_questions enabled,
ask ONE focused clarifying question. Execute tasks silently — do not announce tool calls.
If the task is clear, proceed directly — do not ask unnecessary confirmation questions.
</reasoning_approach>

<output_format>
Email drafts
  Present the full email with clear labels:
    To: ...
    Subject: ...
    Body:
    [full email body — never truncate]

Reading emails
  Output the FULL email body exactly as returned by the tool.
  Only summarise if the email is extremely long (>2 000 words); in that case
  provide key points and offer to show the full text.

Search results
  Show a numbered list: sender | subject | date | 1-line snippet.
  Offer to open any specific email.

After sending / drafting
  Confirm clearly what was done, to whom, and with which subject.

Errors
  Explain what went wrong in plain language and suggest the next step.

Language
  Always respond in the user's preferred language: {language}.
</output_format>

<user_context>
Full name        : {full_name}
Role / Title     : {role_title}
Company          : {company}
Preferred tone   : {tone}
Email length     : {length}
Default action   : {default_action}
Ask clarifying Qs: {ask_clarifying_questions}
Relationships    : {relationships}
Email signature  : {signature}
Custom instructions: {custom_instructions}
</user_context>

{memory_section}

{attachment_section}

<memory_instructions>
After EVERY response, evaluate whether you learned a NEW durable fact about the user.
Save a memory ONLY when ALL of the following are true:
  1. It concerns the user's habits, preferences, relationships, or recurring contacts.
  2. It is NOT already present in <saved_memories> above.
  3. It would genuinely help you assist them better in a FUTURE session.

Do NOT save: the content of emails, one-off tasks, temporary context, or anything
that will not matter next session.

If a memory in <saved_memories> is wrong or outdated based on what the user just said,
call delete_memory with that exact key immediately, then optionally save a corrected one.
</memory_instructions>

<attachment_rules>
  • Use attachment IDs EXACTLY as shown in <uploaded_files> — do not modify or guess them.
  • Never claim a file is attached in an email unless you explicitly pass its ID to
    send_email or create_draft.
  • If two uploaded files have similar names, ask the user which one to use before proceeding.
  • Images uploaded this turn are visible to you directly — describe or reference them freely.
    You can also attach them to emails using their ID.
</attachment_rules>
"""

_FALLBACK_SYSTEM = """\
<role>
You are an expert AI email assistant with full access to the user's Gmail account.
Help the user read, search, draft, send, and manage their emails.
Always act on behalf of the user — match their preferred tone, style, and language exactly.
Your goal is to be helpful but invisible. Do not be conversational or chatty.
</role>

<capabilities>
Tools available:
  - search_emails    : search Gmail by query
  - get_email        : fetch a full email by Gmail message ID
  - get_thread       : fetch a full thread by Gmail thread ID
  - send_email       : send an email (always confirm with the user first)
  - create_draft     : save a draft without sending (default action)
  - save_memory      : persist a durable user fact for future sessions
  - delete_memory    : remove an outdated saved fact

Default to create_draft unless the user explicitly says to send.
Always confirm before calling send_email.
</capabilities>

<memory_instructions>
After each response, save genuinely useful durable facts about the user using save_memory.
Delete outdated facts with delete_memory. Do not over-save temporary or session-specific info.
</memory_instructions>
"""

# Build the template once at module load — it is stateless and reusable.
_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        SystemMessagePromptTemplate.from_template(_SYSTEM_TEMPLATE),
    ]
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def build_prompt_parts(
    user_id: str,
    human_text: str,
    prefs: dict | None = None,
    extracted_attachments: list[ExtractedAttachment] | None = None,
    message_history: list[BaseMessage] | None = None,
) -> tuple[SystemMessage, list[dict], list[BaseMessage]]:
    """
    Build all inputs needed for one LangGraph agent turn.

    Returns a 3-tuple:
        system_msg      — Fully rendered SystemMessage containing preferences,
                          memories, and extracted text-file content.
        human_content   — Content block list for HumanMessage: the user's text
                          plus any image vision blocks for uploaded images.
        trimmed_history — Previous messages from the checkpointer, filtered to
                          remove stale SystemMessages and trimmed to fit the
                          context window. Pass as the middle of inputs["messages"].

    Typical usage in chat.py:
        system_msg, human_content, history = await build_prompt_parts(...)
        inputs = {
            "messages": [
                system_msg,
                *history,
                HumanMessage(content=human_content),
            ]
        }

    Args:
        user_id:               Internal user ID (fetches prefs + memories).
        human_text:            The user's raw message string.
        prefs:                 Optional pre-fetched preferences dict.
        extracted_attachments: Files extracted this turn by attachment_extractor.
        message_history:       Full message list from agent.aget_state().
    """
    attachments = extracted_attachments or []

    text_attachments = [a for a in attachments if a.kind == AttachmentKind.TEXT]
    image_attachments = [a for a in attachments if a.kind == AttachmentKind.IMAGE]
    unknown_attachments = [a for a in attachments if a.kind == AttachmentKind.UNKNOWN]

    system_msg = await _render_system_message(
        user_id, prefs, text_attachments, unknown_attachments
    )
    human_content = _build_human_content(human_text, image_attachments)
    safe_history = _prepare_history(message_history or [])

    return system_msg, human_content, safe_history


# ---------------------------------------------------------------------------
# System message rendering
# ---------------------------------------------------------------------------


async def _render_system_message(
    user_id: str,
    prefs: dict | None,
    text_attachments: list[ExtractedAttachment],
    unknown_attachments: list[ExtractedAttachment],
) -> SystemMessage:
    if prefs is None:
        prefs = get_user_preferences(user_id)

    if not prefs:
        return SystemMessage(content=_FALLBACK_SYSTEM, id="system_prompt")

    memory_section = await _build_memory_section(user_id, prefs)
    attachment_section = _build_text_attachment_section(
        text_attachments, unknown_attachments
    )

    # ChatPromptTemplate handles safe variable substitution
    rendered = _PROMPT_TEMPLATE.format_messages(
        language=prefs.get("language", "en"),
        full_name=prefs.get("full_name", "the user"),
        role_title=prefs.get("role_title", ""),
        company=prefs.get("company", ""),
        tone=prefs.get("tone", "formal"),
        length=prefs.get("length", "medium"),
        default_action=prefs.get("default_action", "draft"),
        ask_clarifying_questions=prefs.get("ask_clarifying_questions", True),
        relationships=prefs.get("relationships", "None specified"),
        signature=prefs.get("signature", ""),
        custom_instructions=prefs.get("custom_instructions", "None"),
        memory_section=memory_section,
        attachment_section=attachment_section,
    )

    # rendered[0] is the SystemMessage produced by SystemMessagePromptTemplate
    return SystemMessage(content=rendered[0].content, id="system_prompt")


async def _build_memory_section(user_id: str, prefs: dict) -> str:
    """
    Fetch saved memories and format them for injection into the system prompt.
    Memory keys are shown so the agent knows what to pass to delete_memory.
    Returns an empty string if memory is disabled or there are no saved memories.
    """
    if not prefs.get("ai_memory_enabled", True):
        return ""

    memories = await get_memories(user_id)
    if not memories:
        return ""

    lines = "\n".join(
        f"  - [{m.key}]: {m.value.get('memory')}"
        for m in memories
        if isinstance(m.value, dict) and "memory" in m.value
    )
    return f"<saved_memories>\n{lines}\n</saved_memories>"


def _build_text_attachment_section(
    text_attachments: list[ExtractedAttachment],
    unknown_attachments: list[ExtractedAttachment],
) -> str:
    """
    Format extracted text-file content and unknown-type files for injection
    into the system prompt as an <uploaded_files> XML block.
    Images are handled separately as vision blocks in the HumanMessage.
    """
    if not text_attachments and not unknown_attachments:
        return ""

    parts: list[str] = ["<uploaded_files>"]

    for att in text_attachments:
        content = att.text_content or ""
        if len(content) > _MAX_TEXT_CHARS:
            content = (
                content[:_MAX_TEXT_CHARS]
                + f"\n... [truncated at {_MAX_TEXT_CHARS} chars — file is very large]"
            )
        parts.append(
            f'<file id="{att.attachment_id}" name="{att.filename}" type="{att.mime_type}">\n'
            f"{content}\n"
            f"</file>"
        )

    for att in unknown_attachments:
        parts.append(
            f'<file id="{att.attachment_id}" name="{att.filename}" type="{att.mime_type}">\n'
            f"[Content could not be extracted from this file type. "
            f"You can still attach it to emails using its ID.]\n"
            f"</file>"
        )

    parts.append("</uploaded_files>")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Human message content builder
# ---------------------------------------------------------------------------


def _build_human_content(
    human_text: str,
    image_attachments: list[ExtractedAttachment],
) -> list[dict]:
    """
    Build the content block list for HumanMessage.

    Structure:
      1. The user's text message (always first)
      2. For each image: a vision block (LLM sees it) + a text block (gives
         the LLM the filename and attachable ID)

    The OpenAI vision format is used:
      {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<data>", "detail": "high"}}
    """
    content: list[dict] = [{"type": "text", "text": human_text}]

    for att in image_attachments:
        # Vision block — the model can see the image directly
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{att.image_media_type};base64,{att.image_base64}",
                    "detail": "high",
                },
            }
        )
        # Companion text — gives the model the filename and the ID for attaching
        content.append(
            {
                "type": "text",
                "text": (
                    f"[Image uploaded — Name: {att.filename} | "
                    f"Attachment ID: {att.attachment_id} | Type: {att.mime_type}] "
                    f"You can describe this image and attach it to emails using its ID."
                ),
            }
        )

    return content


# ---------------------------------------------------------------------------
# Message history: filter + trim
# ---------------------------------------------------------------------------


def _prepare_history(history: list[BaseMessage]) -> list[BaseMessage]:
    """
    Prepare the checkpointer message history for safe injection into the agent.

    Step 1 — filter_messages:
        Remove any SystemMessage entries that the checkpointer persisted from
        previous turns. We always inject a fresh SystemMessage ourselves, so
        old ones would cause duplication, stale preferences, and wasted tokens.
        Also removes any tool-result messages that have no corresponding
        tool call, which can confuse some models.

    Step 2 — trim_messages:
        Trim oldest messages first (strategy="last") so total token count
        stays under _MAX_HISTORY_TOKENS. start_on="human" ensures the
        trimmed history never begins mid-AI-response.
        allow_partial=False prevents cutting a single message in half.

    Fails open: if trim_messages raises (e.g. token counter unavailable),
    the full filtered history is returned so the agent still works.
    """
    if not history:
        return []

    # Step 1: keep only human, ai, and tool messages — drop stale system messages
    filtered = filter_messages(history, include_types=["human", "ai", "tool"])

    if not filtered:
        return []

    # Step 2: trim to context window limit
    try:
        trimmed = trim_messages(
            filtered,
            max_tokens=_MAX_HISTORY_TOKENS,
            token_counter=_token_counter,
            strategy="last",  # keep the most recent messages
            start_on="human",  # never start history on an AI turn
            include_system=False,  # we inject system separately
            allow_partial=False,  # never cut a message in half
        )
    except Exception as exc:
        print(f"[WARN] prompt_builder: trim_messages failed, using full history: {exc}")
        trimmed = filtered

    # Step 3: Fix trailing tool calls
    # If the last AI message has tool_calls but no ToolMessages follow it,
    # OpenAI will reject the request. This often happens if the tool crashed.
    # We strip the tool_calls from that AI message so the turn can proceed.
    if trimmed and isinstance(trimmed[-1], AIMessage) and trimmed[-1].tool_calls:
        # Check if there are any ToolMessages after this AIMessage
        # (Though with strategy="last" and start_on="human", trimmed should end on AI or Human)
        has_tool_response = False
        for i in range(len(trimmed) - 1, -1, -1):
            if isinstance(trimmed[i], ToolMessage):
                has_tool_response = True
                break
            if isinstance(trimmed[i], AIMessage):
                # This is our target AI message
                break
        
        if not has_tool_response:
            print(f"[INFO] prompt_builder: stripping unanswered tool_calls from last AIMessage")
            # Create a shallow copy of the message with tool_calls removed
            last_msg = trimmed[-1]
            trimmed[-1] = AIMessage(
                content=last_msg.content,
                additional_kwargs={k: v for k, v in last_msg.additional_kwargs.items() if k != "tool_calls"},
                id=last_msg.id
            )

    return trimmed
