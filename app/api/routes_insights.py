"""Аналитика и PDF-отчёт."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import AppContext, current_user, get_ctx, limit
from app.api.schemas import ReportIn
from app.services.journal import period_data, report_pdf, stats
from app.services.report import ReportError
from app.storage.users import User

router = APIRouter(prefix="/api", tags=["insights"])
log = logging.getLogger(__name__)


@router.get("/insights")
async def get_insights(days: int = Query(default=14, ge=7, le=90), user: User = Depends(current_user),
                       ctx: AppContext = Depends(get_ctx)) -> dict:
    data, *_ = await period_data(ctx.storage, user, days)
    tolerances = await ctx.storage.tolerances.all(user.id)
    return {**data, "tolerances": [t.to_dict() for t in tolerances.values()],
            "progress": await stats(ctx.storage, user)}


@router.post("/report")
async def report(body: ReportIn, user: User = Depends(limit("report")), ctx: AppContext = Depends(get_ctx)):
    try:
        pdf, filename, period = await report_pdf(ctx.storage, user, body.days)
    except ReportError as exc:
        log.error("report failed: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Не удалось собрать PDF") from exc
    if ctx.send_document is None:
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    await ctx.send_document(user.id, pdf, filename, f"📄 Отчёт за {period}. Его можно переслать врачу.")
    return {"sent": True}
