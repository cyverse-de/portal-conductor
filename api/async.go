package api

import (
	"fmt"
	"log"
	"net/http"
	"path"
	"regexp"
	"strings"
	"time"

	"github.com/cyverse-de/portal-conductor/kinds"
	"github.com/cyverse-de/portal-conductor/terrain"
)

var uuidRE = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

// analysisIDParam returns the analysis_id path value, rejecting non-UUIDs
// with a 422 before they reach the apps service, which 500s on them.
func analysisIDParam(r *http.Request) (string, error) {
	id := r.PathValue("analysis_id")
	if !uuidRE.MatchString(id) {
		return "", &httpError{status: http.StatusUnprocessableEntity, detail: []kinds.ValidationError{
			{Type: "uuid_parsing", Loc: []string{"path", "analysis_id"}, Msg: "Input should be a valid UUID"},
		}}
	}
	return id, nil
}

// ensureAsyncConfigured returns the Terrain client or a 503 when the async
// user-deletion integration is not configured.
func (a *API) ensureAsyncConfigured() (*terrain.Client, error) {
	if a.terrain == nil || !a.cfg.TerrainAsyncConfigured() {
		return nil, &httpError{status: http.StatusServiceUnavailable, detail: "Terrain integration not configured."}
	}
	return a.terrain, nil
}

// resolveDeletionAppID returns the user-deletion app ID, retrying the
// by-name lookup if it was not resolved at startup.
func (a *API) resolveDeletionAppID(client *terrain.Client) (string, error) {
	a.appIDMu.Lock()
	defer a.appIDMu.Unlock()

	if a.deletionAppID != "" {
		return a.deletionAppID, nil
	}

	appName := a.cfg.Terrain.UserDeletionAppName
	systemID := a.cfg.Terrain.SystemID
	if appName != "" {
		log.Printf("[user-deletion] App ID not cached, looking up '%s' in system '%s'", appName, systemID)
		resolvedID, err := client.GetAppIDByName(systemID, appName)
		if err != nil {
			// Propagate so this surfaces as a gateway error (502/503), not as
			// a misconfiguration; Terrain is likely unreachable or degraded.
			log.Printf("[user-deletion] App ID lookup failed; terrain may be unreachable or degraded: %v", err)
			return "", err
		}
		if resolvedID != "" {
			log.Printf("[user-deletion] Resolved app ID: %s", resolvedID)
			a.deletionAppID = resolvedID
			return resolvedID, nil
		}
		log.Printf("[user-deletion] No app named '%s' found in system '%s'", appName, systemID)
	}

	return "", &httpError{
		status: http.StatusInternalServerError,
		detail: "Terrain user deletion app ID not configured. " +
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
func (a *API) usernameParamID(client *terrain.Client, systemID, appID string) (string, error) {
	jobView, err := client.GetAppJobView(systemID, appID)
	if err != nil {
		return "", err
	}

	groups, _ := jobView["groups"].([]any)
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

// deleteUserAsync submits a Terrain batch job that deletes the user.
// @Summary      Delete user asynchronously
// @Description  Submit a request to delete a user asynchronously from all systems including the database.
// @Produce      json
// @Param        username path string true "Username"
// @Success      200 {object} kinds.AsyncDeleteUserResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Terrain not configured)"
// @Security     BasicAuth
// @Router       /async/users/{username} [delete]
func (a *API) deleteUserAsync(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	client, err := a.ensureAsyncConfigured()
	if err != nil {
		return err
	}
	appID, err := a.resolveDeletionAppID(client)
	if err != nil {
		return err
	}
	systemID := a.cfg.Terrain.SystemID

	paramID, err := a.usernameParamID(client, systemID, appID)
	if err != nil {
		return err
	}

	// Terrain requires every submission field, including output_dir, which
	// goes under the service account's home collection.
	name := fmt.Sprintf("user-deletion-%s-%d", username, time.Now().Unix())
	submission := map[string]any{
		"name":       name,
		"config":     map[string]any{paramID: username},
		"debug":      false,
		"notify":     true,
		"output_dir": path.Join(a.ds.UserHome(a.cfg.Terrain.User), "analyses", name),
	}

	log.Printf("Submitting deletion analysis for user: %s", username)
	result, err := client.LaunchAnalysis(systemID, appID, submission)
	if err != nil {
		return err
	}

	analysisID, _ := result["id"].(string)
	if analysisID == "" {
		return fmt.Errorf("terrain launch response is missing the analysis id; the deletion may not have been submitted: %v", result)
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
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Terrain not configured)"
// @Security     BasicAuth
// @Router       /async/status/{analysis_id} [get]
func (a *API) getDeletionStatus(w http.ResponseWriter, r *http.Request) error {
	analysisID, err := analysisIDParam(r)
	if err != nil {
		return err
	}

	client, err := a.ensureAsyncConfigured()
	if err != nil {
		return err
	}

	log.Printf("Checking status for analysis: %s", analysisID)
	result, err := client.GetAnalysisByID(analysisID)
	if err != nil {
		return err
	}
	log.Printf("Analysis %s status: %v", analysisID, result["status"])

	status, ok := result["status"].(string)
	if !ok {
		status = "Unknown"
	}
	// The deletion app is a batch job, so it never gets a VICE URL.
	urlReady := false
	writeJSON(w, http.StatusOK, kinds.AnalysisStatusResponse{
		AnalysisID: analysisID,
		Status:     status,
		URLReady:   &urlReady,
	})
	return nil
}

// listAnalyses lists the deletion-account analyses filtered by status
// (default Running).
// @Summary      List analyses
// @Description  List deletion job analyses, optionally filtered by status (defaults to "Running").
// @Produce      json
// @Param        status query string false "Status filter (defaults to Running)"
// @Success      200 {object} kinds.AnalysesListResponse
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Terrain not configured)"
// @Security     BasicAuth
// @Router       /async/analyses [get]
func (a *API) listAnalyses(w http.ResponseWriter, r *http.Request) error {
	status := r.URL.Query().Get("status")
	if status == "" {
		status = "Running"
	}

	client, err := a.ensureAsyncConfigured()
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
		item.AnalysisID, _ = analysis["id"].(string)
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

// getAnalysisDetails passes through the analysis listing document from
// Terrain.
// @Summary      Get analysis details
// @Description  Get the details of a specific deletion job analysis.
// @Produce      json
// @Param        analysis_id path string true "Analysis ID"
// @Success      200 {object} interface{} "Returns raw analysis JSON representation"
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      503 {object} kinds.GenericResponse "Service Unavailable (Terrain not configured)"
// @Security     BasicAuth
// @Router       /async/analyses/{analysis_id}/details [get]
func (a *API) getAnalysisDetails(w http.ResponseWriter, r *http.Request) error {
	analysisID, err := analysisIDParam(r)
	if err != nil {
		return err
	}

	client, err := a.ensureAsyncConfigured()
	if err != nil {
		return err
	}

	log.Printf("Fetching details for analysis: %s", analysisID)
	result, err := client.GetAnalysisByID(analysisID)
	if err != nil {
		return err
	}
	log.Printf("Retrieved details for analysis: %v", result["name"])

	writeJSON(w, http.StatusOK, result)
	return nil
}
