package api

import (
	"net/http"

	"github.com/cyverse-de/portal-conductor/kinds"
)

// sendEmail sends an email via the configured SMTP server.
func (a *API) sendEmail(w http.ResponseWriter, r *http.Request) error {
	var req kinds.EmailRequest
	if err := decodeBody(r, &req, "to", "subject"); err != nil {
		return err
	}

	hasText := req.TextBody != nil && *req.TextBody != ""
	hasHTML := req.HTMLBody != nil && *req.HTMLBody != ""
	if !hasText && !hasHTML {
		return httpErrorf(http.StatusBadRequest, "Either text_body or html_body must be provided")
	}

	if !a.email.Send(req.To, req.Subject, req.TextBody, req.HTMLBody, req.FromEmail, req.BCC) {
		return httpErrorf(http.StatusInternalServerError, "Failed to send email")
	}
	writeJSON(w, http.StatusOK, kinds.EmailResponse{Success: true, Message: "Email sent successfully"})
	return nil
}
