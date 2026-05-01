-- RBAC v2 Test Users Setup
-- Run this AFTER migrations are applied (alembic upgrade head)
-- This creates test users for the rbac_test_runner.py script
--
-- Adjust companyId (1) and roleIds to match your seeded role templates.
-- Password hash = bcrypt of 'Super@2026', 'Admin@2026', 'Dir@2026', 'Hod@2026', 'Kro@2026'
-- Generate with: python -c "from passlib.hash import bcrypt; print(bcrypt.hash('YourPassword'))"

-- Step 1: Find role IDs for the seeded templates in company 1
-- SELECT roleId, roleName FROM RoleMaster WHERE companyId = 1 AND isActive = 1;

-- Step 2: Insert test users (adjust roleId values below)
-- NOTE: Run the Python script below instead for proper bcrypt hashing

-- ============================================================
-- Use this Python script to create test users via API:
-- ============================================================
--
-- python tests/create_test_users.py --base-url http://localhost:8000/api/v1
--
