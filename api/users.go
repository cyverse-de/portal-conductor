package api

import (
	"log"
	"net/http"

	"github.com/cyverse-de/portal-conductor/kinds"
	"github.com/cyverse-de/portal-conductor/ldapclient"
)

var createUserRequiredFields = []string{
	"first_name", "last_name", "email", "username", "user_uid",
	"password", "department", "organization", "title",
}

// addUser creates a user in LDAP (with default groups) and the datastore.
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
func (a *API) deleteUser(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	if err := a.deleteUserFromDatastore(username); err != nil {
		return err
	}
	if err := a.deleteUserFromLDAP(username); err != nil {
		return err
	}

	writeJSON(w, http.StatusOK, kinds.UserResponse{User: username})
	return nil
}

func (a *API) deleteUserFromDatastore(username string) error {
	log.Printf("Deleting datastore files and account for user: %s", username)
	exists, err := a.ds.UserExists(username)
	if err != nil {
		return err
	}
	if !exists {
		log.Printf("User %s does not exist in datastore, skipping datastore deletion", username)
		return nil
	}
	if err := a.ds.DeleteHome(username); err != nil {
		return err
	}
	log.Printf("Deleted home directory for user: %s", username)
	if err := a.ds.DeleteUser(username); err != nil {
		return err
	}
	log.Printf("Deleted datastore user: %s", username)
	return nil
}

func (a *API) deleteUserFromLDAP(username string) error {
	log.Printf("Checking if user %s exists in LDAP", username)
	entry, err := a.ldap.GetUser(username)
	if err != nil {
		return err
	}
	if entry == nil {
		log.Printf("User %s does not exist in LDAP, skipping LDAP deletion", username)
		return nil
	}

	log.Printf("Deleting LDAP user: %s", username)
	groups, err := a.ldap.GetUserGroups(username)
	if err != nil {
		return err
	}
	for _, group := range groups {
		if len(group.Attrs["cn"]) == 0 {
			continue
		}
		groupName := group.Attrs["cn"][0]
		log.Printf("Removing user %s from group %s", username, groupName)
		if err := a.ldap.RemoveUserFromGroup(username, groupName); err != nil {
			return err
		}
		log.Printf("Removed user %s from group %s", username, groupName)
	}

	log.Printf("Deleting user %s from LDAP", username)
	if err := a.ldap.DeleteUser(username); err != nil {
		return err
	}
	log.Printf("Deleted LDAP user: %s", username)
	return nil
}
