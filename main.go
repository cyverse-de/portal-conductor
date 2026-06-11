// Command portal-conductor serves the CyVerse portal management API. It is a
// Go rewrite of the original Python/FastAPI service with the same HTTP+JSON
// contract and configuration file.
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/sirupsen/logrus"

	"github.com/cyverse-de/portal-conductor/api"
	"github.com/cyverse-de/portal-conductor/config"
	"github.com/cyverse-de/portal-conductor/datastore"
	"github.com/cyverse-de/portal-conductor/emailsvc"
	"github.com/cyverse-de/portal-conductor/ldapclient"
	"github.com/cyverse-de/portal-conductor/mailman"
	"github.com/cyverse-de/portal-conductor/terrain"

	_ "github.com/cyverse-de/portal-conductor/docs"
)

// @title           Portal Conductor API
// @version         1.0
// @description     API for managing CyVerse users, LDAP, DataStore, and email notifications.
// @BasePath        /
// @securityDefinitions.basic BasicAuth
func main() {
	// go-irodsclient logs connection-pool details at info level through
	// logrus; only surface its warnings and errors.
	logrus.SetLevel(logrus.WarnLevel)

	httpPortFlag := flag.Int("http-port", 0, "HTTP port to listen on (overrides config file and environment variables)")
	httpsPortFlag := flag.Int("https-port", 0, "HTTPS port to listen on when SSL is enabled (overrides config file)")
	flag.Parse()

	cfg := config.Load()
	if err := cfg.Validate(); err != nil {
		msg := err.Error()
		log.Printf("%s", strings.ToUpper(msg[:1])+msg[1:])
		os.Exit(1)
	}
	if !cfg.Mailman.Enabled {
		fmt.Println("MAILMAN_ENABLED is not set to true, mailman integration disabled")
	}

	handler := buildAPI(cfg)

	httpPort := cfg.Server.HTTPPort
	if *httpPortFlag != 0 {
		httpPort = *httpPortFlag
	}
	sslPort := cfg.SSL.Port
	if *httpsPortFlag != 0 {
		sslPort = *httpsPortFlag
	}

	serve(cfg, handler, httpPort, sslPort)
}

func buildAPI(cfg *config.Config) http.Handler {
	ldapClient, err := ldapclient.New(cfg.LDAP.URL, cfg.LDAP.User, cfg.LDAP.Password, cfg.LDAP.BaseDN)
	if err != nil {
		log.Fatalf("Failed to connect to LDAP: %v", err)
	}

	ds := datastore.New(cfg.IRODS.Host, cfg.IRODS.Port.Int(1247), cfg.IRODS.User, cfg.IRODS.Password, cfg.IRODS.Zone)

	terrainClient, err := terrain.New(cfg.Terrain.URL, cfg.Terrain.User, cfg.Terrain.Password)
	if err != nil {
		log.Fatalf("Failed to configure Terrain client: %v", err)
	}

	mailmanClient, err := mailman.New(cfg.Mailman.URL, cfg.Mailman.Password)
	if err != nil {
		log.Fatalf("Failed to configure Mailman client: %v", err)
	}

	emailService := emailsvc.New(cfg.SMTP)

	// The user-deletion app ID is resolved by name lazily on first async use,
	// so an unreachable Terrain can't block startup and delay health checks.
	if cfg.TerrainAsyncConfigured() && cfg.Terrain.UserDeletionAppID == "" {
		log.Printf("User-deletion app ID not set; it will be resolved from name '%s' on first async use", cfg.Terrain.UserDeletionAppName)
	}

	a := api.New(cfg, ldapClient, ds, terrainClient, mailmanClient, emailService, cfg.Terrain.UserDeletionAppID)
	return a.Handler()
}

func newServer(addr string, handler http.Handler) *http.Server {
	return &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 30 * time.Second,
	}
}

// serve mirrors start_dual.py: HTTPS (full API) plus HTTP (health checks
// only) when SSL is enabled and certificates exist, otherwise HTTP only.
func serve(cfg *config.Config, handler http.Handler, httpPort, sslPort int) {
	sslReady := cfg.SSL.Enabled && fileExists(cfg.SSL.CertFile) && fileExists(cfg.SSL.KeyFile)

	switch {
	case sslReady:
		log.Printf("Starting Portal Conductor in dual-port mode:")
		log.Printf("  HTTPS (full API): port %d", sslPort)
		log.Printf("  HTTP (health only): port %d", httpPort)
		log.Printf("  SSL Certificate: %s", cfg.SSL.CertFile)
		log.Printf("  SSL Key: %s", cfg.SSL.KeyFile)

		go func() {
			log.Printf("Health check server started on HTTP port %d", httpPort)
			healthServer := newServer(fmt.Sprintf(":%d", httpPort), api.HealthHandler())
			log.Fatal(healthServer.ListenAndServe())
		}()

		log.Printf("Starting full API server on HTTPS port %d", sslPort)
		apiServer := newServer(fmt.Sprintf(":%d", sslPort), handler)
		log.Fatal(apiServer.ListenAndServeTLS(cfg.SSL.CertFile, cfg.SSL.KeyFile))

	case cfg.SSL.Enabled:
		log.Printf("SSL enabled but certificate files not found or not accessible:")
		log.Printf("  Certificate: %s (exists: %t)", cfg.SSL.CertFile, fileExists(cfg.SSL.CertFile))
		log.Printf("  Key: %s (exists: %t)", cfg.SSL.KeyFile, fileExists(cfg.SSL.KeyFile))
		log.Printf("Falling back to HTTP mode (full API)")
		log.Fatal(newServer(fmt.Sprintf(":%d", httpPort), handler).ListenAndServe())

	default:
		log.Printf("Starting Portal Conductor with HTTP on port %d (full API)", httpPort)
		log.Fatal(newServer(fmt.Sprintf(":%d", httpPort), handler).ListenAndServe())
	}
}

func fileExists(path string) bool {
	if path == "" {
		return false
	}
	_, err := os.Stat(path)
	return err == nil
}
