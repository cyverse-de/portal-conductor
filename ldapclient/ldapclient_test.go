package ldapclient

import (
	"errors"
	"fmt"
	"testing"

	"github.com/go-ldap/ldap/v3"
)

func TestIgnoreMissingMember(t *testing.T) {
	noSuchAttr := ldap.NewError(ldap.LDAPResultNoSuchAttribute, errors.New("modify/delete: memberUid: no such value"))
	noSuchObject := ldap.NewError(ldap.LDAPResultNoSuchObject, errors.New("no such object"))
	plain := errors.New("connection reset")

	tests := []struct {
		name string
		err  error
		want error
	}{
		{name: "nil", err: nil, want: nil},
		{name: "no such attribute", err: noSuchAttr, want: nil},
		{name: "wrapped no such attribute", err: fmt.Errorf("modify: %w", noSuchAttr), want: nil},
		{name: "other LDAP error", err: noSuchObject, want: noSuchObject},
		{name: "non-LDAP error", err: plain, want: plain},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ignoreMissingMember(tt.err); got != tt.want {
				t.Errorf("ignoreMissingMember(%v) = %v, want %v", tt.err, got, tt.want)
			}
		})
	}
}
