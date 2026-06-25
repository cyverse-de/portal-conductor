package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/cyverse-de/portal-conductor/terrain"
)

// newAppJobViewServer serves Terrain's token endpoint and an app job-view
// endpoint returning the given parameter groups.
func newAppJobViewServer(t *testing.T, jobView map[string]any) *httptest.Server {
	t.Helper()
	return newTerrainTestServer(t, func(mux *http.ServeMux) {
		mux.HandleFunc("GET /apps/de/app-123", func(w http.ResponseWriter, _ *http.Request) {
			json.NewEncoder(w).Encode(jobView) //nolint:errcheck
		})
	})
}

func TestUsernameParamID(t *testing.T) {
	param := func(id, label, typ string, visible, required bool, defaultValue, name any) map[string]any {
		return map[string]any{
			"id": id, "label": label, "type": typ,
			"isVisible": visible, "required": required,
			"defaultValue": defaultValue, "name": name,
		}
	}

	tests := []struct {
		name      string
		groups    []any
		wantID    string
		wantError bool
	}{
		{
			"matches by username label",
			[]any{map[string]any{"parameters": []any{
				param("p1", "Output dir", "Text", true, true, nil, nil),
				param("p2", "Username", "Text", true, true, nil, nil),
			}}},
			"p2", false,
		},
		{
			"matches by user name label case-insensitively",
			[]any{map[string]any{"parameters": []any{
				param("p1", "The User Name", "Text", false, false, nil, nil),
			}}},
			"p1", false,
		},
		{
			"matches visible required text param without default or name",
			[]any{map[string]any{"parameters": []any{
				param("p1", "Config", "Text", true, true, "preset", nil),
				param("p2", "Target", "Text", true, true, nil, ""),
			}}},
			"p2", false,
		},
		{
			"falls back to last visible required parameter",
			[]any{map[string]any{"parameters": []any{
				param("p1", "First", "Flag", true, true, "x", "--first"),
				param("p2", "Second", "Flag", true, true, "y", "--second"),
			}}},
			"p2", false,
		},
		{
			"skips empty group and matches in second",
			[]any{
				map[string]any{"parameters": []any{}},
				map[string]any{"parameters": []any{param("p9", "Username", "Text", true, true, nil, nil)}},
			},
			"p9", false,
		},
		{"no groups", []any{}, "", true},
		{
			"no candidate parameters",
			[]any{map[string]any{"parameters": []any{
				param("p1", "Hidden", "Text", false, false, nil, nil),
			}}},
			"", true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := newAppJobViewServer(t, map[string]any{"groups": tt.groups})
			client, err := terrain.New(server.URL, "svc", "pw")
			if err != nil {
				t.Fatal(err)
			}

			a := New(testConfig(), nil, nil, client, nil, nil, "app-123", nil)
			id, err := a.usernameParamID(client, "de", "app-123")

			if tt.wantError {
				var he *httpError
				if !errors.As(err, &he) || he.status != http.StatusInternalServerError {
					t.Fatalf("expected 500 httpError, got %v", err)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if id != tt.wantID {
				t.Errorf("got param ID %q, want %q", id, tt.wantID)
			}
		})
	}
}

func TestTruthy(t *testing.T) {
	tests := []struct {
		name string
		v    any
		want bool
	}{
		{"nil", nil, false},
		{"empty string", "", false},
		{"string", "x", true},
		{"false", false, false},
		{"true", true, true},
		{"zero", 0.0, false},
		{"number", 2.0, true},
		{"empty map", map[string]any{}, false},
		{"map", map[string]any{"k": "v"}, true},
		{"empty list", []any{}, false},
		{"list", []any{"x"}, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := truthy(tt.v); got != tt.want {
				t.Errorf("truthy(%v) = %v, want %v", tt.v, got, tt.want)
			}
		})
	}
}
