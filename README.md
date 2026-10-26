# Gira Perimi — API

FastAPI backend for **Gira Perimi**, a Kinyarwanda platform for learning Rwanda's road-traffic rules and practising
the provisional driving-licence theory exam.

- Question bank of **404 official exam questions** (399 used in exams), extracted verbatim from the
  question booklet, with their original images.
- **16 lessons** written from Iteka rya Perezida n° 85/01 (traffic code) and Itegeko n° 014/2026 (new road-traffic law).
- **166 road signs and markings** (categories A–F) cropped from the code's annexes.
- **An explanation for every question** (why the answer is right, and the article of law it rests on), editable by
  admins.
- **Spaced review** ("Isubiramo"): mistakes and unknown signs come back after 1, 3, 7, 14 and 30 days.
- **Study plan**: exam date, daily goal, streak, today's checklist, and opt-in daily reminder emails.
- **Offline study**: an offline copy of the bank for the installable app, and safe syncing of answers given offline.
- Google sign-in for learners, email + password sign-in for admins, progress tracking, readiness recommendation,
  admin dashboard, and a paywall hook for future subscriptions.

Stack: Python 3.12 · FastAPI · SQLAlchemy 2 (async) · SQLite (aiosqlite) · Alembic · Pydantic v2 · PyJWT · bcrypt · google-auth.

## Quick start

```bash
uv sync                                   # install dependencies
cp .env.example .env                      # then edit SECRET_KEY / GOOGLE_CLIENT_ID
uv run alembic upgrade head               # create the SQLite database
uv run python -m app.cli create-admin --email you@example.com --name "Your Name"
uv run fastapi dev app/main.py            # http://127.0.0.1:8000  (Swagger UI at /docs)
```

The frontend (`gira-perimi-fe`) proxies `/api/*` and `/media/*` to this server, so session cookies stay first-party.
`FRONTEND_ORIGINS` must list the site's exact origin (scheme + host + port): state-changing requests from any other
origin are rejected with `403` as a CSRF safeguard.

### Google sign-in (learners)

Learners register and sign in **only** with Google; there is no learner email/password form.

1. Open [Google Cloud Console → Google Auth Platform](https://console.cloud.google.com/auth/overview) and create a
   project if you have none.
2. *Branding*: set the app name (Gira Perimi), support email and, for production, your domain.
   *Audience*: choose **External**. While the app is in *Testing*, only the test users you list can sign in; click
   **Publish app** to open it to every Gmail account (basic scopes — email, profile, openid — need no Google review).
3. *Clients → Create client* → **Web application**. Under **Authorized JavaScript origins** add every origin the site
   is opened from: `http://localhost:3000` **and** `http://localhost` for development, plus `https://your-domain`.
   No redirect URI is needed (the button uses a popup).
4. Copy the client ID into `GOOGLE_CLIENT_ID` in `.env` and restart the API. The frontend reads it from
   `GET /api/v1/auth/config`; nothing needs to change there.

Open the site at `http://localhost:3000`, not `http://127.0.0.1:3000`, unless that origin is also authorized.
Changes to the origins can take a few minutes to reach Google's servers.

The browser receives a Google ID token; the API verifies its signature, audience, issuer and expiry (10 s clock skew
allowed), requires a verified email, then creates the account on first sign-in (registration) or signs the learner in.
Returning learners are matched by their Google account id, then by email. Name and photo come from Google.
`POST /auth/google` answers `401` for an invalid token and `503` when Google sign-in is not configured or Google's
signing keys cannot be fetched (the error log then says why). On hosts that only reach the internet through a proxy,
set `OUTBOUND_PROXY` — on PythonAnywhere free accounts, `OUTBOUND_PROXY=http://proxy.server:3128`.

### Admin accounts

Admins never use Google: email + password is the admin-only sign-in. Create or reset one with the CLI (the password is
prompted, or read from `GP_ADMIN_PASSWORD`):

```bash
uv run python -m app.cli create-admin --email you@example.com --name "Your Name"
uv run python -m app.cli list-admins
```

Admin sign-in is rate limited (5 failed attempts per 15 minutes per IP and per email). The website never links to
the admin sign-in page: it lives at a private URL set by `ADMIN_LOGIN_PATH` in the frontend (see its README).
In production the OpenAPI schema and Swagger UI are switched off, so the admin API is not advertised either.

## Learning features

### Explanations

Defaults ship in `app/data/explanations.json` (`{"<question id>": {"text": "...", "law": "..."}}`), one per active
question; a test fails if a question is left without one. They were drafted from Iteka rya Perezida n° 85/01 and Itegeko
n° 014/2026, follow the booklet's answer key, and cite the article only where the text supports it. Admins review and
edit them in the admin area (*Ibisobanuro*); an edit is stored in `question_explanations` and wins over the default,
and "reset" brings the default back. Explanations appear after a practice answer, in review, in the landing-page demo
and in a finished exam's review — never while an exam is running.

### Spaced review (Leitner boxes)

A wrong answer — in practice, review, a finished exam, or a "Sinari nkizi" sign flashcard — puts the item in box 1,
due at the start of the next Kigali day. Recalling a **due** item correctly moves it up a box (due after 1, 3, 7, 14,
30 days); recalling it in box 5 masters it. Answering correctly before it is due changes nothing. `GET /review`
returns up to 20 due items; question answers go through `POST /practice/answers`, sign results through
`POST /review/signs`.

### Study plan and reminders

Learners set an exam date and a daily question goal (`PATCH /me`). The dashboard turns them into a pace
(`on_track` / `tight` / `today` / `passed`), a mock-exam rhythm and today's checklist.

Reminder emails are opt-in and off until SMTP is configured (`SMTP_HOST`, `SMTP_FROM`, usually `SMTP_USERNAME` and
`SMTP_PASSWORD`; `SITE_URL` builds the links). Run the sender once a day, e.g. 18:00 Kigali = 16:00 UTC:

```bash
uv run python -m app.cli send-reminders --dry-run   # who would be reminded
uv run python -m app.cli send-reminders
```

It emails learners who switched reminders on, have not reached today's goal and were not reminded today. Every email
has a one-click unsubscribe link (`List-Unsubscribe` + `POST /reminders/unsubscribe`, RFC 8058). With Gmail use
`SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587` and an *app password* (Google account → Security → App passwords).

### Offline study

`GET /offline/pack` returns every active question with its answer and explanation, versioned by content hash, for the
frontend's offline mode. Answers given offline come back through `POST /practice/answers/offline`: each carries a
`client_id`, so a retried sync never saves an answer twice, and its original time (up to 60 days old) keeps streaks
and daily goals right.

## Rules implemented

| Rule | Value | Setting |
|---|---|---|
| Questions per mock exam | 20, drawn at random, no duplicates | `EXAM_QUESTION_COUNT` |
| Time limit | 20 minutes, enforced by the server; unanswered time-outs are graded with saved answers | `EXAM_DURATION_MINUTES` |
| Pass mark | 12/20 (60%) | `EXAM_PASS_MARK` |
| Readiness recommendation | **more than 10** completed exams **and** average **above 15/20** | `READINESS_MIN_EXAMS`, `READINESS_MIN_AVERAGE` |

Exam format source: Rwanda National Police (20 questions, 20 minutes, 60% to pass).

## API overview (`/api/v1`)

| Area | Endpoints |
|---|---|
| Auth | `GET /auth/config`, `POST /auth/google`, `POST /auth/logout`, `GET /auth/me` |
| Public content | `GET /overview`, `/topics`, `/lessons`, `/lessons/{slug}`, `/signs`, `/questions/sample` |
| Mock exams | `POST /exams` (start or resume), `GET /exams`, `GET /exams/{id}`, `PUT /exams/{id}/answers/{position}`, `POST /exams/{id}/submit` |
| Practice | `GET /practice/questions?topic=&mode=random\|new\|mistakes&count=`, `POST /practice/answers`, `POST /practice/answers/offline` |
| Review | `GET /review`, `POST /review/signs` |
| Offline | `GET /offline/pack` |
| Learner | `GET /me/dashboard`, `PATCH /me` (phone, exam date, daily goal, reminders), `DELETE /me`, `PUT\|DELETE /me/lessons/{slug}` |
| Reminders | `POST /reminders/unsubscribe?token=` (public, signed token) |
| Admin | `POST /admin/auth/login`, `POST /admin/auth/logout`, `GET /admin/auth/me`, `GET /admin/stats`, `GET /admin/users`, `GET\|PATCH\|DELETE /admin/users/{id}`, `GET /admin/questions`, `PUT\|DELETE /admin/questions/{id}/explanation` |

Images are served from `/media/questions/*` and `/media/signs/*`.

## Content

| Path | What it is |
|---|---|
| `app/data/questions.json` | Question bank: text, options, answer index, topic, image names, `active` flag |
| `app/data/signs.json` | Sign catalogue (code, category, name, description) |
| `app/data/explanations.json` | Default explanation and law reference per question |
| `app/content/lessons/*.md` | Lessons in a small Markdown dialect (see `app/services/lesson_parser.py`) |
| `media/` | WebP images for questions and signs |

Notes on the question bank:

- Answer keys are kept exactly as marked in the booklet.
- Booklet question 390 marks every option as correct, so it is kept but excluded from exams and practice.
- Four questions that are exact duplicates of earlier ones (booklet 176, 178, 212, 378) are excluded so a learner never
  sees the same question twice in one exam.

To edit a lesson, change its Markdown file and restart the API; broken sign references fail at startup.

### Rebuilding the question bank from the PDFs

`scripts/content/` holds the one-off extraction pipeline (PyMuPDF + Pillow, installed with `uv sync --group content`).
Each script reads untrusted PDFs, so run them with `python -I` and paths outside the repository:

```bash
uv run python -I scripts/content/extract_qa.py questions.pdf out/
uv run python -I scripts/content/parse_qa.py out/
uv run python -I scripts/content/render_images.py questions.pdf out/
cp scripts/content/topic_overrides.json out/
uv run python -I scripts/content/build_bank.py out/ app/data/questions.json media/questions/
uv run python -I scripts/content/extract_signs.py gazette.pdf signs/
uv run python -I scripts/content/build_signs.py signs/ app/data/signs.json media/signs/
```

Manual fixes found while reviewing the contact sheets are encoded in `build_bank.py` and `build_signs.py`.

## Deploying an update

```bash
git pull                     # or upload the changed files
uv sync --no-dev
uv run alembic upgrade head  # 0002 adds review_items, question_explanations and the study-plan columns
```

Then reload the web app. On PythonAnywhere: `pa website reload --domain <your domain>`, and add a daily *Scheduled
task* (16:00 UTC) running `cd ~/gira-perimi-be && .venv/bin/python -m app.cli send-reminders` once SMTP is set up.

## Subscriptions (future)

`users.plan` / `users.plan_expires_at` already exist. Set `PAYWALL_ENABLED=true` and mock exams, practice and every
lesson not marked `free: true` answer `402 Payment Required` for learners without an active premium plan.
Admins can switch a learner's plan from the admin dashboard (`PATCH /admin/users/{id}`).

## Tests and linting

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Production checklist

- `ENVIRONMENT=production`, a random `SECRET_KEY` (≥ 32 chars), real `GOOGLE_CLIENT_ID` and `FRONTEND_ORIGINS`.
- Serve over HTTPS (cookies become `Secure` automatically); `/docs` is disabled in production.
- Run `uv run alembic upgrade head` on every deploy and back up the SQLite file.
- The admin login rate limiter is in-process: run a single API worker, or move it to a shared store.
