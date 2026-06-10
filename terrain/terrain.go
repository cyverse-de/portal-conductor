// Package terrain ports terrain.py to Go: a small client for the Terrain
// API's Keycloak token and concurrent-job-limit endpoints.
package terrain

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"sync"
	"time"

	"github.com/cyverse-de/portal-conductor/external"
)

// refreshBuffer is how long before expiry the token is refreshed.
const refreshBuffer = 60 * time.Second

// Client calls the Terrain API using the configured service account, caching
// the Keycloak token until shortly before it expires.
type Client struct {
	baseURL    *url.URL
	username   string
	password   string
	httpClient *http.Client

	mu          sync.Mutex
	token       string
	tokenExpiry time.Time
}

// New returns a Client for the Terrain API at apiURL.
func New(apiURL, username, password string) (*Client, error) {
	base, err := url.Parse(apiURL)
	if err != nil {
		return nil, fmt.Errorf("parsing terrain URL %q: %w", apiURL, err)
	}
	return &Client{
		baseURL:    base,
		username:   username,
		password:   password,
		httpClient: &http.Client{Timeout: 60 * time.Second},
	}, nil
}

func (c *Client) apiURL(parts ...string) string {
	return c.baseURL.JoinPath(parts...).String()
}

func (c *Client) doJSON(req *http.Request, out any) error {
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return &external.RequestError{URL: req.URL.String(), Err: err}
	}
	defer resp.Body.Close() //nolint:errcheck
	if err := external.CheckResponse(resp); err != nil {
		return err
	}
	if out != nil {
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			return fmt.Errorf("decoding response from %s: %w", req.URL, err)
		}
	}
	return nil
}

// accessToken returns a cached token, fetching a fresh one when missing,
// nearly expired, or when forceRefresh is set.
func (c *Client) accessToken(forceRefresh bool) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if forceRefresh || c.token == "" || time.Now().After(c.tokenExpiry.Add(-refreshBuffer)) {
		token, err := c.GetKeycloakToken()
		if err != nil {
			return "", err
		}
		c.token = token
		c.tokenExpiry = external.TokenExpiry(token)
	}
	return c.token, nil
}

// attempt performs one authenticated request, fetching or refreshing the
// token as needed.
func (c *Client) attempt(method, requestURL string, payload []byte, forceTokenRefresh bool) (*http.Response, error) {
	var reqBody io.Reader
	if payload != nil {
		reqBody = bytes.NewReader(payload)
	}
	req, err := http.NewRequest(method, requestURL, reqBody)
	if err != nil {
		return nil, err
	}

	token, err := c.accessToken(forceTokenRefresh)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, &external.RequestError{URL: requestURL, Err: err}
	}
	return resp, nil
}

func (c *Client) doAuthedJSON(method, requestURL string, payload []byte, out any) error {
	resp, err := c.attempt(method, requestURL, payload, false)
	if err != nil {
		return err
	}

	// A 401/403 can mean the cached token predates a role or permission
	// change in Keycloak; retry once with a freshly minted token.
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		resp.Body.Close() //nolint:errcheck
		log.Printf("[Terrain] %d from %s; retrying once with a fresh token in case the cached one predates a Keycloak permission change", resp.StatusCode, requestURL)
		resp, err = c.attempt(method, requestURL, payload, true)
		if err != nil {
			return err
		}
	}

	defer resp.Body.Close() //nolint:errcheck
	if err := external.CheckResponse(resp); err != nil {
		return err
	}
	if out != nil {
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			return fmt.Errorf("decoding response from %s: %w", requestURL, err)
		}
	}
	return nil
}

// GetKeycloakToken fetches an access token for the service account via
// Terrain's token endpoint.
func (c *Client) GetKeycloakToken() (string, error) {
	u := c.apiURL("token", "keycloak")
	log.Printf("Requesting Keycloak token from: %s", u)
	req, err := http.NewRequest(http.MethodGet, u, nil)
	if err != nil {
		return "", err
	}
	req.SetBasicAuth(c.username, c.password)

	var body struct {
		AccessToken string `json:"access_token"`
	}
	if err := c.doJSON(req, &body); err != nil {
		return "", err
	}
	return body.AccessToken, nil
}

// GetConcurrentJobLimits returns the raw job-limits document for username.
func (c *Client) GetConcurrentJobLimits(username string) (map[string]any, error) {
	var result map[string]any
	if err := c.doAuthedJSON(http.MethodGet, c.apiURL("admin", "settings", "concurrent-job-limits", username), nil, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// SetConcurrentJobLimits sets the concurrent job limit for username.
func (c *Client) SetConcurrentJobLimits(username string, limit int) error {
	payload, err := json.Marshal(map[string]int{"concurrent_jobs": limit})
	if err != nil {
		return err
	}
	return c.doAuthedJSON(http.MethodPut, c.apiURL("admin", "settings", "concurrent-job-limits", username), payload, nil)
}
