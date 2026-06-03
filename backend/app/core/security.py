import hashlib
import uuid

from jose import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from datetime import datetime, timedelta

from app.core.config import settings
from app.models.refresh_tokens import RefreshToken

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed hash used to equalize login timing when the email doesn't exist,
# so an attacker can't distinguish "no such user" from "wrong password".
DUMMY_PASSWORD_HASH = pwd_context.hash("not-a-real-password")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)
    
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def hash_token(token: str) -> str:
    """SHA-256 of a refresh token for at-rest storage as tokens are high-entropy"""
    return hashlib.sha256(token.encode()).hexdigest()

def create_refresh_token(user_id: str, expires_at) -> str:
    payload = {
        "sub": user_id,
        "exp": expires_at,
        "type": "refresh",
        "jti": uuid.uuid4().hex,   # nonce so every refresh token and its hash is unique
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_access_token(user_id: str) -> str:
    payload = {"sub": user_id,
               "exp" : datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRY_MINUTES),
               "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        decoded = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id= decoded.get("sub")
        if decoded.get("type") != "access":
            raise HTTPException(status_code=401, detail="invalid token type")
        if user_id is None:
            raise  HTTPException(status_code=401, detail="invalid token")
    except HTTPException:
        raise 
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    
    return user_id
    
    
    




