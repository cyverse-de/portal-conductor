// Package external holds error types and shared helpers for talking to
// external HTTP services (Terrain, Mailman, Keycloak). The API
// layer maps the error types to the same responses the Python service
// produced for httpx errors: StatusError -> 404/502, RequestError -> 503.
package external

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// StatusError is returned when an external service responds with an HTTP
// error status (the equivalent of httpx.HTTPStatusError).
type StatusError struct {
	StatusCode int
	URL        string
	Body       string
}

func (e *StatusError) Error() string {
	return fmt.Sprintf("external API error: %d - %s", e.StatusCode, e.URL)
}

// RequestError is returned when an external service cannot be reached (the
// equivalent of httpx.RequestError).
type RequestError struct {
	URL string
	Err error
}

func (e *RequestError) Error() string {
	return fmt.Sprintf("request error for %s: %v", e.URL, e.Err)
}

func (e *RequestError) Unwrap() error { return e.Err }

// CheckResponse converts a non-2xx response into a StatusError, consuming the
// body for diagnostics. It returns nil for successful responses.
func CheckResponse(resp *http.Response) error {
	if resp.StatusCode < 400 {
		return nil
	}
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	return &StatusError{StatusCode: resp.StatusCode, URL: resp.Request.URL.String(), Body: string(body)}
}

// StatusCodeOf returns the HTTP status of err if it is a StatusError, or 0.
func StatusCodeOf(err error) int {
	var se *StatusError
	if errors.As(err, &se) {
		return se.StatusCode
	}
	return 0
}

// TokenExpiry extracts the exp claim from a JWT without verifying the
// signature. It returns the zero time when the token can't be decoded, which
// callers should treat as already expired so a fresh token gets fetched.
func TokenExpiry(token string) time.Time {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return time.Time{}
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return time.Time{}
	}
	var claims struct {
		Exp int64 `json:"exp"`
	}
	if err := json.Unmarshal(payload, &claims); err != nil {
		return time.Time{}
	}
	return time.Unix(claims.Exp, 0)
}
