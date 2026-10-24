from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, model_validator

# -------------------------------------------------------------
# Base & Generic Schemas
# -------------------------------------------------------------
class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None

# -------------------------------------------------------------
# Registration & Authentication Schemas
# -------------------------------------------------------------
class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150, description="Full Name of the researcher")
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$", description="Unique username")
    email: EmailStr = Field(..., description="Valid academic/personal email address")
    password: str = Field(..., min_length=6, max_length=128, description="Strong password")
    confirm_password: str = Field(..., min_length=6, max_length=128, description="Matching password confirmation")
    institution: Optional[str] = Field(default=None, max_length=200, description="University or Institution")
    department: Optional[str] = Field(default=None, max_length=200, description="Department")
    research_interests: Optional[str] = Field(default=None, max_length=1000, description="Fields of research interest")

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class UserLogin(BaseModel):
    identifier: str = Field(..., min_length=3, description="Email address or username")
    password: str = Field(..., min_length=1, description="Account password")


class UserResponse(BaseModel):
    id: int
    full_name: str
    username: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    profile_image: Optional[str] = None
    institution: Optional[str] = None
    department: Optional[str] = None
    research_interests: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, description="Verification token sent to email")


class ResendVerificationRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address to resend verification link")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered account email")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, description="Password reset token")
    new_password: str = Field(..., min_length=6, max_length=128, description="New strong password")
    confirm_new_password: str = Field(..., min_length=6, max_length=128, description="Matching password confirmation")

    @model_validator(mode="after")
    def check_new_passwords_match(self):
        if self.new_password != self.confirm_new_password:
            raise ValueError("New passwords do not match.")
        return self


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, description="Current existing password")
    new_password: str = Field(..., min_length=6, max_length=128, description="New strong password")
    confirm_new_password: str = Field(..., min_length=6, max_length=128, description="Confirm new password")

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.new_password != self.confirm_new_password:
            raise ValueError("New passwords do not match.")
        return self


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    institution: Optional[str] = Field(default=None, max_length=200)
    department: Optional[str] = Field(default=None, max_length=200)
    research_interests: Optional[str] = Field(default=None, max_length=1000)
