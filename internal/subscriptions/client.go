// Package subscriptions is a client for the DE subscriptions (QMS) service's
// plan-assignment endpoint. The subscriptions service is internal (cluster-only)
// and requires no authentication.
package subscriptions

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// Client calls the subscriptions service.
type Client struct {
	baseURL    *url.URL
	httpClient *http.Client
}

// New returns a Client for the subscriptions service at the given base URL.
func New(baseURL string) (*Client, error) {
	u, err := url.Parse(baseURL)
	if err != nil {
		return nil, fmt.Errorf("parsing subscriptions URL %q: %w", baseURL, err)
	}
	return &Client{
		baseURL:    u,
		httpClient: &http.Client{Timeout: 30 * time.Second},
	}, nil
}

func (c *Client) url(parts ...string) string {
	return c.baseURL.JoinPath(parts...).String()
}

// SetSubscriptionPlan assigns the named plan to username. The paid parameter
// controls whether the subscription is marked as paid.
func (c *Client) SetSubscriptionPlan(username, plan string, paid bool) error {
	u := c.url("v1", "users", username, plan)
	u += fmt.Sprintf("?paid=%t", paid)
	req, err := http.NewRequest(http.MethodPut, u, nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("subscriptions: assigning plan %q to %s: %w", plan, username, err)
	}
	defer resp.Body.Close() //nolint:errcheck
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("subscriptions: assigning plan %q to %s: %d %s", plan, username, resp.StatusCode, string(body))
	}
	return nil
}
