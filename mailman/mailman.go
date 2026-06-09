// Package mailman ports mailman.py to Go: it drives the Mailman 2.1 admin
// web interface, since Mailman 2.1 has no real API. Member information is
// scraped from the letter-paginated roster pages.
package mailman

import (
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"slices"
	"strings"
	"time"

	"github.com/cyverse-de/portal-conductor/external"
)

// rosterEmailPattern matches email addresses in the roster page HTML.
var rosterEmailPattern = regexp.MustCompile(`\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b`)

// Client drives a Mailman 2.1 admin interface.
type Client struct {
	baseURL    *url.URL
	password   string
	httpClient *http.Client
}

// New returns a Client for the Mailman server at apiURL. Only the scheme and
// host of apiURL are used; admin pages always live under /mailman/admin.
func New(apiURL, password string) (*Client, error) {
	base, err := url.Parse(apiURL)
	if err != nil {
		return nil, fmt.Errorf("parsing mailman URL %q: %w", apiURL, err)
	}
	return &Client{
		baseURL:    base,
		password:   password,
		httpClient: &http.Client{Timeout: 60 * time.Second},
	}, nil
}

func (c *Client) adminURL(listName string, parts ...string) *url.URL {
	u := *c.baseURL
	u.Path = "/" + strings.Join(append([]string{"mailman", "admin", listName}, parts...), "/")
	u.RawQuery = ""
	return &u
}

// redact masks the admin password (raw and URL-encoded) in error text so it
// never reaches response bodies or logs.
func (c *Client) redact(s string) string {
	if c.password == "" {
		return s
	}
	s = strings.ReplaceAll(s, url.QueryEscape(c.password), "[REDACTED]")
	return strings.ReplaceAll(s, c.password, "[REDACTED]")
}

func (c *Client) do(method string, u *url.URL, params url.Values) (string, error) {
	u.RawQuery = params.Encode()
	req, err := http.NewRequest(method, u.String(), nil)
	if err != nil {
		return "", err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", &external.RequestError{URL: c.redact(u.String()), Err: errors.New(c.redact(err.Error()))}
	}
	defer resp.Body.Close() //nolint:errcheck
	if err := external.CheckResponse(resp); err != nil {
		var statusErr *external.StatusError
		if errors.As(err, &statusErr) {
			statusErr.URL = c.redact(statusErr.URL)
			statusErr.Body = c.redact(statusErr.Body)
		}
		return "", err
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

// AddMember subscribes email to listName without sending a welcome message.
func (c *Client) AddMember(listName, email string) error {
	params := url.Values{
		"subscribe_or_invite":            {"0"},
		"send_welcome_msg_to_this_batch": {"0"},
		"subscribees_upload":             {email},
		"adminpw":                        {c.password},
	}
	_, err := c.do(http.MethodPost, c.adminURL(listName, "members", "add"), params)
	return err
}

// RemoveMember unsubscribes email from listName without notifications.
func (c *Client) RemoveMember(listName, email string) error {
	params := url.Values{
		"send_unsub_ack_to_this_batch":           {"0"},
		"send_unsub_notifications_to_list_owner": {"0"},
		"unsubscribees_upload":                   {email},
		"adminpw":                                {c.password},
	}
	_, err := c.do(http.MethodPost, c.adminURL(listName, "members", "remove"), params)
	return err
}

// MemberExists reports whether email is subscribed to listName by scanning
// the roster page for the email's first letter.
func (c *Client) MemberExists(listName, email string) (bool, error) {
	decoded, err := url.QueryUnescape(email)
	if err != nil {
		decoded = email
	}
	if decoded == "" {
		return false, nil
	}
	firstLetter := strings.ToLower(decoded[:1])

	params := url.Values{"adminpw": {c.password}, "letter": {firstLetter}}
	body, err := c.do(http.MethodGet, c.adminURL(listName, "members"), params)
	if err != nil {
		return false, err
	}

	pattern, err := regexp.Compile(`\b` + regexp.QuoteMeta(strings.ToLower(decoded)) + `\b`)
	if err != nil {
		return false, err
	}
	return pattern.MatchString(strings.ToLower(body)), nil
}

// ListMembers returns the sorted member emails of listName, collected across
// all letter-paginated roster pages (a-z, 0-9).
func (c *Client) ListMembers(listName string) ([]string, error) {
	emails := make(map[string]struct{})
	for _, letter := range "abcdefghijklmnopqrstuvwxyz0123456789" {
		params := url.Values{"adminpw": {c.password}, "letter": {string(letter)}}
		body, err := c.do(http.MethodGet, c.adminURL(listName, "members"), params)
		if err != nil {
			// A single missing letter page shouldn't fail the whole listing.
			log.Printf("Failed to fetch letter page '%c' for list %s: %v", letter, listName, err)
			continue
		}
		for _, match := range rosterEmailPattern.FindAllString(body, -1) {
			email := strings.ToLower(match)
			// Skip Mailman's own boilerplate addresses.
			if strings.HasSuffix(email, "@mailman.org") || strings.HasSuffix(email, "@example.com") {
				continue
			}
			emails[email] = struct{}{}
		}
	}

	result := make([]string, 0, len(emails))
	for email := range emails {
		result = append(result, email)
	}
	slices.Sort(result)
	return result, nil
}
