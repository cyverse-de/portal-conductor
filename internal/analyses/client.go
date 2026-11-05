// Package analyses is a client for the DE analyses service's concurrent-job-limit
// endpoints. The analyses service is internal (cluster-only) and requires no
// authentication.
package analyses

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// Client calls the analyses service.
type Client struct {
	baseURL    *url.URL
	httpClient *http.Client
}

// New returns a Client for the analyses service at the given base URL.
func New(baseURL string) (*Client, error) {
	u, err := url.Parse(baseURL)
	if err != nil {
		return nil, fmt.Errorf("parsing analyses URL %q: %w", baseURL, err)
	}
	return &Client{
		baseURL:    u,
		httpClient: &http.Client{Timeout: 30 * time.Second},
	}, nil
}

func (c *Client) url(parts ...string) string {
	return c.baseURL.JoinPath(parts...).String()
}

// SetConcurrentJobLimit sets the concurrent job limit for username.
func (c *Client) SetConcurrentJobLimit(username string, limit int) error {
	payload, err := json.Marshal(map[string]int{"concurrent_jobs": limit})
	if err != nil {
		return err
	}
	req, err := http.NewRequest(http.MethodPut, c.url("settings", "concurrent-job-limits", username), bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("analyses: setting job limit for %s: %w", username, err)
	}
	defer resp.Body.Close() //nolint:errcheck
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("analyses: setting job limit for %s: %d %s", username, resp.StatusCode, string(body))
	}
	return nil
}
