import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource
def engine():
    url = (
        f"postgresql+psycopg2://{os.environ['PGUSER']}:{os.environ['PGPASSWORD']}"
        f"@{os.environ.get('PGHOST', 'postgres')}:{os.environ.get('PGPORT', '5432')}"
        f"/{os.environ.get('PGDATABASE', 'restaurant_db')}"
    )
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=30)
def query(sql: str, **params) -> pd.DataFrame:
    """อ่านจาก PostgreSQL โดยตรง (cache 30 วินาที)"""
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def table_exists(name: str) -> bool:
    df = query("SELECT to_regclass(:n) IS NOT NULL AS ok", n=f"public.{name}")
    return bool(df.iloc[0]["ok"])
