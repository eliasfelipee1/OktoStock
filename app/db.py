import os
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()


def connect():
    conn = psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)
    conn.execute("SELECT set_config('TimeZone', %s, false)", (os.getenv('APP_TIMEZONE', 'America/Sao_Paulo'),))
    return conn
