// Package api implements the portal-conductor HTTP API. Routes, request and
// response bodies, status codes, and error envelopes match the original
// FastAPI service so this can act as a drop-in replacement.
package api

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"

	"github.com/cyverse-de/portal-conductor/config"
	"github.com/cyverse-de/portal-conductor/datastore"
	"github.com/cyverse-de/portal-conductor/emailsvc"
	"github.com/cyverse-de/portal-conductor/external"
	"github.com/cyverse-de/portal-conductor/formation"
	"github.com/cyverse-de/portal-conductor/ldapclient"
	"github.com/cyverse-de/portal-conductor/mailman"
	"github.com/cyverse-de/portal-conductor/terrain"
)

const greetingMessage = "Hello from portal-conductor."

// API holds the service clients and configuration shared by all handlers.
type API struct {
	cfg       *config.Config
	ldap      *ldapclient.Client
	ds        *datastore.DataStore
	terrain   *terrain.Client
	mailman   *mailman.Client
	email     *emailsvc.Service
	formation *formation.Client // nil when the Formation integration is not configured

	// formationAppID caches the user-deletion app ID; it may be resolved
	// lazily when the startup lookup failed.
	appIDMu        sync.Mutex
	formationAppID string
}

// New assembles the API from its dependencies. formationClient may be nil and
// formationAppID may be empty when unresolved at startup.
func New(
	cfg *config.Config,
	ldapClient *ldapclient.Client,
	ds *datastore.DataStore,
	terrainClient *terrain.Client,
	mailmanClient *mailman.Client,
	emailService *emailsvc.Service,
	formationClient *formation.Client,
	formationAppID string,
) *API {
	return &API{
		cfg:            cfg,
		ldap:           ldapClient,
		ds:             ds,
		terrain:        terrainClient,
		mailman:        mailmanClient,
		email:          emailService,
		formation:      formationClient,
		formationAppID: formationAppID,
	}
}

// httpError carries an explicit status code and detail payload, like
// FastAPI's HTTPException.
type httpError struct {
	status int
	detail any
}

func (e *httpError) Error() string {
	return fmt.Sprintf("HTTP %d: %v", e.status, e.detail)
}

func httpErrorf(status int, format string, args ...any) *httpError {
	return &httpError{status: status, detail: fmt.Sprintf(format, args...)}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	data, err := json.Marshal(v)
	if err != nil {
		log.Printf("Failed to encode response: %v", err)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = fmt.Fprint(w, `{"detail":"Internal server error"}`)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	w.Write(data) //nolint:errcheck
}

func writeDetail(w http.ResponseWriter, status int, detail any) {
	writeJSON(w, status, map[string]any{"detail": detail})
}

// validationError mirrors one entry of FastAPI's 422 validation response.
type validationError struct {
	Type string   `json:"type"`
	Loc  []string `json:"loc"`
	Msg  string   `json:"msg"`
}

// decodeBody parses the JSON request body into dst and verifies the required
// top-level keys are present, producing a FastAPI-style 422 otherwise.
func decodeBody(r *http.Request, dst any, required ...string) error {
	body, err := io.ReadAll(http.MaxBytesReader(nil, r.Body, 10<<20))
	if err != nil {
		return &httpError{status: http.StatusUnprocessableEntity, detail: []validationError{
			{Type: "json_invalid", Loc: []string{"body"}, Msg: "Failed to read request body"},
		}}
	}

	var fields map[string]json.RawMessage
	if err := json.Unmarshal(body, &fields); err != nil {
		return &httpError{status: http.StatusUnprocessableEntity, detail: []validationError{
			{Type: "json_invalid", Loc: []string{"body"}, Msg: "JSON decode error"},
		}}
	}
	if err := json.Unmarshal(body, dst); err != nil {
		return &httpError{status: http.StatusUnprocessableEntity, detail: []validationError{
			{Type: "value_error", Loc: []string{"body"}, Msg: err.Error()},
		}}
	}

	var missing []validationError
	for _, field := range required {
		if _, ok := fields[field]; !ok {
			missing = append(missing, validationError{Type: "missing", Loc: []string{"body", field}, Msg: "Field required"})
		}
	}
	if len(missing) > 0 {
		return &httpError{status: http.StatusUnprocessableEntity, detail: missing}
	}
	return nil
}

// handlerFunc is an HTTP handler that reports failures as errors, which
// handle() maps to the FastAPI-compatible error responses.
type handlerFunc func(w http.ResponseWriter, r *http.Request) error

func (a *API) handle(fn handlerFunc) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		err := fn(w, r)
		if err == nil {
			return
		}

		var he *httpError
		if errors.As(err, &he) {
			log.Printf("%s %s -> %v", r.Method, r.URL.Path, he)
			writeDetail(w, he.status, he.detail)
			return
		}

		var se *external.StatusError
		if errors.As(err, &se) {
			log.Printf("External API error: %d - %s", se.StatusCode, se.URL)
			if se.Body != "" {
				log.Printf("Response: %s", se.Body)
			}
			// Pass through 404s, convert everything else to 502 (Bad Gateway).
			if se.StatusCode == http.StatusNotFound {
				writeDetail(w, http.StatusNotFound, "Resource not found in external service")
				return
			}
			writeDetail(w, http.StatusBadGateway, fmt.Sprintf("External service error: %d", se.StatusCode))
			return
		}

		var re *external.RequestError
		if errors.As(err, &re) {
			log.Printf("Request error: %v", re)
			writeDetail(w, http.StatusServiceUnavailable, "Failed to connect to external service")
			return
		}

		log.Printf("Unhandled exception on %s %s: %v", r.Method, r.URL.Path, err)
		writeDetail(w, http.StatusInternalServerError, "Internal server error")
	})
}

// protected wraps fn with HTTP Basic authentication when auth is enabled.
func (a *API) protected(fn handlerFunc) http.Handler {
	return a.handle(func(w http.ResponseWriter, r *http.Request) error {
		if a.cfg.Auth.Enabled {
			username, password, ok := r.BasicAuth()
			if !ok {
				w.Header().Set("WWW-Authenticate", "Basic")
				return &httpError{status: http.StatusUnauthorized, detail: "Not authenticated"}
			}
			if !a.authenticate(username, password) {
				w.Header().Set("WWW-Authenticate", fmt.Sprintf("Basic realm=%q", a.cfg.Auth.Realm))
				return &httpError{status: http.StatusUnauthorized, detail: "Incorrect username or password"}
			}
		}
		return fn(w, r)
	})
}

func (a *API) authenticate(username, password string) bool {
	configuredUser := a.cfg.Auth.Username
	configuredPass := a.cfg.Auth.Password
	if configuredUser == "" || configuredPass == "" {
		return false
	}
	userMatch := subtle.ConstantTimeCompare([]byte(username), []byte(configuredUser)) == 1
	passMatch := subtle.ConstantTimeCompare([]byte(password), []byte(configuredPass)) == 1
	return userMatch && passMatch
}

func greeting(w http.ResponseWriter, _ *http.Request) error {
	writeJSON(w, http.StatusOK, greetingMessage)
	return nil
}

func notFound(w http.ResponseWriter, _ *http.Request) {
	writeDetail(w, http.StatusNotFound, "Not Found")
}

// Handler returns the full API router.
func (a *API) Handler() http.Handler {
	mux := http.NewServeMux()

	// Health check; intentionally unauthenticated for load balancers.
	mux.Handle("GET /{$}", a.handle(greeting))

	// User management
	mux.Handle("POST /users", a.protected(a.addUser))
	mux.Handle("POST /users/{$}", a.protected(a.addUser))
	mux.Handle("POST /users/{username}/validate", a.protected(a.validateCredentials))
	mux.Handle("POST /users/{username}/password", a.protected(a.changePassword))
	mux.Handle("DELETE /users/{username}", a.protected(a.deleteUser))

	// Async operations (Formation)
	mux.Handle("DELETE /async/users/{username}", a.protected(a.deleteUserAsync))
	mux.Handle("GET /async/status/{analysis_id}", a.protected(a.getDeletionStatus))
	mux.Handle("GET /async/analyses", a.protected(a.listAnalyses))
	mux.Handle("GET /async/analyses/{analysis_id}/details", a.protected(a.getAnalysisDetails))

	// LDAP management
	mux.Handle("POST /ldap/users", a.protected(a.createLDAPUser))
	mux.Handle("POST /ldap/users/{username}/groups/{groupname}", a.protected(a.addUserToLDAPGroup))
	mux.Handle("GET /ldap/users/{username}/groups", a.protected(a.getUserLDAPGroups))
	mux.Handle("DELETE /ldap/users/{username}/groups/{groupname}", a.protected(a.removeUserFromLDAPGroup))
	mux.Handle("GET /ldap/users/{username}", a.protected(a.getUserLDAPInfo))
	mux.Handle("GET /ldap/users/{username}/exists", a.protected(a.checkUserExistsInLDAP))
	mux.Handle("GET /ldap/groups", a.protected(a.getLDAPGroups))
	mux.Handle("PUT /ldap/users/{username}/attributes/{attribute}", a.protected(a.modifyUserLDAPAttribute))

	// Email sending
	mux.Handle("POST /emails/send", a.protected(a.sendEmail))

	// Mailing lists
	mux.Handle("GET /mailinglists/{listname}/members", a.protected(a.listMailingListMembers))
	mux.Handle("POST /mailinglists/{listname}/members", a.protected(a.addToMailingList))
	mux.Handle("DELETE /mailinglists/{listname}/members/{email}", a.protected(a.removeFromMailingList))
	mux.Handle("GET /mailinglists/{listname}/members/{email}/exists", a.protected(a.checkEmailInMailingList))

	// DataStore
	mux.Handle("POST /datastore/users", a.protected(a.createDatastoreUser))
	mux.Handle("GET /datastore/users/{username}/exists", a.protected(a.checkUserExistsInDatastore))
	mux.Handle("POST /datastore/users/{username}/services", a.protected(a.registerDatastoreService))

	// Terrain
	mux.Handle("GET /terrain/users/{username}/job-limits", a.protected(a.getJobLimits))
	mux.Handle("POST /terrain/users/{username}/job-limits", a.protected(a.setJobLimits))

	mux.HandleFunc("/", notFound)

	return logRequests(mux)
}

// HealthHandler returns the health-check-only app served on the HTTP port in
// dual-port mode.
func HealthHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, greetingMessage)
	})
	mux.HandleFunc("/", notFound)
	return logRequests(mux)
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

func logRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		log.Printf("%s - \"%s %s\" %d", r.RemoteAddr, r.Method, r.URL.Path, rec.status)
	})
}
