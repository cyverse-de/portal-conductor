package api

import (
	"log"
	"net/http"

	"github.com/cyverse-de/portal-conductor/kinds"
	"github.com/cyverse-de/portal-conductor/ldapclient"
	"github.com/cyverse-de/portal-conductor/userdel"
)

var createUserRequiredFields = []string{
	"first_name", "last_name", "email", "username", "user_uid",
	"password", "department", "organization", "title",
}

// addUser creates a user in LDAP (with default groups) and the datastore.
// @Summary      Create user
// @Description  Create a complete user account in both LDAP (with default groups) and DataStore.
// @Accept       json
// @Produce      json
// @Param        request body kinds.CreateUserRequest true "User Details"
// @Success      200 {object} kinds.UserResponse
// @Failure      400 {object} kinds.GenericResponse "Bad request"
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      500 {object} kinds.GenericResponse "Internal server error"
// @Router       /users [post]
func (a *API) addUser(w http.ResponseWriter, r *http.Request) error {
	var user kinds.CreateUserRequest
	if err := decodeBody(r, &user, createUserRequiredFields...); err != nil {
		return err
	}

	if err := a.ldap.CreateUserWithGroups(user, a.cfg.LDAP.EveryoneGroup, a.cfg.LDAP.CommunityGroup); err != nil {
		return err
	}
	if err := a.ds.CreateUserWithPermissions(user.Username, user.Password, a.cfg.IRODS.IPCServicesUser, a.cfg.IRODS.AdminUser); err != nil {
		return err
	}

	log.Printf("User creation completed successfully for: %s", user.Username)
	writeJSON(w, http.StatusOK, kinds.UserResponse{User: user.Username})
	return nil
}

// validateCredentials checks a username/password pair against LDAP.
// @Summary      Validate credentials
// @Description  Validate user credentials against LDAP.
// @Accept       json
// @Produce      json
// @Param        username path string true "Username"
// @Param        request body kinds.PasswordChangeRequest true "Password details"
// @Success      200 {object} kinds.ValidateResponse
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Router       /users/{username}/validate [post]
func (a *API) validateCredentials(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")
	var req kinds.PasswordChangeRequest
	if err := decodeBody(r, &req, "password"); err != nil {
		return err
	}

	valid, err := a.ldap.ValidateCredentials(username, req.Password)
	if err != nil {
		return err
	}
	writeJSON(w, http.StatusOK, kinds.ValidateResponse{Valid: valid})
	return nil
}

// changePassword updates the user's password in LDAP and the datastore.
// @Summary      Change password
// @Description  Update the user's password in both LDAP and the datastore.
// @Accept       json
// @Produce      json
// @Param        username path string true "Username"
// @Param        request body kinds.PasswordChangeRequest true "New password details"
// @Success      200 {object} kinds.UserResponse
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Router       /users/{username}/password [post]
func (a *API) changePassword(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")
	var req kinds.PasswordChangeRequest
	if err := decodeBody(r, &req, "password"); err != nil {
		return err
	}

	if err := a.ldap.ChangePassword(username, req.Password); err != nil {
		return err
	}
	if err := a.ldap.SetShadowLastChange(ldapclient.DaysSinceEpoch(), username); err != nil {
		return err
	}
	if err := a.ds.ChangePassword(username, req.Password); err != nil {
		return err
	}
	writeJSON(w, http.StatusOK, kinds.UserResponse{User: username})
	return nil
}

// deleteUser synchronously removes the user from the datastore and LDAP.
// @Summary      Delete user synchronously
// @Description  Synchronously remove the user from the datastore and LDAP.
// @Produce      json
// @Param        username path string true "Username"
// @Success      200 {object} kinds.UserResponse
// @Router       /users/{username} [delete]
func (a *API) deleteUser(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	if err := userdel.FromDatastore(a.ds, username, false); err != nil {
		return err
	}
	if err := userdel.FromLDAP(a.ldap, username, false); err != nil {
		return err
	}

	writeJSON(w, http.StatusOK, kinds.UserResponse{User: username})
	return nil
}
