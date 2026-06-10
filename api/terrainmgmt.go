package api

import (
	"fmt"
	"net/http"

	"github.com/cyverse-de/portal-conductor/external"
	"github.com/cyverse-de/portal-conductor/kinds"
)

// getJobLimits returns the user's VICE concurrent job limit from Terrain.
// @Summary      Get job limits
// @Description  Get VICE job limits for a specific user.
// @Produce      json
// @Param        username path string true "Username"
// @Success      200 {object} kinds.JobLimitsResponse
// @Failure      404 {object} kinds.GenericResponse "No job limits configured"
// @Failure      500 {object} kinds.GenericResponse "Failed to retrieve job limits"
// @Router       /terrain/users/{username}/job-limits [get]
func (a *API) getJobLimits(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	result, err := a.terrain.GetConcurrentJobLimits(username)
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

// setJobLimits sets the user's VICE concurrent job limit via Terrain.
// @Summary      Set job limits
// @Description  Set VICE concurrent-job limit for a specific user.
// @Accept       json
// @Produce      json
// @Param        username path string true "Username"
// @Param        request body kinds.JobLimitsRequest true "Job Limit Details"
// @Success      200 {object} kinds.GenericResponse
// @Failure      422 {object} kinds.ValidationErrorResponse "Validation error"
// @Failure      500 {object} kinds.GenericResponse "Failed to set job limits"
// @Router       /terrain/users/{username}/job-limits [post]
func (a *API) setJobLimits(w http.ResponseWriter, r *http.Request) error {
	username := r.PathValue("username")

	var req kinds.JobLimitsRequest
	if err := decodeBody(r, &req, "limit"); err != nil {
		return err
	}

	if err := a.terrain.SetConcurrentJobLimits(username, req.Limit); err != nil {
		return httpErrorf(http.StatusInternalServerError, "Failed to set job limits: %v", err)
	}
	writeJSON(w, http.StatusOK, kinds.GenericResponse{
		Success: true,
		Message: fmt.Sprintf("Set job limit %d for user %s", req.Limit, username),
	})
	return nil
}
