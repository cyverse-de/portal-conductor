// Package external defines error types for failures reaching external HTTP
// services (Terrain, Mailman, Formation, Keycloak). The API layer maps them
// to the same responses the Python service produced for httpx errors:
// StatusError -> 404/502, RequestError -> 503.
package external

import (
	"errors"
	"fmt"
	"io"
	"net/http"
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
