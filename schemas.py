"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict

class Developer(BaseModel):
    """
    Developers collection schema
    Collection name: "developer"
    """
    username: str = Field(..., description="GitHub username")
    name: Optional[str] = Field(None, description="Display name")
    email: Optional[str] = Field(None, description="Primary email")
    avatar_url: Optional[HttpUrl] = Field(None, description="Avatar URL")
    bio: Optional[str] = Field(None, description="Bio from GitHub or custom")
    company: Optional[str] = None
    location: Optional[str] = None
    blog: Optional[str] = None
    twitter_username: Optional[str] = None
    html_url: Optional[HttpUrl] = None
    public_repos: Optional[int] = 0

class Session(BaseModel):
    """
    Session tokens for authenticated users
    Collection: "session"
    """
    token: str = Field(..., description="Opaque session token")
    user_id: str = Field(..., description="Reference to developer _id")
    expires_at: float = Field(..., description="Unix timestamp when token expires")

class Portfolio(BaseModel):
    """
    Public portfolio content per user
    Collection: "portfolio"
    """
    username: str = Field(..., description="GitHub username (slug)")
    headline: Optional[str] = Field("Building with code.", description="Hero headline")
    subheadline: Optional[str] = Field("Developer portfolio powered by GitHub.")
    sections: List[Dict] = Field(default_factory=list, description="Flexible content blocks")
    theme: Dict = Field(default_factory=lambda: {"accent":"#3b82f6"})
