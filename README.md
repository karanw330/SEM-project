# Financial Clarity Web App

A modern, high-performance web version of the **Financial Clarity** expense tracker and tag manager application. Built with a **Python FastAPI** backend and a modern **Tailwind CSS + JavaScript (SPA)** frontend matching the Stitch Neo-Brutalist design system.

---

## 🌟 Features

- 📊 **Financial Dashboard**:
  - Month and time range selectors
  - Bento Grid summary cards (Total Spent, Top Expense)
  - Interactive SVG Donut Spending Breakdown Chart
  - Interactive Daily Trend Bar Chart (7-day history)
  - Untagged transactions review banner
  - Operations / Recent transactions list
- 📜 **History & Transactions**:
  - Instant search filtering by merchant name or notes
  - Filter pills for categories (All, Untagged, Food, Transport, Subscriptions, etc.)
  - Transactions grouped by date (TODAY, YESTERDAY, EARLIER)
  - Quick tag assignment and transaction deletion
- 🏷️ **Tag Manager**:
  - Custom category tags with names, emojis, and hex color codes
  - Transaction count and spending calculation per tag
  - Create, edit, and delete tags
- ⚡ **Auto-Tag Rules**:
  - Keyword-based auto-tagging rules (e.g., keyword `ZOMATO` -> tag `Food`)
  - One-click rule execution across existing untagged transactions
- 🌓 **Light & Dark Theme**: Toggle between light mode and dark mode with persistent settings.

---

## 📁 Directory Structure

```
web_app/
├── backend/
│   ├── main.py          # FastAPI application entry point & routes
│   ├── database.py      # SQLite database engine configuration
│   ├── models.py        # SQLAlchemy ORM models (Transaction, Tag, AutoTagRule)
│   ├── schemas.py       # Pydantic validation schemas
│   ├── crud.py          # Database operations & dashboard analytics calculation
│   ├── seed_data.py     # Default tags, rules, and demo transactions seeder
│   ├── requirements.txt # Python dependencies
│   └── expense_tracker.db # SQLite Database file (created on launch)
├── frontend/
│   ├── index.html       # Single Page Application HTML structure
│   ├── css/
│   │   └── styles.css   # Modern Tailwind CSS & chart styling
│   └── js/
│       ├── api.js       # Frontend API client
│       └── app.js       # SPA tab router, state management & DOM renderer
└── run.py               # Application runner script
```

---

## 🚀 How to Run

### 1. Install Dependencies
```bash
cd web_app/backend
pip install -r requirements.txt
```

### 2. Start Application
From the `web_app` directory, run:
```bash
python run.py
```
Or directly from `web_app/backend`:
```bash
python main.py
```

The FastAPI backend will launch on `http://127.0.0.1:8000` and automatically serve the web application frontend at `http://127.0.0.1:8000`.

---

## 🧪 White-Box Testing (Selenium + Python)

The `tests/` folder holds an automated white-box test suite (Assignment 7). Selenium drives the real app in Chrome along code paths chosen from the source code: statement, branch, condition (MC/DC), path and loop coverage. Meanwhile the backend runs under **coverage.py** to measure which statements and branches were executed.

```bash
pip install -r requirements-test.txt
pytest                         # runs headless Chrome; prints the backend coverage table at the end
HEADLESS=0 pytest -k p02       # watch a single test in a visible browser
```

- The tests start their own server on a free port with a **temporary database**, so your `expense_tracker.db` is never touched.
- HTML coverage report: `tests/reports/coverage_html/index.html`
- Test design (control-flow graphs, cyclomatic complexity, test-case table, defects found): [`tests/WHITE_BOX_TEST_PLAN.md`](tests/WHITE_BOX_TEST_PLAN.md)

| Test file | Technique |
|---|---|
| `test_wb_01_statement_coverage.py` | Statement coverage |
| `test_wb_02_branch_coverage.py` | Branch / decision coverage |
| `test_wb_03_condition_coverage.py` | Condition coverage + MC/DC |
| `test_wb_04_path_coverage.py` | Basis-path coverage |
| `test_wb_05_loop_testing.py` | Loop testing (0, 1, n-1, n, n+1) |

### Code-level white-box tests (no browser)

`tests/whitebox/` has 96 pytest tests that call the backend functions and API routes directly. They take about 2 seconds and reach **98% statement + branch coverage**. Report: [`tests/WHITE_BOX_UNIT_REPORT.md`](tests/WHITE_BOX_UNIT_REPORT.md).

```bash
pytest tests/whitebox --cov=backend --cov-branch --cov-report=term-missing
```

Optional environment variables: `CHROME_BINARY` (custom Chrome path), `CHROMEDRIVER_PATH` (custom driver; otherwise Selenium Manager finds one), `HEADLESS=0`, `NO_COVERAGE=1`.
