// Package kinds defines the request and response bodies for the
// portal-conductor API, matching the Pydantic models in kinds.py. Optional
// fields are pointers without omitempty so responses include explicit nulls,
// like the original service.
package kinds

import (
	"encoding/json"
	"errors"
)

// StringList unmarshals from either a single JSON string or a list of
// strings, matching Pydantic's `str | list[str]` fields.
type StringList []string

// UnmarshalJSON accepts both `"a@b.com"` and `["a@b.com", "c@d.com"]`.
func (s *StringList) UnmarshalJSON(data []byte) error {
	var single string
	if err := json.Unmarshal(data, &single); err == nil {
		*s = StringList{single}
		return nil
	}
	var many []string
	if err := json.Unmarshal(data, &many); err == nil {
		*s = StringList(many)
		return nil
	}
	return errors.New("expected a string or a list of strings")
}

// CreateUserRequest contains the fields required to create a new portal user.
type CreateUserRequest struct {
	FirstName    string `json:"first_name"`
	LastName     string `json:"last_name"`
	Email        string `json:"email"`
	Username     string `json:"username"`
	UserUID      string `json:"user_uid"`
	Password     string `json:"password"`
	Department   string `json:"department"`
	Organization string `json:"organization"`
	Title        string `json:"title"`
}

// PasswordChangeRequest holds a new password for a change or validate operation.
type PasswordChangeRequest struct {
	Password string `json:"password"`
}

// UserAttributeModifyRequest holds the new value for a single LDAP attribute.
type UserAttributeModifyRequest struct {
	Value string `json:"value"`
}

// UserResponse is returned from user create, delete, and password operations.
type UserResponse struct {
	User string `json:"user"`
}

// ValidateResponse reports whether credentials were valid.
type ValidateResponse struct {
	Valid bool `json:"valid"`
}

// AsyncDeleteUserResponse is returned when a user-deletion job is submitted.
type AsyncDeleteUserResponse struct {
	User       string `json:"user"`
	AnalysisID string `json:"analysis_id"`
	Status     string `json:"status"`
}

// AnalysisStatusResponse carries the current status of a DE analysis.
type AnalysisStatusResponse struct {
	AnalysisID string  `json:"analysis_id"`
	Status     string  `json:"status"`
	URLReady   *bool   `json:"url_ready"`
	URL        *string `json:"url"`
}

// AnalysisListItem represents a single analysis in a listing response.
type AnalysisListItem struct {
	AnalysisID string `json:"analysis_id"`
	Name       string `json:"name"`
	AppID      string `json:"app_id"`
	SystemID   string `json:"system_id"`
	Status     string `json:"status"`
}

// AnalysesListResponse is the envelope returned when listing analyses.
type AnalysesListResponse struct {
	Analyses []AnalysisListItem `json:"analyses"`
}

// DatastoreUserRequest holds credentials for creating or resetting a datastore user.
type DatastoreUserRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// DatastoreServiceRequest holds the iRODS path for a service-directory registration.
type DatastoreServiceRequest struct {
	IRODSPath string  `json:"irods_path"`
	IRODSUser *string `json:"irods_user"`
}

// MailingListMemberRequest holds an email address for mailing list subscribe/unsubscribe operations.
type MailingListMemberRequest struct {
	Email string `json:"email"`
}

// JobLimitsRequest carries the new concurrent-job limit value.
type JobLimitsRequest struct {
	Limit int `json:"limit"`
}

// JobLimitsResponse carries the current concurrent-job limit for a user.
type JobLimitsResponse struct {
	Username       string `json:"username"`
	ConcurrentJobs *int   `json:"concurrent_jobs"`
}

// GenericResponse is returned for operations that produce only a success/failure message.
type GenericResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

// EmailRequest carries the recipients, subject, and body for an outbound email.
type EmailRequest struct {
	To        StringList `json:"to"`
	Subject   string     `json:"subject"`
	TextBody  *string    `json:"text_body"`
	HTMLBody  *string    `json:"html_body"`
	FromEmail *string    `json:"from_email"`
	BCC       StringList `json:"bcc"`
}

// UserExistsResponse reports whether a username exists in a system.
type UserExistsResponse struct {
	Username string `json:"username"`
	Exists   bool   `json:"exists"`
}

// EmailExistsResponse reports whether an email address is subscribed to a mailing list.
type EmailExistsResponse struct {
	Email  string `json:"email"`
	Exists bool   `json:"exists"`
}

// MailingListMembersResponse carries the member email addresses of a mailing list.
type MailingListMembersResponse struct {
	Listname string   `json:"listname"`
	Members  []string `json:"members"`
}

// UserLDAPInfo carries the LDAP attributes of a posixAccount/inetOrgPerson entry.
type UserLDAPInfo struct {
	Username         string    `json:"username"`
	UIDNumber        *int      `json:"uid_number"`
	GIDNumber        *int      `json:"gid_number"`
	GivenName        *string   `json:"given_name"`
	Surname          *string   `json:"surname"`
	CommonName       *string   `json:"common_name"`
	Email            *string   `json:"email"`
	Department       *string   `json:"department"`
	Organization     *string   `json:"organization"`
	Title            *string   `json:"title"`
	HomeDirectory    *string   `json:"home_directory"`
	LoginShell       *string   `json:"login_shell"`
	ShadowLastChange *int      `json:"shadow_last_change"`
	ShadowMin        *int      `json:"shadow_min"`
	ShadowMax        *int      `json:"shadow_max"`
	ShadowWarning    *int      `json:"shadow_warning"`
	ShadowInactive   *int      `json:"shadow_inactive"`
	ObjectClasses    *[]string `json:"object_classes"`
}

// LDAPGroupInfo carries the LDAP attributes of a posixGroup entry.
type LDAPGroupInfo struct {
	Name           string    `json:"name"`
	GIDNumber      *int      `json:"gid_number"`
	DisplayName    *string   `json:"display_name"`
	Description    *string   `json:"description"`
	SambaGroupType *int      `json:"samba_group_type"`
	SambaSID       *string   `json:"samba_sid"`
	ObjectClasses  *[]string `json:"object_classes"`
}

// ValidationError mirrors one entry of FastAPI's 422 validation response.
type ValidationError struct {
	Type string   `json:"type" example:"missing"`
	Loc  []string `json:"loc" example:"body,username"`
	Msg  string   `json:"msg" example:"Field required"`
}

// ValidationErrorResponse represents the HTTP 422 validation error body.
type ValidationErrorResponse struct {
	Detail []ValidationError `json:"detail"`
}

// PortalCreateUserRequest holds the fields for creating a user across all
// systems (Portal DB, LDAP, DataStore, Terrain). Only Username, Email,
// FirstName, and LastName are required; all other fields have sensible
// defaults for SSO-provisioned users.
type PortalCreateUserRequest struct {
	Username          string `json:"username"`
	Email             string `json:"email"`
	FirstName         string `json:"first_name"`
	LastName          string `json:"last_name"`
	Password          string `json:"password"`
	Department        string `json:"department"`
	Institution       string `json:"institution"`
	OccupationID      int    `json:"occupation_id"`
	FundingAgencyID   int    `json:"funding_agency_id"`
	GenderID          int    `json:"gender_id"`
	EthnicityID       int    `json:"ethnicity_id"`
	RegionID          int    `json:"region_id"`
	ResearchAreaID    int    `json:"research_area_id"`
	AwareChannelID    int    `json:"aware_channel_id"`
	GridInstitutionID *int   `json:"grid_institution_id"`
	JobLimit          *int   `json:"job_limit"`
}

// PortalCreateUserDefaults returns a PortalCreateUserRequest pre-populated
// with "Not Provided" defaults for all optional fields.
func PortalCreateUserDefaults() PortalCreateUserRequest {
	return PortalCreateUserRequest{
		Department:      "Not Provided",
		Institution:     "Not Provided",
		OccupationID:    13,   // "Not Provided"
		FundingAgencyID: 21,   // "Not Provided"
		GenderID:        11,   // "Not Provided"
		EthnicityID:     8,    // "Not Provided"
		RegionID:        4394, // "Not Provided" (US)
		ResearchAreaID:  155,  // "Not Provided"
		AwareChannelID:  11,   // "Not Provided"
	}
}

// PortalCreateUserResponse is returned after successfully creating a user
// across all systems.
type PortalCreateUserResponse struct {
	User   string `json:"user"`
	UserID int64  `json:"user_id"`
}

// PortalUserExistsResponse reports whether a username exists or is restricted
// in the portal database.
type PortalUserExistsResponse struct {
	Username     string `json:"username"`
	Valid        bool   `json:"valid"`
	Exists       bool   `json:"exists"`
	IsRestricted bool   `json:"is_restricted"`
}

// PortalEmailExistsResponse reports whether an email address is already in
// use in the portal database.
type PortalEmailExistsResponse struct {
	Email  string `json:"email"`
	Exists bool   `json:"exists"`
}

// UsernameValidationResponse reports whether a username is valid and
// available.
type UsernameValidationResponse struct {
	Username string  `json:"username"`
	Valid    bool    `json:"valid"`
	Reason   *string `json:"reason"`
}
