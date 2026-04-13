from datetime import datetime
from typing import Optional
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
