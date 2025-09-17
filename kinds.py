from pydantic import BaseModel


class CreateUserRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    username: str
    user_uid: str
    password: str
    department: str
    organization: str
    title: str


class SimpleUser(BaseModel):
    user: str


class SimplePassword(BaseModel):
    password: str