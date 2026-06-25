package api

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/cyverse-de/portal-conductor/kinds"
	"github.com/cyverse-de/portal-conductor/ldapclient"
)

func TestUsernameValid(t *testing.T) {
	tests := []struct {
		username string
		valid    bool
	}{
		{"johndoe", true},
		{"abc123", true},
		{"a", true},
		{"0", true},
		{"", false},
		{"John", false},     // uppercase
		{"john_doe", false}, // underscore
		{"john-doe", false}, // hyphen
		{"john.doe", false}, // dot
		{"john doe", false}, // space
		{"john@doe", false}, // special char
		{"john123!", false}, // exclamation
	}
	for _, tt := range tests {
		t.Run(tt.username, func(t *testing.T) {
			got := usernameValid(tt.username)
			if got != tt.valid {
				t.Errorf("usernameValid(%q) = %v, want %v", tt.username, got, tt.valid)
			}
		})
	}
}

func TestGeneratePassword(t *testing.T) {
	pw, err := generatePassword()
	if err != nil {
		t.Fatalf("generatePassword() error: %v", err)
	}
	if len(pw) == 0 {
		t.Fatal("generatePassword() returned empty string")
	}
	// base64 of 36 bytes = 48 characters
	if len(pw) != 48 {
		t.Errorf("generatePassword() length = %d, want 48", len(pw))
	}

	// Two calls should produce different results.
	pw2, _ := generatePassword()
	if pw == pw2 {
		t.Error("generatePassword() produced duplicate passwords")
	}
}

func TestPortalEndpointsReturn503WhenDBNil(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "", nil).Handler()

	endpoints := []struct {
		method string
		path   string
	}{
		{http.MethodGet, "/portal/users/testuser/exists"},
		{http.MethodGet, "/portal/emails/test@example.com/exists"},
		{http.MethodPost, "/portal/users/testuser/validate"},
		{http.MethodPost, "/portal/users"},
	}

	for _, ep := range endpoints {
		t.Run(ep.method+" "+ep.path, func(t *testing.T) {
			body := ""
			if ep.method == http.MethodPost && ep.path == "/portal/users" {
				body = `{"username":"foo","email":"foo@bar.com","first_name":"Foo","last_name":"Bar"}`
			}
			rec := doRequest(t, handler, ep.method, ep.path, "admin", "secret", body)
			if rec.Code != http.StatusServiceUnavailable {
				t.Errorf("got status %d, want %d", rec.Code, http.StatusServiceUnavailable)
			}
		})
	}
}

func TestCreatePortalUserReturns503WhenRequiredDependenciesMissing(t *testing.T) {
	portalDB := &sql.DB{}

	tests := []struct {
		name       string
		ldap       *ldapclient.Client
		wantDetail string
	}{
		{
			name:       "ldap missing",
			ldap:       nil,
			wantDetail: "LDAP integration not configured",
		},
		{
			name:       "datastore missing",
			ldap:       &ldapclient.Client{},
			wantDetail: "DataStore integration not configured",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			handler := New(testConfig(), tt.ldap, nil, nil, nil, nil, "", portalDB).Handler()
			rec := doRequest(t, handler, http.MethodPost, "/portal/users", "admin", "secret", "")

			if rec.Code != http.StatusServiceUnavailable {
				t.Fatalf("got status %d, want %d", rec.Code, http.StatusServiceUnavailable)
			}
			if d := detailOf(t, rec); d != tt.wantDetail {
				t.Errorf("got detail %v, want %s", d, tt.wantDetail)
			}
		})
	}
}

func TestCreatePortalUserDefaultsApplied(t *testing.T) {
	// Verify that PortalCreateUserDefaults produces expected values.
	defaults := kinds.PortalCreateUserDefaults()

	if defaults.Department != "Not Provided" {
		t.Errorf("Department = %q, want %q", defaults.Department, "Not Provided")
	}
	if defaults.Institution != "Not Provided" {
		t.Errorf("Institution = %q, want %q", defaults.Institution, "Not Provided")
	}
	if defaults.OccupationID != 13 {
		t.Errorf("OccupationID = %d, want 13", defaults.OccupationID)
	}
	if defaults.FundingAgencyID != 21 {
		t.Errorf("FundingAgencyID = %d, want 21", defaults.FundingAgencyID)
	}
	if defaults.GenderID != 11 {
		t.Errorf("GenderID = %d, want 11", defaults.GenderID)
	}
	if defaults.EthnicityID != 8 {
		t.Errorf("EthnicityID = %d, want 8", defaults.EthnicityID)
	}
	if defaults.RegionID != 4394 {
		t.Errorf("RegionID = %d, want 4394", defaults.RegionID)
	}
	if defaults.ResearchAreaID != 155 {
		t.Errorf("ResearchAreaID = %d, want 155", defaults.ResearchAreaID)
	}
	if defaults.AwareChannelID != 11 {
		t.Errorf("AwareChannelID = %d, want 11", defaults.AwareChannelID)
	}
}

func TestCreatePortalUserDefaultsOverlaidByJSON(t *testing.T) {
	// Verify that JSON unmarshaling onto defaults correctly overlays
	// provided values while keeping defaults for omitted ones.
	defaults := kinds.PortalCreateUserDefaults()
	body := `{"username":"jdoe","email":"j@example.com","first_name":"Jane","last_name":"Doe","department":"Biology"}`

	if err := json.Unmarshal([]byte(body), &defaults); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if defaults.Username != "jdoe" {
		t.Errorf("Username = %q, want %q", defaults.Username, "jdoe")
	}
	if defaults.Department != "Biology" {
		t.Errorf("Department = %q, want %q (should be overridden)", defaults.Department, "Biology")
	}
	// These should still be defaults since they weren't in the JSON.
	if defaults.OccupationID != 13 {
		t.Errorf("OccupationID = %d, want 13 (should remain default)", defaults.OccupationID)
	}
	if defaults.RegionID != 4394 {
		t.Errorf("RegionID = %d, want 4394 (should remain default)", defaults.RegionID)
	}
}

func TestCreatePortalUserValidationNoAuth(t *testing.T) {
	handler := New(testConfig(), nil, nil, nil, nil, nil, "", nil).Handler()

	// No auth should return 401.
	req := httptest.NewRequest(http.MethodPost, "/portal/users", strings.NewReader(`{}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Errorf("got status %d, want %d", rec.Code, http.StatusUnauthorized)
	}
}
