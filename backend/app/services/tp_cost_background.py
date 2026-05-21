"""Background TP Cost Scheduler — runs inside the FastAPI process.

Starts a background asyncio task on app startup that:
1. Checks every 60 seconds if midnight IST has passed and hasn't run today
2. Updates TPWGST in Draft quotation line items based on latest effective costs
3. Also provides trigger_immediate_update() for instant execution

No external scheduler needed.
"""

import asyncio
import logging
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.timezone import now_ist

logger = logging.getLogger("tp_cost_scheduler")

_last_run_date: Optional[date] = None

COST_HEADS = [
    "TPWGST", "Marketing", "FreightTrailer", "FreightTruck", "Unloading",
    "OHD", "IFC", "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge",
    "ShortLnthCharge", "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation",
    "Commission", "Misc", "Testing", "MOUTOD", "SplDisc", "JC",
]


def _recalc(dtl):
    """Recalculate totRate/GST/totAmount for a QuotDetails row.
    CD + SplDisc are deducted (CR #2)."""
    from app.services.quotation_service import sum_cost_heads
    total = float(sum_cost_heads(dtl))
    dtl.totRate = round(total, 2)
    gst = round(total * 0.18, 2)
    if dtl.gstMode == "CGST_SGST":
        dtl.IGST = 0
        dtl.CGST = round(gst / 2, 2)
        dtl.SGST = round(gst / 2, 2)
    else:
        dtl.IGST = gst
        dtl.CGST = 0
        dtl.SGST = 0
    dtl.totAmount = round(total + gst, 2)
    dtl.basicRate = dtl.totRate


def _get_latest_tp_map(db: Session, company_id: int, as_of: date) -> dict:
    """Return {dia_string: tpcost} for the latest cost per dia where effectedFrom <= as_of."""
    from app.models.raw_material_cost import RawMaterialCost

    sub = (
        db.query(
            RawMaterialCost.dia,
            func.max(RawMaterialCost.effectedFrom).label("maxEff"),
        )
        .filter(
            RawMaterialCost.companyId == company_id,
            RawMaterialCost.isActive == True,
            RawMaterialCost.effectedFrom <= as_of,
        )
        .group_by(RawMaterialCost.dia)
        .subquery()
    )

    rows = (
        db.query(RawMaterialCost.dia, RawMaterialCost.tpcost)
        .join(sub, (RawMaterialCost.dia == sub.c.dia) & (RawMaterialCost.effectedFrom == sub.c.maxEff))
        .filter(
            RawMaterialCost.companyId == company_id,
            RawMaterialCost.isActive == True,
        )
        .all()
    )
    return {str(r.dia).strip(): float(r.tpcost) for r in rows}


def _run_update(target_date: date, company_id: Optional[int] = None) -> dict:
    """Run the TP cost update. Safe to call from sync or async context."""
    from app.models.quotation import QuotSummary, QuotDetails
    from app.models.company import Company

    db = SessionLocal()
    try:
        if company_id:
            cids = [company_id]
        else:
            cids = [c.companyId for c in db.query(Company.companyId).filter(Company.isActive == True).all()]

        total = 0
        for cid in cids:
            tp_map = _get_latest_tp_map(db, cid, target_date)
            if not tp_map:
                continue

            draft_ids = [
                q.quotId for q in
                db.query(QuotSummary.quotId).filter(
                    QuotSummary.companyId == cid,
                    QuotSummary.status == "Draft",
                    QuotSummary.isActive == True,
                ).all()
            ]
            if not draft_ids:
                continue

            details = db.query(QuotDetails).filter(
                QuotDetails.quotId.in_(draft_ids),
                QuotDetails.isActive == True,
            ).all()

            for dtl in details:
                dia = str(dtl.itemDia or "").strip()
                if dia in tp_map:
                    new_tp = tp_map[dia]
                    old_tp = float(dtl.TPWGST or 0)
                    if old_tp != new_tp:
                        dtl.TPWGST = new_tp
                        _recalc(dtl)
                        total += 1

            db.commit()

        logger.info(f"TP update for {target_date}: {total} rows updated across {len(cids)} companies")
        return {"date": str(target_date), "rows_updated": total}

    except Exception as e:
        logger.error(f"TP cost update failed: {e}", exc_info=True)
        db.rollback()
        return {"date": str(target_date), "error": str(e)}
    finally:
        db.close()


def trigger_immediate_update(company_id: int) -> dict:
    """Call when a RawMaterialCost is saved with effectedFrom <= today."""
    today = now_ist().date()
    return _run_update(today, company_id=company_id)


async def _scheduler_loop():
    """Background loop: runs the update once per day after midnight IST."""
    global _last_run_date
    logger.info("TP Cost background scheduler started")

    while True:
        try:
            today = now_ist().date()
            if _last_run_date != today:
                logger.info(f"Running scheduled TP cost update for {today}")
                result = _run_update(today)
                _last_run_date = today
                logger.info(f"Scheduled update result: {result}")
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}", exc_info=True)

        await asyncio.sleep(60)


def start_scheduler(app):
    """Register the background scheduler on FastAPI startup."""

    @app.on_event("startup")
    async def _start():
        asyncio.create_task(_scheduler_loop())
        logger.info("TP Cost scheduler registered")
