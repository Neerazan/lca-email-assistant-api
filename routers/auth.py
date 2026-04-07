from fastapi import APIRouter

router = APIRouter()


@router.get("/login")
def login():
    return {"message": "Google OAuth login - coming soon"}


@router.get("/callback")
def callback():
    return {"message": "OAuth callback - coming soon"}


@router.post("/logout")
def logout():
    return {"message": "Logout - coming soon"}
