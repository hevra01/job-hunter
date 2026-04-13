"""
Job Hunter — FastAPI web application.

Endpoints:
  GET  /                        — review queue dashboard
  GET  /api/jobs                — list jobs (JSON)
  GET  /api/jobs/{id}           — job detail (JSON)
  POST /api/jobs/{id}/approve   — approve and queue for sending
  POST /api/jobs/{id}/reject    — reject job
  POST /api/jobs/{id}/send      — actually send the application
  POST /api/jobs/{id}/cover-letter — regenerate cover letter
  POST /api/scrape              — trigger manual scrape
  GET  /api/stats               — pipeline stats
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import Session, select

from models import Application, Job, create_tables, engine, get_application, get_job, get_jobs, get_session
from scheduler import run_discovery, start_scheduler

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")
Path("data").mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    scheduler = start_scheduler(CONFIG_PATH)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Job Hunter", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="ui/static"), name="static")
templates = Jinja2Templates(directory="ui/templates")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ─── HTML Views ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, status: str = "queued", session: Session = Depends(get_session)):
    cfg = load_config()
    min_score = cfg["targets"]["min_relevance_score"]

    jobs = get_jobs(session, status=status if status != "all" else None, min_score=0)
    counts = {
        "queued": len([j for j in get_jobs(session, status="queued")]),
        "approved": len([j for j in get_jobs(session, status="approved")]),
        "applied": len([j for j in get_jobs(session, status="applied")]),
        "rejected": len([j for j in get_jobs(session, status="rejected")]),
        "all": len(get_jobs(session)),
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "jobs": jobs,
            "counts": counts,
            "active_status": status,
            "min_score": min_score,
        },
    )


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail_page(request: Request, job_id: int, session: Session = Depends(get_session)):
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    application = get_application(session, job_id)
    cfg = load_config()
    rec_path = cfg.get("attachments", {}).get("recommendation_letter", "assets/recommendation.pdf")
    has_rec_letter = Path(rec_path).exists()

    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "job": job,
            "application": application,
            "has_rec_letter": has_rec_letter,
        },
    )


# ─── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def list_jobs(status: Optional[str] = None, min_score: int = 0, session: Session = Depends(get_session)):
    jobs = get_jobs(session, status=status, min_score=min_score)
    return [
        {
            "id": j.id,
            "title": j.title,
            "organization": j.organization,
            "url": j.url,
            "job_type": j.job_type,
            "source": j.source,
            "relevance_score": j.relevance_score,
            "relevance_reasoning": j.relevance_reasoning,
            "application_method": j.application_method,
            "contact_email": j.contact_email,
            "discovered_at": j.discovered_at.isoformat(),
            "status": j.status,
        }
        for j in jobs
    ]


@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: int, session: Session = Depends(get_session)):
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    application = get_application(session, job_id)
    return {
        "job": {
            "id": job.id,
            "title": job.title,
            "organization": job.organization,
            "url": job.url,
            "description": job.description,
            "job_type": job.job_type,
            "source": job.source,
            "relevance_score": job.relevance_score,
            "relevance_reasoning": job.relevance_reasoning,
            "application_method": job.application_method,
            "contact_email": job.contact_email,
            "discovered_at": job.discovered_at.isoformat(),
            "status": job.status,
        },
        "application": {
            "id": application.id,
            "cover_letter": application.edited_cover_letter or application.cover_letter,
            "include_cv": application.include_cv,
            "include_recommendation": application.include_recommendation,
            "send_method": application.send_method,
            "send_status": application.send_status,
            "sent_at": application.sent_at.isoformat() if application.sent_at else None,
        } if application else None,
    }


class ApproveRequest(BaseModel):
    cover_letter: Optional[str] = None
    include_cv: bool = True
    include_recommendation: bool = False
    send_method: Optional[str] = None  # override: email | form | manual


@app.post("/api/jobs/{job_id}/approve")
def approve_job(job_id: int, body: ApproveRequest, session: Session = Depends(get_session)):
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    application = get_application(session, job_id)
    if not application:
        raise HTTPException(status_code=400, detail="No application draft for this job")

    job.status = "approved"
    application.approved_at = datetime.utcnow()
    application.include_cv = body.include_cv
    application.include_recommendation = body.include_recommendation
    if body.cover_letter:
        application.edited_cover_letter = body.cover_letter
    if body.send_method:
        application.send_method = body.send_method

    session.add(job)
    session.add(application)
    session.commit()
    return {"status": "approved", "job_id": job_id}


@app.post("/api/jobs/{job_id}/reject")
def reject_job(job_id: int, session: Session = Depends(get_session)):
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = "rejected"
    session.add(job)
    session.commit()
    return {"status": "rejected", "job_id": job_id}


@app.post("/api/jobs/{job_id}/send")
def send_application(job_id: int, session: Session = Depends(get_session)):
    """Send the approved application via email or form filling."""
    job = get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "approved":
        raise HTTPException(status_code=400, detail="Job must be approved before sending")

    application = get_application(session, job_id)
    if not application:
        raise HTTPException(status_code=400, detail="No application found")

    cfg = load_config()
    user = cfg["user"]
    cv_path = cfg["attachments"]["cv"]
    rec_path = cfg["attachments"].get("recommendation_letter", "assets/recommendation.pdf")

    cover_letter_text = application.edited_cover_letter or application.cover_letter

    attachments = []
    if application.include_cv:
        attachments.append(cv_path)
    if application.include_recommendation and Path(rec_path).exists():
        attachments.append(rec_path)

    send_method = application.send_method or job.application_method
    result = {"success": False, "message": "", "needs_manual": False}

    if send_method == "email" and job.contact_email:
        from sender.gmail import send_email
        subject = f"Application for {job.title} at {job.organization}"
        success = send_email(
            to=job.contact_email,
            subject=subject,
            body=cover_letter_text,
            sender=user["email"],
            attachments=attachments,
        )
        result = {
            "success": success,
            "message": "Email sent" if success else "Email send failed",
            "needs_manual": not success,
        }
    elif send_method == "form":
        from sender.form_filler import submit_form_application, ApplicantInfo
        name_parts = user["name"].split(" ", 1)
        info = ApplicantInfo(
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else "",
            email=user["email"],
            phone=user.get("phone", ""),
            cover_letter=cover_letter_text,
            cv_path=cv_path,
        )
        result = submit_form_application(job.url, info)
    else:
        result = {
            "success": False,
            "message": "No email address and no form URL — please apply manually",
            "needs_manual": True,
        }

    if result["success"]:
        job.status = "applied"
        application.sent_at = datetime.utcnow()
        application.send_status = "sent"
    else:
        application.send_status = "failed" if not result.get("needs_manual") else "manual"
        if result.get("needs_manual"):
            application.notes = result.get("message", "")

    session.add(job)
    session.add(application)
    session.commit()
    return result



@app.post("/api/scrape")
def trigger_scrape():
    """Manually trigger a discovery run (runs in background thread)."""
    import threading
    thread = threading.Thread(target=run_discovery, kwargs={"config_path": CONFIG_PATH}, daemon=True)
    thread.start()
    return {"status": "started", "message": "Discovery run started in background"}


@app.get("/api/stats")
def get_stats(session: Session = Depends(get_session)):
    all_jobs = get_jobs(session)
    return {
        "total": len(all_jobs),
        "by_status": {
            status: len([j for j in all_jobs if j.status == status])
            for status in ["new", "queued", "approved", "rejected", "applied", "archived"]
        },
        "by_source": {},
        "avg_score": (
            sum(j.relevance_score for j in all_jobs) / len(all_jobs)
            if all_jobs else 0
        ),
    }
