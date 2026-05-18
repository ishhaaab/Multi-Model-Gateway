from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status, Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.users import User


class UserCreate(BaseModel):
    email: str
    password: str

router = APIRouter()

@router.post("/register")
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalar_one_or_none()
    
    if user != None:
        raise HTTPException(status_code=400, detail="user already exists")

    new_user = User(email=user_data.email, hashed_password=hash_password(user_data.password))
    db.add(new_user)
    await db.commit()    
    return {"message": "user created successfully"}
    
    

@router.post("/login")
async def login_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalar_one_or_none()
    
    if user is not None and verify_password(user_data.password, user.hashed_password):
        token = create_access_token(str(user.id))
        return {"access_token": token, "token_type": "bearer"}
    
    raise HTTPException(status_code=401, detail="invalid credentials")