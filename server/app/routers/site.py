from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Doing, Setting, Track
from ..schemas import DoingIn, DoingOut, SiteIn, SiteOut, TrackIn, TrackOut
from ..security import current_user

router = APIRouter(prefix="/api/site", tags=["site"], dependencies=[Depends(current_user)])


def _get_site(db: Session) -> dict:
    row = db.get(Setting, "site")
    return dict(row.value) if row and row.value else {}


def _site_out(db: Session) -> SiteOut:
    base = _get_site(db)
    tracks = db.scalars(select(Track).order_by(Track.sort, Track.id)).all()
    doing = db.scalars(select(Doing).order_by(Doing.sort, Doing.id)).all()
    payload = {
        k: base.get(k, "")
        for k in ("name", "en", "mark", "intro", "lead", "desc", "playlistId", "musicApi", "musicServer", "portfolioUrl", "backgroundImage")
    }
    payload["backgroundImageDim"] = base.get("backgroundImageDim", 0.0)
    payload["contact"] = base.get("contact", {})
    payload["bio"] = base.get("bio", [])
    payload["facts"] = base.get("facts", [])
    payload["tracks"] = [TrackOut.model_validate(t) for t in tracks]
    payload["doing"] = [DoingOut.model_validate(d) for d in doing]
    return SiteOut(**payload)


@router.get("", response_model=SiteOut)
def get_site(db: Session = Depends(get_db)):
    return _site_out(db)


@router.put("", response_model=SiteOut)
def update_site(payload: SiteIn, db: Session = Depends(get_db)):
    row = db.get(Setting, "site")
    value = payload.model_dump()
    if row is None:
        db.add(Setting(key="site", value=value))
    else:
        row.value = value
    db.commit()
    return _site_out(db)


# ---------- 曲目 ----------


@router.get("/tracks", response_model=list[TrackOut])
def list_tracks(db: Session = Depends(get_db)):
    return db.scalars(select(Track).order_by(Track.sort, Track.id)).all()


@router.post("/tracks", response_model=TrackOut, status_code=201)
def create_track(payload: TrackIn, db: Session = Depends(get_db)):
    track = Track(**payload.model_dump())
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


@router.put("/tracks/{track_id}", response_model=TrackOut)
def update_track(track_id: int, payload: TrackIn, db: Session = Depends(get_db)):
    track = db.get(Track, track_id)
    if not track:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="曲目不存在")
    for key, value in payload.model_dump().items():
        setattr(track, key, value)
    db.commit()
    db.refresh(track)
    return track


@router.delete("/tracks/{track_id}", status_code=204)
def delete_track(track_id: int, db: Session = Depends(get_db)):
    track = db.get(Track, track_id)
    if not track:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="曲目不存在")
    db.delete(track)
    db.commit()


# ---------- 在做的事 ----------


@router.get("/doing", response_model=list[DoingOut])
def list_doing(db: Session = Depends(get_db)):
    return db.scalars(select(Doing).order_by(Doing.sort, Doing.id)).all()


@router.post("/doing", response_model=DoingOut, status_code=201)
def create_doing(payload: DoingIn, db: Session = Depends(get_db)):
    item = Doing(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/doing/{doing_id}", response_model=DoingOut)
def update_doing(doing_id: int, payload: DoingIn, db: Session = Depends(get_db)):
    item = db.get(Doing, doing_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="这一条不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/doing/{doing_id}", status_code=204)
def delete_doing(doing_id: int, db: Session = Depends(get_db)):
    item = db.get(Doing, doing_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="这一条不存在")
    db.delete(item)
    db.commit()
