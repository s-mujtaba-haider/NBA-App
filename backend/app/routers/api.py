"""Data endpoints for the web and desktop app."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import exporting, jobs, logbuffer, record, runner, simulation, slate
from ..config import settings
from ..markets import BOOKS, MARKETS, ORDER, RULE_OF_RECORD
from ..security import optional_user, require_admin

router = APIRouter(prefix="/api", tags=["data"], dependencies=[Depends(optional_user)])


@router.get("/info")
def info():
    return dict(app=settings.app_name, version=settings.version, markets=[dict(key=k, **MARKETS[k]) for k in ORDER], books=BOOKS,
                rule=RULE_OF_RECORD, require_login=settings.require_api_key, odds_configured=settings.odds_configured,
                auto_picks=settings.auto_picks)


@router.get("/summary")
def summary():
    return record.summary()


@router.get("/board")
def board(day: Optional[str] = None):
    return slate.board(day)


@router.get("/equity")
def equity(markets: Optional[str] = None, live: bool = True):
    return record.equity(markets.split(",") if markets else None, live)


@router.get("/monthly")
def monthly(live: bool = True):
    return record.monthly(live)


@router.get("/books")
def books(live: bool = True):
    return record.by_book(live)


@router.get("/edge")
def edge(market: Optional[str] = None):
    return dict(buckets=record.edge_buckets(market), calibration=record.calibration(market))


@router.get("/bets")
def bets(market: Optional[str] = None, season: Optional[str] = None, q: Optional[str] = None, result: Optional[str] = None,
         limit: int = Query(100, le=1000), offset: int = 0):
    return record.bets(market, season, q, result, limit, offset)


@router.get("/player")
def player(name: str, market: str, before: Optional[str] = None):
    stat = MARKETS.get(market, {}).get("stat")
    if not stat:
        raise HTTPException(400, "Not a player market")
    return slate.player_form(name, stat, before=before)


class SimRequest(BaseModel):
    markets: List[str] = Field(default_factory=lambda: list(ORDER))
    days: int = 120
    sims: int = 5000
    bankroll: float = 100.0
    stake: float = 1.0
    staking: str = Field("flat", pattern="^(flat|percent)$")
    haircut: float = Field(0.0, ge=0, le=0.1)
    seasons: Optional[List[str]] = None


@router.post("/simulate")
def simulate(body: SimRequest):
    bad = [m for m in body.markets if m not in MARKETS]
    if bad or not body.markets:
        raise HTTPException(422, f"Unknown or empty markets: {bad}")
    try:
        return simulation.run(**body.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))


# ---------------------------------------------------------------- engine
@router.get("/engine")
def engine_status(day: Optional[str] = None):
    return dict(credits=runner.credit_status(), plan=runner.plan(day), ticks=runner.ticks(30), auto_picks=settings.auto_picks,
                jobs=jobs.recent(10))


@router.post("/engine/{kind}", dependencies=[Depends(require_admin)] if settings.require_api_key else [])
def engine_run(kind: str):
    if kind not in ("picks", "results", "test"):
        raise HTTPException(404, "Unknown run")
    return dict(job_id=runner.submit(kind))


@router.get("/jobs")
def job_list(limit: int = 20):
    return dict(jobs=jobs.recent(limit))


@router.get("/jobs/{job_id}")
def job_get(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "No such job")
    return j


@router.get("/logs")
def logs(level: str = "all", limit: int = 200, search: Optional[str] = None):
    return dict(logs=logbuffer.recent(level, limit, None, search))


# ---------------------------------------------------------------- exports
def _file(data: bytes, name: str, mime: str) -> Response:
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/export/picks.{fmt}")
def export_picks(fmt: str, day: Optional[str] = None):
    day = day or slate.today_et()
    if fmt == "csv":
        return _file(exporting.to_csv(exporting.picks_frame(day)), f"baseline_picks_{day}.csv", "text/csv")
    if fmt == "pdf":
        return _file(exporting.picks_pdf(day), f"baseline_picks_{day}.pdf", "application/pdf")
    raise HTTPException(404, "csv or pdf")


@router.get("/export/bets.csv")
def export_bets(market: Optional[str] = None, season: Optional[str] = None):
    return _file(exporting.to_csv(exporting.bets_frame(market, season)), "baseline_bets.csv", "text/csv")


@router.get("/export/report.pdf")
def export_report():
    return _file(exporting.report_pdf(), "baseline_track_record.pdf", "application/pdf")
