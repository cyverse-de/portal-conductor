// Package formation ports formation.py to Go: a client for the Formation
// batch-job service with automatic OAuth2 client-credentials token refresh
// against Keycloak.
package formation

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/cyverse-de/portal-conductor/external"
)

// refreshBuffer is how long before expiry the token is refreshed.
const refreshBuffer = 60 * time.Second

// Client calls the Formation API, refreshing its Keycloak token as needed.
type Client struct {
	baseURL      *url.URL
	keycloakURL  string
	realm        string
	clientID     string
	clientSecret string

	httpClient  *http.Client
	tokenClient *http.Client

	mu          sync.Mutex
	token       string
	tokenExpiry time.Time
}

// New returns a Client for the Formation API. verifySSL=false disables TLS
// certificate verification for development with self-signed certificates.
func New(apiURL, keycloakURL, realm, clientID, clientSecret string, verifySSL bool, timeout time.Duration) (*Client, error) {
	base, err := url.Parse(apiURL)
	if err != nil {
		return nil, fmt.Errorf("parsing formation URL %q: %w", apiURL, err)
	}

	var transport http.RoundTripper
	if !verifySSL {
		transport = &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}
	}
	return &Client{
		baseURL:      base,
		keycloakURL:  strings.TrimRight(keycloakURL, "/"),
		realm:        realm,
		clientID:     clientID,
		clientSecret: clientSecret,
		httpClient:   &http.Client{Timeout: timeout, Transport: transport},
		tokenClient:  &http.Client{Timeout: 10 * time.Second, Transport: transport},
	}, nil
}

func (c *Client) tokenEndpoint() string {
	return fmt.Sprintf("%s/realms/%s/protocol/openid-connect/token", c.keycloakURL, c.realm)
}

func (c *Client) refreshToken() error {
	form := url.Values{
		"grant_type":    {"client_credentials"},
		"client_id":     {c.clientID},
		"client_secret": {c.clientSecret},
	}
	resp, err := c.tokenClient.PostForm(c.tokenEndpoint(), form)
	if err != nil {
		return &external.RequestError{URL: c.tokenEndpoint(), Err: err}
	}
	defer resp.Body.Close() //nolint:errcheck
	if err := external.CheckResponse(resp); err != nil {
		return err
	}

	var tokenData struct {
		AccessToken string  `json:"access_token"`
		ExpiresIn   float64 `json:"expires_in"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&tokenData); err != nil {
		return fmt.Errorf("decoding Keycloak token response: %w", err)
	}

	c.token = tokenData.AccessToken
	c.tokenExpiry = external.TokenExpiry(c.token)
	if c.tokenExpiry.IsZero() {
		log.Printf("[Formation] Failed to decode JWT expiry; the token will be refreshed on every request")
	}
	log.Printf("[Formation] Token refreshed, expires in %.0fs", tokenData.ExpiresIn)
	return nil
}

func (c *Client) accessToken(forceRefresh bool) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if forceRefresh || c.token == "" || time.Now().After(c.tokenExpiry.Add(-refreshBuffer)) {
		if err := c.refreshToken(); err != nil {
			return "", err
		}
	}
	return c.token, nil
}

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

func (c *Client) doJSON(method, requestURL string, query url.Values, body any, out any) error {
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			return err
		}
	}
	if len(query) > 0 {
		requestURL += "?" + query.Encode()
	}

	resp, err := c.attempt(method, requestURL, payload, false)
	if err != nil {
		return err
	}

	// A 401/403 can mean the cached token predates a role or permission
	// change in Keycloak; retry once with a freshly minted token.
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		resp.Body.Close() //nolint:errcheck
		log.Printf("[Formation] %d from %s; retrying once with a fresh token in case the cached one predates a Keycloak permission change", resp.StatusCode, requestURL)
		resp, err = c.attempt(method, requestURL, payload, true)
		if err != nil {
			return err
		}
	}

	defer resp.Body.Close() //nolint:errcheck
	if err := external.CheckResponse(resp); err != nil {
		return err
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

// SearchApps searches Formation apps by name and filters the results to
// the given system ID client-side.
func (c *Client) SearchApps(systemID, search string) (map[string]any, error) {
	var result map[string]any
	err := c.doJSON(http.MethodGet, c.baseURL.JoinPath("apps").String(), url.Values{"name": {search}}, nil, &result)
	if err != nil {
		return nil, err
	}

	if rawApps, ok := result["apps"].([]any); ok {
		filtered := make([]any, 0, len(rawApps))
		for _, rawApp := range rawApps {
			if app, ok := rawApp.(map[string]any); ok && app["system_id"] == systemID {
				filtered = append(filtered, rawApp)
			}
		}
		result["apps"] = filtered
		result["total"] = len(filtered)
	}
	return result, nil
}

// GetAppIDByName looks up an app's UUID by name, preferring an exact match
// and falling back to a case-insensitive one. Returns "" if not found.
func (c *Client) GetAppIDByName(systemID, appName string) (string, error) {
	results, err := c.SearchApps(systemID, appName)
	if err != nil {
		return "", err
	}
	apps, _ := results["apps"].([]any)

	appField := func(app any, field string) string {
		m, ok := app.(map[string]any)
		if !ok {
			return ""
		}
		s, _ := m[field].(string)
		return s
	}

	for _, app := range apps {
		if appField(app, "name") == appName {
			return appField(app, "id"), nil
		}
	}
	for _, app := range apps {
		if strings.EqualFold(appField(app, "name"), appName) {
			return appField(app, "id"), nil
		}
	}
	return "", nil
}

// GetAppParameters returns the app's parameter-group configuration.
func (c *Client) GetAppParameters(systemID, appID string) (map[string]any, error) {
	var result map[string]any
	err := c.doJSON(http.MethodGet, c.baseURL.JoinPath("apps", systemID, appID, "parameters").String(), nil, nil, &result)
	return result, err
}

// LaunchAnalysis submits a batch job and returns Formation's response.
func (c *Client) LaunchAnalysis(systemID, appID string, submission map[string]any) (map[string]any, error) {
	var result map[string]any
	err := c.doJSON(http.MethodPost, c.baseURL.JoinPath("app", "launch", systemID, appID).String(), nil, submission, &result)
	return result, err
}

// GetAnalysisStatus returns the current status document for an analysis.
func (c *Client) GetAnalysisStatus(analysisID string) (map[string]any, error) {
	var result map[string]any
	err := c.doJSON(http.MethodGet, c.baseURL.JoinPath("apps", "analyses", analysisID, "status").String(), nil, nil, &result)
	return result, err
}

// ListAnalyses lists analyses filtered by status.
func (c *Client) ListAnalyses(status string) (map[string]any, error) {
	var result map[string]any
	err := c.doJSON(http.MethodGet, c.baseURL.JoinPath("apps", "analyses").String()+"/", url.Values{"status": {status}}, nil, &result)
	return result, err
}

// GetAnalysisDetails returns the full analysis document, passed through
// verbatim to the API response.
func (c *Client) GetAnalysisDetails(analysisID string) (map[string]any, error) {
	var result map[string]any
	err := c.doJSON(http.MethodGet, c.baseURL.JoinPath("apps", "analyses", analysisID, "details").String(), nil, nil, &result)
	return result, err
}
