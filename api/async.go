package api

import (
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/cyverse-de/portal-conductor/formation"
	"github.com/cyverse-de/portal-conductor/kinds"
)

// ensureFormationConfigured returns the Formation client or a 503 when the
// integration is not configured.
func (a *API) ensureFormationConfigured() (*formation.Client, error) {
	if a.formation == nil {
		return nil, &httpError{status: http.StatusServiceUnavailable, detail: "Formation integration not configured."}
	}
	return a.formation, nil
}

// resolveFormationAppID returns the user-deletion app ID, retrying the
// by-name lookup if it was not resolved at startup.
func (a *API) resolveFormationAppID(client *formation.Client) (string, error) {
	a.appIDMu.Lock()
	defer a.appIDMu.Unlock()

	if a.formationAppID != "" {
		return a.formationAppID, nil
	}

	appName := a.cfg.Formation.UserDeletionAppName
	systemID := a.cfg.Formation.SystemID
	if appName != "" {
		log.Printf("[user-deletion] App ID not cached, retrying lookup for '%s' in system '%s'", appName, systemID)
		resolvedID, err := client.GetAppIDByName(systemID, appName)
		if err != nil {
			log.Printf("[user-deletion] App ID lookup failed: %v", err)
		} else if resolvedID != "" {
			log.Printf("[user-deletion] Resolved app ID: %s", resolvedID)
			a.formationAppID = resolvedID
			return resolvedID, nil
		}
	}

	return "", &httpError{
		status: http.StatusInternalServerError,
		detail: "Formation user deletion app ID not configured. " +
			"Check that either user_deletion_app_id is set or " +
			"user_deletion_app_name refers to a valid app.",
	}
}

// truthy mirrors Python truthiness for the JSON values that can appear in
// app parameter fields.
func truthy(v any) bool {
	switch val := v.(type) {
	case nil:
		return false
	case bool:
		return val
	case string:
		return val != ""
	case float64:
		return val != 0
	case []any:
		return len(val) > 0
	case map[string]any:
		return len(val) > 0
	default:
		return true
	}
}

// usernameParamID finds the ID of the app parameter that receives the
// username, by label, then by visible/required text parameter heuristics.
func (a *API) usernameParamID(client *formation.Client, systemID, appID string) (string, error) {
	appParams, err := client.GetAppParameters(systemID, appID)
	if err != nil {
		return "", err
	}

	groups, _ := appParams["groups"].([]any)
	for _, rawGroup := range groups {
		group, ok := rawGroup.(map[string]any)
		if !ok {
			continue
		}
		parameters, _ := group["parameters"].([]any)
		if len(parameters) == 0 {
			continue
		}

		params := make([]map[string]any, 0, len(parameters))
		for _, rawParam := range parameters {
			if param, ok := rawParam.(map[string]any); ok {
				params = append(params, param)
			}
		}

		// First, try to find by label.
		for _, param := range params {
			label, _ := param["label"].(string)
			label = strings.ToLower(label)
			if strings.Contains(label, "username") || strings.Contains(label, "user name") {
				if id, ok := param["id"].(string); ok {
					return id, nil
				}
			}
		}

		// Then look for a visible, required Text parameter with no default
		// value and no name (name="" means positional arg, not flag).
		for _, param := range params {
			if param["type"] == "Text" && truthy(param["isVisible"]) && truthy(param["required"]) &&
				!truthy(param["defaultValue"]) && !truthy(param["name"]) {
				if id, ok := param["id"].(string); ok {
					return id, nil
				}
			}
		}

		// Fallback: the last visible required parameter.
		for i := len(params) - 1; i >= 0; i-- {
			if truthy(params[i]["isVisible"]) && truthy(params[i]["required"]) {
				if id, ok := params[i]["id"].(string); ok {
					return id, nil
				}
			}
		}
	}

	return "", &httpError{
		status: http.StatusInternalServerError,
		detail: "Could not find username parameter in app configuration. Expected a parameter with label 'Username' or a visible required Text parameter.",
	}
}

// deleteUserAsync submits a Formation batch job that deletes the user.
// @Summary      Delete user asynchronously
// @Description  Submit a request to delete a user asynchronously from all systems including the database.
// @Produce      json
// @Param        username path string true "Username"
// @Success      200 {object} kinds.AsyncDeleteUserResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Formation not configured)"
// @Security     BasicAuth
// @Router       /async/users/{username} [delete]
func (a *API) deleteUserAsync(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	client, err := a.ensureFormationConfigured()
	if err != nil {
		return err
	}
	appID, err := a.resolveFormationAppID(client)
	if err != nil {
		return err
	}
	systemID := a.cfg.Formation.SystemID

	paramID, err := a.usernameParamID(client, systemID, appID)
	if err != nil {
		return err
	}

	submission := map[string]any{
		"name":   fmt.Sprintf("user-deletion-%s-%d", username, time.Now().Unix()),
		"config": map[string]any{paramID: username},
	}

	log.Printf("Submitting deletion analysis for user: %s", username)
	result, err := client.LaunchAnalysis(systemID, appID, submission)
	if err != nil {
		return err
	}

	analysisID, _ := result["analysis_id"].(string)
	if analysisID == "" {
		return fmt.Errorf("formation launch response is missing analysis_id; the deletion may not have been submitted: %v", result)
	}
	status, ok := result["status"].(string)
	if !ok {
		status = "Submitted"
	}
	log.Printf("Analysis submitted: %s, status: %s", analysisID, status)
	log.Printf("User deletion analysis will handle: mailing lists, LDAP, iRODS, and database operations")

	writeJSON(w, http.StatusOK, kinds.AsyncDeleteUserResponse{
		User:       username,
		AnalysisID: analysisID,
		Status:     status,
	})
	return nil
}

// getDeletionStatus reports the current status of an analysis.
// @Summary      Get deletion status
// @Description  Check the status of a user deletion analysis job.
// @Produce      json
// @Param        analysis_id path string true "Analysis ID"
// @Success      200 {object} kinds.AnalysisStatusResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Formation not configured)"
// @Security     BasicAuth
// @Router       /async/status/{analysis_id} [get]
func (a *API) getDeletionStatus(w http.ResponseWriter, r *http.Request) error {
	analysisID := r.PathValue("analysis_id")

	client, err := a.ensureFormationConfigured()
	if err != nil {
		return err
	}

	log.Printf("Checking status for analysis: %s", analysisID)
	result, err := client.GetAnalysisStatus(analysisID)
	if err != nil {
		return err
	}
	log.Printf("Analysis %s status: %v", analysisID, result["status"])

	resp := kinds.AnalysisStatusResponse{}
	resp.AnalysisID, _ = result["analysis_id"].(string)
	resp.Status, _ = result["status"].(string)
	if urlReady, ok := result["url_ready"].(bool); ok {
		resp.URLReady = &urlReady
	}
	if analysisURL, ok := result["url"].(string); ok {
		resp.URL = &analysisURL
	}
	writeJSON(w, http.StatusOK, resp)
	return nil
}

// listAnalyses lists Formation analyses filtered by status (default Running).
// @Summary      List analyses
// @Description  List deletion job analyses, optionally filtered by status (defaults to "Running").
// @Produce      json
// @Param        status query string false "Status filter (defaults to Running)"
// @Success      200 {object} kinds.AnalysesListResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Formation not configured)"
// @Security     BasicAuth
// @Router       /async/analyses [get]
func (a *API) listAnalyses(w http.ResponseWriter, r *http.Request) error {
	status := r.URL.Query().Get("status")
	if status == "" {
		status = "Running"
	}

	client, err := a.ensureFormationConfigured()
	if err != nil {
		return err
	}

	log.Printf("Listing analyses with status: %s", status)
	result, err := client.ListAnalyses(status)
	if err != nil {
		return err
	}

	rawAnalyses, _ := result["analyses"].([]any)
	analyses := make([]kinds.AnalysisListItem, 0, len(rawAnalyses))
	for _, rawAnalysis := range rawAnalyses {
		analysis, ok := rawAnalysis.(map[string]any)
		if !ok {
			continue
		}
		item := kinds.AnalysisListItem{}
		item.AnalysisID, _ = analysis["analysis_id"].(string)
		item.Name, _ = analysis["name"].(string)
		item.AppID, _ = analysis["app_id"].(string)
		item.SystemID, _ = analysis["system_id"].(string)
		item.Status, _ = analysis["status"].(string)
		analyses = append(analyses, item)
	}
	log.Printf("Found %d analyses", len(analyses))

	writeJSON(w, http.StatusOK, kinds.AnalysesListResponse{Analyses: analyses})
	return nil
}

// getAnalysisDetails passes through the full analysis document from Formation.
// @Summary      Get analysis details
// @Description  Get the details of a specific deletion job analysis.
// @Produce      json
// @Param        analysis_id path string true "Analysis ID"
// @Success      200 {object} interface{} "Returns raw analysis JSON representation"
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Formation not configured)"
// @Security     BasicAuth
// @Router       /async/analyses/{analysis_id}/details [get]
func (a *API) getAnalysisDetails(w http.ResponseWriter, r *http.Request) error {
	analysisID := r.PathValue("analysis_id")

	client, err := a.ensureFormationConfigured()
	if err != nil {
		return err
	}

	log.Printf("Fetching details for analysis: %s", analysisID)
	result, err := client.GetAnalysisDetails(analysisID)
	if err != nil {
		return err
	}
	log.Printf("Retrieved details for analysis: %v", result["name"])

	writeJSON(w, http.StatusOK, result)
	return nil
}
