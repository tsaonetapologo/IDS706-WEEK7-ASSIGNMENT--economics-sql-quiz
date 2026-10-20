# Economics SQL Quiz

**Quiz site:** https://ids706-week7-assignment--economics-sql-quiz-cdqjbyzzrxtpiyyepq.streamlit.app/

This project is a Streamlit SQL lab backed by a hosted Supabase PostgreSQL
database. Students create an account or sign in, write a query for one of five
economics questions, run it against the live `economic_indicators` table, see
the result rows, and save their SQL for later. Each question is worth 4 points,
for 20 points total.

## Stack and access controls

- **Hosted database and authentication:** Supabase PostgreSQL and Supabase Auth.
- **Web app:** Streamlit.
- **Database driver:** psycopg connects through Supabase's **Session pooler**
  using TLS (`sslmode=require`).
- **GitHub Actions:** `.github/workflows/database-check.yml` verifies that the
  hosted table can be queried using a repository secret.
- Only signed-in users can run or save queries. Supabase row-level security
  restricts saved queries to their owner.
- The SQL runner accepts exactly one parsed `SELECT`, switches to the
  `quiz_reader` database role, opens a read-only transaction, applies a
  five-second timeout, and limits displayed results to 500 rows.

## Supabase setup

1. Create a Supabase project. In **Authentication → Providers**, enable email
   sign-up. For a classroom deployment, either configure email delivery so
   students can confirm accounts or disable email confirmation for the class.
2. In **Project Settings → API**, copy the project URL and its publishable key
   (or legacy anon key). The app uses this key for Supabase Auth and the
   row-level-security-protected `quiz_saves` table. Do not use a service-role
   key in the app.
3. In the Supabase SQL Editor, run [`schema.sql`](./schema.sql). It creates and
   seeds the economics table, creates the private save table and its
   owner-only policy, and configures the restricted query role. The supplied
   data contains 10 countries.
4. In **Database → Connect**, select the **Session pooler** (not Direct
   connection) and copy its PostgreSQL URI. Put the database password in that
   URI and ensure it has `sslmode=require`. The connection must be able to
   `SET ROLE quiz_reader`; the setup SQL grants that membership to the
   Supabase `postgres` login.

## Run locally

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with the Supabase project URL, publishable/anon key, and the
Session pooler database URI:

```dotenv
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-publishable-or-anon-key
SUPABASE_DATABASE_URL=postgresql://postgres.your-project-ref:YOUR_DB_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

Keep `.env` private; `.gitignore` excludes it. Start the app:

```sh
streamlit run app.py
```

Open the local URL printed by Streamlit, create an account or sign in, choose a
question, write SQL, and select **Run query** to see live database rows.
**Save query** stores that question's SQL under the signed-in user's account.
Use the hint expander to preview the expected result. Each question allows three
query attempts; after the third, query submission is locked. Click **Show correct
answer** to reveal the example SQL and expected result.

Run the local test suite with:

```sh
python -m unittest discover -s tests -v
```

## GitHub Actions

1. Push this project to a GitHub repository.
2. In **Settings → Secrets and variables → Actions**, add a repository secret
   named `SUPABASE_DATABASE_URL`. Its value is the same Session pooler URI used
   locally, with `sslmode=require`. Do not put the password in workflow YAML,
   source files, or commit history.
3. Push a commit or use **Actions → Hosted database check → Run workflow**.
   A successful job reports that the connection and `quiz_reader` access work.

The workflow deliberately tests with the restricted `quiz_reader` role, not
with a superuser query path.

## Deploy the quiz site

1. Push the project to GitHub and sign in to Streamlit Community Cloud.
2. Create an app from the repository, selecting `app.py` as the entry point.
3. In the app's **Settings → Secrets**, add the three settings in TOML form:

   ```toml
   SUPABASE_URL = "https://your-project-ref.supabase.co"
   SUPABASE_KEY = "your-publishable-or-anon-key"
   SUPABASE_DATABASE_URL = "postgresql://postgres.your-project-ref:YOUR_DB_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require"
   ```

4. After the app deploys, replace the **Quiz site** line at the top of this
   README with the actual public URL. Submit the GitHub repository URL.

## Quiz questions

All questions require writing SQL; none are multiple choice. They cover
sorting, filtering, aggregation, counting, and population thresholds. Students
can compare their result with the expected rows, and reveal the example SQL
after three attempts at a question. Further query submissions are locked after
the third attempt.
