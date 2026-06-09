package kinds

import (
	"encoding/json"
	"slices"
	"testing"
)

func TestStringListUnmarshal(t *testing.T) {
	tests := []struct {
		name    string
		json    string
		want    []string
		wantErr bool
	}{
		{"single string", `"a@b.com"`, []string{"a@b.com"}, false},
		{"list of strings", `["a@b.com", "c@d.com"]`, []string{"a@b.com", "c@d.com"}, false},
		{"empty list", `[]`, []string{}, false},
		{"number rejected", `42`, nil, true},
		{"mixed list rejected", `["a", 1]`, nil, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var s StringList
			err := json.Unmarshal([]byte(tt.json), &s)
			if tt.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if !slices.Equal([]string(s), tt.want) {
				t.Errorf("got %v, want %v", s, tt.want)
			}
		})
	}
}

func TestOptionalFieldsSerializeAsNull(t *testing.T) {
	data, err := json.Marshal(AnalysisStatusResponse{AnalysisID: "abc", Status: "Running"})
	if err != nil {
		t.Fatal(err)
	}
	want := `{"analysis_id":"abc","status":"Running","url_ready":null,"url":null}`
	if string(data) != want {
		t.Errorf("got %s, want %s", data, want)
	}
}
