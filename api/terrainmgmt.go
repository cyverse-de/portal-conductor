package api

import (
	"fmt"
	"net/http"

	"github.com/cyverse-de/portal-conductor/external"
	"github.com/cyverse-de/portal-conductor/kinds"
)

// getJobLimits returns the user's VICE concurrent job limit from Terrain.
func (a *API) getJobLimits(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	result, err := a.fetchJobLimits(username)
	if err != nil {
		// Terrain returns 404 when the user has no limits configured.
		if external.StatusCodeOf(err) == http.StatusNotFound {
			return httpErrorf(http.StatusNotFound, "No job limits configured for user '%s'", username)
		}
		return httpErrorf(http.StatusInternalServerError, "Failed to retrieve job limits: %v", err)
	}

	resp := kinds.JobLimitsResponse{Username: username}
	if jobs, ok := result["concurrent_jobs"].(float64); ok {
		n := int(jobs)
		resp.ConcurrentJobs = &n
	}
	writeJSON(w, http.StatusOK, resp)
	return nil
}

func (a *API) fetchJobLimits(username string) (map[string]any, error) {
	token, err := a.terrain.GetKeycloakToken()
	if err != nil {
		return nil, err
	}
	return a.terrain.GetConcurrentJobLimits(token, username)
}

// setJobLimits sets the user's VICE concurrent job limit via Terrain.
func (a *API) setJobLimits(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	var req kinds.JobLimitsRequest
	if err := decodeBody(r, &req, "limit"); err != nil {
		return err
	}

	token, err := a.terrain.GetKeycloakToken()
	if err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to set job limits: %v", err)
	}
	if err := a.terrain.SetConcurrentJobLimits(token, username, req.Limit); err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to set job limits: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{
		Success: true,
		Message: fmt.Sprintf("Set job limit %d for user %s", req.Limit, username),
	})
	return nil
}
