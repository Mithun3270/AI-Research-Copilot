from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from backend.database import get_db
from backend.models import User
from backend.schemas import (
    UserRegister,
    UserLogin,
    UserResponse,
    Token,
    VerifyEmailRequest,
    ResendVerificationRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MessageResponse,
)
from backend.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_random_token,
)
from backend.email_service import email_service
from backend.dependencies import get_current_user
from backend.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Registers a new researcher account, generates an email verification token,
    and dispatches a verification link.
    """
    normalized_email = payload.email.lower().strip()
    normalized_username = payload.username.lower().strip()

    # Check for duplicate email
    if db.query(User).filter(func.lower(User.email) == normalized_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # Check for duplicate username
    if db.query(User).filter(func.lower(User.username) == normalized_username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This username is already taken. Please choose another.",
        )

    # If first registered user in the entire system, grant admin role
    is_first_user = db.query(User).count() == 0
    assigned_role = "admin" if is_first_user else "user"

    token = generate_random_token()
    token_expiry = datetime.utcnow() + timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS)

    new_user = User(
        full_name=payload.full_name.strip(),
        username=payload.username.strip(),
        email=normalized_email,
        hashed_password=hash_password(payload.password),
        role=assigned_role,
        is_active=True,
        is_verified=False,
        verification_token=token,
        verification_token_expires=token_expiry,
        institution=payload.institution.strip() if payload.institution else None,
        department=payload.department.strip() if payload.department else None,
        research_interests=payload.research_interests.strip() if payload.research_interests else None,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Dispatch email
    email_service.send_verification_email(
        to_email=new_user.email,
        full_name=new_user.full_name,
        token=token
    )

    return MessageResponse(
        message="Registration successful! Check your email to verify your account.",
        detail=f"Verification link sent to {new_user.email}."
    )


@router.get("/verify-email", response_model=MessageResponse)
def verify_email_get(token: str = Query(..., description="Verification token"), db: Session = Depends(get_db)):
    """Verifies user email via URL query parameter token."""
    return _process_email_verification(token, db)


@router.post("/verify-email", response_model=MessageResponse)
def verify_email_post(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verifies user email via JSON request body token."""
    return _process_email_verification(payload.token, db)


def _process_email_verification(token: str, db: Session) -> MessageResponse:
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unrecognized verification token.",
        )

    if user.verification_token_expires and user.verification_token_expires < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification link has expired. Please request a new verification email.",
        )

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.commit()

    return MessageResponse(
        message="Email verified successfully. You can now log in.",
        detail="Account is activated."
    )


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)):
    """Resends account verification link if the account is unverified."""
    normalized_email = payload.email.lower().strip()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()

    if not user:
        # Avoid user enumeration
        return MessageResponse(
            message="If an unverified account exists with that email, a verification link has been sent."
        )

    if user.is_verified:
        return MessageResponse(
            message="This account is already verified. You can proceed directly to login."
        )

    token = generate_random_token()
    user.verification_token = token
    user.verification_token_expires = datetime.utcnow() + timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS)
    db.commit()

    email_service.send_verification_email(
        to_email=user.email,
        full_name=user.full_name,
        token=token
    )

    return MessageResponse(
        message="If an unverified account exists with that email, a verification link has been sent.",
        detail=f"Verification link sent to {user.email}."
    )


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticates user via Email OR Username and password,
    returning a JWT access token and user profile.
    """
    identifier = payload.identifier.strip().lower()

    user = db.query(User).filter(
        or_(
            func.lower(User.email) == identifier,
            func.lower(User.username) == identifier
        )
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Please contact support.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    # Update last login timestamp
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)

    # Create JWT
    token_payload = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": user.role,
    }
    access_token = create_access_token(data=token_payload)

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse)
def logout():
    """Client-side token disposal endpoint."""
    return MessageResponse(message="Successfully logged out.")


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user's profile information."""
    return current_user


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Sends a password reset link to the user's email if the account exists.
    Always returns a generic success message to prevent user enumeration.
    """
    normalized_email = payload.email.lower().strip()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()

    if user:
        reset_token = generate_random_token()
        user.reset_password_token = reset_token
        user.reset_password_token_expires = datetime.utcnow() + timedelta(hours=settings.RESET_TOKEN_EXPIRE_HOURS)
        db.commit()

        email_service.send_password_reset_email(
            to_email=user.email,
            full_name=user.full_name,
            token=reset_token
        )

    return MessageResponse(
        message="If the account exists, a reset link has been sent to your email."
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Resets user password using a valid reset token."""
    user = db.query(User).filter(User.reset_password_token == payload.token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    if user.reset_password_token_expires and user.reset_password_token_expires < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired. Please request a new one.",
        )

    user.hashed_password = hash_password(payload.new_password)
    user.reset_password_token = None
    user.reset_password_token_expires = None
    db.commit()

    return MessageResponse(
        message="Password reset successful. You may now log in with your new password."
    )
