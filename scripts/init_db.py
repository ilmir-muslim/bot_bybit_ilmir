import sys
from pathlib import Path
from app.db import engine, Base
import app.models  

sys.path.append(str(Path(__file__).resolve().parent.parent / "app"))


def init_db():
    print("🔧 Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Done.")

if __name__ == "__main__":
    init_db()
