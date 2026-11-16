import json
import sqlite3

from config import DB_PATH

con = sqlite3.connect(DB_PATH, check_same_thread=False)
con.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
con.execute("""CREATE TABLE IF NOT EXISTS delays (
    ts TEXT DEFAULT CURRENT_TIMESTAMP, day TEXT, origin TEXT, mission TEXT,
    base_dep TEXT, delay_min INTEGER, cancelled INTEGER)""")
con.commit()


def get(k, default=None):
    row = con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(row[0]) if row else default


def put(k, v):
    con.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (k, json.dumps(v, default=str)))
    con.commit()


def log_delay(day, origin, mission, base_dep, delay, cancelled):
    con.execute("INSERT INTO delays (day, origin, mission, base_dep, delay_min, cancelled) VALUES (?,?,?,?,?,?)",
                (day, origin, mission, base_dep, delay, int(cancelled)))
    con.commit()


def last_delays(n=20):
    return con.execute("SELECT day, origin, mission, base_dep, delay_min, cancelled FROM delays "
                       "ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
