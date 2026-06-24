package api

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"log"
	"net/http"
	"regexp"
	"strconv"

	"github.com/cyverse-de/portal-conductor/kinds"
	"github.com/cyverse-de/portal-conductor/portaldb"
)

// usernamePattern matches valid usernames: lowercase alphanumeric only.
var usernamePattern = regexp.MustCompile(`^[0-9a-z]+$`)

// usernameValid checks whether a username matches the required format.
func usernameValid(username string) bool {
	return usernamePattern.MatchString(username)
}

// generatePassword creates a cryptographically random password string.
func generatePassword() (string, error) {
	b := make([]byte, 36)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("generating random password: %w", err)
	}
	return base64.URLEncoding.EncodeToString(b), nil
}

// ensurePortalDB returns an httpError if the portal database is not configured.
func (a *API) ensurePortalDB() error {
	if a.portalDB == nil {
		return httpErrorf(http.StatusServiceUnavailable, "Portal database not configured")
	}
	return nil
}

// checkPortalUserExists reports whether a username exists or is restricted in
// the portal database.
//
//	@Summary      Check if username exists in portal DB
//	@Description  Checks both account_user and account_restrictedusername tables.
//	@Produce      json
//	@Param        username path string true "Username to check"
//	@Success      200 {object} kinds.PortalUserExistsResponse
//	@Failure      503 {object} map[string]string "Portal database not configured"
//	@Security     BasicAuth
//	@Router       /portal/users/{username}/exists [get]
func (a *API) checkPortalUserExists(w http.ResponseWriter, r *http.Request) error {
	if err := a.ensurePortalDB(); err != nil {
		return err
	}

	username := r.PathValue("username")
	ctx := r.Context()

	valid := usernameValid(username)

	userExists, err := portaldb.UserExistsByUsername(ctx, a.portalDB, username)
	if err != nil {
		return fmt.Errorf("checking user existence: %w", err)
	}

	isRestricted, err := portaldb.IsRestrictedUsername(ctx, a.portalDB, username)
	if err != nil {
		return fmt.Errorf("checking restricted username: %w", err)
	}

	writeJSON(w, http.StatusOK, kinds.PortalUserExistsResponse{
		Username:     username,
		Valid:        valid,
		Exists:       userExists || isRestricted,
		IsRestricted: isRestricted,
	})
	return nil
}

// checkPortalEmailExists reports whether an email address is already in use
// in the portal database.
//
//	@Summary      Check if email exists in portal DB
//	@Description  Case-insensitive check against account_emailaddress table.
//	@Produce      json
//	@Param        email path string true "Email address to check"
//	@Success      200 {object} kinds.PortalEmailExistsResponse
//	@Failure      503 {object} map[string]string "Portal database not configured"
//	@Security     BasicAuth
//	@Router       /portal/emails/{email}/exists [get]
func (a *API) checkPortalEmailExists(w http.ResponseWriter, r *http.Request) error {
	if err := a.ensurePortalDB(); err != nil {
		return err
	}

	email := r.PathValue("email")
	ctx := r.Context()

	exists, err := portaldb.EmailExists(ctx, a.portalDB, email)
	if err != nil {
		return fmt.Errorf("checking email existence: %w", err)
	}

	writeJSON(w, http.StatusOK, kinds.PortalEmailExistsResponse{
		Email:  email,
		Exists: exists,
	})
	return nil
}

// validatePortalUsername validates a username's format, restriction status,
// and availability.
//
//	@Summary      Validate username
//	@Description  Checks format (lowercase alphanumeric), restricted list, and availability.
//	@Produce      json
//	@Param        username path string true "Username to validate"
//	@Success      200 {object} kinds.UsernameValidationResponse
//	@Failure      503 {object} map[string]string "Portal database not configured"
//	@Security     BasicAuth
//	@Router       /portal/users/{username}/validate [post]
func (a *API) validatePortalUsername(w http.ResponseWriter, r *http.Request) error {
	if err := a.ensurePortalDB(); err != nil {
		return err
	}

	username := r.PathValue("username")
	ctx := r.Context()

	if !usernameValid(username) {
		reason := "Username format is invalid."
		writeJSON(w, http.StatusOK, kinds.UsernameValidationResponse{
			Username: username,
			Valid:    false,
			Reason:   &reason,
		})
		return nil
	}

	isRestricted, err := portaldb.IsRestrictedUsername(ctx, a.portalDB, username)
	if err != nil {
		return fmt.Errorf("checking restricted username: %w", err)
	}
	if isRestricted {
		reason := "Username is restricted."
		writeJSON(w, http.StatusOK, kinds.UsernameValidationResponse{
			Username: username,
			Valid:    false,
			Reason:   &reason,
		})
		return nil
	}

	exists, err := portaldb.UserExistsByUsername(ctx, a.portalDB, username)
	if err != nil {
		return fmt.Errorf("checking user existence: %w", err)
	}
	if exists {
		reason := "Username already taken."
		writeJSON(w, http.StatusOK, kinds.UsernameValidationResponse{
			Username: username,
			Valid:    false,
			Reason:   &reason,
		})
		return nil
	}

	writeJSON(w, http.StatusOK, kinds.UsernameValidationResponse{
		Username: username,
		Valid:    true,
		Reason:   nil,
	})
	return nil
}

// createPortalUser creates a user across all systems: Portal DB, LDAP,
// DataStore, and optionally Terrain (job limits).
//
//	@Summary      Create user in all systems
//	@Description  Full user registration: portal DB, LDAP, iRODS datastore, and Terrain job limits.
//	@Accept       json
//	@Produce      json
//	@Param        request body kinds.PortalCreateUserRequest true "User creation request"
//	@Success      201 {object} kinds.PortalCreateUserResponse
//	@Failure      400 {object} map[string]string "Username/email conflict"
//	@Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
//	@Failure      503 {object} map[string]string "Portal database not configured"
//	@Security     BasicAuth
//	@Router       /portal/users [post]
func (a *API) createPortalUser(w http.ResponseWriter, r *http.Request) error {
	if err := a.ensurePortalDB(); err != nil {
		return err
	}

	// Start with defaults, then overlay the request body on top.
	req := kinds.PortalCreateUserDefaults()
	if err := decodeBody(r, &req, "username", "email", "first_name", "last_name"); err != nil {
		return err
	}

	ctx := r.Context()

	// Validate username format.
	if !usernameValid(req.Username) {
		return httpErrorf(http.StatusBadRequest, "Username format is invalid.")
	}

	// Check restricted.
	isRestricted, err := portaldb.IsRestrictedUsername(ctx, a.portalDB, req.Username)
	if err != nil {
		return fmt.Errorf("checking restricted username: %w", err)
	}
	if isRestricted {
		return httpErrorf(http.StatusBadRequest, "Username is restricted.")
	}

	// Check username taken.
	userExists, err := portaldb.UserExistsByUsername(ctx, a.portalDB, req.Username)
	if err != nil {
		return fmt.Errorf("checking user existence: %w", err)
	}
	if userExists {
		return httpErrorf(http.StatusBadRequest, "Username already taken.")
	}

	// Check email taken.
	emailExists, err := portaldb.EmailExists(ctx, a.portalDB, req.Email)
	if err != nil {
		return fmt.Errorf("checking email existence: %w", err)
	}
	if emailExists {
		return httpErrorf(http.StatusBadRequest, "Email already in use.")
	}

	// Generate a random password if none was provided. SSO users don't need
	// one, but LDAP and iRODS require a password to be set.
	password := req.Password
	if password == "" {
		password, err = generatePassword()
		if err != nil {
			return err
		}
	}

	// Look up occupation name for the LDAP title field.
	occupationName, err := portaldb.GetOccupationName(ctx, a.portalDB, req.OccupationID)
	if err != nil {
		return fmt.Errorf("looking up occupation: %w", err)
	}
	if occupationName == "" {
		occupationName = "Unknown"
	}

	// 1. Create user and email address in the portal database atomically.
	// If either insert fails, the transaction rolls back and no cleanup is needed.
	log.Printf("Creating user in portal database: %s", req.Username)
	userData := portaldb.CreateUserData{
		Username:          req.Username,
		Email:             req.Email,
		Password:          "", // Portal DB password is empty; auth goes through Keycloak/LDAP.
		FirstName:         req.FirstName,
		LastName:          req.LastName,
		Institution:       req.Institution,
		Department:        req.Department,
		OccupationID:      req.OccupationID,
		FundingAgencyID:   req.FundingAgencyID,
		GenderID:          req.GenderID,
		EthnicityID:       req.EthnicityID,
		RegionID:          req.RegionID,
		ResearchAreaID:    req.ResearchAreaID,
		AwareChannelID:    req.AwareChannelID,
		GridInstitutionID: req.GridInstitutionID,
		HasVerifiedEmail:  true, // SSO users arrive from a trusted IdP.
	}
	// emailVerified=true: the IdP has already validated ownership of this address.
	userID, err := portaldb.CreateUserWithEmail(ctx, a.portalDB, userData, true)
	if err != nil {
		return fmt.Errorf("creating portal user: %w", err)
	}

	// compensate rolls back the portal DB records if a downstream step fails,
	// so that a retry with the same username/email can succeed.
	compensate := func(cause error, step string) error {
		log.Printf("Provisioning failed at %s for user %s: %v — removing portal DB records", step, req.Username, cause)
		if delErr := portaldb.DeleteUserByID(ctx, a.portalDB, userID); delErr != nil {
			log.Printf("WARNING: compensation failed for user %s (id=%d): %v — manual cleanup required", req.Username, userID, delErr)
		}
		return fmt.Errorf("%s: %w", step, cause)
	}

	// 2. Create user in LDAP with default groups.
	uidNumber := userID + int64(a.cfg.Security.UIDNumberOffset)
	log.Printf("Creating LDAP user: %s (uid: %d)", req.Username, uidNumber)

	ldapUser := kinds.CreateUserRequest{
		FirstName:    req.FirstName,
		LastName:     req.LastName,
		Email:        req.Email,
		Username:     req.Username,
		UserUID:      strconv.FormatInt(uidNumber, 10),
		Password:     password,
		Department:   req.Department,
		Organization: req.Institution,
		Title:        occupationName,
	}
	if err := a.ldap.CreateUserWithGroups(ldapUser, a.cfg.LDAP.EveryoneGroup, a.cfg.LDAP.CommunityGroup); err != nil {
		return compensate(err, "creating LDAP user")
	}

	// 3. Create user in DataStore.
	log.Printf("Creating DataStore user: %s", req.Username)
	if err := a.ds.CreateUserWithPermissions(req.Username, password, a.cfg.IRODS.IPCServicesUser, a.cfg.IRODS.AdminUser); err != nil {
		return compensate(err, "creating DataStore user")
	}

	// 4. Set job limits via Terrain (optional).
	if a.terrain != nil && req.JobLimit != nil {
		log.Printf("Setting job limits for user: %s", req.Username)
		if limitErr := a.terrain.SetConcurrentJobLimits(req.Username, *req.JobLimit); limitErr != nil {
			log.Printf("WARNING: Failed to set job limits for %s: %v", req.Username, limitErr)
			// Continue — job limits are not critical.
		}
	}

	log.Printf("User creation completed: %s (id=%d)", req.Username, userID)
	writeJSON(w, http.StatusCreated, kinds.PortalCreateUserResponse{
		User:   req.Username,
		UserID: userID,
	})
	return nil
}
