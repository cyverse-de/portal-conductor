package mailman

import (
	"errors"
	"net/url"
	"strings"

	"github.com/cyverse-de/portal-conductor/external"

	"fmt"
	"net/http"
	"net/http/httptest"
	"slices"
	"testing"
)

func TestMemberExists(t *testing.T) {
	tests := []struct {
		name     string
		email    string
		pageHTML string
		want     bool
	}{
		{"present", "john.doe@example.org", `<td>john.doe@example.org</td>`, true},
		{"absent", "john.doe@example.org", `<td>jane@example.org</td>`, false},
		{"no partial match", "doe@example.org", `<td>john.doe@example.orgx</td>`, false},
		{"case insensitive", "John.Doe@Example.org", `<td>john.doe@example.org</td>`, true},
		{"url-encoded email", "john.doe%40example.org", `<td>john.doe@example.org</td>`, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var gotLetter, gotPassword string
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/mailman/admin/mylist/members" {
					t.Errorf("unexpected path %s", r.URL.Path)
				}
				gotLetter = r.URL.Query().Get("letter")
				gotPassword = r.URL.Query().Get("adminpw")
				_, _ = fmt.Fprint(w, tt.pageHTML)
			}))
			defer server.Close()

			client, err := New(server.URL, "adminsecret")
			if err != nil {
				t.Fatal(err)
			}
			exists, err := client.MemberExists("mylist", tt.email)
			if err != nil {
				t.Fatal(err)
			}
			if exists != tt.want {
				t.Errorf("got exists=%v, want %v", exists, tt.want)
			}
			if gotLetter != "j" && gotLetter != "d" {
				t.Errorf("letter param %q should be the email's first letter", gotLetter)
			}
			if gotPassword != "adminsecret" {
				t.Errorf("adminpw param %q", gotPassword)
			}
		})
	}
}

func TestListMembers(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Query().Get("letter") {
		case "a":
			_, _ = fmt.Fprint(w, `<td>alice@site.org</td><td>Filtered@example.com</td>`)
		case "b":
			_, _ = fmt.Fprint(w, `<td>BOB@other.net</td><td>alice@site.org</td>`)
		default:
			_, _ = fmt.Fprint(w, `<html>no members</html>`)
		}
	}))
	defer server.Close()

	client, err := New(server.URL, "pw")
	if err != nil {
		t.Fatal(err)
	}
	members, err := client.ListMembers("mylist")
	if err != nil {
		t.Fatal(err)
	}

	want := []string{"alice@site.org", "bob@other.net"}
	if !slices.Equal(members, want) {
		t.Errorf("got members %v, want %v", members, want)
	}
}

func TestListMembersContinuesOnPageError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("letter") == "a" {
			http.Error(w, "boom", http.StatusInternalServerError)
			return
		}
		_, _ = fmt.Fprint(w, `<td>carol@site.org</td>`)
	}))
	defer server.Close()

	client, err := New(server.URL, "pw")
	if err != nil {
		t.Fatal(err)
	}
	members, err := client.ListMembers("mylist")
	if err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(members, []string{"carol@site.org"}) {
		t.Errorf("got members %v", members)
	}
}

func TestAdminURLIgnoresBasePath(t *testing.T) {
	client, err := New("http://mailman-server/some/base", "pw")
	if err != nil {
		t.Fatal(err)
	}
	got := client.adminURL("mylist", "members", "add").String()
	want := "http://mailman-server/mailman/admin/mylist/members/add"
	if got != want {
		t.Errorf("got %s, want %s", got, want)
	}
}

func TestErrorsRedactAdminPassword(t *testing.T) {
	const password = "$onorand0g!"

	t.Run("request error", func(t *testing.T) {
		// Unreachable port: the connection error embeds the request URL.
		client, err := New("http://127.0.0.1:1", password)
		if err != nil {
			t.Fatal(err)
		}
		err = client.AddMember("mylist", "a@b.com")
		if err == nil {
			t.Fatal("expected connection error")
		}
		assertRedacted(t, err.Error(), password)
	})

	t.Run("status error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Echo the password back so the body needs redaction too.
			http.Error(w, "bad admin password: "+r.URL.Query().Get("adminpw"), http.StatusUnauthorized)
		}))
		defer server.Close()

		client, err := New(server.URL, password)
		if err != nil {
			t.Fatal(err)
		}
		err = client.AddMember("mylist", "a@b.com")
		if err == nil {
			t.Fatal("expected status error")
		}
		var statusErr *external.StatusError
		if !errors.As(err, &statusErr) {
			t.Fatalf("expected StatusError, got %T", err)
		}
		assertRedacted(t, statusErr.URL, password)
		assertRedacted(t, statusErr.Body, password)
	})
}

func assertRedacted(t *testing.T, s, password string) {
	t.Helper()
	if strings.Contains(s, password) || strings.Contains(s, url.QueryEscape(password)) {
		t.Errorf("password leaked into %q", s)
	}
	if !strings.Contains(s, "[REDACTED]") {
		t.Errorf("expected [REDACTED] marker in %q", s)
	}
}
