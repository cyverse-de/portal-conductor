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
