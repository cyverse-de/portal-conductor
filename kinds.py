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
    name: str
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


class PortalUserExistsResponse(BaseModel):
    """Response for checking if a username exists in the portal database."""

    username: str
    valid: bool
    exists: bool
    is_restricted: bool = False


class PortalEmailExistsResponse(BaseModel):
    """Response for checking if an email exists in the portal database."""

    email: str
    exists: bool


class UsernameValidationResponse(BaseModel):
    """Response for username validation."""

    username: str
    valid: bool
    reason: str | None = None


class CreatePortalUserRequest(BaseModel):
    """Request to create a user in all systems (Portal DB, LDAP, DataStore, Terrain).

    Only username, email, first_name, and last_name are required. All other fields
    have sensible defaults suitable for SSO-provisioned users where detailed profile
    information is not available at account creation time.
    """

    username: str
    email: str
    first_name: str
    last_name: str
    password: str | None = None
    department: str = "Not Provided"
    institution: str = "Not Provided"
    occupation_id: int = 13        # "Not Provided"
    funding_agency_id: int = 21    # "Not Provided"
    gender_id: int = 11            # "Not Provided"
    ethnicity_id: int = 8          # "Not Provided"
    region_id: int = 4394          # "Not Provided" (US)
    research_area_id: int = 155    # "Not Provided"
    aware_channel_id: int = 11     # "Not Provided"
    grid_institution_id: int | None = None
    job_limit: int | None = None


class CreatePortalUserResponse(BaseModel):
    """Response after creating a user in all systems."""

    user: str
    user_id: int
