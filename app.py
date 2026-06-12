"""
Nexus — Local OT/Cybersecurity AI Workbench (Streamlit UI)

Two tools, one private app, all running on the local RunPod model
(nothing leaves the box):

  • Blueprint Analyzer — upload a P&ID; the vision model reads the instrument
    tags and looks up each one's failure-state info in ChromaDB.
  • Assistant — a general chat model for gap assessments, IEC 62443 / NIST
    work, analysis, drafting, and ad-hoc questions.

Run on the server with:
    streamlit run app.py --server.address 0.0.0.0 --server.port 8501
Then tunnel from your Mac:
    ssh -N -L 8501:localhost:8501 root@<ip> -p <port> -i ~/.ssh/id_ed25519
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import config
import rag_engine
import chat_engine
import ingest


def _enable_fullpage_drop() -> None:
    """
    Make the WHOLE window a drop target (Streamlit only drops on the widget by
    default). On drop anywhere, the file is forwarded into the chat's attach
    input. Best-effort: relies on Streamlit's DOM, so it may need tweaks across
    Streamlit versions.
    """
    components.html(
        """
<script>
const doc = window.parent.document;
if (!doc.__nexusFullDrop) {
  doc.__nexusFullDrop = true;
  const ov = doc.createElement('div');
  ov.style.cssText = 'position:fixed;inset:0;z-index:999999;display:none;'
    + 'align-items:center;justify-content:center;background:rgba(20,22,30,.55);'
    + 'backdrop-filter:blur(2px);color:#fff;font:600 26px sans-serif;'
    + 'pointer-events:none;border:3px dashed rgba(255,255,255,.5)';
  ov.innerText = '📎 Drop file to attach';
  doc.body.appendChild(ov);
  let depth = 0;
  const hasFiles = e => e.dataTransfer && [...e.dataTransfer.types].includes('Files');
  const findInput = () => {
    let i = doc.querySelector('[data-testid="stChatInput"] input[type=file]');
    if (i) return i;
    const all = doc.querySelectorAll('input[type=file]');
    return all[all.length - 1] || null;   // chat input is last on the page
  };
  doc.addEventListener('dragenter', e => { if (hasFiles(e)) { depth++; ov.style.display='flex'; } });
  doc.addEventListener('dragover',  e => { if (hasFiles(e)) e.preventDefault(); });
  doc.addEventListener('dragleave', e => { if (--depth <= 0) { depth=0; ov.style.display='none'; } });
  doc.addEventListener('drop', e => {
    if (!hasFiles(e)) return;
    e.preventDefault(); depth=0; ov.style.display='none';
    const input = findInput();
    if (!input) return;
    const dt = new DataTransfer();
    for (const f of e.dataTransfer.files) dt.items.add(f);
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
}
</script>
""",
        height=0,
    )

st.set_page_config(page_title="Nexus — OT AI Workbench", page_icon="🔧",
                   layout="wide", initial_sidebar_state="expanded")


def _inject_css() -> None:
    """ChatGPT-style dark, minimal theme. Colors are the variables in :root."""
    st.markdown(
        """
<style>
  :root {
    --bg:#000000; --panel:#000000; --elev:#303030; --hover:#1c1c1c;
    --border:#2a2a2a; --text:#ECECEC; --muted:#8e8e8e; --user-bubble:#303030;
  }
  .stApp { background:var(--bg); color:var(--text); }
  html, body, [class*="css"], textarea, input, button {
    font-family: ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif !important;
  }
  /* hide streamlit chrome */
  [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer { display:none !important; }
  [data-testid="stHeader"] { background:transparent; }
  /* Sidebar is always visible (avoids the collapse-then-stuck bug). The native
     collapse buttons are hidden since collapsing is disabled. */
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="collapsedControl"] { display:none !important; }
  /* readable centered column */
  .block-container { max-width: 780px; padding-top: 1.5rem; padding-bottom: 7rem; }

  /* ---- sidebar ---- */
  section[data-testid="stSidebar"] {
    background:var(--panel); border-right:1px solid #000;
    min-width:270px !important; width:270px !important;
  }
  section[data-testid="stSidebar"] * { color:var(--text); }
  /* sidebar buttons look like chat list rows (stay transparent, not white) */
  section[data-testid="stSidebar"] .stButton > button {
    background:transparent !important; border:none !important; text-align:left;
    justify-content:flex-start; border-radius:8px !important; padding:.4rem .6rem !important;
    font-weight:400 !important; color:var(--text) !important;
  }
  section[data-testid="stSidebar"] .stButton > button * { color:var(--text) !important; }
  section[data-testid="stSidebar"] .stButton > button:hover { background:var(--hover) !important; }
  /* selected chat row */
  section[data-testid="stSidebar"] .stButton > button[kind="primary"],
  section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background:var(--hover) !important; border:none !important; color:var(--text) !important;
  }

  /* ---- tabs ---- */
  [data-baseweb="tab-list"] { gap:4px; border-bottom:1px solid #2a2a2a; }
  [data-baseweb="tab"] { color:var(--muted); }
  [aria-selected="true"][data-baseweb="tab"] { color:var(--text); }

  /* ---- chat input: ChatGPT pill ---- */
  [data-testid="stChatInput"] {
    background:var(--elev) !important; border:1px solid var(--border) !important;
    border-radius:28px !important; box-shadow:0 2px 16px rgba(0,0,0,.35); padding:4px 6px;
  }
  [data-testid="stChatInput"] textarea { background:transparent !important; color:var(--text) !important; font-size:1rem; }
  /* white circular send button (ChatGPT) */
  [data-testid="stChatInput"] button {
    border-radius:50% !important; background:#fff !important; border:none !important;
  }
  [data-testid="stChatInput"] button svg, [data-testid="stChatInput"] button * {
    color:#000 !important; fill:#000 !important;
  }

  /* ---- messages (ChatGPT layout) ---- */
  .msg-user {
    background:var(--user-bubble); border-radius:20px; padding:10px 16px;
    margin:10px 0 10px auto; width:fit-content; max-width:75%; line-height:1.5;
  }
  .msg-assistant { padding:6px 2px 14px 2px; line-height:1.65; }
  .greeting { text-align:center; font-size:1.9rem; font-weight:600;
    color:var(--text); margin:22vh 0 0 0; }

  /* ---- general buttons → white pill (ChatGPT style) ---- */
  .stButton > button, [data-testid="stPopover"] > button {
    border-radius:9999px !important; background:#fff !important; color:#000 !important;
    border:none !important; font-weight:500 !important; padding:.45rem 1.1rem !important;
  }
  .stButton > button:hover, [data-testid="stPopover"] > button:hover { background:#e3e3e3 !important; }
  .stButton > button *, [data-testid="stPopover"] > button * { color:#000 !important; }
  /* expanders / code */
  [data-testid="stExpander"] { border:1px solid #2a2a2a; border-radius:10px; background:var(--panel); }
  .stCode, pre { background:#0f0f0f !important; }
</style>
""",
        unsafe_allow_html=True,
    )


_inject_css()


# --------------------------------------------------------------------------- #
# Optional password gate (enabled only when APP_PASSWORD is set)
# --------------------------------------------------------------------------- #
def _check_password() -> bool:
    if not config.APP_PASSWORD:
        return True  # auth disabled
    if st.session_state.get("authed"):
        return True
    st.title("🔒 Nexus — OT AI Workbench")
    pw = st.text_input("Password", type="password")
    if pw:
        if pw == config.APP_PASSWORD:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


_check_password()
_enable_fullpage_drop()

# --------------------------------------------------------------------------- #
# Conversations (multiple chats, like Claude/ChatGPT)
# --------------------------------------------------------------------------- #
import time as _time


def _new_conversation() -> str:
    cid = str(_time.time_ns())
    st.session_state.conversations[cid] = {"title": "New chat", "messages": []}
    st.session_state.current_chat = cid
    return cid


if "conversations" not in st.session_state:
    st.session_state.conversations = {}
    _new_conversation()


def _current_messages() -> list[dict]:
    return st.session_state.conversations[st.session_state.current_chat]["messages"]

# --------------------------------------------------------------------------- #
# Sidebar: conversations + connection status + model info
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("💬 Conversations")
    if st.button("➕ New chat", use_container_width=True):
        _new_conversation()
        st.rerun()
    for cid, conv in reversed(list(st.session_state.conversations.items())):
        is_current = cid == st.session_state.current_chat
        c1, c2 = st.columns([6, 1])
        label = ("▶ " if is_current else "") + (conv["title"] or "New chat")[:28]
        if c1.button(label, key=f"sel_{cid}", use_container_width=True,
                     type="primary" if is_current else "secondary"):
            st.session_state.current_chat = cid
            st.rerun()
        if c2.button("🗑", key=f"del_{cid}", help="Delete this chat"):
            del st.session_state.conversations[cid]
            if not st.session_state.conversations:
                _new_conversation()
            if st.session_state.current_chat == cid:
                st.session_state.current_chat = next(iter(st.session_state.conversations))
            st.rerun()

    # Diagnostics tucked away at the bottom, collapsed by default.
    st.divider()
    st.caption("🔒 Runs locally — no data leaves the server.")
    with st.expander("🛠 Diagnostics"):
        st.code(
            f"Ollama : {config.OLLAMA_HOST}\n"
            f"Chroma : {config.CHROMA_HOST}:{config.CHROMA_PORT}\n"
            f"Vision : {config.VISION_MODEL}\n"
            f"Chat   : {config.CHAT_MODEL}",
            language="text",
        )
        if st.button("Test connections", use_container_width=True):
            with st.spinner("Pinging services…"):
                try:
                    rag_engine._ollama_client().list()
                    st.success("Ollama reachable ✅")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Ollama unreachable: {e}")
                try:
                    count = rag_engine.chroma_doc_count()
                    st.success(f"ChromaDB reachable ✅ ({count} docs)")
                except Exception as e:  # noqa: BLE001
                    st.error(f"ChromaDB unreachable: {e}")


# --------------------------------------------------------------------------- #
# Custom sidebar collapse toggle (reliable — we control both directions)
# --------------------------------------------------------------------------- #
if "sidebar_open" not in st.session_state:
    st.session_state.sidebar_open = True

st.markdown('<div id="sb-toggle"></div>', unsafe_allow_html=True)
_tcol, _ = st.columns([1, 14])
with _tcol:
    if st.button("☰", help="Show/hide sidebar", key="sidebar_toggle"):
        st.session_state.sidebar_open = not st.session_state.sidebar_open
        st.rerun()
if st.session_state.sidebar_open:
    # Force visible — overrides Streamlit's own (possibly stuck) collapsed state.
    st.markdown(
        "<style>section[data-testid='stSidebar']{"
        "display:flex !important; visibility:visible !important; opacity:1 !important;"
        "transform:none !important; margin-left:0 !important; left:0 !important;}"
        "</style>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        "<style>section[data-testid='stSidebar']{display:none !important;}</style>",
        unsafe_allow_html=True,
    )


tab_chat, tab_blueprint, tab_manuals = st.tabs(
    ["💬 Assistant", "🔧 Blueprint Analyzer", "📚 Manuals"]
)


# --------------------------------------------------------------------------- #
# Tab 1 — General assistant (chat)
# --------------------------------------------------------------------------- #
with tab_chat:
    messages = _current_messages()

    # Compact options popover keeps the chat area clean (ChatGPT-like).
    with st.popover("⚙️ Options"):
        mode = st.radio(
            "Model mode",
            ["Auto", "General (fast)", "Deep reasoning"],
            help="Auto = pick the right model per question automatically. "
                 "General = fast generalist model. Deep reasoning = thinks "
                 "step-by-step; slower but better for hard analysis.",
        )
        use_rag = st.toggle(
            "🔎 Use my documents", value=True,
            help="On: search your uploaded manuals/standards and answer grounded "
                 "in them, with citations. Off: general knowledge only.",
        )
        save_to_lib = st.checkbox(
            "💾 Save attached files to my library (permanent)", value=False,
            help="Off: attached files are used only for this conversation. "
                 "On: also added to your searchable library.",
        )
        if st.button("🗑️ Clear this chat", use_container_width=True):
            messages.clear()
            st.rerun()

    def _passages_from_uploads(files) -> tuple[list[dict], list]:
        """Extract relevance-rankable passages from attached files."""
        out, paths, tmp = [], [], tempfile.mkdtemp()
        for uf in files:
            p = Path(tmp) / uf.name
            p.write_bytes(uf.getvalue())
            paths.append(p)
            for text, loc in ingest.extract_passages(p):
                tags = ingest.tags_in(text)
                out.append({"manual": text, "source": uf.name, "loc": loc,
                            "tag": tags[0] if tags else "—"})
        return out, paths

    def _render_sources(sources: list[dict]) -> None:
        if not sources:
            return
        with st.expander(f"📎 Sources ({len(sources)})"):
            for i, s in enumerate(sources, 1):
                cite = rag_engine.format_citation(s["source"], s.get("loc"))
                st.markdown(
                    f"**[{i}]** _{cite}_ · tag `{s['tag']}` · "
                    f"dist `{s['distance']}`\n\n{s['manual'][:300]}…"
                )

    import html as _h
    import re as _re_b

    def _user_bubble(text: str) -> None:
        safe = _h.escape(text).replace("\n", "<br>")
        safe = _re_b.sub(r"\*(.+?)\*", r"<em>\1</em>", safe)
        st.markdown(f'<div class="msg-user">{safe}</div>', unsafe_allow_html=True)

    # Empty-state greeting (ChatGPT-style).
    if not messages:
        st.markdown('<div class="greeting">What are you working on?</div>',
                    unsafe_allow_html=True)

    # Replay history.
    for msg in messages:
        if msg["role"] == "user":
            _user_bubble(msg["content"])
        else:
            st.markdown(msg["content"])
            if msg.get("model"):
                st.caption(f"🧭 {msg['model']}")
            _render_sources(msg.get("sources", []))

    submission = st.chat_input(
        "Ask anything…  (drag a file in or click 📎 to attach)",
        accept_file="multiple",
        file_type=["pdf", "docx", "txt", "md", "csv", "xlsx", "xls",
                   "png", "jpg", "jpeg"],
    )
    if submission and (submission.text or submission.files):
        attached = submission.files or []
        prompt = submission.text or (
            "Summarize and explain the attached file(s)." if attached else "")
        label = (submission.text or "*(no message)*") + (
            f"\n\n*📎 {len(attached)} file(s) attached*" if attached else "")
        # Title a fresh conversation from its first message.
        conv = st.session_state.conversations[st.session_state.current_chat]
        if conv["title"] == "New chat":
            conv["title"] = (submission.text or "Attached file(s)")[:40]
        messages.append({"role": "user", "content": label})
        _user_bubble(label)

        # Route to the right model for this question.
        chat_model = chat_engine.choose_model(prompt, mode)

        context = []

        # 1) Files attached to this chat take priority as context.
        if attached:
            try:
                with st.spinner("Reading attached file(s)…"):
                    passages, paths = _passages_from_uploads(attached)
                    if save_to_lib:
                        ingest.ingest_files(paths, reset=False, log=lambda *_: None)
                    context += chat_engine.rank_passages(prompt, passages, k=5)
            except Exception as e:  # noqa: BLE001
                st.warning(f"Couldn't read an attached file: {e}")

        # 2) Plus the permanent library (if enabled).
        if use_rag:
            try:
                context += chat_engine.retrieve(prompt, k=5)
            except Exception:  # noqa: BLE001
                pass

        if mode == "Auto":
            st.caption(f"🧭 routed to `{chat_model}`")
        try:
            reply = st.write_stream(
                chat_engine.stream_reply(messages, model=chat_model, context=context)
            )
        except Exception as e:  # noqa: BLE001
            reply = f"⚠️ Error talking to the model: {e}"
            st.error(reply)
        _render_sources(context)
        messages.append(
            {"role": "assistant", "content": reply, "sources": context,
             "model": chat_model}
        )


# --------------------------------------------------------------------------- #
# Tab 2 — Blueprint analyzer (P&ID → failure-state lookup)
# --------------------------------------------------------------------------- #
with tab_blueprint:
    st.subheader("Blueprint Analyzer")
    st.caption(
        "Upload one or more P&ID / engineering blueprints. The vision model "
        "reads the instrument tags and matches each to your failure-state "
        "manuals."
    )

    uploaded = st.file_uploader(
        "Upload blueprint(s)", type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )
    use_sample = st.checkbox("Use bundled sample (01fig07.jpg)", value=not uploaded)

    # Build the list of (name, bytes) images to analyze.
    images: list[tuple[str, bytes]] = []
    if uploaded:
        images = [(f.name, f.getvalue()) for f in uploaded]
    elif use_sample:
        try:
            with open("01fig07.jpg", "rb") as fh:
                images = [("01fig07.jpg (sample)", fh.read())]
        except FileNotFoundError:
            st.warning("Sample image 01fig07.jpg not found in the project folder.")

    def _render_result(result: dict) -> None:
        """Render one image's analysis: found vs. not-found, with sources."""
        tags = result["tags"]
        if not tags:
            st.warning("No valid instrument tags were detected.")
            with st.expander("Show raw vision output"):
                st.text(result["raw_text"])
            return

        found = [r for r in result["results"] if r["manual"]]
        missing = [r for r in result["results"] if not r["manual"]]

        st.success(f"Detected {len(tags)} tag(s): {', '.join(tags)}")
        c1, c2 = st.columns(2)
        c1.metric("Manuals found", len(found))
        c2.metric("No exact manual", len(missing))

        if found:
            st.markdown("**✅ Failure-state manuals**")
            for item in found:
                badge = "" if item["match"] == "exact" else "  *(OCR-corrected)*"
                cite = rag_engine.format_citation(item["source"], item.get("loc"))
                with st.expander(f"📄 {item['tag']}{badge}  ·  {cite}",
                                 expanded=True):
                    st.markdown(item["manual"])

        if missing:
            st.markdown("**⚠️ Tags with no exact manual**")
            for item in missing:
                with st.expander(f"❓ {item['tag']}", expanded=False):
                    st.info("No exact failure-state manual for this tag.")
                    if item["suggestions"]:
                        st.caption("Closest related passages (semantic — not exact):")
                        for s in item["suggestions"]:
                            cite = rag_engine.format_citation(s["source"], s.get("loc"))
                            st.markdown(
                                f"- **[{s['tag']}]** · _{cite}_ · "
                                f"similarity dist `{s['distance']}`\n\n"
                                f"  {s['manual'][:300]}…"
                            )

        with st.expander("Show raw vision output"):
            st.text(result["raw_text"])

    if images:
        st.image([img for _, img in images],
                 caption=[name for name, _ in images], width=240)
        if st.button(f"🔍 Analyze {len(images)} blueprint(s)",
                     type="primary", use_container_width=True):
            for name, data in images:
                st.divider()
                st.markdown(f"### 🖼️ {name}")
                try:
                    with st.spinner(f"Vision model reading {name}…"):
                        result = rag_engine.analyze_image(data)
                except Exception as e:  # noqa: BLE001
                    st.error(
                        f"Couldn't analyze **{name}**: {e}\n\n"
                        "The model or database may be starting up or unreachable. "
                        "Try the **Test connections** button in the sidebar."
                    )
                    continue
                _render_result(result)
    else:
        st.info("Upload one or more images, or enable the bundled sample, to begin.")


# --------------------------------------------------------------------------- #
# Tab 3 — Manuals (self-service document upload / ingestion)
# --------------------------------------------------------------------------- #
with tab_manuals:
    st.subheader("Failure-State Manuals")
    st.caption(
        "Upload your own documents — PDF, Word, Excel, CSV, text, or scanned "
        "images. They're read, the instrument tags are found automatically, and "
        "stored so the Blueprint Analyzer can cite them. Files stay on this "
        "server."
    )

    try:
        current = rag_engine.chroma_doc_count()
        st.metric("Passages currently in the database", current)
    except Exception:  # noqa: BLE001
        st.warning("Database not reachable right now.")

    manual_files = st.file_uploader(
        "Upload manual(s)",
        type=["pdf", "docx", "txt", "md", "csv", "xlsx", "xls",
              "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    replace = st.checkbox(
        "Replace everything currently in the database",
        value=False,
        help="On: wipe existing manuals first (use when loading a fresh, "
             "complete set). Off: add these to what's already there.",
    )

    if st.button("📥 Ingest uploaded manuals", type="primary",
                 disabled=not manual_files, use_container_width=True):
        logs: list[str] = []
        with st.status("Ingesting…", expanded=True) as status:
            try:
                # Persist uploads to a temp folder, then run the shared engine.
                with tempfile.TemporaryDirectory() as tmp:
                    paths = []
                    for uf in manual_files:
                        p = Path(tmp) / uf.name
                        p.write_bytes(uf.getvalue())
                        paths.append(p)

                    def _log(msg: str) -> None:
                        logs.append(str(msg))
                        status.write(str(msg))

                    summary = ingest.ingest_files(paths, reset=replace, log=_log)
            except Exception as e:  # noqa: BLE001
                status.update(label="Ingestion failed", state="error")
                st.error(
                    f"Couldn't ingest: {e}\n\n"
                    "Is the database running? Try **Test connections** in the sidebar."
                )
            else:
                status.update(label="Ingestion complete", state="complete")
                c1, c2, c3 = st.columns(3)
                c1.metric("Files read", summary["files"])
                c2.metric("Tag entries added", summary["entries"])
                c3.metric("Total in database", summary["total_in_db"])
                if summary["tags"]:
                    st.success(
                        f"Tags now available ({len(summary['tags'])}): "
                        f"{', '.join(summary['tags'])}"
                    )
                if summary["untagged"]:
                    st.warning(
                        "No instrument tags were found in: "
                        f"{', '.join(summary['untagged'])}. These files were read "
                        "but can't be retrieved by tag — check they actually "
                        "contain tags like PT-101."
                    )
