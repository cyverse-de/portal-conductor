package api

import (
	"net/http"
	"strings"
	"testing"

	"github.com/cyverse-de/portal-conductor/terrain"
)

func TestGetJobLimits(t *testing.T) {
	tests := []struct {
		name         string
		limitsStatus int
		limitsBody   string
		wantStatus   int
		wantBody     string
	}{
		{
			"limits configured",
			http.StatusOK, `{"username": "john", "concurrent_jobs": 5}`,
			http.StatusOK, `{"username":"john","concurrent_jobs":5}`,
		},
		{
			"limit value null",
			http.StatusOK, `{"username": "john", "concurrent_jobs": null}`,
			http.StatusOK, `{"username":"john","concurrent_jobs":null}`,
		},
		{
			"no limits configured maps 404",
			http.StatusNotFound, `{"reason": "not found"}`,
			http.StatusNotFound, `{"detail":"No job limits configured for user 'john'"}`,
		},
		{
			"other terrain errors map to 500",
			http.StatusBadGateway, `boom`,
			http.StatusInternalServerError, `Failed to retrieve job limits`,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := newTerrainTestServer(t, func(mux *http.ServeMux) {
				mux.HandleFunc("/admin/settings/concurrent-job-limits/", func(w http.ResponseWriter, _ *http.Request) {
					w.WriteHeader(tt.limitsStatus)
					w.Write([]byte(tt.limitsBody)) //nolint:errcheck
				})
			})
			terrainClient, err := terrain.New(server.URL, "svc", "pw")
			if err != nil {
				t.Fatal(err)
			}
			handler := New(testConfig(), nil, nil, terrainClient, nil, nil, "", nil).Handler()

			rec := doRequest(t, handler, http.MethodGet, "/terrain/users/john/job-limits", "admin", "secret", "")
			if rec.Code != tt.wantStatus {
				t.Fatalf("got status %d, want %d (body: %s)", rec.Code, tt.wantStatus, rec.Body.String())
			}
			if !strings.Contains(rec.Body.String(), tt.wantBody) {
				t.Errorf("body %s does not contain %s", rec.Body.String(), tt.wantBody)
			}
		})
	}
}
