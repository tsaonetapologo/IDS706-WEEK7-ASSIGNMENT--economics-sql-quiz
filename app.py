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

from quiz import (
    COUNTRY_FLAGS,
    QUESTIONS,
    add_country_flags,
    results_match_expected,
    run_read_only_query,
)


ANSWER_REVEAL_ATTEMPTS = 3

st.set_page_config(page_title="Economics SQL Quiz", page_icon="📊", layout="wide")
st.markdown(
    """
    <style>
    .economist-guide {
        display: flex;
        align-items: center;
        gap: 1.15rem;
        padding: 1rem 1.25rem;
        margin: 0.75rem 0 1rem;
        border: 1px solid rgba(49, 51, 63, 0.15);
        border-radius: 1rem;
        background: linear-gradient(115deg, rgba(40, 95, 168, 0.12), rgba(255, 255, 255, 0.72));
    }
    .economist-guide__portrait {
        width: 100px;
        min-width: 100px;
        height: 126px;
    }
    .economist-guide__copy {
        font-size: 0.98rem;
    }
    .economist-guide__copy strong {
        display: block;
        font-size: 1.15rem;
        margin-bottom: 0.25rem;
    }
    .country-flag-strip {
        display: flex;
        justify-content: space-around;
        align-items: center;
        gap: 0.5rem;
        overflow: hidden;
        padding: 0.7rem 0.9rem;
        margin: 0.7rem 0 0.9rem;
        border: 1px solid rgba(40, 95, 168, 0.13);
        border-radius: 0.9rem;
        background: linear-gradient(110deg, rgba(40, 95, 168, 0.08), rgba(255, 255, 255, 0.55));
    }
    .country-flag-strip span {
        font-size: clamp(1.15rem, 3vw, 1.8rem);
        line-height: 1;
        filter: saturate(0.82);
    }
    .country-flag-strip__label {
        display: block;
        margin-top: -0.45rem;
        margin-bottom: 0.8rem;
        color: rgba(49, 51, 63, 0.68);
        font-size: 0.82rem;
    }
    @media (max-width: 480px) {
        .economist-guide {
            gap: 0.65rem;
            padding: 0.8rem;
        }
        .economist-guide__portrait {
            width: 78px;
            min-width: 78px;
            height: 108px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

ECONOMIST_GUIDE = """
<div class="economist-guide">
  <svg class="economist-guide__portrait" viewBox="0 0 100 126"
       role="img" aria-labelledby="economist-title" xmlns="http://www.w3.org/2000/svg">
    <title id="economist-title">Illustration of a young Black economist with an afro, wearing a blue, black, and white dress</title>
    <circle cx="50" cy="50" r="43" fill="#e7f0fc"/>
    <path d="M32 59c-7-3-10-10-7-17-6-7-4-16 3-21-1-9 7-16 15-14 5-8 16-8 21-1 9-2 17 5 16 14 8 5 10 14 4 21 3 8-1 15-8 18l-7-3H37z" fill="#171717"/>
    <circle cx="34" cy="27" r="2.2" fill="#302b2b"/>
    <circle cx="43" cy="19" r="2" fill="#302b2b"/>
    <circle cx="54" cy="17" r="2.2" fill="#302b2b"/>
    <circle cx="65" cy="21" r="2" fill="#302b2b"/>
    <circle cx="73" cy="30" r="2.2" fill="#302b2b"/>
    <ellipse cx="51" cy="43" rx="19" ry="23" fill="#75452f"/>
    <path d="M33 34c4-11 12-16 20-16 9 0 15 4 19 12-7-2-12-5-15-10-7 7-15 11-24 14z" fill="#171717"/>
    <path d="M42 43h5m10 0h5" stroke="#211915" stroke-width="2" stroke-linecap="round"/>
    <path d="M47 53c3 2 6 2 9 0" fill="none" stroke="#512b22" stroke-width="1.7" stroke-linecap="round"/>
    <path d="M38 66l-8 7-8 26 9 3 9-17 1 34h39l-1-34 9 17 8-4-10-27-13-8-12-3H49z" fill="#285fa8"/>
    <path d="M48 63l3 8-9 8 8 15 3 25h19l-2-28 7-12-11-8 2-8-10 5z" fill="#fff" stroke="#17202b" stroke-width="1"/>
    <path d="M70 65l13 8 8 26-9 4-9-17 1 32H69l-3-24 7-18-9-8z" fill="#171717"/>
    <path d="M50 71l5 4 5-4" fill="none" stroke="#285fa8" stroke-width="2"/>
    <path d="M21 102l9 3m58-3-9 3" stroke="#75452f" stroke-width="4" stroke-linecap="round"/>
    <path d="M43 119h36" stroke="#17202b" stroke-width="2"/>
  </svg>
  <div class="economist-guide__copy">
      <strong>Meet your economist &amp; data-scientist guide</strong>
      Your 25-year-old Black guide rocks a natural afro and a blue, black, and white
      dress, and is here to cheer you on through the data lab. 📈
  </div>
</div>
"""

COUNTRY_FLAG_STRIP = (
    '<div class="country-flag-strip" role="img" aria-label="Flags of the countries '
    'in the economics dataset">'
    + "".join(
        f'<span title="{country}" aria-hidden="true">{flag}</span>'
        for country, flag in COUNTRY_FLAGS.items()
    )
    + "</div>"
    '<div class="country-flag-strip__label">Exploring 10 economies across Africa and the Indian Ocean</div>'
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
                    if key.startswith(("query_", "result_", "attempt_", "answer_")):
                        st.session_state.pop(key, None)
                st.rerun()
        return True

    st.title("📊 Economics SQL Quiz")
    st.write("Sign in or create an account to write and run SQL against the live database.")
    st.markdown(
        ECONOMIST_GUIDE,
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
st.markdown(ECONOMIST_GUIDE, unsafe_allow_html=True)
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
st.markdown(COUNTRY_FLAG_STRIP, unsafe_allow_html=True)
st.markdown(question["prompt"])
st.caption("Your economist guide's tip: run your query, inspect the rows, then save your solution.")

with st.expander("Hint: expected result"):
    st.write("**Expected result**")
    st.dataframe(
        add_country_flags(question["expected_rows"]),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Country flags are display-only; write SQL using the database column values.")

query_key = f"query_{question['number']}"
attempt_key = f"attempt_{question['number']}"
answer_key = f"answer_visible_{question['number']}"
if query_key not in st.session_state:
    st.session_state[query_key] = saved_queries.get(question["number"], "")
if attempt_key not in st.session_state:
    st.session_state[attempt_key] = 0

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
    st.session_state[attempt_key] += 1
    st.session_state.pop(f"result_{question['number']}", None)
    try:
        columns, rows, truncated = run_read_only_query(SUPABASE_DATABASE_URL, query)
        st.session_state[f"result_{question['number']}"] = {
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "correct": results_match_expected(
                columns, rows, question["expected_rows"]
            ),
        }
    except ValueError as error:
        st.error(str(error))
    except PsycopgError as error:
        st.error(f"Query failed: {error}")

attempts = st.session_state[attempt_key]
if attempts < ANSWER_REVEAL_ATTEMPTS:
    st.caption(
        f"Run {ANSWER_REVEAL_ATTEMPTS - attempts} more "
        f"{'query' if ANSWER_REVEAL_ATTEMPTS - attempts == 1 else 'queries'} "
        "to unlock the correct answer."
    )

show_answer = st.button(
    "Show correct answer",
    key=f"show_answer_{question['number']}",
    disabled=attempts < ANSWER_REVEAL_ATTEMPTS,
)
if show_answer:
    st.session_state[answer_key] = True

if st.session_state.get(answer_key):
    st.subheader("Correct answer")
    st.code(question["sql"], language="sql")
    st.write("**Expected result**")
    st.dataframe(
        add_country_flags(question["expected_rows"]),
        use_container_width=True,
        hide_index=True,
    )

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
    if result["correct"]:
        st.success("Correct! Your query returns the expected result.")
    else:
        st.warning("Not quite yet. Review the result and try another query.")
    result_rows = [dict(zip(result["columns"], row)) for row in result["rows"]]
    if result_rows and "country" in result_rows[0]:
        result_rows = add_country_flags(result_rows)
    st.dataframe(
        result_rows,
        use_container_width=True,
        hide_index=True,
    )
    if result["truncated"]:
        st.warning("Showing the first 500 rows. Refine your query to see fewer results.")
