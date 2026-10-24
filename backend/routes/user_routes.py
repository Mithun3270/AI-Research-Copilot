from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.schemas import (
    UserResponse,
    UserProfileUpdate,
    ChangePasswordRequest,
    MessageResponse,
)
from backend.security import hash_password, verify_password
from backend.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/profile", response_model=UserResponse)
def get_user_profile(current_user: User = Depends(get_current_user)):
    """Retrieves current user profile."""
    return current_user


@router.put("/profile", response_model=UserResponse)
def update_user_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates user profile information."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip()
    if payload.institution is not None:
        current_user.institution = payload.institution.strip()
    if payload.department is not None:
        current_user.department = payload.department.strip()
    if payload.research_interests is not None:
        current_user.research_interests = payload.research_interests.strip()

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allows an authenticated user to change their password."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()

    return MessageResponse(message="Password successfully updated.")


@router.delete("/account", response_model=MessageResponse)
def deactivate_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivates user account."""
    current_user.is_active = False
    db.commit()
    return MessageResponse(message="Account successfully deactivated.")
