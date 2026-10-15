package ldapclient

import (
	"errors"
	"fmt"
	"testing"

	"github.com/go-ldap/ldap/v3"
)

func TestIsMissingMember(t *testing.T) {
	noSuchAttr := ldap.NewError(ldap.LDAPResultNoSuchAttribute, errors.New("modify/delete: memberUid: no such value"))

	tests := []struct {
		name string
		err  error
		want bool
	}{
		{name: "nil", err: nil, want: false},
		{name: "no such attribute", err: noSuchAttr, want: true},
		{name: "wrapped no such attribute", err: fmt.Errorf("modify: %w", noSuchAttr), want: true},
		{name: "other LDAP error", err: ldap.NewError(ldap.LDAPResultNoSuchObject, errors.New("no such object")), want: false},
		{name: "non-LDAP error", err: errors.New("connection reset"), want: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isMissingMember(tt.err); got != tt.want {
				t.Errorf("isMissingMember(%v) = %v, want %v", tt.err, got, tt.want)
			}
		})
	}
}
