from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.trade_log import router as trade_log_router
from app.api.routes.bot_control import router as bot_control_router

app = FastAPI()

# ✅ Настройка CORS для доступа с фронтенда (например, Vue на localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # можно расширить позже
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Подключаем API-роуты
app.include_router(trade_log_router, prefix="/api")
app.include_router(bot_control_router, prefix="/api/bot")
