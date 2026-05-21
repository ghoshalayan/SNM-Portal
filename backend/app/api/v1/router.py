from fastapi import APIRouter

from app.api.v1 import (
    auth, company, users, roles, menus, masters,
    customers, enquiries, quotations, assets, email,
    org_tree, communication_logs, quotation_formats, transfers, cost_templates,
    viability, annexure, admin, cycles,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(company.router, prefix="/companies", tags=["Companies"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles"])
api_router.include_router(menus.router, prefix="/menus", tags=["Menus"])
api_router.include_router(masters.router, prefix="/masters", tags=["Masters"])
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
api_router.include_router(enquiries.router, prefix="/enquiries", tags=["Enquiries"])
api_router.include_router(quotations.router, prefix="/quotations", tags=["Quotations"])
api_router.include_router(assets.router, prefix="/assets", tags=["Assets"])
api_router.include_router(email.router, prefix="/email", tags=["Email"])
api_router.include_router(org_tree.router, prefix="/org-tree", tags=["Organization Tree"])
api_router.include_router(communication_logs.router, prefix="/communication-logs", tags=["Communication Logs"])
api_router.include_router(quotation_formats.router, prefix="/quotation-formats", tags=["Quotation Formats"])
api_router.include_router(transfers.router, prefix="/transfers", tags=["Ownership Transfers"])
api_router.include_router(cost_templates.router, prefix="/cost-templates", tags=["Cost Templates"])
# Viability router uses full paths on its endpoints (/quotations/{id}/viability
# and /viability/{id}/...) so it's registered without a prefix.
api_router.include_router(viability.router, tags=["Viability"])
# Annexure router uses full paths (/quotations/{id}/annexure and /annexure/{id}/...),
# registered without a prefix for the same reason as viability.
api_router.include_router(annexure.router, tags=["Annexure"])
# Cycle router (LOI / Multi-PO CR — Phase 1C). Uses full paths
# (/quotations/{qid}/cycles[/...]), registered without a prefix.
api_router.include_router(cycles.router, tags=["Order Cycles"])
# SuperAdmin-only destructive / maintenance endpoints.
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
