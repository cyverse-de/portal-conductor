package terrain

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/cyverse-de/portal-conductor/external"
)

// fakeTerrain issues a distinct JWT per token request and lets the test
// decide how /apps responds based on which token the client presents.
type fakeTerrain struct {
	mu           sync.Mutex
	tokensIssued []string
	appsAuth     []string
	appsHandler  func(w http.ResponseWriter, tokenIndex int)
}

func (f *fakeTerrain) tokenIndexFor(authHeader string) int {
	for i, token := range f.tokensIssued {
		if authHeader == "Bearer "+token {
			return i
		}
	}
	return -1
}

func newFakeTerrain(t *testing.T, appsHandler func(w http.ResponseWriter, tokenIndex int)) (*fakeTerrain, *Client) {
	t.Helper()
	fake := &fakeTerrain{appsHandler: appsHandler}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /token/keycloak", func(w http.ResponseWriter, r *http.Request) {
		if _, _, ok := r.BasicAuth(); !ok {
			http.Error(w, "missing basic auth", http.StatusUnauthorized)
			return
		}
		fake.mu.Lock()
		defer fake.mu.Unlock()
		claims, _ := json.Marshal(map[string]any{"exp": time.Now().Add(time.Hour).Unix()})
		token := fmt.Sprintf("h%d.%s.s", len(fake.tokensIssued), base64.RawURLEncoding.EncodeToString(claims))
		fake.tokensIssued = append(fake.tokensIssued, token)
		json.NewEncoder(w).Encode(map[string]any{"access_token": token}) //nolint:errcheck
	})
	mux.HandleFunc("GET /apps", func(w http.ResponseWriter, r *http.Request) {
		fake.mu.Lock()
		defer fake.mu.Unlock()
		auth := r.Header.Get("Authorization")
		fake.appsAuth = append(fake.appsAuth, auth)
		fake.appsHandler(w, fake.tokenIndexFor(auth))
	})

	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	client, err := New(server.URL, "svc", "pw")
	if err != nil {
		t.Fatal(err)
	}
	return fake, client
}

// A 403 from a stale token must trigger exactly one retry with a freshly
// minted token, so Keycloak role changes take effect without a restart.
func TestRetriesOnceWithFreshTokenOnForbidden(t *testing.T) {
	fake, client := newFakeTerrain(t, func(w http.ResponseWriter, tokenIndex int) {
		if tokenIndex == 0 {
			http.Error(w, `{"detail":"token predates role change"}`, http.StatusForbidden)
			return
		}
		json.NewEncoder(w).Encode(map[string]any{ //nolint:errcheck
			"apps": []any{map[string]any{"id": "app-1", "name": "portal-delete-user", "system_id": "de"}},
		})
	})

	id, err := client.GetAppIDByName("de", "portal-delete-user")
	if err != nil {
		t.Fatalf("expected retry to succeed, got %v", err)
	}
	if id != "app-1" {
		t.Errorf("got app ID %q, want app-1", id)
	}
	if len(fake.tokensIssued) != 2 {
		t.Errorf("expected 2 token requests, got %d", len(fake.tokensIssued))
	}
	if len(fake.appsAuth) != 2 || fake.appsAuth[0] == fake.appsAuth[1] {
		t.Errorf("expected the retry to use a different token: %v", fake.appsAuth)
	}
}

// When the fresh token is still rejected, the 403 surfaces after a single
// retry instead of looping.
func TestForbiddenAfterRetrySurfacesError(t *testing.T) {
	fake, client := newFakeTerrain(t, func(w http.ResponseWriter, _ int) {
		http.Error(w, `{"detail":"nope"}`, http.StatusForbidden)
	})

	_, err := client.GetAppIDByName("de", "portal-delete-user")
	var statusErr *external.StatusError
	if !errors.As(err, &statusErr) || statusErr.StatusCode != http.StatusForbidden {
		t.Fatalf("expected 403 StatusError, got %v", err)
	}
	if len(fake.appsAuth) != 2 {
		t.Errorf("expected exactly 2 attempts, got %d", len(fake.appsAuth))
	}
}

// Non-auth errors must not trigger a token refresh or retry.
func TestNoRetryOnServerError(t *testing.T) {
	fake, client := newFakeTerrain(t, func(w http.ResponseWriter, _ int) {
		http.Error(w, "boom", http.StatusInternalServerError)
	})

	_, err := client.GetAppIDByName("de", "portal-delete-user")
	var statusErr *external.StatusError
	if !errors.As(err, &statusErr) || statusErr.StatusCode != http.StatusInternalServerError {
		t.Fatalf("expected 500 StatusError, got %v", err)
	}
	if len(fake.appsAuth) != 1 {
		t.Errorf("expected exactly 1 attempt, got %d", len(fake.appsAuth))
	}
	if len(fake.tokensIssued) != 1 {
		t.Errorf("expected exactly 1 token request, got %d", len(fake.tokensIssued))
	}
}

func TestGetAppIDByName(t *testing.T) {
	app := func(id, name, systemID string) map[string]any {
		return map[string]any{"id": id, "name": name, "system_id": systemID}
	}

	tests := []struct {
		name   string
		apps   []any
		search string
		wantID string
	}{
		{
			"exact match preferred over case-insensitive",
			[]any{app("a1", "Portal-Delete-User", "de"), app("a2", "portal-delete-user", "de")},
			"portal-delete-user", "a2",
		},
		{
			"case-insensitive fallback",
			[]any{app("a1", "Portal-Delete-User", "de")},
			"portal-delete-user", "a1",
		},
		{
			"other systems filtered out",
			[]any{app("a1", "portal-delete-user", "agave"), app("a2", "portal-delete-user", "de")},
			"portal-delete-user", "a2",
		},
		{
			"not found returns empty",
			[]any{app("a1", "something-else", "de")},
			"portal-delete-user", "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, client := newFakeTerrain(t, func(w http.ResponseWriter, _ int) {
				json.NewEncoder(w).Encode(map[string]any{"apps": tt.apps, "total": len(tt.apps)}) //nolint:errcheck
			})

			id, err := client.GetAppIDByName("de", tt.search)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if id != tt.wantID {
				t.Errorf("got app ID %q, want %q", id, tt.wantID)
			}
		})
	}
}

// newAnalysesServer serves the token endpoint plus /analyses, recording the
// filter query values and request bodies it receives.
func newAnalysesServer(t *testing.T, response map[string]any) (*Client, *[]string, *[]map[string]any) {
	t.Helper()
	var filters []string
	var bodies []map[string]any

	mux := http.NewServeMux()
	mux.HandleFunc("GET /token/keycloak", func(w http.ResponseWriter, _ *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"access_token": "tok"}) //nolint:errcheck
	})
	mux.HandleFunc("/analyses", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Errorf("decoding submission body: %v", err)
			}
			bodies = append(bodies, body)
		} else {
			filters = append(filters, r.URL.Query().Get("filter"))
		}
		json.NewEncoder(w).Encode(response) //nolint:errcheck
	})
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	client, err := New(server.URL, "svc", "pw")
	if err != nil {
		t.Fatal(err)
	}
	return client, &filters, &bodies
}

func decodeFilter(t *testing.T, filter string) []map[string]string {
	t.Helper()
	if filter == "" {
		return nil
	}
	var decoded []map[string]string
	if err := json.Unmarshal([]byte(filter), &decoded); err != nil {
		t.Fatalf("filter %q is not JSON: %v", filter, err)
	}
	return decoded
}

func TestListAnalyses(t *testing.T) {
	tests := []struct {
		name       string
		status     string
		wantFilter []map[string]string
	}{
		{"status filter", "Running", []map[string]string{{"field": "status", "value": "Running"}}},
		{"empty status lists all", "", nil},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			client, filters, _ := newAnalysesServer(t, map[string]any{"analyses": []any{}})

			if _, err := client.ListAnalyses(tt.status); err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if len(*filters) != 1 {
				t.Fatalf("expected 1 listing request, got %d", len(*filters))
			}
			got := decodeFilter(t, (*filters)[0])
			if fmt.Sprint(got) != fmt.Sprint(tt.wantFilter) {
				t.Errorf("got filter %v, want %v", got, tt.wantFilter)
			}
		})
	}
}

func TestGetAnalysisByID(t *testing.T) {
	t.Run("returns the matching entry", func(t *testing.T) {
		client, filters, _ := newAnalysesServer(t, map[string]any{
			"analyses": []any{map[string]any{"id": "an-1", "status": "Running"}},
		})

		analysis, err := client.GetAnalysisByID("an-1")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if analysis["id"] != "an-1" {
			t.Errorf("got analysis %v", analysis)
		}
		want := []map[string]string{{"field": "id", "value": "an-1"}}
		if got := decodeFilter(t, (*filters)[0]); fmt.Sprint(got) != fmt.Sprint(want) {
			t.Errorf("got filter %v, want %v", got, want)
		}
	})

	t.Run("empty listing maps to 404", func(t *testing.T) {
		client, _, _ := newAnalysesServer(t, map[string]any{"analyses": []any{}})

		_, err := client.GetAnalysisByID("missing")
		var statusErr *external.StatusError
		if !errors.As(err, &statusErr) || statusErr.StatusCode != http.StatusNotFound {
			t.Fatalf("expected 404 StatusError, got %v", err)
		}
	})
}

func TestLaunchAnalysis(t *testing.T) {
	client, _, bodies := newAnalysesServer(t, map[string]any{"id": "an-1", "status": "Submitted"})

	submission := map[string]any{
		"name":       "user-deletion-u-1",
		"config":     map[string]any{"step_param": "u"},
		"debug":      false,
		"notify":     true,
		"output_dir": "/zone/home/svc/analyses/user-deletion-u-1",
	}
	result, err := client.LaunchAnalysis("de", "app-123", submission)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result["id"] != "an-1" {
		t.Errorf("got result %v", result)
	}

	if len(*bodies) != 1 {
		t.Fatalf("expected 1 submission, got %d", len(*bodies))
	}
	body := (*bodies)[0]
	want := map[string]any{
		"name":       "user-deletion-u-1",
		"debug":      false,
		"notify":     true,
		"output_dir": "/zone/home/svc/analyses/user-deletion-u-1",
		"system_id":  "de",
		"app_id":     "app-123",
	}
	for field, wantValue := range want {
		if body[field] != wantValue {
			t.Errorf("body[%q] = %v, want %v", field, body[field], wantValue)
		}
	}
	config, _ := body["config"].(map[string]any)
	if config["step_param"] != "u" {
		t.Errorf("got config %v", body["config"])
	}
}
