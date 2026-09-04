package ldapclient

import (
	"fmt"
	"slices"
	"strings"
	"testing"
)

// The batching, folding, and filter assembly are the parts of the bulk lookup
// that decide whether a user reaches the response at all, and they are pure
// logic: no directory needed to exercise them.
func TestUsersFilter(t *testing.T) {
	tests := []struct {
		name      string
		usernames []string
		want      string
	}{
		{"no usernames", nil, "(&(objectClass=posixAccount)(|))"},
		{"one username", []string{"alice"}, "(&(objectClass=posixAccount)(|(uid=alice)))"},
		{"several usernames", []string{"alice", "bob"},
			"(&(objectClass=posixAccount)(|(uid=alice)(uid=bob)))"},
		// Escaped, or a name could widen the search to every entry.
		{"a wildcard", []string{"*"}, `(&(objectClass=posixAccount)(|(uid=\2a)))`},
		{"filter syntax", []string{"a)(uid=b"}, `(&(objectClass=posixAccount)(|(uid=a\29\28uid=b)))`},
		{"a backslash", []string{`a\b`}, `(&(objectClass=posixAccount)(|(uid=a\5cb)))`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := usersFilter(tt.usernames); got != tt.want {
				t.Errorf("usersFilter(%q) = %s, want %s", tt.usernames, got, tt.want)
			}
		})
	}
}

func TestFoldUsernames(t *testing.T) {
	tests := []struct {
		name      string
		usernames []string
		want      []string
	}{
		{"empty", nil, []string{}},
		{"already folded", []string{"alice", "bob"}, []string{"alice", "bob"}},
		{"mixed case is lowered", []string{"Alice", "BOB"}, []string{"alice", "bob"}},
		// uid matches case-insensitively, so these name one user, not two.
		{"case-differing duplicates collapse", []string{"Alice", "alice", "ALICE"}, []string{"alice"}},
		{"order is first occurrence", []string{"carol", "Alice", "carol"}, []string{"carol", "alice"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := foldUsernames(tt.usernames); !slices.Equal(got, tt.want) {
				t.Errorf("foldUsernames(%q) = %q, want %q", tt.usernames, got, tt.want)
			}
		})
	}
}

// A dropped final batch would silently omit the last 1-99 users, which the
// caller reads as those users having left the group.
func TestUserBatchingCoversEveryUsername(t *testing.T) {
	tests := []struct {
		name        string
		count       int
		wantBatches int
		wantLast    int
	}{
		{"under one batch", 1, 1, 1},
		{"exactly one batch", maxUsersPerSearch, 1, maxUsersPerSearch},
		{"one over a batch", maxUsersPerSearch + 1, 2, 1},
		{"several batches with a partial last", 2*maxUsersPerSearch + 7, 3, 7},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			usernames := make([]string, 0, tt.count)
			for i := range tt.count {
				usernames = append(usernames, fmt.Sprintf("user%04d", i))
			}

			var batches [][]string
			for batch := range slices.Chunk(foldUsernames(usernames), maxUsersPerSearch) {
				batches = append(batches, batch)
			}

			if len(batches) != tt.wantBatches {
				t.Fatalf("got %d batches, want %d", len(batches), tt.wantBatches)
			}
			if last := len(batches[len(batches)-1]); last != tt.wantLast {
				t.Errorf("last batch holds %d usernames, want %d", last, tt.wantLast)
			}

			var covered []string
			for _, batch := range batches {
				covered = append(covered, batch...)
				if !strings.HasPrefix(usersFilter(batch), "(&(objectClass=posixAccount)(|(uid=") {
					t.Errorf("batch produced a malformed filter: %s", usersFilter(batch))
				}
			}
			if !slices.Equal(covered, usernames) {
				t.Errorf("batches covered %d usernames, want all %d in order", len(covered), len(usernames))
			}
		})
	}
}
