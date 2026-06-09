// Package ldapclient ports portal_ldap.py to Go using go-ldap. Each
// operation dials a fresh connection, which replaces the Python
// ReconnectLDAPObject's retry-on-stale-connection behavior.
package ldapclient

import (
	"errors"
	"fmt"
	"log"
	"strconv"
	"time"

	"github.com/go-ldap/ldap/v3"

	"github.com/cyverse-de/portal-conductor/kinds"
)

var defaultGroupAttrs = []string{
	"objectClass",
	"displayName",
	"sambaGroupType",
	"sambaSID",
	"gidNumber",
	"cn",
	"description",
}

// Group holds the LDAP attributes of a posixGroup entry.
type Group struct {
	DN    string
	Attrs map[string][]string
}

// Client performs the LDAP operations needed by the portal.
type Client struct {
	url          string
	bindDN       string
	bindPassword string
	baseDN       string
}

// New returns a Client and verifies connectivity by binding once, mirroring
// the eager connect in portal_ldap.connect.
func New(url, bindDN, bindPassword, baseDN string) (*Client, error) {
	c := &Client{url: url, bindDN: bindDN, bindPassword: bindPassword, baseDN: baseDN}
	conn, err := c.dial()
	if err != nil {
		return nil, err
	}
	_ = conn.Close()
	return c, nil
}

func (c *Client) dial() (*ldap.Conn, error) {
	conn, err := ldap.DialURL(c.url)
	if err != nil {
		return nil, fmt.Errorf("dialing LDAP server %s failed (server down or unreachable?): %w", c.url, err)
	}
	conn.SetTimeout(time.Minute)
	if err := conn.Bind(c.bindDN, c.bindPassword); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("LDAP bind as %s failed (bad service credentials?): %w", c.bindDN, err)
	}
	return conn, nil
}

func (c *Client) do(fn func(conn *ldap.Conn) error) error {
	conn, err := c.dial()
	if err != nil {
		return err
	}
	defer conn.Close() //nolint:errcheck
	return fn(conn)
}

func (c *Client) search(conn *ldap.Conn, filter string, attrs []string) ([]*ldap.Entry, error) {
	req := ldap.NewSearchRequest(
		c.baseDN, ldap.ScopeWholeSubtree, ldap.NeverDerefAliases, 0, 0, false,
		filter, attrs, nil,
	)
	res, err := conn.Search(req)
	if err != nil {
		return nil, err
	}
	return res.Entries, nil
}

func (c *Client) userDN(username string) string {
	return fmt.Sprintf("uid=%s,ou=People,%s", ldap.EscapeDN(username), c.baseDN)
}

func (c *Client) groupDN(group string) string {
	return fmt.Sprintf("cn=%s,ou=Groups,%s", ldap.EscapeDN(group), c.baseDN)
}

// GetUser returns the posixAccount entry for username, or nil if not found.
func (c *Client) GetUser(username string) (*ldap.Entry, error) {
	var entry *ldap.Entry
	err := c.do(func(conn *ldap.Conn) error {
		filter := fmt.Sprintf("(&(objectClass=posixAccount)(uid=%s))", ldap.EscapeFilter(username))
		entries, err := c.search(conn, filter, nil)
		if err != nil {
			return err
		}
		if len(entries) > 0 {
			entry = entries[0]
		}
		return nil
	})
	return entry, err
}

// GetUserDN returns the DN of the person entry for username, or "" if not found.
func (c *Client) GetUserDN(username string) (string, error) {
	var dn string
	err := c.do(func(conn *ldap.Conn) error {
		filter := fmt.Sprintf("(&(objectClass=person)(uid=%s))", ldap.EscapeFilter(username))
		entries, err := c.search(conn, filter, []string{"dn"})
		if err != nil {
			return err
		}
		if len(entries) > 0 {
			dn = entries[0].DN
		}
		return nil
	})
	return dn, err
}

// GetUserGroups returns the posixGroups that username is a memberUid of. The
// memberUid attribute itself is excluded because it can be huge.
func (c *Client) GetUserGroups(username string) ([]Group, error) {
	var groups []Group
	err := c.do(func(conn *ldap.Conn) error {
		filter := fmt.Sprintf("(&(objectClass=posixGroup)(memberUid=%s))", ldap.EscapeFilter(username))
		entries, err := c.search(conn, filter, defaultGroupAttrs)
		if err != nil {
			return err
		}
		groups = entriesToGroups(entries)
		return nil
	})
	return groups, err
}

// GetGroups returns all posixGroup entries in the directory.
func (c *Client) GetGroups() ([]Group, error) {
	var groups []Group
	err := c.do(func(conn *ldap.Conn) error {
		entries, err := c.search(conn, "(objectClass=posixGroup)", defaultGroupAttrs)
		if err != nil {
			return err
		}
		groups = entriesToGroups(entries)
		return nil
	})
	return groups, err
}

func entriesToGroups(entries []*ldap.Entry) []Group {
	groups := make([]Group, 0, len(entries))
	for _, e := range entries {
		attrs := make(map[string][]string, len(e.Attributes))
		for _, a := range e.Attributes {
			attrs[a.Name] = a.Values
		}
		groups = append(groups, Group{DN: e.DN, Attrs: attrs})
	}
	return groups
}

// DaysSinceEpoch returns the number of days since the Unix epoch, used for
// the shadowLastChange attribute.
func DaysSinceEpoch() int {
	return int(time.Since(time.Unix(0, 0)) / (24 * time.Hour))
}

func validateUIDNumber(userUID string) (int, error) {
	n, err := strconv.Atoi(userUID)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("invalid uidNumber '%s': must be a positive integer", userUID)
	}
	return n, nil
}

// CreateUser adds a new posixAccount/shadowAccount/inetOrgPerson entry under
// ou=People with the same attributes as portal_ldap.create_user.
func (c *Client) CreateUser(daysSinceEpoch int, user kinds.CreateUserRequest) error {
	uidNumber, err := validateUIDNumber(user.UserUID)
	if err != nil {
		return err
	}
	if daysSinceEpoch < 0 {
		return fmt.Errorf("invalid shadowLastChange '%d': must be a non-negative integer", daysSinceEpoch)
	}

	req := ldap.NewAddRequest(c.userDN(user.Username), nil)
	req.Attribute("objectClass", []string{"posixAccount", "shadowAccount", "inetOrgPerson"})
	req.Attribute("givenName", []string{user.FirstName})
	req.Attribute("sn", []string{user.LastName})
	req.Attribute("cn", []string{fmt.Sprintf("%s %s", user.FirstName, user.LastName)})
	req.Attribute("uid", []string{user.Username})
	req.Attribute("userPassword", []string{user.Password})
	req.Attribute("mail", []string{user.Email})
	req.Attribute("departmentNumber", []string{user.Department})
	req.Attribute("o", []string{user.Organization})
	req.Attribute("title", []string{user.Title})
	req.Attribute("homeDirectory", []string{fmt.Sprintf("/home/%s", user.Username)})
	req.Attribute("loginShell", []string{"/bin/bash"})
	req.Attribute("gidNumber", []string{"10013"})
	req.Attribute("uidNumber", []string{strconv.Itoa(uidNumber)})
	req.Attribute("shadowLastChange", []string{strconv.Itoa(daysSinceEpoch)})
	req.Attribute("shadowMin", []string{"1"})
	req.Attribute("shadowMax", []string{"730"})
	req.Attribute("shadowInactive", []string{"10"})
	req.Attribute("shadowWarning", []string{"10"})

	return c.do(func(conn *ldap.Conn) error { return conn.Add(req) })
}

// CreateUserWithGroups creates the user if absent, sets their password, and
// idempotently adds them to the everyone and community groups.
func (c *Client) CreateUserWithGroups(user kinds.CreateUserRequest, everyoneGroup, communityGroup string) error {
	existing, err := c.GetUser(user.Username)
	if err != nil {
		return err
	}
	if existing == nil {
		log.Printf("Creating LDAP user: %s", user.Username)
		if err := c.CreateUser(DaysSinceEpoch(), user); err != nil {
			return err
		}
		log.Printf("Setting LDAP password for: %s", user.Username)
		if err := c.ChangePassword(user.Username, user.Password); err != nil {
			return err
		}
	} else {
		log.Printf("LDAP user %s already exists, skipping creation", user.Username)
	}

	for _, group := range []string{everyoneGroup, communityGroup} {
		if group == "" {
			continue
		}
		inGroup, err := c.userInGroup(user.Username, group)
		if err != nil {
			return err
		}
		if inGroup {
			log.Printf("User %s already in group: %s", user.Username, group)
			continue
		}
		log.Printf("Adding user %s to group: %s", user.Username, group)
		if err := c.AddUserToGroup(user.Username, group); err != nil {
			return err
		}
	}
	return nil
}

func (c *Client) userInGroup(username, group string) (bool, error) {
	groups, err := c.GetUserGroups(username)
	if err != nil {
		return false, err
	}
	for _, g := range groups {
		if len(g.Attrs["cn"]) > 0 && g.Attrs["cn"][0] == group {
			return true, nil
		}
	}
	return false, nil
}

// UserInGroup reports whether username is a memberUid of group.
func (c *Client) UserInGroup(username, group string) (bool, error) {
	return c.userInGroup(username, group)
}

// AddUserToGroup adds username to group's memberUid attribute.
func (c *Client) AddUserToGroup(username, group string) error {
	req := ldap.NewModifyRequest(c.groupDN(group), nil)
	req.Add("memberUid", []string{username})
	return c.do(func(conn *ldap.Conn) error { return conn.Modify(req) })
}

// RemoveUserFromGroup removes username from group's memberUid attribute.
func (c *Client) RemoveUserFromGroup(username, group string) error {
	req := ldap.NewModifyRequest(c.groupDN(group), nil)
	req.Delete("memberUid", []string{username})
	return c.do(func(conn *ldap.Conn) error { return conn.Modify(req) })
}

// DeleteUser removes the user entry from ou=People.
func (c *Client) DeleteUser(username string) error {
	req := ldap.NewDelRequest(c.userDN(username), nil)
	return c.do(func(conn *ldap.Conn) error { return conn.Del(req) })
}

// ChangePassword sets the user's password via the LDAP Password Modify
// extended operation (the equivalent of python-ldap's passwd_s).
func (c *Client) ChangePassword(username, password string) error {
	req := ldap.NewPasswordModifyRequest(c.userDN(username), "", password)
	return c.do(func(conn *ldap.Conn) error {
		_, err := conn.PasswordModify(req)
		return err
	})
}

// SetShadowLastChange replaces the shadowLastChange attribute with the given
// days-since-epoch value.
func (c *Client) SetShadowLastChange(daysSinceEpoch int, username string) error {
	if daysSinceEpoch < 0 {
		return fmt.Errorf("invalid shadowLastChange '%d': must be a non-negative integer", daysSinceEpoch)
	}
	req := ldap.NewModifyRequest(c.userDN(username), nil)
	req.Delete("shadowLastChange", nil)
	req.Add("shadowLastChange", []string{strconv.Itoa(daysSinceEpoch)})
	return c.do(func(conn *ldap.Conn) error { return conn.Modify(req) })
}

// ModifyUserAttribute replaces a single attribute value on the user entry.
func (c *Client) ModifyUserAttribute(username, attribute, value string) error {
	if value == "" {
		return fmt.Errorf("value cannot be empty for attribute '%s'", attribute)
	}
	req := ldap.NewModifyRequest(c.userDN(username), nil)
	req.Replace(attribute, []string{value})
	return c.do(func(conn *ldap.Conn) error { return conn.Modify(req) })
}

// ValidateCredentials binds as the user to check the password. It returns
// false (with no error) for unknown users or wrong passwords.
func (c *Client) ValidateCredentials(username, password string) (bool, error) {
	dn, err := c.GetUserDN(username)
	if err != nil {
		return false, err
	}
	if dn == "" {
		return false, nil
	}

	conn, err := ldap.DialURL(c.url)
	if err != nil {
		return false, fmt.Errorf("dialing LDAP server %s failed (server down or unreachable?): %w", c.url, err)
	}
	defer conn.Close() //nolint:errcheck
	conn.SetTimeout(time.Minute)

	if err := conn.Bind(dn, password); err != nil {
		var ldapErr *ldap.Error
		if errors.As(err, &ldapErr) && ldapErr.ResultCode == ldap.LDAPResultInvalidCredentials {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

func strAttr(attrs map[string][]string, name string) *string {
	if vals, ok := attrs[name]; ok && len(vals) > 0 && vals[0] != "" {
		v := vals[0]
		return &v
	}
	return nil
}

func intAttr(attrs map[string][]string, name string) *int {
	if vals, ok := attrs[name]; ok && len(vals) > 0 {
		if n, err := strconv.Atoi(vals[0]); err == nil {
			return &n
		}
	}
	return nil
}

func listAttr(attrs map[string][]string, name string) *[]string {
	if vals, ok := attrs[name]; ok && len(vals) > 0 {
		out := make([]string, len(vals))
		copy(out, vals)
		return &out
	}
	return nil
}

// ParseUserAttributes converts a user entry into the API's UserLDAPInfo.
func ParseUserAttributes(username string, entry *ldap.Entry) kinds.UserLDAPInfo {
	attrs := make(map[string][]string, len(entry.Attributes))
	for _, a := range entry.Attributes {
		attrs[a.Name] = a.Values
	}
	return kinds.UserLDAPInfo{
		Username:         username,
		UIDNumber:        intAttr(attrs, "uidNumber"),
		GIDNumber:        intAttr(attrs, "gidNumber"),
		GivenName:        strAttr(attrs, "givenName"),
		Surname:          strAttr(attrs, "sn"),
		CommonName:       strAttr(attrs, "cn"),
		Email:            strAttr(attrs, "mail"),
		Department:       strAttr(attrs, "departmentNumber"),
		Organization:     strAttr(attrs, "o"),
		Title:            strAttr(attrs, "title"),
		HomeDirectory:    strAttr(attrs, "homeDirectory"),
		LoginShell:       strAttr(attrs, "loginShell"),
		ShadowLastChange: intAttr(attrs, "shadowLastChange"),
		ShadowMin:        intAttr(attrs, "shadowMin"),
		ShadowMax:        intAttr(attrs, "shadowMax"),
		ShadowWarning:    intAttr(attrs, "shadowWarning"),
		ShadowInactive:   intAttr(attrs, "shadowInactive"),
		ObjectClasses:    listAttr(attrs, "objectClass"),
	}
}

// ParseGroupAttributes converts a group entry into the API's LDAPGroupInfo.
// The Name field is empty when the entry has no cn.
func ParseGroupAttributes(group Group) kinds.LDAPGroupInfo {
	name := ""
	if n := strAttr(group.Attrs, "cn"); n != nil {
		name = *n
	}
	return kinds.LDAPGroupInfo{
		Name:           name,
		GIDNumber:      intAttr(group.Attrs, "gidNumber"),
		DisplayName:    strAttr(group.Attrs, "displayName"),
		Description:    strAttr(group.Attrs, "description"),
		SambaGroupType: intAttr(group.Attrs, "sambaGroupType"),
		SambaSID:       strAttr(group.Attrs, "sambaSID"),
		ObjectClasses:  listAttr(group.Attrs, "objectClass"),
	}
}
