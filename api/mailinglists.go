package api

import (
	"fmt"
	"net/http"

	"github.com/cyverse-de/portal-conductor/kinds"
)

// requireMailman returns a 503 when the Mailman integration is disabled.
func (a *API) requireMailman() error {
	if !a.cfg.Mailman.Enabled {
		return &httpError{status: http.StatusServiceUnavailable, detail: "Mailing list functionality is not enabled"}
	}
	return nil
}

// listMailingListMembers returns all member emails of a mailing list.
// @Summary      List mailing list members
// @Description  Retrieve a list of members in a mailing list.
// @Produce      json
// @Param        listname path string true "Mailing list name"
// @Success      200 {object} kinds.MailingListMembersResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Mailman integration disabled)"
// @Router       /mailinglists/{listname}/members [get]
func (a *API) listMailingListMembers(w http.ResponseWriter, r *http.Request) error {
	if err := a.requireMailman(); err != nil {
		return err
	}
	listname := r.PathValue("listname")

	members, err := a.mailman.ListMembers(listname)
	if err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to retrieve mailing list members: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.MailingListMembersResponse{Listname: listname, Members: members})
	return nil
}

// addToMailingList subscribes an email address to a mailing list.
// @Summary      Add to mailing list
// @Description  Subscribe an email address to a mailing list.
// @Accept       json
// @Produce      json
// @Param        listname path string true "Mailing list name"
// @Param        request body kinds.MailingListMemberRequest true "Mailing list member details"
// @Success      200 {object} kinds.GenericResponse
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Mailman integration disabled)"
// @Router       /mailinglists/{listname}/members [post]
func (a *API) addToMailingList(w http.ResponseWriter, r *http.Request) error {
	if err := a.requireMailman(); err != nil {
		return err
	}
	listname := r.PathValue("listname")

	var req kinds.MailingListMemberRequest
	if err := decodeBody(r, &req, "email"); err != nil {
		return err
	}

	if err := a.mailman.AddMember(listname, req.Email); err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to add user to mailing list: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{
		Success: true,
		Message: fmt.Sprintf("Added %s to mailing list %s", req.Email, listname),
	})
	return nil
}

// removeFromMailingList unsubscribes an email address from a mailing list.
// @Summary      Remove from mailing list
// @Description  Unsubscribe an email address from a mailing list.
// @Produce      json
// @Param        listname path string true "Mailing list name"
// @Param        email path string true "Email address to unsubscribe"
// @Success      200 {object} kinds.GenericResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Mailman integration disabled)"
// @Router       /mailinglists/{listname}/members/{email} [delete]
func (a *API) removeFromMailingList(w http.ResponseWriter, r *http.Request) error {
	if err := a.requireMailman(); err != nil {
		return err
	}
	listname := r.PathValue("listname")
	email := r.PathValue("email")

	if err := a.mailman.RemoveMember(listname, email); err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to remove user from mailing list: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{
		Success: true,
		Message: fmt.Sprintf("Removed %s from mailing list %s", email, listname),
	})
	return nil
}

// checkEmailInMailingList reports whether an email address is subscribed.
// @Summary      Check email in mailing list
// @Description  Check whether an email address is subscribed to a mailing list.
// @Produce      json
// @Param        listname path string true "Mailing list name"
// @Param        email path string true "Email address"
// @Success      200 {object} kinds.EmailExistsResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Mailman integration disabled)"
// @Router       /mailinglists/{listname}/members/{email}/exists [get]
func (a *API) checkEmailInMailingList(w http.ResponseWriter, r *http.Request) error {
	if err := a.requireMailman(); err != nil {
		return err
	}
	listname := r.PathValue("listname")
	email := r.PathValue("email")

	exists, err := a.mailman.MemberExists(listname, email)
	if err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to check email existence in mailing list: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.EmailExistsResponse{Email: email, Exists: exists})
	return nil
}
