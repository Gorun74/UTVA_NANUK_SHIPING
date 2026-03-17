from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker, DeclarativeBase
from flask import g
import os


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def init_engine(database_url: str):
    global _engine, _session_factory

    # SQLite needs check_same_thread=False
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    _engine = create_engine(database_url, connect_args=connect_args)
    _session_factory = scoped_session(sessionmaker(bind=_engine))
    return _engine


def get_session():
    """Return a SQLAlchemy session scoped to the current Flask request."""
    if "db_session" not in g:
        g.db_session = _session_factory()
    return g.db_session


def close_session(error=None):
    session = g.pop("db_session", None)
    if session is not None:
        if error:
            session.rollback()
        session.close()


def init_db():
    """Create all tables."""
    from app.models import Base as ModelBase
    ModelBase.metadata.create_all(bind=_engine)
    _run_migrations()


def _run_migrations():
    """Apply any schema additions that might be missing."""
    with _engine.connect() as conn:
        migrations = [
            "ALTER TABLE containers ADD COLUMN total_cbm REAL",
            "ALTER TABLE containers ADD COLUMN ship_ocean_aud REAL",
            "ALTER TABLE containers ADD COLUMN ship_extras_aud REAL",
            "ALTER TABLE containers ADD COLUMN ship_insurance_aud REAL",
            "ALTER TABLE containers ADD COLUMN ship_duty_aud REAL",
            "ALTER TABLE containers ADD COLUMN ship_gst_aud REAL",
            "ALTER TABLE containers ADD COLUMN ship_total_aud REAL",
            "ALTER TABLE fifo_lots ADD COLUMN ship_cost_per_unit_aud REAL",
            "ALTER TABLE fifo_lots ADD COLUMN duty_per_unit_aud REAL",
            "ALTER TABLE sale_lines ADD COLUMN ship_cost_per_unit_aud REAL",
            "ALTER TABLE sale_lines ADD COLUMN ship_cost_sale_aud REAL",
            "ALTER TABLE sale_lines ADD COLUMN duty_per_unit_aud REAL",
            "ALTER TABLE sale_lines ADD COLUMN net_profit_aud REAL",
            "ALTER TABLE sale_lines ADD COLUMN net_margin_pct REAL",
            "ALTER TABLE sale_lines ADD COLUMN total_return_aud REAL",
        ]
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass

        # Create sale_allocations if missing
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sale_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                sale_line_id INTEGER,
                container_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                qty INTEGER NOT NULL,
                revenue_aud REAL,
                cogs_aud REAL,
                net_profit_aud REAL,
                FOREIGN KEY(sale_id) REFERENCES sales(id),
                FOREIGN KEY(sale_line_id) REFERENCES sale_lines(id),
                FOREIGN KEY(container_id) REFERENCES containers(id)
            )
        """))
        conn.commit()
