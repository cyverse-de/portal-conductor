package api

import (
	"fmt"
	"net/http"
	"slices"
	"strings"

	"github.com/cyverse-de/portal-conductor/kinds"
	"github.com/cyverse-de/portal-conductor/ldapclient"
)

// createLDAPUser creates a user in LDAP and adds them to the default groups
// (idempotent).
func (a *API) createLDAPUser(w http.ResponseWriter, r *http.Request) error {
	var user kinds.CreateUserRequest
	if err := decodeBody(r, &user, createUserRequiredFields...); err != nil {
		return err
	}

	if err := a.ldap.CreateUserWithGroups(user, a.cfg.LDAP.EveryoneGroup, a.cfg.LDAP.CommunityGroup); err != nil {
		return err
	}
	writeJSON(w, http.StatusOK, kinds.UserResponse{User: user.Username})
	return nil
}

// addUserToLDAPGroup adds a user to an LDAP group if they aren't a member.
func (a *API) addUserToLDAPGroup(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")
	groupname := r.PathValue("groupname")

	inGroup, err := a.ldap.UserInGroup(username, groupname)
	if err != nil {
		return err
	}

	message := fmt.Sprintf("User %s already in group %s", username, groupname)
	if !inGroup {
		if err := a.ldap.AddUserToGroup(username, groupname); err != nil {
			return err
		}
		message = fmt.Sprintf("User %s added to group %s", username, groupname)
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{Success: true, Message: message})
	return nil
}

// getUserLDAPGroups returns the names of the groups a user belongs to.
func (a *API) getUserLDAPGroups(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	groups, err := a.ldap.GetUserGroups(username)
	if err != nil {
		return err
	}
	names := make([]string, 0, len(groups))
	for _, group := range groups {
		if len(group.Attrs["cn"]) > 0 {
			names = append(names, group.Attrs["cn"][0])
		}
	}
	writeJSON(w, http.StatusOK, names)
	return nil
}

// removeUserFromLDAPGroup removes a user from an LDAP group.
func (a *API) removeUserFromLDAPGroup(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")
	groupname := r.PathValue("groupname")

	if err := a.ldap.RemoveUserFromGroup(username, groupname); err != nil {
		return err
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{
		Success: true,
		Message: fmt.Sprintf("User %s removed from group %s", username, groupname),
	})
	return nil
}

// getUserLDAPInfo returns the full LDAP profile for a user.
func (a *API) getUserLDAPInfo(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	entry, err := a.ldap.GetUser(username)
	if err != nil {
		return err
	}
	if entry == nil {
		return httpErrorf(http.StatusNotFound, "User '%s' not found in LDAP directory", username)
	}
	writeJSON(w, http.StatusOK, ldapclient.ParseUserAttributes(username, entry))
	return nil
}

// getLDAPGroups returns all posixGroups, sorted by name.
func (a *API) getLDAPGroups(w http.ResponseWriter, r *http.Request) error {
	groups, err := a.ldap.GetGroups()
	if err != nil {
		return err
	}

	infos := make([]kinds.LDAPGroupInfo, 0, len(groups))
	for _, group := range groups {
		info := ldapclient.ParseGroupAttributes(group)
		if info.Name != "" {
			infos = append(infos, info)
		}
	}
	slices.SortFunc(infos, func(a, b kinds.LDAPGroupInfo) int {
		return strings.Compare(strings.ToLower(a.Name), strings.ToLower(b.Name))
	})
	writeJSON(w, http.StatusOK, infos)
	return nil
}

// checkUserExistsInLDAP reports whether a user exists in LDAP.
func (a *API) checkUserExistsInLDAP(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	entry, err := a.ldap.GetUser(username)
	if err != nil {
		return err
	}
	writeJSON(w, http.StatusOK, kinds.UserExistsResponse{Username: username, Exists: entry != nil})
	return nil
}

// modifyUserLDAPAttribute replaces a single LDAP attribute on a user.
func (a *API) modifyUserLDAPAttribute(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")
	attribute := r.PathValue("attribute")

	var req kinds.UserAttributeModifyRequest
	if err := decodeBody(r, &req, "value"); err != nil {
		return err
	}

	entry, err := a.ldap.GetUser(username)
	if err != nil {
		return err
	}
	if entry == nil {
		return httpErrorf(http.StatusNotFound, "User '%s' not found in LDAP directory", username)
	}

	if req.Value == "" {
		return httpErrorf(http.StatusBadRequest, "Value cannot be empty for attribute '%s'", attribute)
	}
	if err := a.ldap.ModifyUserAttribute(username, attribute, req.Value); err != nil {
		return err
	}

	writeJSON(w, http.StatusOK, kinds.GenericResponse{
		Success: true,
		Message: fmt.Sprintf("Updated attribute '%s' for user '%s'", attribute, username),
	})
	return nil
}
