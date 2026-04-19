from datetime import datetime
from typing import Optional
from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field, create_engine, Session, select
import json


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    organization: str
    url: str = Field(unique=True)
    description: str
    job_type: str  # phd | research_scientist | ml_engineer | postdoc | other
    source: str    # scraper name: euraxess | academic_positions | jobs_ac_uk | lab | company | linkedin
    relevance_score: int = Field(default=0)
    relevance_reasoning: str = Field(default="")
    application_method: str = Field(default="form")  # email | form | unknown
    contact_email: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="new")
    # new | queued | approved | rejected | applied | archived
    company_tier: str = Field(default="")  # high | medium | startup | accessible | ""


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    cover_letter: str
    edited_cover_letter: Optional[str] = None
    include_cv: bool = Field(default=True)
    include_recommendation: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    send_method: str = Field(default="")  # email | form | manual
    send_status: str = Field(default="pending")  # pending | sent | failed | manual
    notes: str = Field(default="")


class InterviewProblem(SQLModel, table=True):
    """LeetCode interview problem imported from GitHub dataset."""
    __table_args__ = (
        UniqueConstraint("leetcode_url", "company", "recency", name="uq_problem_company_recency"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    difficulty: str = ""          # Easy | Medium | Hard
    frequency: float = 0.0
    acceptance_rate: float = 0.0
    leetcode_url: str
    topics: str = ""              # comma-separated
    company: str                  # "Google", "Amazon", etc.
    recency: str                  # "30d" | "90d" | "6m" | "older" | "all"
    imported_at: datetime = Field(default_factory=datetime.utcnow)


class PracticeSession(SQLModel, table=True):
    """Tracks user progress on interview problems."""
    id: Optional[int] = Field(default=None, primary_key=True)
    problem_id: int = Field(foreign_key="interviewproblem.id")
    status: str = Field(default="unsolved")  # unsolved | attempted | solved
    user_solution: Optional[str] = None
    notes: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


DATABASE_URL = "sqlite:///./data/db.sqlite"
engine = create_engine(DATABASE_URL, echo=False)


def create_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def get_jobs(session: Session, status: Optional[str] = None, min_score: int = 0):
    query = select(Job).where(Job.relevance_score >= min_score)
    if status:
        query = query.where(Job.status == status)
    return session.exec(query.order_by(Job.relevance_score.desc())).all()


def get_job(session: Session, job_id: int) -> Optional[Job]:
    return session.get(Job, job_id)


def get_application(session: Session, job_id: int) -> Optional[Application]:
    return session.exec(select(Application).where(Application.job_id == job_id)).first()


def job_exists(session: Session, url: str) -> bool:
    return session.exec(select(Job).where(Job.url == url)).first() is not None


# ─── Interview Prep Helpers ──────────────────────────────────────────────────

def get_interview_problems(
    session: Session,
    company: Optional[str] = None,
    difficulty: Optional[str] = None,
    recency: Optional[str] = None,
    status: Optional[str] = None,
):
    """Query interview problems with optional filters. Joins PracticeSession for status filter."""
    query = select(InterviewProblem)
    if company:
        query = query.where(InterviewProblem.company == company)
    if difficulty:
        query = query.where(InterviewProblem.difficulty == difficulty)
    if recency:
        query = query.where(InterviewProblem.recency == recency)

    problems = session.exec(query.order_by(InterviewProblem.frequency.desc())).all()

    if status:
        # Filter by practice status (requires joining in Python since SQLModel join is verbose)
        filtered = []
        for p in problems:
            ps = get_practice_session(session, p.id)
            p_status = ps.status if ps else "unsolved"
            if p_status == status:
                filtered.append(p)
        return filtered
    return problems


def get_practice_session(session: Session, problem_id: int) -> Optional[PracticeSession]:
    """Get the practice session for a problem, or None."""
    return session.exec(
        select(PracticeSession).where(PracticeSession.problem_id == problem_id)
    ).first()


def get_interview_stats(session: Session, company: Optional[str] = None) -> dict:
    """Get interview prep statistics."""
    query = select(InterviewProblem)
    if company:
        query = query.where(InterviewProblem.company == company)
    problems = session.exec(query).all()

    problem_ids = {p.id for p in problems}
    sessions = session.exec(
        select(PracticeSession).where(PracticeSession.problem_id.in_(problem_ids))
    ).all() if problem_ids else []
    status_map = {s.problem_id: s.status for s in sessions}

    solved = sum(1 for s in status_map.values() if s == "solved")
    attempted = sum(1 for s in status_map.values() if s == "attempted")

    by_difficulty = {}
    for p in problems:
        d = p.difficulty or "Unknown"
        if d not in by_difficulty:
            by_difficulty[d] = {"total": 0, "solved": 0}
        by_difficulty[d]["total"] += 1
        if status_map.get(p.id) == "solved":
            by_difficulty[d]["solved"] += 1

    by_company = {}
    for p in problems:
        if p.company not in by_company:
            by_company[p.company] = {"total": 0, "solved": 0}
        by_company[p.company]["total"] += 1
        if status_map.get(p.id) == "solved":
            by_company[p.company]["solved"] += 1

    return {
        "total": len(problems),
        "solved": solved,
        "attempted": attempted,
        "unsolved": len(problems) - solved - attempted,
        "by_difficulty": by_difficulty,
        "by_company": by_company,
    }
