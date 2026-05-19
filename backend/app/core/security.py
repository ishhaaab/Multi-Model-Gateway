from jose import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from datetime import datetime, timedelta
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)
    
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: str) -> str:
    payload = {"sub": user_id,
               "exp" : datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRY_MINUTES)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        decoded = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id= decoded.get("sub")
        if user_id is None:
            raise  HTTPException(status_code=401, detail="invalid token")
    except HTTPException:
        raise 
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    
    return user_id
    
    
    




