// Package terrain ports terrain.py to Go: a small client for the Terrain
// API's Keycloak token and concurrent-job-limit endpoints.
package terrain

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"time"

	"github.com/cyverse-de/portal-conductor/external"
)

// Client calls the Terrain API using the configured service account.
type Client struct {
	baseURL    *url.URL
	username   string
	password   string
	httpClient *http.Client
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
func (c *Client) GetConcurrentJobLimits(token, username string) (map[string]any, error) {
	req, err := http.NewRequest(http.MethodGet, c.apiURL("admin", "settings", "concurrent-job-limits", username), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+token)

	var result map[string]any
	if err := c.doJSON(req, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// SetConcurrentJobLimits sets the concurrent job limit for username.
func (c *Client) SetConcurrentJobLimits(token, username string, limit int) error {
	payload, err := json.Marshal(map[string]int{"concurrent_jobs": limit})
	if err != nil {
		return err
	}
	req, err := http.NewRequest(http.MethodPut, c.apiURL("admin", "settings", "concurrent-job-limits", username), bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	return c.doJSON(req, nil)
}
