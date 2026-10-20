from pathlib import Path
import os

import streamlit as st
from httpx import HTTPError
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from psycopg import Error as PsycopgError
from streamlit.errors import StreamlitSecretNotFoundError
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError

from quiz import QUESTIONS, run_read_only_query


st.set_page_config(page_title="Economics SQL Quiz", page_icon="📊", layout="wide")
st.markdown(
    """
    <style>
    .quiz-mascot {
        display: flex;
        align-items: center;
        gap: 0.9rem;
        padding: 1rem 1.25rem;
        margin: 0.25rem 0 1rem;
        border: 1px solid rgba(49, 51, 63, 0.15);
        border-radius: 1rem;
        background: linear-gradient(115deg, rgba(255, 205, 86, 0.2), rgba(82, 196, 166, 0.13));
    }
    .quiz-mascot__face {
        font-size: 2.6rem;
        line-height: 1;
    }
    .quiz-mascot__copy {
        font-size: 1rem;
    }
    .quiz-mascot__copy strong {
        display: block;
        font-size: 1.1rem;
        margin-bottom: 0.15rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def setting(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except StreamlitSecretNotFoundError:
        return None


SUPABASE_URL = setting("SUPABASE_URL")
SUPABASE_KEY = setting("SUPABASE_KEY")
SUPABASE_DATABASE_URL = setting("SUPABASE_DATABASE_URL")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY.")
    st.stop()


def get_supabase_client() -> Client:
    if "supabase_client" not in st.session_state:
        st.session_state.supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return st.session_state.supabase_client


client = get_supabase_client()


def show_authentication() -> bool:
    if st.session_state.get("user_id"):
        with st.sidebar:
            st.success(f"Signed in as {st.session_state['user_email']}")
            if st.button("Sign out", use_container_width=True):
                client.auth.sign_out()
                for key in ("user_id", "user_email", "saved_queries"):
                    st.session_state.pop(key, None)
                for key in list(st.session_state):
                    if key.startswith(("query_", "result_")):
                        st.session_state.pop(key, None)
                st.rerun()
        return True

    st.title("📊 Economics SQL Quiz")
    st.write("Sign in or create an account to write and run SQL against the live database.")
    st.markdown(
        """
        <div class="quiz-mascot">
          <span class="quiz-mascot__face" role="img" aria-label="Professor Panda">🐼</span>
          <div class="quiz-mascot__copy">
            <strong>Professor Panda says: ready, set, SELECT!</strong>
            Sign in to explore the data and save your SQL work.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    sign_in_tab, sign_up_tab = st.tabs(["Sign in", "Create account"])

    with sign_in_tab:
        with st.form("sign_in_form"):
            email = st.text_input("Email", key="sign_in_email")
            password = st.text_input("Password", type="password", key="sign_in_password")
            sign_in = st.form_submit_button("Sign in", type="primary")
        if sign_in:
            try:
                response = client.auth.sign_in_with_password(
                    {"email": email.strip(), "password": password}
                )
                if response.user is None or response.session is None:
                    st.error("Supabase did not return a signed-in user session.")
                else:
                    st.session_state.user_id = response.user.id
                    st.session_state.user_email = response.user.email or email.strip()
                    st.rerun()
            except (AuthApiError, HTTPError) as error:
                st.error(f"Sign-in failed: {error}")

    with sign_up_tab:
        with st.form("sign_up_form"):
            new_email = st.text_input("Email", key="sign_up_email")
            new_password = st.text_input(
                "Password", type="password", key="sign_up_password"
            )
            sign_up = st.form_submit_button("Create account")
        if sign_up:
            try:
                response = client.auth.sign_up(
                    {"email": new_email.strip(), "password": new_password}
                )
                if response.session is None:
                    st.info("Account created. Check your email to confirm it, then sign in.")
                elif response.user is not None:
                    st.session_state.user_id = response.user.id
                    st.session_state.user_email = response.user.email or new_email.strip()
                    st.rerun()
            except (AuthApiError, HTTPError) as error:
                st.error(f"Could not create account: {error}")

    return False


if not show_authentication():
    st.stop()

st.title("🌍 Economics SQL Quiz")
st.write(
    "Write SQL for each question, run it against the live `economic_indicators` "
    "table, and compare your result with the expected output."
)
st.markdown(
    """
    <div class="quiz-mascot">
      <span class="quiz-mascot__face" role="img" aria-label="Professor Panda">🐼</span>
      <div class="quiz-mascot__copy">
        <strong>Professor Panda's data lab</strong>
        Five SQL challenges, live country data, and 20 points up for grabs. Keep
        queries curious and read-only!
      </div>
      <span class="quiz-mascot__face" role="img" aria-label="Sparkles">✨</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info("Five coding questions · 4 points each · 20 points total")

if not SUPABASE_DATABASE_URL:
    st.error(
        "The SQL runner is not configured. Add SUPABASE_DATABASE_URL using the "
        "Supabase Session pooler connection string with SSL enabled."
    )
    st.stop()

try:
    saved_rows = (
        client.table("quiz_saves")
        .select("question_number, sql_text")
        .eq("user_id", st.session_state.user_id)
        .execute()
        .data
    )
    saved_queries = {row["question_number"]: row["sql_text"] for row in saved_rows}
except (APIError, HTTPError) as error:
    st.error(f"Could not load your saved queries: {error}")
    st.stop()

question_labels = [
    f"Question {question['number']} · {question['points']} points"
    for question in QUESTIONS
]
selected_index = st.selectbox(
    "Choose a question",
    range(len(QUESTIONS)),
    format_func=lambda index: question_labels[index],
)
question = QUESTIONS[selected_index]
st.subheader(f"Question {question['number']} · {question['points']} points")
st.markdown(question["prompt"])
st.caption("🐼 Professor Panda's tip: run your query, inspect the rows, then save your solution.")

with st.expander("Hint: expected SQL and result"):
    st.code(question["sql"], language="sql")
    st.write("**Expected result**")
    st.dataframe(question["expected_rows"], use_container_width=True, hide_index=True)

query_key = f"query_{question['number']}"
if query_key not in st.session_state:
    st.session_state[query_key] = saved_queries.get(question["number"], "")

with st.form(f"query_form_{question['number']}"):
    query = st.text_area(
        "Your SQL query",
        key=query_key,
        height=220,
        placeholder="SELECT country\nFROM public.economic_indicators\nORDER BY country;",
    )
    run_query, save_query = st.columns(2)
    with run_query:
        run_clicked = st.form_submit_button("Run query", type="primary")
    with save_query:
        save_clicked = st.form_submit_button("Save query")

if run_clicked:
    try:
        columns, rows, truncated = run_read_only_query(SUPABASE_DATABASE_URL, query)
        st.session_state[f"result_{question['number']}"] = {
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
        }
    except ValueError as error:
        st.error(str(error))
    except PsycopgError as error:
        st.error(f"Query failed: {error}")

if save_clicked:
    if not query.strip():
        st.warning("Enter a SQL query before saving.")
    else:
        try:
            client.table("quiz_saves").upsert(
                {
                    "user_id": st.session_state.user_id,
                    "question_number": question["number"],
                    "sql_text": query,
                },
                on_conflict="user_id,question_number",
            ).execute()
            st.success("Your query was saved.")
        except (APIError, HTTPError) as error:
            st.error(f"Could not save your query: {error}")

result = st.session_state.get(f"result_{question['number']}")
if result is not None:
    st.subheader("Query result")
    st.dataframe(
        [dict(zip(result["columns"], row)) for row in result["rows"]],
        use_container_width=True,
        hide_index=True,
    )
    if result["truncated"]:
        st.warning("Showing the first 500 rows. Refine your query to see fewer results.")
