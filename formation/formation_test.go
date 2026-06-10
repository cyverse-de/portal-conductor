package formation

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

// fakeFormation issues a distinct JWT per token request and lets the test
// decide how /apps responds based on which token the client presents.
type fakeFormation struct {
	mu           sync.Mutex
	tokensIssued []string
	appsAuth     []string
	appsHandler  func(w http.ResponseWriter, tokenIndex int)
}

func (f *fakeFormation) tokenIndexFor(authHeader string) int {
	for i, token := range f.tokensIssued {
		if authHeader == "Bearer "+token {
			return i
		}
	}
	return -1
}

func newFakeFormation(t *testing.T, appsHandler func(w http.ResponseWriter, tokenIndex int)) (*fakeFormation, *Client) {
	t.Helper()
	fake := &fakeFormation{appsHandler: appsHandler}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /realms/r/protocol/openid-connect/token", func(w http.ResponseWriter, _ *http.Request) {
		fake.mu.Lock()
		defer fake.mu.Unlock()
		claims, _ := json.Marshal(map[string]any{"exp": time.Now().Add(time.Hour).Unix()})
		token := fmt.Sprintf("h%d.%s.s", len(fake.tokensIssued), base64.RawURLEncoding.EncodeToString(claims))
		fake.tokensIssued = append(fake.tokensIssued, token)
		json.NewEncoder(w).Encode(map[string]any{"access_token": token, "expires_in": 3600}) //nolint:errcheck
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

	client, err := New(server.URL, server.URL, "r", "cid", "csecret", true, 10*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	return fake, client
}

// A 403 from a stale token must trigger exactly one retry with a freshly
// minted token, so Keycloak role changes take effect without a restart.
func TestRetriesOnceWithFreshTokenOnForbidden(t *testing.T) {
	fake, client := newFakeFormation(t, func(w http.ResponseWriter, tokenIndex int) {
		if tokenIndex == 0 {
			http.Error(w, `{"detail":"Service account missing required role"}`, http.StatusForbidden)
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
	fake, client := newFakeFormation(t, func(w http.ResponseWriter, _ int) {
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
	fake, client := newFakeFormation(t, func(w http.ResponseWriter, _ int) {
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
