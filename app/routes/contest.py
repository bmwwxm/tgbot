import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import Database
from app.routes.user import get_current_user
from app.routes.admin import require_admin

router = APIRouter(prefix="/api/contest", tags=["contest"])

_db: Database | None = None

REWARD_PER_100_VIEWS = 0.1
BOT_LINK = "t.me/originalton_bot"

PLATFORM_PATTERNS = {
    "tiktok": re.compile(r"(tiktok\.com|vm\.tiktok\.com)", re.I),
    "instagram": re.compile(r"(instagram\.com|instagr\.am)", re.I),
    "youtube": re.compile(r"(youtube\.com/shorts|youtu\.be)", re.I),
}


def init_routes(db: Database) -> None:
    global _db
    _db = db


def _detect_platform(url: str) -> str | None:
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url):
            return platform
    return None


class SubmitVideo(BaseModel):
    video_url: str


@router.post("/submit")
async def submit_video(req: SubmitVideo, user: dict = Depends(get_current_user)):
    assert _db is not None

    url = req.video_url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    platform = _detect_platform(url)
    if not platform:
        raise HTTPException(
            status_code=400,
            detail="Неверная ссылка. Поддерживаются: TikTok, Instagram Reels, YouTube Shorts",
        )

    submission_id = await _db.add_contest_submission(
        user_id=user["user_id"],
        platform=platform,
        video_url=url,
    )
    if not submission_id:
        raise HTTPException(status_code=400, detail="Это видео уже отправлено")

    return {
        "status": "ok",
        "submission_id": submission_id,
        "platform": platform,
        "message": "Видео отправлено на проверку! Администратор проверит наличие ссылки и начислит награду.",
    }


@router.get("/my")
async def my_submissions(user: dict = Depends(get_current_user)):
    assert _db is not None
    submissions = await _db.get_user_submissions(user["user_id"])
    return {"submissions": submissions}


@router.get("/rules")
async def get_rules():
    return {
        "reward_per_100_views": REWARD_PER_100_VIEWS,
        "bot_link": BOT_LINK,
        "platforms": ["TikTok", "Instagram Reels", "YouTube Shorts"],
    }


# ── Admin endpoints ─────────────────────────────────────

@router.get("/admin/list")
async def admin_list_submissions(
    status: str = "all",
    admin: dict = Depends(require_admin),
):
    assert _db is not None
    submissions = await _db.get_all_contest_submissions(status=status)
    return {"submissions": submissions}


class ReviewSubmission(BaseModel):
    submission_id: int
    status: str  # approved / rejected
    has_link: bool = False
    admin_note: str = ""


@router.post("/admin/review")
async def admin_review(req: ReviewSubmission, admin: dict = Depends(require_admin)):
    assert _db is not None
    if req.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status: approved or rejected")
    updated = await _db.update_contest_submission(
        req.submission_id,
        status=req.status,
        has_link=req.has_link,
        admin_note=req.admin_note,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"status": "ok", "submission": updated}


class PayoutSubmission(BaseModel):
    submission_id: int
    views_count: int


@router.post("/admin/payout")
async def admin_payout(req: PayoutSubmission, admin: dict = Depends(require_admin)):
    assert _db is not None

    submissions = await _db.get_all_contest_submissions(status="all")
    sub = None
    for s in submissions:
        if s["id"] == req.submission_id:
            sub = s
            break
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub["status"] != "approved":
        raise HTTPException(status_code=400, detail="Submission not approved")
    if not sub["has_link"]:
        raise HTTPException(status_code=400, detail="Link not verified")

    new_views = req.views_count
    old_views = sub["last_views"]
    if new_views <= old_views:
        raise HTTPException(status_code=400, detail="Views count must be higher than last check")

    added_views = new_views - old_views
    reward_units = added_views // 100
    reward = reward_units * REWARD_PER_100_VIEWS

    if reward <= 0:
        raise HTTPException(status_code=400, detail="Not enough new views for reward (need 100+)")

    await _db.contest_payout(req.submission_id, sub["user_id"], reward, new_views)

    try:
        from app.bot import notify_user
        await notify_user(
            sub["user_id"], "contest_payout",
            views=new_views, reward=reward,
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "reward": reward,
        "new_views": new_views,
        "added_views": added_views,
    }
