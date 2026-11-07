from pydantic import BaseModel


# Schema for profile update
class ProfileUpdate(BaseModel):
    name: str
