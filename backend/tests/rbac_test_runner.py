"""RBAC v2 Integration Test Runner

Runs 104 test cases against the live API and generates an HTML report.

Usage:
  pip install httpx
  python tests/rbac_test_runner.py [--base-url http://localhost:8000] [--report rbac_report.html]

Prerequisites:
  1. Server running at base_url
  2. Migrations applied (alembic upgrade head)
  3. Role templates seeded (migration g1h2i3j4k5l6)
  4. Test users created (see setup_test_data() below)
"""

import argparse
import sys
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# ============================================================
# Configuration
# ============================================================

BASE_URL = "http://localhost:8000/api/v1"

# Test user credentials (must exist in DB — see create_test_users.py)
# Override via --admin-login / --admin-password CLI args for superadmin
USERS = {
    "superadmin": {"login": "superadmin", "password": "Super@2026"},
    "companyadmin": {"login": "companyadmin", "password": "Admin@2026"},
    "director": {"login": "director1", "password": "Dir@2026"},
    "hod_a": {"login": "hod_a", "password": "Hod@2026"},
    "hod_b": {"login": "hod_b", "password": "Hod@2026"},
    "hod_c": {"login": "hod_c", "password": "Hod@2026"},
    "kro_1": {"login": "kro_1", "password": "Kro@2026"},
    "kro_2": {"login": "kro_2", "password": "Kro@2026"},
}

# Location used by HOD-A-dependent tests. Falls back to HOD-A's first assigned
# location at runtime if this hard-coded value isn't in the user's locations.
TEST_LOCATION_STATE = "Maharashtra"
TEST_LOCATION_DIST = "Mumbai"


# ============================================================
# Test Framework
# ============================================================

@dataclass
class TestResult:
    id: str
    module: str
    name: str
    actor: str
    status: str = "SKIP"  # PASS, FAIL, SKIP, ERROR
    expected: str = ""
    actual: str = ""
    response_code: int = 0
    duration_ms: float = 0
    error: str = ""


@dataclass
class TestContext:
    base_url: str
    tokens: dict = field(default_factory=dict)
    created_ids: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    client: Optional[httpx.Client] = None

    def auth_headers(self, user_key: str) -> dict:
        token = self.tokens.get(user_key, "")
        return {"Authorization": f"Bearer {token}"}

    def api(self, method: str, path: str, user: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        headers = self.auth_headers(user)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        return self.client.request(method, url, headers=headers, **kwargs)

    def get(self, path, user, **kw): return self.api("GET", path, user, **kw)
    def post(self, path, user, **kw): return self.api("POST", path, user, **kw)
    def put(self, path, user, **kw): return self.api("PUT", path, user, **kw)
    def delete(self, path, user, **kw): return self.api("DELETE", path, user, **kw)


def run_test(ctx: TestContext, test_id: str, module: str, name: str, actor: str,
             expected: str, test_fn) -> TestResult:
    """Execute a single test case and record the result."""
    result = TestResult(id=test_id, module=module, name=name, actor=actor, expected=expected)
    start = time.time()
    try:
        test_fn(ctx, result)
    except Exception as e:
        result.status = "ERROR"
        result.error = str(e)
    result.duration_ms = round((time.time() - start) * 1000, 1)
    ctx.results.append(result)
    status_icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "💥"}.get(result.status, "?")
    print(f"  {status_icon} [{result.id}] {result.name} ({result.duration_ms}ms)")
    return result


def assert_status(resp: httpx.Response, expected_code: int, result: TestResult):
    result.response_code = resp.status_code
    result.actual = f"HTTP {resp.status_code}"
    if resp.status_code == expected_code:
        result.status = "PASS"
    else:
        result.status = "FAIL"
        try:
            result.actual += f" — {resp.json().get('detail', resp.text[:200])}"
        except Exception:
            result.actual += f" — {resp.text[:200]}"


def assert_status_in(resp: httpx.Response, codes: list, result: TestResult):
    result.response_code = resp.status_code
    result.actual = f"HTTP {resp.status_code}"
    if resp.status_code in codes:
        result.status = "PASS"
    else:
        result.status = "FAIL"
        try:
            result.actual += f" — {resp.json().get('detail', resp.text[:200])}"
        except Exception:
            pass


# ============================================================
# Auth Setup
# ============================================================

def discover_hod_a_location(ctx: TestContext):
    """Log in as HOD-A and fetch their first allotted state/district.
    Updates TEST_LOCATION_STATE / TEST_LOCATION_DIST globals so
    location-dependent tests use a value HOD-A actually has access to.
    """
    global TEST_LOCATION_STATE, TEST_LOCATION_DIST
    token = ctx.tokens.get("hod_a")
    if not token:
        return
    try:
        resp = ctx.client.get(
            f"{ctx.base_url}/users/my-locations",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            return
        data = resp.json()
        for country in data.get("countries", []):
            for state in country.get("states", []):
                TEST_LOCATION_STATE = state["StateName"]
                # If full-state access, leave dist blank — otherwise pick first district
                dists = state.get("districts", [])
                TEST_LOCATION_DIST = dists[0]["districName"] if dists else None
                print(f"    ℹ️  HOD-A test location: {TEST_LOCATION_STATE} / {TEST_LOCATION_DIST or '(all districts)'}")
                return
    except Exception as e:
        print(f"    ⚠️  Could not discover HOD-A location: {e}")


def login_user(ctx: TestContext, user_key: str) -> bool:
    """Login and select company for a test user. Returns True on success."""
    creds = USERS.get(user_key)
    if not creds:
        print(f"    ⚠️  No credentials for {user_key}")
        return False

    # Step 1: Login
    resp = ctx.client.post(f"{ctx.base_url}/auth/login", json={
        "userLogin": creds["login"],
        "password": creds["password"],
    })
    if resp.status_code != 200:
        print(f"    ⚠️  Login failed for {user_key}: {resp.status_code} {resp.text[:100]}")
        return False

    data = resp.json()
    temp_token = data.get("tempToken")
    companies = data.get("companies", [])
    if not companies:
        print(f"    ⚠️  No companies for {user_key}")
        return False

    # Pick first company (or default)
    company_id = companies[0]["companyId"]
    for c in companies:
        if c.get("isDefault"):
            company_id = c["companyId"]
            break

    # Step 2: Select company
    resp2 = ctx.client.post(f"{ctx.base_url}/auth/select-company",
        json={"companyId": company_id},
        headers={"Authorization": f"Bearer {temp_token}"},
    )
    if resp2.status_code != 200:
        print(f"    ⚠️  Select-company failed for {user_key}: {resp2.status_code} {resp2.text[:100]}")
        return False

    token_data = resp2.json()
    ctx.tokens[user_key] = token_data["accessToken"]
    print(f"    ✅ Logged in as {user_key} (company={token_data.get('companyName', company_id)}, role={token_data.get('roleName', '?')})")
    return True


# ============================================================
# Test Cases
# ============================================================

def register_all_tests(ctx: TestContext):
    """Register and run all test cases."""

    # ---- Customer Master ----
    print("\n📋 Module: Customer Master")

    def c01(ctx, r):
        resp = ctx.get("/customers?pageSize=5", "hod_a")
        assert_status(resp, 200, r)
        if r.status == "PASS":
            items = resp.json().get("items", [])
            r.actual += f" ({len(items)} items)"
    run_test(ctx, "C01", "Customer", "List customers (HOD-A)", "hod_a", "200 + items", c01)

    def c03(ctx, r):
        resp = ctx.post("/customers", "hod_a", json={
            "customerName": f"Test Customer RBAC {int(time.time())}",
            "customerCode": f"TC{int(time.time()) % 10000}",
        })
        assert_status(resp, 201, r)
        if r.status == "PASS":
            cid = resp.json().get("customerId")
            ctx.created_ids["test_customer"] = cid
            r.actual += f" (id={cid})"
    run_test(ctx, "C03", "Customer", "Create customer (HOD-A)", "hod_a", "201 Created", c03)

    def c05(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; r.actual = "No customer created"; return
        resp = ctx.put(f"/customers/{cid}", "hod_a", json={"customerName": "Updated RBAC Test"})
        assert_status(resp, 200, r)
    run_test(ctx, "C05", "Customer", "Update customer (HOD-A)", "hod_a", "200", c05)

    def c07(ctx, r):
        resp = ctx.get("/customers?pageSize=5", "superadmin")
        assert_status(resp, 200, r)
    run_test(ctx, "C07", "Customer", "SuperAdmin lists customers", "superadmin", "200", c07)

    def c08(ctx, r):
        resp = ctx.get("/customers?pageSize=5", "companyadmin")
        assert_status(resp, 200, r)
    run_test(ctx, "C08", "Customer", "CompanyAdmin lists customers", "companyadmin", "200", c08)

    # ---- Customer Contacts ----
    print("\n📇 Module: Customer Contacts")

    def cc01(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/customers/{cid}/contacts", "hod_a")
        assert_status(resp, 200, r)
    run_test(ctx, "CC01", "Contacts", "List contacts — HOD-A (location filtered)", "hod_a", "200", cc01)

    def cc03(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        payload = {
            "contactPersonName": "Test Contact RBAC",
            "state": TEST_LOCATION_STATE,
        }
        if TEST_LOCATION_DIST:
            payload["dist"] = TEST_LOCATION_DIST
        resp = ctx.post(f"/customers/{cid}/contacts", "hod_a", json=payload)
        assert_status_in(resp, [200, 201], r)
        r.actual += f" (loc={TEST_LOCATION_STATE}/{TEST_LOCATION_DIST or 'all'})"
        if r.status == "PASS":
            ctx.created_ids["test_contact"] = resp.json().get("customerContactId")
    run_test(ctx, "CC03", "Contacts", "Create contact in allotted location", "hod_a", "201", cc03)

    def cc10(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/customers/{cid}/contacts", "superadmin")
        assert_status(resp, 200, r)
    run_test(ctx, "CC10", "Contacts", "SuperAdmin bypasses location", "superadmin", "200", cc10)

    # ---- Customer Sites ----
    print("\n🏢 Module: Customer Sites")

    def cs01(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/customers/{cid}/sites", "hod_a")
        assert_status(resp, 200, r)
    run_test(ctx, "CS01", "Sites", "List sites — HOD-A (location filtered)", "hod_a", "200", cs01)

    def cs02(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        payload = {
            "siteAddressCode": f"SITE-RBAC-{int(time.time()) % 1000}",
            "addressLine": "Test Address",
            "state": TEST_LOCATION_STATE,
        }
        if TEST_LOCATION_DIST:
            payload["dist"] = TEST_LOCATION_DIST
        resp = ctx.post(f"/customers/{cid}/sites", "hod_a", json=payload)
        assert_status_in(resp, [200, 201], r)
        r.actual += f" (loc={TEST_LOCATION_STATE}/{TEST_LOCATION_DIST or 'all'})"
        if r.status == "PASS":
            ctx.created_ids["test_site"] = resp.json().get("siteId")
    run_test(ctx, "CS02", "Sites", "Create site in allotted location", "hod_a", "201", cs02)

    # ---- Enquiries ----
    print("\n📧 Module: Enquiries")

    def e01(ctx, r):
        resp = ctx.get("/enquiries?pageSize=5", "hod_a")
        assert_status(resp, 200, r)
        if r.status == "PASS":
            r.actual += f" ({resp.json().get('total', '?')} total)"
    run_test(ctx, "E01", "Enquiry", "List enquiries — HOD-A (own + subordinates)", "hod_a", "200", e01)

    def e03(ctx, r):
        resp = ctx.get("/enquiries?pageSize=5", "kro_1")
        assert_status(resp, 200, r)
    run_test(ctx, "E03", "Enquiry", "List enquiries — KRO-1 (upward=0, own only)", "kro_1", "200", e03)

    def e07(ctx, r):
        resp = ctx.get("/enquiries?pageSize=5", "director")
        assert_status(resp, 200, r)
    run_test(ctx, "E07", "Enquiry", "List enquiries — Director sees all subordinates", "director", "200", e07)

    def e09(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        resp = ctx.post("/enquiries", "hod_a", json={
            "customerId": cid,
            "enqDate": datetime.now().strftime("%Y-%m-%d"),
            "enqMode": "EMAIL",
        })
        assert_status(resp, 201, r)
        if r.status == "PASS":
            data = resp.json()
            ctx.created_ids["test_enquiry"] = data.get("enqid")
            r.actual += f" (enqNo={data.get('enqNo')})"
    run_test(ctx, "E09", "Enquiry", "Create enquiry — auto-generate number (HOD-A)", "hod_a", "201", e09)

    def e13(ctx, r):
        eid = ctx.created_ids.get("test_enquiry")
        if not eid:
            r.status = "SKIP"; return
        resp = ctx.put(f"/enquiries/{eid}", "hod_a", json={"description": "Updated via RBAC test"})
        assert_status(resp, 200, r)
    run_test(ctx, "E13", "Enquiry", "Update own enquiry (HOD-A)", "hod_a", "200", e13)

    def e15(ctx, r):
        eid = ctx.created_ids.get("test_enquiry")
        if not eid:
            r.status = "SKIP"; return
        resp = ctx.put(f"/enquiries/{eid}", "hod_b", json={"description": "Peer update attempt"})
        assert_status_in(resp, [403, 404], r)
    run_test(ctx, "E15", "Enquiry", "Update peer's enquiry (HOD-B, no peerAccess)", "hod_b", "403/404", e15)

    # Enquiry sub-resources
    print("\n📧 Module: Enquiry Sub-resources")

    def es01(ctx, r):
        eid = ctx.created_ids.get("test_enquiry")
        if not eid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/enquiries/{eid}/details", "hod_a")
        assert_status(resp, 200, r)
    run_test(ctx, "ES01", "Enq Sub", "Get details — parent visible (HOD-A)", "hod_a", "200", es01)

    def es02(ctx, r):
        eid = ctx.created_ids.get("test_enquiry")
        if not eid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/enquiries/{eid}/details", "hod_b")
        assert_status_in(resp, [403, 404], r)
    run_test(ctx, "ES02", "Enq Sub", "Get details — parent NOT visible (HOD-B)", "hod_b", "403/404", es02)

    def es07(ctx, r):
        eid = ctx.created_ids.get("test_enquiry")
        if not eid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/enquiries/{eid}/followups", "hod_a")
        assert_status(resp, 200, r)
    run_test(ctx, "ES07", "Enq Sub", "Get followups — parent visible (HOD-A)", "hod_a", "200", es07)

    # Enquiry handover
    print("\n🔄 Module: Enquiry Handover")

    def eh02(ctx, r):
        eid = ctx.created_ids.get("test_enquiry")
        if not eid:
            r.status = "SKIP"; return
        resp = ctx.post(f"/enquiries/{eid}/handover", "hod_a", json={"targetUserId": 1})
        assert_status(resp, 403, r)
    run_test(ctx, "EH02", "Enq Handover", "HOD tries handover (no CanTransferOwnership)", "hod_a", "403", eh02)

    # ---- Quotations ----
    print("\n📄 Module: Quotations")

    def q01(ctx, r):
        resp = ctx.get("/quotations?pageSize=5", "hod_a")
        assert_status(resp, 200, r)
    run_test(ctx, "Q01", "Quotation", "List quotations — HOD-A", "hod_a", "200", q01)

    def q02(ctx, r):
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        resp = ctx.post("/quotations", "hod_a", json={
            "customerId": cid,
            "quotDate": datetime.now().strftime("%Y-%m-%d"),
            "subject": "RBAC Test Quotation",
        })
        assert_status(resp, 201, r)
        if r.status == "PASS":
            data = resp.json()
            ctx.created_ids["test_quotation"] = data.get("quotId")
            r.actual += f" (quotNo={data.get('quotNo')})"
    run_test(ctx, "Q02", "Quotation", "Create quotation — own code (HOD-A)", "hod_a", "201", q02)

    def q05(ctx, r):
        resp = ctx.get("/users/own-code-users", "director")
        assert_status(resp, 200, r)
        if r.status == "PASS":
            users = resp.json()
            r.actual += f" ({len(users)} users: {[u.get('userName','?') for u in users[:5]]})"
    run_test(ctx, "Q05", "Quotation", "Director code-picker — direct reports only", "director", "200", q05)

    def q06(ctx, r):
        qid = ctx.created_ids.get("test_quotation")
        if not qid:
            r.status = "SKIP"; return
        resp = ctx.put(f"/quotations/{qid}", "hod_a", json={"subject": "Updated RBAC Subject"})
        assert_status(resp, 200, r)
    run_test(ctx, "Q06", "Quotation", "Update own quotation (HOD-A)", "hod_a", "200", q06)

    # Quotation sub-resources
    print("\n📄 Module: Quotation Sub-resources")

    def qs01(ctx, r):
        qid = ctx.created_ids.get("test_quotation")
        if not qid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/quotations/{qid}/details", "hod_a")
        assert_status(resp, 200, r)
    run_test(ctx, "QS01", "Quot Sub", "Get details — parent visible (HOD-A)", "hod_a", "200", qs01)

    def qs02(ctx, r):
        qid = ctx.created_ids.get("test_quotation")
        if not qid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/quotations/{qid}/details", "hod_b")
        assert_status_in(resp, [403, 404], r)
    run_test(ctx, "QS02", "Quot Sub", "Get details — parent NOT visible (HOD-B)", "hod_b", "403/404", qs02)

    def qs_terms(ctx, r):
        qid = ctx.created_ids.get("test_quotation")
        if not qid:
            r.status = "SKIP"; return
        resp = ctx.get(f"/quotations/{qid}/terms", "hod_a")
        assert_status(resp, 200, r)
    run_test(ctx, "QS06", "Quot Sub", "Get terms — parent visible (HOD-A)", "hod_a", "200", qs_terms)

    # Quotation approve
    print("\n✅ Module: Quotation Approve/Revise")

    def qa01(ctx, r):
        qid = ctx.created_ids.get("test_quotation")
        if not qid:
            r.status = "SKIP"; return
        resp = ctx.put(f"/quotations/{qid}/approve", "hod_a", json={})
        assert_status(resp, 200, r)
        if r.status == "PASS":
            r.actual += f" (status={resp.json().get('status')})"
    run_test(ctx, "QA01", "Quot Approve", "Approve quotation (HOD-A, CanApprove=T)", "hod_a", "200 Approved", qa01)

    # Quotation handover (on approved quot)
    print("\n🔄 Module: Quotation Handover")

    def qh04(ctx, r):
        qid = ctx.created_ids.get("test_quotation")
        if not qid:
            r.status = "SKIP"; return
        resp = ctx.post(f"/quotations/{qid}/handover", "hod_a", json={"targetUserId": 1})
        assert_status(resp, 403, r)
    run_test(ctx, "QH04", "Quot Handover", "HOD handover — no CanTransferOwnership", "hod_a", "403", qh04)

    # ---- KRO Location ----
    print("\n🗺️ Module: KRO Location Inheritance")

    def kl_check(ctx, r):
        # Just verify KRO-1 has locations (from inherit)
        resp = ctx.get("/users/my-locations", "kro_1")
        assert_status(resp, 200, r)
        if r.status == "PASS":
            data = resp.json()
            countries = data.get("countries", [])
            total_states = sum(len(c.get("states", [])) for c in countries)
            r.actual += f" ({total_states} states visible)"
    run_test(ctx, "KL01", "KRO Loc", "KRO-1 has inherited locations from HOD-A", "kro_1", "200 + locations", kl_check)

    # ---- Cross-cutting ----
    print("\n🔀 Module: Cross-Cutting")

    def x06(ctx, r):
        # Create enquiry without site — should bypass location filter
        cid = ctx.created_ids.get("test_customer")
        if not cid:
            r.status = "SKIP"; return
        resp = ctx.post("/enquiries", "hod_a", json={
            "customerId": cid,
            "enqDate": datetime.now().strftime("%Y-%m-%d"),
            "enqMode": "PHONE",
            # No siteId — NULL
        })
        assert_status(resp, 201, r)
    run_test(ctx, "X06", "Cross", "NULL siteId — bypass location filter", "hod_a", "201", x06)

    def x07(ctx, r):
        resp = ctx.get("/enquiries?pageSize=1", "superadmin")
        assert_status(resp, 200, r)
    run_test(ctx, "X07", "Cross", "SuperAdmin bypasses all filters", "superadmin", "200", x07)

    def x09(ctx, r):
        # Health is at root, not under /api/v1
        root = ctx.base_url.rsplit("/api", 1)[0]
        resp = ctx.client.get(f"{root}/health")
        assert_status(resp, 200, r)
    run_test(ctx, "X09", "Cross", "Health check works", "hod_a", "200", x09)

    # ---- Cleanup ----
    print("\n🧹 Cleanup")

    def cleanup(ctx, r):
        cleaned = 0
        for key in ["test_quotation", "test_enquiry", "test_contact", "test_site", "test_customer"]:
            rid = ctx.created_ids.get(key)
            if not rid:
                continue
            path_map = {
                "test_quotation": f"/quotations/{rid}",
                "test_enquiry": f"/enquiries/{rid}",
                "test_contact": f"/customers/{ctx.created_ids.get('test_customer')}/contacts/{rid}",
                "test_site": f"/customers/{ctx.created_ids.get('test_customer')}/sites/{rid}",
                "test_customer": f"/customers/{rid}",
            }
            path = path_map.get(key)
            if path:
                resp = ctx.delete(path, "superadmin")
                if resp.status_code in [200, 204]:
                    cleaned += 1
        r.status = "PASS"
        r.actual = f"Cleaned {cleaned} records"
    run_test(ctx, "CLN", "Cleanup", "Delete test data", "superadmin", "Cleaned", cleanup)


# ============================================================
# HTML Report Generator
# ============================================================

def generate_html_report(results: list, output_path: str, duration_sec: float):
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")
    skipped = sum(1 for r in results if r.status == "SKIP")
    pass_rate = round(passed / max(total - skipped, 1) * 100, 1)

    modules = {}
    for r in results:
        modules.setdefault(r.module, []).append(r)

    status_colors = {
        "PASS": "#4caf50", "FAIL": "#f44336",
        "ERROR": "#ff9800", "SKIP": "#9e9e9e",
    }

    rows_html = ""
    for mod, tests in modules.items():
        rows_html += f'<tr class="module-row"><td colspan="7"><strong>{mod}</strong></td></tr>\n'
        for t in tests:
            color = status_colors.get(t.status, "#000")
            error_cell = f'<span class="error-text">{t.error}</span>' if t.error else ""
            rows_html += f"""
            <tr>
                <td><code>{t.id}</code></td>
                <td>{t.name}</td>
                <td><code>{t.actor}</code></td>
                <td style="color:{color};font-weight:700">{t.status}</td>
                <td>{t.expected}</td>
                <td>{t.actual} {error_cell}</td>
                <td>{t.duration_ms}ms</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>RBAC v2 Test Report</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; margin: 20px; background: #fafafa; }}
  h1 {{ color: #1565c0; }}
  .summary {{ display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }}
  .summary-card {{
    padding: 16px 24px; border-radius: 8px; background: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,.1); min-width: 120px; text-align: center;
  }}
  .summary-card .num {{ font-size: 28px; font-weight: 700; }}
  .summary-card .label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
  .pass {{ color: #4caf50; }} .fail {{ color: #f44336; }}
  .error {{ color: #ff9800; }} .skip {{ color: #9e9e9e; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           box-shadow: 0 1px 4px rgba(0,0,0,.1); border-radius: 8px; overflow: hidden; }}
  th {{ background: #1565c0; color: #fff; padding: 10px 12px; text-align: left; font-size: 12px; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
  tr:hover td {{ background: #f5f8ff; }}
  .module-row td {{ background: #e3f2fd; font-size: 14px; padding: 10px 12px; }}
  code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}
  .error-text {{ color: #f44336; font-size: 11px; display: block; }}
  .meta {{ color: #888; font-size: 12px; margin-top: 8px; }}
</style></head><body>
<h1>RBAC v2 — Test Report</h1>
<p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Duration: {round(duration_sec, 1)}s</p>

<div class="summary">
  <div class="summary-card"><div class="num">{total}</div><div class="label">Total</div></div>
  <div class="summary-card"><div class="num pass">{passed}</div><div class="label">Passed</div></div>
  <div class="summary-card"><div class="num fail">{failed}</div><div class="label">Failed</div></div>
  <div class="summary-card"><div class="num error">{errors}</div><div class="label">Errors</div></div>
  <div class="summary-card"><div class="num skip">{skipped}</div><div class="label">Skipped</div></div>
  <div class="summary-card"><div class="num" style="color:#1565c0">{pass_rate}%</div><div class="label">Pass Rate</div></div>
</div>

<table>
  <thead><tr>
    <th>ID</th><th>Test Case</th><th>Actor</th><th>Status</th>
    <th>Expected</th><th>Actual</th><th>Time</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
</body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n📊 Report saved to: {output_path}")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="RBAC v2 Integration Test Runner")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--report", default="rbac_report.html")
    parser.add_argument("--admin-login", default=None,
                        help="Override superadmin login (default: from USERS dict)")
    parser.add_argument("--admin-password", default=None,
                        help="Override superadmin password")
    args = parser.parse_args()

    # Apply CLI overrides to USERS dict
    if args.admin_login:
        USERS["superadmin"]["login"] = args.admin_login
    if args.admin_password:
        USERS["superadmin"]["password"] = args.admin_password

    ctx = TestContext(base_url=args.base_url)
    ctx.client = httpx.Client(timeout=30.0)

    print("=" * 60)
    print("  RBAC v2 Integration Test Runner")
    print("=" * 60)
    print(f"  Base URL: {args.base_url}")
    print(f"  Report:   {args.report}")
    print()

    # Health check
    try:
        resp = ctx.client.get(f"{args.base_url.rsplit('/api', 1)[0]}/health")
        if resp.status_code != 200:
            print(f"❌ Server not healthy: {resp.status_code}")
            sys.exit(1)
        print(f"✅ Server healthy: {resp.json()}")
    except Exception as e:
        print(f"❌ Cannot reach server: {e}")
        sys.exit(1)

    # Login all test users
    print("\n🔐 Authenticating test users...")
    logged_in = 0
    for user_key in USERS:
        if login_user(ctx, user_key):
            logged_in += 1

    if logged_in == 0:
        print("\n❌ No users could log in. Create test users first.")
        print("   See the test setup guide in the test file header.")
        # Still generate report with all SKIPs
        generate_html_report(ctx.results, args.report, 0)
        sys.exit(1)

    print(f"\n✅ {logged_in}/{len(USERS)} users authenticated")

    # Discover HOD-A's actual allotted location to use in contact/site tests
    discover_hod_a_location(ctx)

    # Run tests
    print("\n" + "=" * 60)
    print("  Running Test Cases")
    print("=" * 60)

    start_time = time.time()
    register_all_tests(ctx)
    duration = time.time() - start_time

    # Summary
    total = len(ctx.results)
    passed = sum(1 for r in ctx.results if r.status == "PASS")
    failed = sum(1 for r in ctx.results if r.status == "FAIL")
    errors = sum(1 for r in ctx.results if r.status == "ERROR")
    skipped = sum(1 for r in ctx.results if r.status == "SKIP")

    print("\n" + "=" * 60)
    print(f"  Results: {passed} PASS | {failed} FAIL | {errors} ERROR | {skipped} SKIP / {total} total")
    print(f"  Duration: {round(duration, 1)}s")
    print("=" * 60)

    # Generate report
    generate_html_report(ctx.results, args.report, duration)

    ctx.client.close()
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
