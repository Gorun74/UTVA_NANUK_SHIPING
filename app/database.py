from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker, DeclarativeBase
from flask import g
import json
import os
from pathlib import Path


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
    """Create all tables and seed if empty."""
    from app.models import Base as ModelBase
    ModelBase.metadata.create_all(bind=_engine)
    _run_migrations()
    _seed_if_empty()


def _run_migrations():
    """Apply any schema additions that might be missing."""
    with _engine.connect() as conn:
        migrations = [
            "ALTER TABLE cases ADD COLUMN category TEXT DEFAULT 'case'",
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


def _seed_if_empty():
    """On first deploy (empty DB), load items from the bundled JSON fixture."""
    with _engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM cases")).scalar()
        if count and count > 0:
            return  # already has data

    fixture = Path(__file__).parent / "data" / "items_fixture.json"
    if not fixture.exists():
        return

    with open(fixture, encoding="utf-8") as f:
        rows = json.load(f)

    from app.models import Item
    session = _session_factory()
    try:
        for row in rows:
            item = Item(
                sku=row["sku"],
                upc=row.get("upc"),
                old_item_number=row.get("old_item_number"),
                description=row.get("description"),
                us_map_price=row.get("us_map_price"),
                price=row.get("price"),
                dim_interior=row.get("dim_interior"),
                dim_exterior=row.get("dim_exterior"),
                int_length_mm=row.get("int_length_mm"),
                int_width_mm=row.get("int_width_mm"),
                int_height_mm=row.get("int_height_mm"),
                ext_length_mm=row.get("ext_length_mm"),
                ext_width_mm=row.get("ext_width_mm"),
                ext_height_mm=row.get("ext_height_mm"),
                volume_m3=row.get("volume_m3"),
                reorder_point=row.get("reorder_point", 3),
                category=row.get("category", "case"),
            )
            session.merge(item)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[seed] Error: {e}")
    finally:
        session.close()
