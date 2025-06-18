from app.database.engine import engine
from app.database.models import Base  # Импортируй Base из models.py

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
