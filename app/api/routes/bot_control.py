from fastapi import APIRouter
from app.services.bot_controller import bot_controller

router = APIRouter()

@router.post("/start")
def start_bot():
    bot_controller.start()
    return {"status": "started"}

@router.post("/stop")
def stop_bot():
    bot_controller.stop()
    return {"status": "stopped"}

@router.get("/status")
def bot_status():
    return {"status": bot_controller.status()}
