from jose import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.core import security
from app.core.config import settings

from app.models.users import User
from app.models.refresh_tokens import RefreshToken

class UserCreate(BaseModel):
    email: str
    password: str

router = APIRouter()

@router.post("/register")
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(User).where(User.email == user_data.email))
    user = query.scalar_one_or_none()
    
    if user is not None:
        raise HTTPException(status_code=400, detail="user already exists")

    new_user = User(email=user_data.email, hashed_password=security.hash_password(user_data.password))
    db.add(new_user)
    await db.commit()    
    return {"message": "user created successfully"}
    

@router.post("/login")
async def login_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(User).where(User.email == user_data.email))
    user = query.scalar_one_or_none()
    
    if user is not None and security.verify_password(user_data.password, user.hashed_password):
        expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRY_DAYS)
        token= security.create_refresh_token(str(user.id), expires_at)
        
        refresh_token= RefreshToken(token= token, 
                                    user_id= user.id,
                                    expires_at= expires_at
        )
        db.add(refresh_token)
        await db.commit()
        
        access_token = security.create_access_token(str(user.id))
        return {"refresh_token": token,
                "access_token": access_token, 
                "token_type": "bearer"}
    
    raise HTTPException(status_code=401, detail="invalid credentials")


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    # find token in database
    query = await db.execute(select(RefreshToken).where(RefreshToken.token== request.refresh_token))
    token_record = query.scalar_one_or_none()

    if token_record is None:
        raise HTTPException(status_code=401, detail="invalid refresh token")

    # verify JWT not expired
    try:
        payload = jwt.decode(request.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="invalid token type")
        if user_id is None:
            raise HTTPException(status_code=401, detail="invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="refresh token expired or invalid")

    # return new access token
    access_token = security.create_access_token(user_id)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: RefreshRequest, db: AsyncSession = Depends(get_db), user_id: str = Depends(security.get_current_user)):
    query = await db.execute(select(RefreshToken).where(RefreshToken.token== request.refresh_token, RefreshToken.user_id== user_id))
    token_record = query.scalar_one_or_none()

    if token_record is None:
        raise HTTPException(status_code=401, detail="invalid refresh token")

    await db.delete(token_record)
    await db.commit()
    return {"message": "logged out successfully"}