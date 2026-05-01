-- ============================================================================
-- SNM Portal - Seed Data
-- Creates: 1 Company, 2 Roles, 2 Users, 25 Menus, Permission tree
-- ============================================================================
-- Login Credentials:
--   Super Admin:   admin / Admin@123
--   Test User:     testuser / Test@123
-- ============================================================================

-- ============================================================================
-- 1. Company
-- ============================================================================
INSERT INTO Company (companyName, companyCode, city, state, country, isActive, createdon, createdby)
VALUES ('SNM Default Company', 'SNM', 'Mumbai', 'Maharashtra', 'India', 1, GETDATE(), 1);

DECLARE @companyId INT = SCOPE_IDENTITY();

-- ============================================================================
-- 2. Roles
-- ============================================================================
INSERT INTO RoleMaster (companyId, roleName, IsSuperAdmin, isActive, createdon, createdby)
VALUES (@companyId, 'Super Admin', 1, 1, GETDATE(), 1);
DECLARE @adminRoleId INT = SCOPE_IDENTITY();

INSERT INTO RoleMaster (companyId, roleName, IsSuperAdmin, isActive, createdon, createdby)
VALUES (@companyId, 'Standard User', 0, 1, GETDATE(), 1);
DECLARE @userRoleId INT = SCOPE_IDENTITY();

-- ============================================================================
-- 3. Users (passwords are bcrypt hashes)
-- ============================================================================
-- admin / Admin@123
INSERT INTO UserMaster (companyId, userName, userCode, userEmail, userLogin, userPassword, isActive, createdon, createdby)
VALUES (@companyId, 'Super Administrator', 'SADMIN', 'admin@snm.com', 'admin',
        '$2b$12$Y5420y.ndEwxszWACVeYfug6U9ifs71r8vihJps9VQPpauYKPm9u6', 1, GETDATE(), 1);
DECLARE @adminUserId INT = SCOPE_IDENTITY();

-- testuser / Test@123
INSERT INTO UserMaster (companyId, userName, userCode, userEmail, userLogin, userPassword, isActive, createdon, createdby)
VALUES (@companyId, 'Test User', 'TUSER', 'test@snm.com', 'testuser',
        '$2b$12$fCY8samkx1FF.nk55aZ48untQta1ZYW1f9N1VVePdlGdWdz.oEnhG', 1, GETDATE(), @adminUserId);
DECLARE @testUserId INT = SCOPE_IDENTITY();

-- ============================================================================
-- 4. User-Role-Company Mapping
-- ============================================================================
INSERT INTO UserRoleMap (userId, roleId, companyId, isDefault, isActive, createdon, createdby)
VALUES (@adminUserId, @adminRoleId, @companyId, 1, 1, GETDATE(), @adminUserId);

INSERT INTO UserRoleMap (userId, roleId, companyId, isDefault, isActive, createdon, createdby)
VALUES (@testUserId, @userRoleId, @companyId, 1, 1, GETDATE(), @adminUserId);

-- ============================================================================
-- 5. Menu Tree (25 menus)
-- ============================================================================

-- Level 0: Root menus
INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Dashboard', '/dashboard', 'dashboard', NULL, 1, 1, GETDATE(), @adminUserId);
DECLARE @menuDashboard INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Administration', NULL, 'admin_panel_settings', NULL, 2, 1, GETDATE(), @adminUserId);
DECLARE @menuAdmin INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Masters', NULL, 'settings', NULL, 3, 1, GETDATE(), @adminUserId);
DECLARE @menuMasters INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Customers', NULL, 'groups', NULL, 4, 1, GETDATE(), @adminUserId);
DECLARE @menuCustomers INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Enquiries', NULL, 'request_quote', NULL, 5, 1, GETDATE(), @adminUserId);
DECLARE @menuEnquiries INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Quotations', NULL, 'description', NULL, 6, 1, GETDATE(), @adminUserId);
DECLARE @menuQuotations INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Assets', '/assets', 'cloud_upload', NULL, 7, 1, GETDATE(), @adminUserId);
DECLARE @menuAssets INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Logs', NULL, 'history', NULL, 8, 1, GETDATE(), @adminUserId);
DECLARE @menuLogs INT = SCOPE_IDENTITY();

-- Level 1: Administration children
INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Company Management', '/companies', 'business', @menuAdmin, 1, 1, GETDATE(), @adminUserId);
DECLARE @menuCompanyMgmt INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'User Management', '/users', 'people', @menuAdmin, 2, 1, GETDATE(), @adminUserId);
DECLARE @menuUserMgmt INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Role Management', '/roles', 'security', @menuAdmin, 3, 1, GETDATE(), @adminUserId);
DECLARE @menuRoleMgmt INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Role-Menu Mapping', '/roles/menu-mapping', 'assignment', @menuAdmin, 4, 1, GETDATE(), @adminUserId);
DECLARE @menuRoleMenuMap INT = SCOPE_IDENTITY();

-- Level 1: Masters children
INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Item Grade', '/masters/item-grades', 'grade', @menuMasters, 1, 1, GETDATE(), @adminUserId);
DECLARE @menuItemGrade INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Item Name', '/masters/item-names', 'inventory_2', @menuMasters, 2, 1, GETDATE(), @adminUserId);
DECLARE @menuItemName INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Item Length', '/masters/item-lengths', 'straighten', @menuMasters, 3, 1, GETDATE(), @adminUserId);
DECLARE @menuItemLength INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Item Size', '/masters/item-sizes', 'aspect_ratio', @menuMasters, 4, 1, GETDATE(), @adminUserId);
DECLARE @menuItemSize INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Delivery Term', '/masters/delivery-terms', 'local_shipping', @menuMasters, 5, 1, GETDATE(), @adminUserId);
DECLARE @menuDeliveryTerm INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Delivery Mode', '/masters/delivery-modes', 'commute', @menuMasters, 6, 1, GETDATE(), @adminUserId);
DECLARE @menuDeliveryMode INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Contact Type', '/masters/contact-types', 'contact_phone', @menuMasters, 7, 1, GETDATE(), @adminUserId);
DECLARE @menuContactType INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Customer Classification', '/masters/customer-classifications', 'category', @menuMasters, 8, 1, GETDATE(), @adminUserId);
DECLARE @menuCustClass INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Cost Point', '/masters/cost-points', 'monetization_on', @menuMasters, 9, 1, GETDATE(), @adminUserId);
DECLARE @menuCostPoint INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Terms & Conditions', '/masters/terms-conditions', 'gavel', @menuMasters, 10, 1, GETDATE(), @adminUserId);
DECLARE @menuTnC INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Raw Material Cost', '/masters/raw-material-costs', 'attach_money', @menuMasters, 11, 1, GETDATE(), @adminUserId);
DECLARE @menuRawMat INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Enquiry Status', '/masters/enq-statuses', 'flag', @menuMasters, 12, 1, GETDATE(), @adminUserId);
DECLARE @menuEnqStatus INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Quotation Status', '/masters/quot-statuses', 'bookmark', @menuMasters, 13, 1, GETDATE(), @adminUserId);
DECLARE @menuQuotStatus INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Communication Mode', '/masters/communication-modes', 'sms', @menuMasters, 14, 1, GETDATE(), @adminUserId);
DECLARE @menuCommMode INT = SCOPE_IDENTITY();

-- Level 1: Customers, Enquiries, Quotations children
INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Customer List', '/customers', 'list', @menuCustomers, 1, 1, GETDATE(), @adminUserId);
DECLARE @menuCustList INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Enquiry List', '/enquiries', 'list_alt', @menuEnquiries, 1, 1, GETDATE(), @adminUserId);
DECLARE @menuEnqList INT = SCOPE_IDENTITY();

INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Quotation List', '/quotations', 'format_list_numbered', @menuQuotations, 1, 1, GETDATE(), @adminUserId);
DECLARE @menuQuotList INT = SCOPE_IDENTITY();

-- Level 1: Logs children
INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (@companyId, 'Communication Logs', '/communication-logs', 'chat', @menuLogs, 1, 1, GETDATE(), @adminUserId);
DECLARE @menuCommLogs INT = SCOPE_IDENTITY();

-- ============================================================================
-- 6. Role-Menu Permissions
-- ============================================================================

-- Super Admin: Full CRUD on ALL 25 menus
INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, isActive, createdon, createdby)
SELECT @adminRoleId, menuId, 1, 1, 1, 1, 1, GETDATE(), @adminUserId
FROM MenuMaster WHERE companyId = @companyId;

-- Standard User: Read-only on Dashboard, Customers
INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, isActive, createdon, createdby)
VALUES
    (@userRoleId, @menuDashboard,  0, 1, 0, 0, 1, GETDATE(), @adminUserId),
    (@userRoleId, @menuCustomers,  0, 1, 0, 0, 1, GETDATE(), @adminUserId),
    (@userRoleId, @menuCustList,   0, 1, 0, 0, 1, GETDATE(), @adminUserId);

-- Standard User: Full CRUD on Enquiries, Quotations, Assets
INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, isActive, createdon, createdby)
VALUES
    (@userRoleId, @menuEnquiries,  1, 1, 1, 1, 1, GETDATE(), @adminUserId),
    (@userRoleId, @menuEnqList,    1, 1, 1, 1, 1, GETDATE(), @adminUserId),
    (@userRoleId, @menuQuotations, 1, 1, 1, 1, 1, GETDATE(), @adminUserId),
    (@userRoleId, @menuQuotList,   1, 1, 1, 1, 1, GETDATE(), @adminUserId),
    (@userRoleId, @menuAssets,     1, 1, 1, 1, 1, GETDATE(), @adminUserId);

-- ============================================================================
-- Verification Queries (run after seeding to confirm)
-- ============================================================================
-- SELECT * FROM Company;
-- SELECT userId, userName, userLogin FROM UserMaster;
-- SELECT u.userLogin, r.roleName, c.companyName FROM UserRoleMap urm
--   JOIN UserMaster u ON urm.userId = u.userId
--   JOIN RoleMaster r ON urm.roleId = r.roleId
--   JOIN Company c ON urm.companyId = c.companyId;
-- SELECT menuId, menuName, parentMenuId, menuOrder FROM MenuMaster ORDER BY menuId;
-- SELECT r.roleName, COUNT(*) as permissions FROM RoleMenuMap rm
--   JOIN RoleMaster r ON rm.roleId = r.roleId GROUP BY r.roleName;
