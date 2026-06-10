package api

import (
	"fmt"
	"net/http"

	"github.com/cyverse-de/portal-conductor/kinds"
)

// createDatastoreUser creates a datastore user (or resets the password of an
// existing one) and sets up home-directory permissions.
// @Summary      Create datastore user
// @Description  Create user in iRODS / DataStore only (or reset password if user already exists).
// @Accept       json
// @Produce      json
// @Param        request body kinds.DatastoreUserRequest true "Datastore User details"
// @Success      200 {object} kinds.UserResponse
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      500 {object} kinds.GenericResponse "Failed to create datastore user"
// @Security     BasicAuth
// @Router       /datastore/users [post]
func (a *API) createDatastoreUser(w http.ResponseWriter, r *http.Request) error {
	var req kinds.DatastoreUserRequest
	if err := decodeBody(r, &req, "username", "password"); err != nil {
		return err
	}

	if err := a.ds.CreateUserWithPermissions(req.Username, req.Password, a.cfg.IRODS.IPCServicesUser, a.cfg.IRODS.AdminUser); err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to create datastore user: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.UserResponse{User: req.Username})
	return nil
}

// checkUserExistsInDatastore reports whether a user exists in iRODS.
// @Summary      Check user datastore existence
// @Description  Check whether a username exists in the DataStore.
// @Produce      json
// @Param        username path string true "Username"
// @Success      200 {object} kinds.UserExistsResponse
// @Failure      500 {object} kinds.GenericResponse "Failed to check user existence in data store"
// @Security     BasicAuth
// @Router       /datastore/users/{username}/exists [get]
func (a *API) checkUserExistsInDatastore(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	exists, err := a.ds.UserExists(username)
	if err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to check user existence in data store: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.UserExistsResponse{Username: username, Exists: exists})
	return nil
}

// registerDatastoreService creates a service directory under the user's home
// with inherit and owner permissions (idempotent).
// @Summary      Register datastore service
// @Description  Register DataStore services with the iRODS path and username.
// @Accept       json
// @Produce      json
// @Param        username path string true "Username"
// @Param        request body kinds.DatastoreServiceRequest true "Datastore Service Details"
// @Success      200 {object} kinds.GenericResponse
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      500 {object} kinds.GenericResponse "Failed to register datastore service"
// @Security     BasicAuth
// @Router       /datastore/users/{username}/services [post]
func (a *API) registerDatastoreService(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	var req kinds.DatastoreServiceRequest
	if err := decodeBody(r, &req, "irods_path"); err != nil {
		return err
	}

	if err := a.ds.RegisterService(username, req.IRODSPath, req.IRODSUser); err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to register datastore service: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{
		Success: true,
		Message: fmt.Sprintf("User %s registered for datastore service %s", username, req.IRODSPath),
	})
	return nil
}
