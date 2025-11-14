import os
import time
import secrets
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import db, create_document, get_documents
from schemas import Developer, Session, Portfolio
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

class AuthStartResponse(BaseModel):
    url: str

class AuthCallbackQuery(BaseModel):
    code: str
    state: Optional[str] = None


@app.get("/")
def read_root():
    return {"message": "Portfolio SaaS Backend Running"}


@app.get("/auth/github/start", response_model=AuthStartResponse)
def github_auth_start():
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{BACKEND_URL}/auth/github/callback",
        "scope": "read:user user:email",
        "state": state,
        "allow_signup": "true",
    }
    qs = "&".join([f"{k}={v}" for k, v in params.items()])
    return {"url": f"https://github.com/login/oauth/authorize?{qs}"}


@app.get("/auth/github/callback")
def github_auth_callback(code: str, state: Optional[str] = None):
    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET):
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    # Exchange code for access token
    token_resp = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": f"{BACKEND_URL}/auth/github/callback",
        },
        timeout=10,
    )
    if token_resp.status_code != 200:
        raise HTTPException(400, detail="Failed to exchange code")
    token_json = token_resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(400, detail="No access token from GitHub")

    # Fetch user profile
    gh_user = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    ).json()

    emails = requests.get(
        "https://api.github.com/user/emails",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    ).json()

    primary_email = None
    if isinstance(emails, list):
        primary = next((e for e in emails if e.get("primary")), None)
        primary_email = (primary or emails[0]).get("email") if emails else None

    dev = Developer(
        username=gh_user.get("login"),
        name=gh_user.get("name"),
        email=primary_email,
        avatar_url=gh_user.get("avatar_url"),
        bio=gh_user.get("bio"),
        company=gh_user.get("company"),
        location=gh_user.get("location"),
        blog=gh_user.get("blog"),
        twitter_username=gh_user.get("twitter_username"),
        html_url=gh_user.get("html_url"),
        public_repos=gh_user.get("public_repos"),
    )

    # Upsert developer
    if db is None:
        raise HTTPException(500, detail="Database not available")
    db["developer"].update_one({"username": dev.username}, {"$set": dev.model_dump()}, upsert=True)

    # Create session
    token = secrets.token_urlsafe(32)
    expiry = time.time() + 60 * 60 * 24 * 7  # 7 days
    sess = Session(token=token, user_id=dev.username, expires_at=expiry)
    db["session"].update_one({"user_id": dev.username}, {"$set": sess.model_dump()}, upsert=True)

    # Ensure portfolio exists
    db["portfolio"].update_one({"username": dev.username}, {"$setOnInsert": Portfolio(username=dev.username).model_dump()}, upsert=True)

    # Redirect to frontend with token
    redirect_url = f"{FRONTEND_URL}/auth?token={token}"
    return {"redirect_to": redirect_url}


# Simple auth dependency using session token header
async def get_current_user(request: Request):
    token = request.headers.get("x-session-token")
    if not token:
        raise HTTPException(401, detail="Missing session token")
    if db is None:
        raise HTTPException(500, detail="Database not available")
    sess = db["session"].find_one({"token": token})
    if not sess or sess.get("expires_at", 0) < time.time():
        raise HTTPException(401, detail="Invalid or expired session token")
    user = db["developer"].find_one({"username": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, detail="User not found")
    return user


@app.get("/me")
async def me(user = Depends(get_current_user)):
    return {"user": user}


@app.get("/portfolio/{username}")
async def get_portfolio(username: str):
    if db is None:
        raise HTTPException(500, detail="Database not available")
    p = db["portfolio"].find_one({"username": username}, {"_id": 0})
    if not p:
        raise HTTPException(404, detail="Portfolio not found")
    return p


class PortfolioUpdate(BaseModel):
    headline: Optional[str] = None
    subheadline: Optional[str] = None
    sections: Optional[list] = None
    theme: Optional[dict] = None


@app.post("/portfolio")
async def update_portfolio(payload: PortfolioUpdate, user = Depends(get_current_user)):
    if db is None:
        raise HTTPException(500, detail="Database not available")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        return {"updated": False}
    db["portfolio"].update_one({"username": user["username"]}, {"$set": update}, upsert=True)
    return {"updated": True}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available" if db is None else "✅ Connected",
    }
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
