package api

import (
	"net/http"

	"github.com/cyverse-de/portal-conductor/kinds"
)

// sendEmail sends an email via the configured SMTP server.
// @Summary      Send email
// @Description  Send an email using SMTP.
// @Accept       json
// @Produce      json
// @Param        request body kinds.EmailRequest true "Email details"
// @Success      200 {object} kinds.GenericResponse
// @Failure      400 {object} kinds.GenericResponse "Either text_body or html_body must be provided"
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      500 {object} kinds.GenericResponse "Failed to send email"
// @Router       /emails/send [post]
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

	if err := a.email.Send(req.To, req.Subject, req.TextBody, req.HTMLBody, req.FromEmail, req.BCC); err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to send email")
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{Success: true, Message: "Email sent successfully"})
	return nil
}
