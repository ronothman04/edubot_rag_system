import streamlit as st
import requests

st.set_page_config(
    page_title="EduBot",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = "http://localhost:8000/chat"

# =========================
# GLOBAL CSS (IMPORTANT)
# =========================
st.markdown("""
<style>
/* Hide default UI */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Main container */
.block-container {
    padding-top: 1rem;
    padding-bottom: 0rem;
    max-width: 100%;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    width: 260px !important;
    background-color: #f7f9fc;
    border-right: 1px solid #e6eaf1;
}

/* Sidebar buttons */
.stButton > button {
    width: 100%;
    border-radius: 10px;
    padding: 10px;
    font-weight: 500;
}

/* Title styling */
.main-title {
    text-align: center;
    margin-top: 18vh;
    color: #1f2a44;
}

.main-title h1 {
    font-size: 28px;
    font-weight: 600;
}

/* Chat input */
.stChatInputContainer {
    border-top: 1px solid #e6eaf1;
    padding-top: 10px;
}

/* Chat bubbles */
[data-testid="stChatMessage"] {
    border-radius: 12px;
    padding: 10px 14px;
}

/* Assistant bubble */
[data-testid="stChatMessage"][data-testid*="assistant"] {
    background-color: #f4f6fb;
}

/* User bubble */
[data-testid="stChatMessage"][data-testid*="user"] {
    background-color: #e9f2ff;
}

/* Empty center icon */
.center-icon {
    text-align: center;
    font-size: 40px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)


# =========================
# SESSION STATE
# =========================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "history" not in st.session_state:
    st.session_state.history = ""


# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("### 🎓 EduBot")
    st.caption("AI Assistant")

    if st.button("➕ New Chat"):
        st.session_state.messages = []
        st.session_state.history = ""
        st.rerun()

    st.markdown("---")
    st.markdown("**Recent**")
    st.caption("No chats yet")

    st.markdown("---")
    st.markdown("⚙️ Settings")

    st.markdown("---")
    st.markdown("👤 John Doe")


# =========================
# MAIN UI
# =========================

# Empty state (like screenshot)
if not st.session_state.messages:
    st.markdown("""
    <div class="main-title">
        <div class="center-icon">🎓</div>
        <h1>How can I help you today?</h1>
    </div>
    """, unsafe_allow_html=True)


# =========================
# CHAT HISTORY
# =========================
for msg in st.session_state.messages:
    avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])


# =========================
# INPUT
# =========================
query = st.chat_input("Ask EduBot anything...")

if query:
    # Store user msg
    st.session_state.messages.append({
        "role": "user",
        "content": query
    })

    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(query)

    # Backend call
    try:
        response = requests.post(
            API_URL,
            json={
                "query": query,
                "history": st.session_state.history
            },
            timeout=15
        )

        data = response.json()
        answer = data.get("answer", "No response")
        sources = data.get("sources", [])

    except Exception as e:
        answer = f"Backend Error: {str(e)}"
        sources = []

    # Update history
    st.session_state.history += f"\nUser: {query}\nAssistant: {answer}"

    # Store assistant msg
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer
    })

    # Display assistant
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(answer)

        if sources:
            with st.expander("📚 Sources"):
                for s in sources:
                    st.write(s)