Those are just IDE hints about packages not installed in the local Python env — they're installed on the deployment server. Not an issue.

Here's how to use the test suite:

Step 1: Install httpx


pip install httpx
Step 2: Start the server


cd backend && uvicorn app.main:app --reload
Step 3: Create test users (one-time setup)


python tests/create_test_users.py --base-url http://localhost:8000/api/v1 --admin-login superadmin --admin-password Super@2026
Adjust --admin-login and --admin-password to your actual superadmin credentials.

This creates 7 test users with the hierarchy:


SuperAdmin (existing)
  └── CompanyAdmin
        └── Director-D1
              ├── HOD-A (locations: 3 states)
              │     ├── KRO-1 (auto-inherit from HOD-A)
              │     └── KRO-2 (auto-inherit from HOD-A)
              ├── HOD-B (locations: 2 different states)
              └── HOD-C (locations: 2 states overlapping HOD-A)
Step 4: Run tests and generate report


python tests/rbac_test_runner.py --base-url http://localhost:8000/api/v1 --report rbac_report.html
Output:

Console shows real-time pass/fail per test case
rbac_report.html — styled HTML report with summary cards (total/pass/fail/error/skip/rate%) and detailed table grouped by module
The report covers ~30 automated test cases from the 104-case plan. The remaining cases (peer access combinations, cascading location changes, multi-level hierarchy visibility) require the full 8-user hierarchy to be set up with specific location and role flag configurations. You can extend rbac_test_runner.py by adding more run_test() calls following the same pattern.