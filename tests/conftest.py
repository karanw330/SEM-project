"""
Shared fixtures for the Selenium white-box test suite.

What this sets up
-----------------
* A real FastAPI/uvicorn server for the app, started on a free port and
  pointed at a throwaway SQLite file (FC_DB_PATH) so the developer's
  expense_tracker.db is never touched.
* The server runs under coverage.py with branch measurement, so every
  Selenium session also produces statement + branch coverage of the
  backend (backend/*.py). This is the "white-box" evidence: which
  statements/branches of the source our UI-driven tests actually executed.
* A headless Chrome WebDriver (Selenium 4).
* `api` - a tiny HTTP helper used to arrange test data directly through
  the REST API (so each test only drives the UI for the path under test).
* `app` - a page helper with waits and access to the SPA's internal
  `state` object (white-box inspection of the frontend).

Environment variables (all optional)
------------------------------------
  CHROME_BINARY      path to a Chrome/Chromium binary
  CHROMEDRIVER_PATH  path to a matching chromedriver (else Selenium Manager)
  HEADLESS=0         show the browser window while tests run
  NO_COVERAGE=1      run the server without coverage.py
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import pytest
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoAlertPresentException,
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(TESTS_DIR, "reports")

DEFAULT_WAIT = 10


# --------------------------------------------------------------------------
# Backend server (under coverage.py)
# --------------------------------------------------------------------------

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url, proc, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Backend server exited early (code %s)" % proc.returncode)
        try:
            urllib.request.urlopen(url + "/api/tags", timeout=1)
            return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.25)
    raise RuntimeError("Backend server did not start within %ss" % timeout)


def _use_coverage():
    if os.environ.get("NO_COVERAGE") == "1":
        return False
    try:
        import coverage  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    tmp_dir = tempfile.mkdtemp(prefix="fc_selenium_")
    env = dict(os.environ)
    env["FC_DB_PATH"] = os.path.join(tmp_dir, "test_expense_tracker.db")
    env["PYTHONUNBUFFERED"] = "1"

    os.makedirs(REPORTS_DIR, exist_ok=True)
    coverage_on = _use_coverage()
    cov_data = os.path.join(REPORTS_DIR, ".coverage")

    uvicorn_args = ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)]
    if coverage_on:
        cmd = [
            sys.executable, "-m", "coverage", "run",
            "--branch",
            "--source", BACKEND_DIR,
            "--data-file", cov_data,
        ] + uvicorn_args
    else:
        cmd = [sys.executable] + uvicorn_args

    log_path = os.path.join(REPORTS_DIR, "server.log")
    log = open(log_path, "w")
    proc = subprocess.Popen(cmd, cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = "http://127.0.0.1:%d" % port
    try:
        _wait_for_server(url, proc)
    except Exception:
        proc.kill()
        log.close()
        print(open(log_path).read())
        raise

    yield url

    # SIGINT lets uvicorn shut down cleanly so coverage.py writes its data file
    if sys.platform == "win32":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)

    if coverage_on and os.path.exists(cov_data):
        html_dir = os.path.join(REPORTS_DIR, "coverage_html")
        base = [sys.executable, "-m", "coverage"]
        report = subprocess.run(base + ["report", "-m", "--data-file", cov_data], cwd=BACKEND_DIR,
                                capture_output=True, text=True).stdout
        subprocess.call(base + ["html", "-d", html_dir, "--data-file", cov_data], cwd=BACKEND_DIR,
                        stdout=subprocess.DEVNULL)
        _COVERAGE_SUMMARY.append(report + "HTML report: %s\n" % os.path.join(html_dir, "index.html"))


_COVERAGE_SUMMARY = []


def pytest_terminal_summary(terminalreporter):
    if _COVERAGE_SUMMARY:
        terminalreporter.section("Backend white-box coverage (statement + branch)")
        terminalreporter.write(_COVERAGE_SUMMARY[0])


# --------------------------------------------------------------------------
# REST helper for arranging test data
# --------------------------------------------------------------------------

class Api:
    def __init__(self, base_url):
        self.base_url = base_url

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def reset(self):
        return self.request("POST", "/api/seed")

    def create_tag(self, name, emoji="🏷️", color_hex="#667EEA"):
        status, body = self.request("POST", "/api/tags", {"name": name, "emoji": emoji, "color_hex": color_hex})
        assert status == 201, body
        return body

    def create_tx(self, amount, account_name, tx_type="DEBIT", tag_id=None, raw_message="", timestamp=None):
        payload = {"amount": amount, "type": tx_type, "account_name": account_name,
                   "raw_message": raw_message, "tag_id": tag_id}
        if timestamp is not None:
            payload["timestamp"] = timestamp
        status, body = self.request("POST", "/api/transactions", payload)
        assert status == 201, body
        return body

    def create_rule(self, keyword, tag_id=None, is_ignore_rule=False):
        return self.request("POST", "/api/rules",
                            {"account_keyword": keyword, "tag_id": tag_id, "is_ignore_rule": is_ignore_rule})

    def transactions(self, **params):
        qs = "&".join("%s=%s" % (k, v) for k, v in params.items())
        return self.request("GET", "/api/transactions" + ("?" + qs if qs else ""))[1]

    def stats(self):
        return self.request("GET", "/api/dashboard/stats")[1]


@pytest.fixture
def api(base_url):
    client = Api(base_url)
    client.reset()  # every test starts from an empty database
    return client


# --------------------------------------------------------------------------
# WebDriver
# --------------------------------------------------------------------------

def _find_chrome_binary():
    if os.environ.get("CHROME_BINARY"):
        return os.environ["CHROME_BINARY"]
    # Pre-installed Playwright Chromium (cloud/CI containers)
    candidate = "/opt/pw-browsers/chromium"
    return candidate if os.path.exists(candidate) else None


@pytest.fixture(scope="session")
def driver():
    options = webdriver.ChromeOptions()
    if os.environ.get("HEADLESS", "1") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")  # desktop layout (md: breakpoint)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    binary = _find_chrome_binary()
    if binary:
        options.binary_location = binary

    service = Service(executable_path=os.environ["CHROMEDRIVER_PATH"]) if os.environ.get("CHROMEDRIVER_PATH") else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.implicitly_wait(0)
    yield drv
    drv.quit()


# --------------------------------------------------------------------------
# Page helper
# --------------------------------------------------------------------------

class App:
    """Thin page-object over the SPA with white-box access to its JS `state`."""

    def __init__(self, driver, base_url):
        self.d = driver
        self.base_url = base_url
        self.wait = WebDriverWait(driver, DEFAULT_WAIT)

    # --- navigation / loading ---
    def open(self):
        self.d.get(self.base_url + "/")
        # loadAllData() has finished once the dashboard stats are in `state`
        self.wait.until(lambda d: d.execute_script(
            "return typeof state !== 'undefined' && state.dashboardStats !== null"))
        # Count in-flight loadAllData() calls so tests can wait until the UI has
        # finished re-rendering (see idle()).
        self.d.execute_script("""
            if (!window.__fcWrapped) {
              window.__fcPending = 0;
              const original = window.loadAllData;
              window.loadAllData = async function () {
                window.__fcPending++;
                try { return await original.apply(this, arguments); }
                finally { window.__fcPending--; }
              };
              window.__fcWrapped = true;
            }""")
        return self

    def idle(self):
        """Wait until no loadAllData() refresh is running."""
        self.wait.until(lambda d: d.execute_script("return (window.__fcPending || 0) === 0;"))

    def reload_data(self):
        """Re-run the app's own loadAllData() and wait for it to resolve."""
        self.d.execute_async_script("const done = arguments[0]; loadAllData().then(() => done(true));")

    def state(self, expr):
        """Read a value from the frontend's internal `state` object."""
        return self.d.execute_script("return state.%s;" % expr)

    def js(self, script, *args):
        return self.d.execute_script(script, *args)

    # --- element helpers ---
    def el(self, css):
        return self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

    def els(self, css):
        return self.d.find_elements(By.CSS_SELECTOR, css)

    def text(self, css):
        return self.el(css).get_attribute("textContent").strip()

    def has_class(self, css, cls):
        return cls in (self.el(css).get_attribute("class") or "").split()

    def click(self, target):
        """Real click when the element is interactable, JS click otherwise
        (e.g. when the Tailwind CDN is unreachable and layout is unstyled)."""
        el = self.el(target) if isinstance(target, str) else target
        self.d.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        try:
            el.click()
        except (ElementClickInterceptedException, ElementNotInteractableException):
            self.d.execute_script("arguments[0].click();", el)

    def type(self, css, value, clear=True):
        el = self.el(css)
        if clear:
            self.d.execute_script("arguments[0].value = '';", el)
        el.send_keys(value)

    def select(self, css, value):
        el = self.el(css)
        try:
            Select(el).select_by_value(str(value))
        except (ElementNotInteractableException, ElementClickInterceptedException):
            self.d.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", el, str(value))

    def set_value(self, css, value):
        """Set an input's value via JS (chromedriver cannot type emoji)."""
        self.d.execute_script("arguments[0].value = arguments[1];", self.el(css), value)

    def upload(self, css, path):
        """Send a file to a (visually hidden) <input type=file>."""
        el = self.el(css)
        self.d.execute_script("arguments[0].classList.remove('hidden'); arguments[0].style.display='block';", el)
        el.send_keys(path)

    def switch_tab(self, tab):
        self.click('nav.md\\:flex .nav-tab[data-tab="%s"]' % tab)
        self.wait.until(lambda d: not self.has_class("#view-%s" % tab, "hidden"))

    def submit(self, form_id):
        self.click("#%s button[type=submit]" % form_id)

    # --- toasts & dialogs ---
    # Toasts are replaced whenever a new one is shown, so read text + style in a
    # single JS call; holding a WebElement here can raise StaleElementReferenceException.
    _TOAST_JS = ("const t=document.getElementById('app-toast');"
                 "return t ? [t.textContent.trim(), t.classList.contains('bg-rose-600')] : null;")

    def toast(self):
        return tuple(self.wait.until(lambda d: d.execute_script(self._TOAST_JS)))

    def wait_toast(self, contains):
        return tuple(self.wait.until(lambda d: (lambda t: t if t and contains in t[0] else None)(
            d.execute_script(self._TOAST_JS))))

    def answer_confirm(self, accept=True):
        alert = self.wait.until(EC.alert_is_present())
        alert.accept() if accept else alert.dismiss()

    def no_alert(self):
        try:
            self.d.switch_to.alert
            return False
        except NoAlertPresentException:
            return True

    def until(self, fn, msg=""):
        return self.wait.until(lambda d: fn(), msg)

    # --- UI workflows reused across tests ---
    def add_transaction_ui(self, amount, account, tx_type="DEBIT", notes="", tag_id=None):
        self.click("#fab-add-tx")
        self.until(lambda: not self.has_class("#modal-transaction", "hidden"))
        self.type("#tx-amount", str(amount))
        self.select("#tx-type", tx_type)
        self.type("#tx-account", account)
        if notes:
            self.type("#tx-notes", notes)
        self.select("#tx-tag", "" if tag_id is None else tag_id)
        before = self.state("transactions.length")
        self.submit("form-transaction")
        self.until(lambda: self.state("transactions.length") != before, "transaction not saved")
        self.idle()

    def add_tag_ui(self, name, color="#22AA55", emoji=None):
        self.switch_tab("tags")
        self.click("#btn-open-add-tag")
        self.until(lambda: not self.has_class("#modal-tag", "hidden"))
        self.type("#tag-name", name)
        self.type("#tag-color", color)
        if emoji:
            self.set_value("#tag-emoji", emoji)
        self.submit("form-tag")

    def add_rule_ui(self, keyword, tag_id=None, ignore=False):
        self.switch_tab("rules")
        self.click("#btn-open-add-rule")
        self.until(lambda: not self.has_class("#modal-rule", "hidden"))
        self.type("#rule-keyword", keyword)
        if ignore:
            self.click("#rule-type-ignore")
        elif tag_id is not None:
            self.select("#rule-tag", tag_id)
        self.submit("form-rule")


def now_ms():
    return int(time.time() * 1000)


def days_ago_ms(days, hour=12):
    """Epoch ms for `hour`:00 local time, `days` days before today."""
    from datetime import datetime, timedelta
    d = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days)
    return int(d.timestamp() * 1000)


@pytest.fixture
def app(driver, base_url, api):
    # api fixture already reset the DB; clear per-test browser state too
    driver.get(base_url + "/")
    driver.execute_script("localStorage.clear();")
    return App(driver, base_url).open()
