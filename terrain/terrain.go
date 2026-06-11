// Package terrain is a client for the Terrain API's Keycloak token,
// concurrent-job-limit, app-discovery, and analysis endpoints.
package terrain

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"maps"
	"net/http"
	"net/url"
	"strings"
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

// SearchApps searches apps by name and returns the raw AppListing document.
func (c *Client) SearchApps(search string) (map[string]any, error) {
	var result map[string]any
	requestURL := c.apiURL("apps") + "?" + url.Values{"search": {search}}.Encode()
	if err := c.doAuthedJSON(http.MethodGet, requestURL, nil, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// GetAppIDByName looks up an app's UUID by name within a system, preferring
// an exact match and falling back to a case-insensitive one. Returns "" if
// not found.
func (c *Client) GetAppIDByName(systemID, appName string) (string, error) {
	results, err := c.SearchApps(appName)
	if err != nil {
		return "", err
	}
	rawApps, _ := results["apps"].([]any)

	apps := make([]map[string]any, 0, len(rawApps))
	for _, rawApp := range rawApps {
		if app, ok := rawApp.(map[string]any); ok && app["system_id"] == systemID {
			apps = append(apps, app)
		}
	}

	appField := func(app map[string]any, field string) string {
		s, _ := app[field].(string)
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

// GetAppJobView returns the app-launch document, including the parameter
// groups under "groups".
func (c *Client) GetAppJobView(systemID, appID string) (map[string]any, error) {
	var result map[string]any
	if err := c.doAuthedJSON(http.MethodGet, c.apiURL("apps", systemID, appID), nil, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// LaunchAnalysis submits an analysis and returns Terrain's response, which
// identifies the new analysis as "id". Terrain requires name, config, debug,
// notify, and output_dir in the submission; system_id and app_id are
// injected here.
func (c *Client) LaunchAnalysis(systemID, appID string, submission map[string]any) (map[string]any, error) {
	body := make(map[string]any, len(submission)+2)
	maps.Copy(body, submission)
	body["system_id"] = systemID
	body["app_id"] = appID

	payload, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := c.doAuthedJSON(http.MethodPost, c.apiURL("analyses"), payload, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// listAnalysesFiltered lists the service account's analyses filtered by one
// field (e.g. status or id). The filter parameter is a JSON-encoded array of
// {field, value} objects.
func (c *Client) listAnalysesFiltered(field, value string) (map[string]any, error) {
	filter, err := json.Marshal([]map[string]string{{"field": field, "value": value}})
	if err != nil {
		return nil, err
	}
	requestURL := c.apiURL("analyses") + "?" + url.Values{"filter": {string(filter)}}.Encode()
	var result map[string]any
	if err := c.doAuthedJSON(http.MethodGet, requestURL, nil, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// ListAnalyses lists analyses with the given status.
func (c *Client) ListAnalyses(status string) (map[string]any, error) {
	return c.listAnalysesFiltered("status", status)
}

// GetAnalysisByID returns the analysis listing entry for analysisID, or a
// 404 StatusError when no such analysis is visible to the service account.
func (c *Client) GetAnalysisByID(analysisID string) (map[string]any, error) {
	result, err := c.listAnalysesFiltered("id", analysisID)
	if err != nil {
		return nil, err
	}
	analyses, _ := result["analyses"].([]any)
	if len(analyses) == 0 {
		return nil, &external.StatusError{
			StatusCode: http.StatusNotFound,
			URL:        c.apiURL("analyses"),
			Body:       fmt.Sprintf("analysis %s not found", analysisID),
		}
	}
	analysis, ok := analyses[0].(map[string]any)
	if !ok {
		return nil, fmt.Errorf("unexpected analysis listing entry for %s: %v", analysisID, analyses[0])
	}
	return analysis, nil
}
