from fastapi import APIRouter

router = APIRouter()


@router.post("/stream")
async def chat_stream():
    return {"message": "Chat streaming coming soon"}


@router.get("/sessions")
def get_sessions():
    return []

