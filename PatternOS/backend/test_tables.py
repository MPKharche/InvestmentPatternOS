from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
rows = db.execute(
    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
).fetchall()
print("Tables:", [r[0] for r in rows])
db.close()
