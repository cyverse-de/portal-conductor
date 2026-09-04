package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"testing"
)

// The handlers that reach the directory need one, so these cover the request
// validation that runs before it: those paths return without touching LDAP,
// which is why a nil client is safe here.
func TestSearchUserLDAPInfoValidation(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "", nil).Handler()

	names := func(n int) string {
		quoted := make([]string, 0, n)
		for i := range n {
			quoted = append(quoted, fmt.Sprintf("%q", fmt.Sprintf("u%d", i)))
		}
		return `{"usernames":[` + strings.Join(quoted, ",") + `]}`
	}

	tests := []struct {
		name string
		body string
		user string
		pass string
		want int
	}{
		{"unauthenticated", names(1), "", "", http.StatusUnauthorized},
		{"wrong password", names(1), "admin", "wrong", http.StatusUnauthorized},
		{"missing usernames field", `{}`, "admin", "secret", http.StatusUnprocessableEntity},
		{"malformed body", `not json`, "admin", "secret", http.StatusUnprocessableEntity},
		{"over the batch cap", names(maxUserSearchBatch + 1), "admin", "secret", http.StatusRequestEntityTooLarge},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rec := doRequest(t, handler, http.MethodPost, "/ldap/users/search", tt.user, tt.pass, tt.body)
			if rec.Code != tt.want {
				t.Errorf("got status %d, want %d (%s)", rec.Code, tt.want, rec.Body.String())
			}
		})
	}
}

func TestSearchUserLDAPInfoEmptyRequest(t *testing.T) {
	// An empty list resolves to an empty response without a directory lookup,
	// so this exercises the whole handler with a nil client.
	handler := New(testConfig(), nil, nil, nil, nil, nil, "", nil).Handler()

	rec := doRequest(t, handler, http.MethodPost, "/ldap/users/search", "admin", "secret", `{"usernames":[]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got status %d, want 200 (%s)", rec.Code, rec.Body.String())
	}

	var resp struct {
		Users []map[string]any `json:"users"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("response is not JSON: %v (%s)", err, rec.Body.String())
	}
	if len(resp.Users) != 0 {
		t.Errorf("got %d users, want none", len(resp.Users))
	}
	if !strings.Contains(rec.Body.String(), `"users":[]`) {
		t.Errorf("an empty result must serialize as [], got %s", rec.Body.String())
	}
}

func TestSearchLDAPUsersEmptyTerm(t *testing.T) {
	// An empty term matches nothing without a directory lookup.
	handler := New(testConfig(), nil, nil, nil, nil, nil, "", nil).Handler()

	for _, path := range []string{"/ldap/users", "/ldap/users?search=", "/ldap/users?search=%20"} {
		rec := doRequest(t, handler, http.MethodGet, path, "admin", "secret", "")
		if rec.Code != http.StatusOK {
			t.Errorf("%s: got status %d, want 200 (%s)", path, rec.Code, rec.Body.String())
		}
		if !strings.Contains(rec.Body.String(), `"users":[]`) {
			t.Errorf("%s: got body %s, want an empty user list", path, rec.Body.String())
		}
	}
}
