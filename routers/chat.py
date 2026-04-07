from fastapi import APIRouter

router = APIRouter()


@router.post("/")
def chat():
    return {"message": "Chat endpoint - coming soon"}


@router.get("/sessions")
def get_sessions():
    return {"message": "Sessions endpoint - coming soon"}
