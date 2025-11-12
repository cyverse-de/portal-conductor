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


class PasswordChangeRequest(BaseModel):
    password: str


class UserAttributeModifyRequest(BaseModel):
    value: str


class UserResponse(BaseModel):
    user: str


class AsyncDeleteUserResponse(BaseModel):
    user: str
    analysis_id: str
    status: str


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str
    url_ready: bool | None = None
    url: str | None = None


class AnalysisListItem(BaseModel):
    analysis_id: str
    app_id: str
    system_id: str
    status: str


class AnalysesListResponse(BaseModel):
    analyses: list[AnalysisListItem]


class EmailListResponse(BaseModel):
    list: str
    email: str


class DatastoreUserRequest(BaseModel):
    username: str
    password: str


class DatastoreServiceRequest(BaseModel):
    irods_path: str
    irods_user: str | None = None


class MailingListMemberRequest(BaseModel):
    email: str


class JobLimitsRequest(BaseModel):
    limit: int


class JobLimitsResponse(BaseModel):
    username: str
    concurrent_jobs: int | None = None


class GenericResponse(BaseModel):
    success: bool
    message: str


class EmailRequest(BaseModel):
    to: str | list[str]
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    from_email: str | None = None
    bcc: str | list[str] | None = None


class EmailResponse(BaseModel):
    success: bool
    message: str


class UserExistsResponse(BaseModel):
    username: str
    exists: bool


class EmailExistsResponse(BaseModel):
    email: str
    exists: bool


class MailingListMembersResponse(BaseModel):
    listname: str
    members: list[str]


class UserLDAPInfo(BaseModel):
    username: str
    uid_number: int | None = None
    gid_number: int | None = None
    given_name: str | None = None
    surname: str | None = None
    common_name: str | None = None
    email: str | None = None
    department: str | None = None
    organization: str | None = None
    title: str | None = None
    home_directory: str | None = None
    login_shell: str | None = None
    shadow_last_change: int | None = None
    shadow_min: int | None = None
    shadow_max: int | None = None
    shadow_warning: int | None = None
    shadow_inactive: int | None = None
    object_classes: list[str] | None = None


class LDAPGroupInfo(BaseModel):
    name: str
    gid_number: int | None = None
    display_name: str | None = None
    description: str | None = None
    samba_group_type: int | None = None
    samba_sid: str | None = None
    object_classes: list[str] | None = None