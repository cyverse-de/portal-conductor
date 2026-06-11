package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"

	"github.com/cyverse-de/portal-conductor/config"
)

func testConfig() *config.Config {
	cfg := &config.Config{}
	cfg.Auth = config.Auth{Enabled: true, Username: "admin", Password: "secret", Realm: "Portal Conductor API"}
	return cfg
}

// newTerrainTestServer serves Terrain's token endpoint plus any routes added
// by configure.
func newTerrainTestServer(t *testing.T, configure func(mux *http.ServeMux)) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /token/keycloak", func(w http.ResponseWriter, r *http.Request) {
		if _, _, ok := r.BasicAuth(); !ok {
			http.Error(w, "missing basic auth", http.StatusUnauthorized)
			return
		}
		json.NewEncoder(w).Encode(map[string]string{"access_token": "tok"}) //nolint:errcheck
	})
	configure(mux)
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)
	return server
}

func doRequest(t *testing.T, handler http.Handler, method, path, user, pass, body string) *httptest.ResponseRecorder {
	t.Helper()
	var reqBody *strings.Reader
	if body == "" {
		reqBody = strings.NewReader("")
	} else {
		reqBody = strings.NewReader(body)
	}
	req := httptest.NewRequest(method, path, reqBody)
	if user != "" || pass != "" {
		req.SetBasicAuth(user, pass)
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec
}

func detailOf(t *testing.T, rec *httptest.ResponseRecorder) any {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("response is not JSON: %v (%s)", err, rec.Body.String())
	}
	return body["detail"]
}

func TestGreetingAndNotFound(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "").Handler()

	t.Run("greeting is unauthenticated", func(t *testing.T) {
		rec := doRequest(t, handler, http.MethodGet, "/", "", "", "")
		if rec.Code != http.StatusOK {
			t.Fatalf("got status %d, want 200", rec.Code)
		}
		if got := strings.TrimSpace(rec.Body.String()); got != `"Hello from portal-conductor."` {
			t.Errorf("got body %s", got)
		}
		if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
			t.Errorf("got content type %s", ct)
		}
	})

	t.Run("unknown path returns JSON 404", func(t *testing.T) {
		rec := doRequest(t, handler, http.MethodGet, "/nope", "", "", "")
		if rec.Code != http.StatusNotFound {
			t.Fatalf("got status %d, want 404", rec.Code)
		}
		if d := detailOf(t, rec); d != "Not Found" {
			t.Errorf("got detail %v", d)
		}
	})
}

func TestAuthentication(t *testing.T) {
	// The mailing-list route reaches its 503 check only after passing auth,
	// so it exercises the auth middleware without touching live clients.
	const path = "/mailinglists/somelist/members"

	tests := []struct {
		name        string
		authEnabled bool
		user, pass  string
		wantStatus  int
		wantDetail  string
	}{
		{"no credentials", true, "", "", http.StatusUnauthorized, "Not authenticated"},
		{"wrong password", true, "admin", "wrong", http.StatusUnauthorized, "Incorrect username or password"},
		{"wrong username", true, "other", "secret", http.StatusUnauthorized, "Incorrect username or password"},
		{"valid credentials", true, "admin", "secret", http.StatusServiceUnavailable, "Mailing list functionality is not enabled"},
		{"auth disabled", false, "", "", http.StatusServiceUnavailable, "Mailing list functionality is not enabled"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := testConfig()
			cfg.Auth.Enabled = tt.authEnabled
			handler := New(cfg, nil, nil, nil, nil, nil, "").Handler()

			rec := doRequest(t, handler, http.MethodGet, path, tt.user, tt.pass, "")
			if rec.Code != tt.wantStatus {
				t.Fatalf("got status %d, want %d", rec.Code, tt.wantStatus)
			}
			if d := detailOf(t, rec); d != tt.wantDetail {
				t.Errorf("got detail %v, want %s", d, tt.wantDetail)
			}
			if tt.wantStatus == http.StatusUnauthorized {
				if rec.Header().Get("WWW-Authenticate") == "" {
					t.Error("missing WWW-Authenticate header")
				}
			}
		})
	}
}

func TestAuthEnabledWithoutConfiguredCredentials(t *testing.T) {
	cfg := testConfig()
	cfg.Auth.Username = ""
	cfg.Auth.Password = ""
	handler := New(cfg, nil, nil, nil, nil, nil, "").Handler()

	rec := doRequest(t, handler, http.MethodGet, "/mailinglists/x/members", "any", "thing", "")
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("got status %d, want 401", rec.Code)
	}
}

func TestAsyncNotConfigured(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "").Handler()

	const analysisID = "6ded3c88-65d7-11f1-b562-32f7aa1defe5"
	paths := []struct {
		method, path string
	}{
		{http.MethodDelete, "/async/users/somebody"},
		{http.MethodGet, "/async/status/" + analysisID},
		{http.MethodGet, "/async/analyses"},
		{http.MethodGet, "/async/analyses/" + analysisID + "/details"},
	}
	for _, p := range paths {
		t.Run(p.method+" "+p.path, func(t *testing.T) {
			rec := doRequest(t, handler, p.method, p.path, "admin", "secret", "")
			if rec.Code != http.StatusServiceUnavailable {
				t.Fatalf("got status %d, want 503", rec.Code)
			}
			if d := detailOf(t, rec); d != "Terrain integration not configured." {
				t.Errorf("got detail %v", d)
			}
		})
	}
}

func TestAsyncRejectsInvalidAnalysisID(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "").Handler()

	for _, p := range []string{"/async/status/not-a-uuid", "/async/analyses/not-a-uuid/details"} {
		t.Run(p, func(t *testing.T) {
			rec := doRequest(t, handler, http.MethodGet, p, "admin", "secret", "")
			if rec.Code != http.StatusUnprocessableEntity {
				t.Fatalf("got status %d, want 422 (body: %s)", rec.Code, rec.Body.String())
			}
			if !strings.Contains(rec.Body.String(), "valid UUID") {
				t.Errorf("body %s does not mention UUID validation", rec.Body.String())
			}
		})
	}
}

func TestRequestValidation(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "").Handler()

	tests := []struct {
		name         string
		method, path string
		body         string
		wantMissing  []string
	}{
		{
			"datastore user missing password",
			http.MethodPost, "/datastore/users",
			`{"username": "u"}`,
			[]string{"password"},
		},
		{
			"create user missing several fields",
			http.MethodPost, "/users",
			`{"username": "u", "password": "p"}`,
			[]string{"first_name", "last_name", "email", "user_uid", "department", "organization", "title"},
		},
		{
			"malformed JSON",
			http.MethodPost, "/datastore/users",
			`{not json`,
			nil,
		},
		{
			"null required field rejected",
			http.MethodPost, "/users/someone/password",
			`{"password": null}`,
			nil,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rec := doRequest(t, handler, tt.method, tt.path, "admin", "secret", tt.body)
			if rec.Code != http.StatusUnprocessableEntity {
				t.Fatalf("got status %d, want 422 (body: %s)", rec.Code, rec.Body.String())
			}
			errorsList, ok := detailOf(t, rec).([]any)
			if !ok || len(errorsList) == 0 {
				t.Fatalf("expected a non-empty detail list, got %s", rec.Body.String())
			}
			var missingFields []string
			for _, rawErr := range errorsList {
				e := rawErr.(map[string]any)
				if e["type"] == "missing" {
					loc := e["loc"].([]any)
					missingFields = append(missingFields, loc[len(loc)-1].(string))
				}
			}
			for _, want := range tt.wantMissing {
				if !slices.Contains(missingFields, want) {
					t.Errorf("expected %q in missing fields %v", want, missingFields)
				}
			}
		})
	}
}

func TestTrailingSlashUserRoute(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "").Handler()

	// Both /users and /users/ must hit the create-user route; an incomplete
	// body proves it reached validation (422) rather than the 404 catch-all.
	for _, path := range []string{"/users", "/users/"} {
		rec := doRequest(t, handler, http.MethodPost, path, "admin", "secret", `{}`)
		if rec.Code != http.StatusUnprocessableEntity {
			t.Errorf("POST %s: got status %d, want 422", path, rec.Code)
		}
	}
}
