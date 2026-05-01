"""Create test users for RBAC v2 integration tests.

Usage:
  python tests/create_test_users.py [--base-url http://localhost:8000/api/v1]

This script:
1. Logs in as the existing superadmin
2. Finds or creates the 5 role templates in company 1
3. Creates 8 test users (superadmin already exists, others are created)
4. Assigns role mappings + org tree hierarchy
5. Assigns locations to HOD and KRO users

Prerequisites:
  - Server running
  - Migrations applied (alembic upgrade head incl. role template seeder)
  - A superadmin user exists (login: 'superadmin' or 'admin')
"""

import argparse
import sys

try:
    import httpx
except ImportError:
    print("pip install httpx"); sys.exit(1)


BASE_URL = "http://localhost:8000/api/v1"
ADMIN_LOGIN = "superadmin"
ADMIN_PASSWORD = "Super@2026"  # Adjust to your actual superadmin password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--admin-login", default=ADMIN_LOGIN)
    parser.add_argument("--admin-password", default=ADMIN_PASSWORD)
    args = parser.parse_args()

    client = httpx.Client(timeout=30, base_url=args.base_url)

    # Login as superadmin
    print("🔐 Logging in as superadmin...")
    resp = client.post("/auth/login", json={
        "userLogin": args.admin_login,
        "password": args.admin_password,
    })
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.status_code} {resp.text[:200]}")
        print("   Adjust --admin-login and --admin-password")
        sys.exit(1)

    data = resp.json()
    temp_token = data["tempToken"]
    companies = data["companies"]
    company_id = companies[0]["companyId"]
    print(f"   Company: {companies[0].get('companyName', company_id)}")

    # Select company
    resp2 = client.post("/auth/select-company",
        json={"companyId": company_id},
        headers={"Authorization": f"Bearer {temp_token}"},
    )
    if resp2.status_code != 200:
        print(f"❌ Select company failed: {resp2.text[:200]}")
        sys.exit(1)

    token = resp2.json()["accessToken"]
    auth = {"Authorization": f"Bearer {token}"}

    # Get roles
    print("\n📋 Finding role templates...")
    resp = client.get("/roles", headers=auth, params={"companyId": company_id})
    roles = resp.json()
    role_map = {r["roleName"]: r["roleId"] for r in roles}
    print(f"   Roles: {role_map}")

    required = ["CompanyAdmin", "Director", "HOD", "KRO"]
    for r in required:
        if r not in role_map:
            print(f"❌ Role '{r}' not found. Run migration g1h2i3j4k5l6 first.")
            sys.exit(1)

    # Define test users
    test_users = [
        {"userLogin": "companyadmin", "userName": "Company Admin Test", "password": "Admin@2026", "role": "CompanyAdmin", "reportTo": None},
        {"userLogin": "director1", "userName": "Director D1 Test", "password": "Dir@2026", "role": "Director", "reportTo": "companyadmin"},
        {"userLogin": "hod_a", "userName": "HOD A Test", "password": "Hod@2026", "role": "HOD", "reportTo": "director1"},
        {"userLogin": "hod_b", "userName": "HOD B Test", "password": "Hod@2026", "role": "HOD", "reportTo": "director1"},
        {"userLogin": "hod_c", "userName": "HOD C Test", "password": "Hod@2026", "role": "HOD", "reportTo": "director1"},
        {"userLogin": "kro_1", "userName": "KRO 1 Test", "password": "Kro@2026", "role": "KRO", "reportTo": "hod_a"},
        {"userLogin": "kro_2", "userName": "KRO 2 Test", "password": "Kro@2026", "role": "KRO", "reportTo": "hod_a"},
    ]

    user_ids = {}

    # Discover existing superadmin userId
    resp = client.get("/users", headers=auth, params={"pageSize": 200})
    existing_users = {u["userLogin"]: u for u in resp.json().get("items", [])}
    if args.admin_login in existing_users:
        user_ids["superadmin"] = existing_users[args.admin_login]["userId"]
        print(f"   SuperAdmin userId: {user_ids['superadmin']}")

    # Create users
    print("\n👤 Creating test users...")
    for u in test_users:
        if u["userLogin"] in existing_users:
            uid = existing_users[u["userLogin"]]["userId"]
            user_ids[u["userLogin"]] = uid
            print(f"   ⏭️  {u['userLogin']} already exists (id={uid})")
            continue

        resp = client.post("/users", headers=auth, json={
            "userName": u["userName"],
            "userLogin": u["userLogin"],
            "userPassword": u["password"],
            "userEmail": f"{u['userLogin']}@test.com",
            "userCode": u["userLogin"].upper().replace("_", ""),
            "companyId": company_id,
        })
        if resp.status_code in [200, 201]:
            uid = resp.json().get("userId")
            user_ids[u["userLogin"]] = uid
            print(f"   ✅ Created {u['userLogin']} (id={uid})")
        else:
            print(f"   ❌ Failed to create {u['userLogin']}: {resp.status_code} {resp.text[:200]}")

    # Assign role mappings
    print("\n🎭 Assigning roles...")
    for u in test_users:
        uid = user_ids.get(u["userLogin"])
        if not uid:
            continue
        report_to_id = user_ids.get(u["reportTo"]) if u["reportTo"] else None
        role_id = role_map[u["role"]]
        resp = client.post(f"/users/{uid}/role-mappings", headers=auth, json=[{
            "companyId": company_id,
            "roleId": role_id,
            "isDefault": True,
            "reportTo": report_to_id,
        }])
        status = "✅" if resp.status_code == 200 else "❌"
        print(f"   {status} {u['userLogin']} → {u['role']} (reportTo={u['reportTo']})")

    # Assign locations (need to find state/district IDs)
    print("\n🗺️ Assigning locations...")
    # Get available locations from superadmin's my-locations
    resp = client.get("/users/my-locations", headers=auth)
    loc_data = resp.json()
    countries = loc_data.get("countries", [])

    # Build state name→id map
    state_map = {}
    country_id = None
    for c in countries:
        if not country_id:
            country_id = c["countryid"]
        for s in c.get("states", []):
            state_map[s["StateName"].lower()] = s["stateid"]

    if not state_map:
        print("   ⚠️  No location data found. Assign locations manually.")
    else:
        print(f"   Available states: {list(state_map.keys())[:10]}...")

        # HOD-A: first 3 states
        state_names = list(state_map.keys())
        hod_a_states = state_names[:3] if len(state_names) >= 3 else state_names
        hod_b_states = state_names[3:5] if len(state_names) >= 5 else state_names[-2:]

        for login, states in [("hod_a", hod_a_states), ("hod_b", hod_b_states), ("hod_c", hod_a_states[:2])]:
            uid = user_ids.get(login)
            if not uid:
                continue
            mappings = [{"countryid": country_id, "stateid": state_map[s], "districtid": None} for s in states]
            resp = client.post(f"/users/{uid}/location-mappings", headers=auth, json=mappings)
            status = "✅" if resp.status_code == 200 else "❌"
            inherited = resp.json().get("cascadedRemovals", 0) if resp.status_code == 200 else 0
            print(f"   {status} {login}: {states} (cascade={inherited})")

        # KRO-1 and KRO-2 should auto-inherit from HOD-A (via enforceChildLocationSubset)
        for login in ["kro_1", "kro_2"]:
            uid = user_ids.get(login)
            if not uid:
                continue
            resp = client.get(f"/users/{uid}/location-mappings", headers=auth)
            if resp.status_code == 200:
                locs = resp.json().get("locations", [])
                print(f"   ℹ️  {login}: {len(locs)} locations (auto-inherited)")

    print("\n✅ Setup complete! Run the test suite:")
    print(f"   python tests/rbac_test_runner.py --base-url {args.base_url}")
    client.close()


if __name__ == "__main__":
    main()
