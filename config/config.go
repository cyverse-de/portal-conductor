// Package config loads the portal-conductor configuration from the same JSON
// file (or environment-variable fallback) used by the original Python service.
package config

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
)

// FlexString unmarshals from either a JSON string or number, since fields like
// irods.port appear as strings in some config files and numbers in others.
type FlexString string

// UnmarshalJSON accepts both `"1247"` and `1247`.
func (s *FlexString) UnmarshalJSON(data []byte) error {
	trimmed := strings.TrimSpace(string(data))
	if len(trimmed) > 0 && trimmed[0] == '"' {
		var str string
		if err := json.Unmarshal(data, &str); err != nil {
			return err
		}
		*s = FlexString(str)
		return nil
	}
	var num json.Number
	if err := json.Unmarshal(data, &num); err != nil {
		return err
	}
	*s = FlexString(num.String())
	return nil
}

// Int converts the value to an int, returning fallback if empty or invalid.
func (s FlexString) Int(fallback int) int {
	if s == "" {
		return fallback
	}
	n, err := strconv.Atoi(string(s))
	if err != nil {
		return fallback
	}
	return n
}

// SSL holds TLS certificate and port configuration for HTTPS mode.
type SSL struct {
	Enabled  bool   `json:"enabled"`
	CertFile string `json:"cert_file"`
	KeyFile  string `json:"key_file"`
	Port     int    `json:"port"`
}

// Server holds HTTP server configuration.
type Server struct {
	HTTPPort int `json:"http_port"`
}

// Auth holds HTTP Basic Auth configuration for the management API.
type Auth struct {
	Enabled  bool   `json:"enabled"`
	Username string `json:"username"`
	Password string `json:"password"`
	Realm    string `json:"realm"`
}

// LDAP holds connection and directory settings for the LDAP server.
type LDAP struct {
	URL            string `json:"url"`
	User           string `json:"user"`
	Password       string `json:"password"`
	BaseDN         string `json:"base_dn"`
	CommunityGroup string `json:"community_group"`
	EveryoneGroup  string `json:"everyone_group"`
}

// IRODS holds connection settings for the iRODS datastore.
type IRODS struct {
	Host            string     `json:"host"`
	Port            FlexString `json:"port"`
	User            string     `json:"user"`
	Password        string     `json:"password"`
	Zone            string     `json:"zone"`
	AdminUser       string     `json:"admin_user"`
	IPCServicesUser string     `json:"ipcservices_user"`
}

// Terrain holds the base URL and service-account credentials for the Terrain API.
type Terrain struct {
	URL      string `json:"url"`
	User     string `json:"user"`
	Password string `json:"password"`
}

// Mailman holds the base URL and admin password for the Mailman 2.1 interface.
type Mailman struct {
	Enabled  bool   `json:"enabled"`
	URL      string `json:"url"`
	Password string `json:"password"`
}

// SMTP holds SMTP server settings for outbound email.
type SMTP struct {
	Host     string     `json:"host"`
	Port     FlexString `json:"port"`
	User     string     `json:"user"`
	Password string     `json:"password"`
	UseTLS   bool       `json:"use_tls"`
	UseSSL   bool       `json:"use_ssl"`
	From     string     `json:"from"`
}

// PortalDB holds connection settings for the portal PostgreSQL database,
// used by the delete-user batch job.
type PortalDB struct {
	Host     string     `json:"host"`
	Port     FlexString `json:"port"`
	Name     string     `json:"name"`
	User     string     `json:"user"`
	Password string     `json:"password"`
	SSLMode  string     `json:"sslmode"`
}

// Keycloak holds client credentials for the Keycloak identity provider.
type Keycloak struct {
	ServerURL    string `json:"server_url"`
	Realm        string `json:"realm"`
	ClientID     string `json:"client_id"`
	ClientSecret string `json:"client_secret"`
}

// Formation holds the URL, Keycloak credentials, and app settings for the Formation service.
type Formation struct {
	BaseURL             string   `json:"base_url"`
	Keycloak            Keycloak `json:"keycloak"`
	UserDeletionAppID   string   `json:"user_deletion_app_id"`
	UserDeletionAppName string   `json:"user_deletion_app_name"`
	SystemID            string   `json:"system_id"`
	VerifySSL           bool     `json:"verify_ssl"`
	Timeout             float64  `json:"timeout"`
}

// Config is the top-level configuration for portal-conductor.
type Config struct {
	SSL       SSL       `json:"ssl"`
	Server    Server    `json:"server"`
	Auth      Auth      `json:"auth"`
	LDAP      LDAP      `json:"ldap"`
	IRODS     IRODS     `json:"irods"`
	Terrain   Terrain   `json:"terrain"`
	Mailman   Mailman   `json:"mailman"`
	SMTP      SMTP      `json:"smtp"`
	Formation Formation `json:"formation"`
	PortalDB  PortalDB  `json:"portal_db"`
}

// defaults returns a Config pre-populated with the same defaults the Python
// service applied via dict.get() fallbacks; JSON unmarshalling overlays the
// file contents on top so absent keys keep their defaults.
func defaults() *Config {
	return &Config{
		SSL:    SSL{Enabled: false, Port: 8443},
		Server: Server{HTTPPort: 8000},
		Auth:   Auth{Enabled: true, Realm: "Portal Conductor API"},
		LDAP:   LDAP{CommunityGroup: "community"},
		IRODS:  IRODS{AdminUser: "rodsadmin", IPCServicesUser: "ipcservices"},
		SMTP:   SMTP{Host: "localhost", Port: "25", From: "noreply@cyverse.org"},
		Formation: Formation{
			UserDeletionAppName: "portal-delete-user",
			SystemID:            "de",
			VerifySSL:           true,
			Timeout:             60.0,
		},
		PortalDB: PortalDB{Port: "5432", SSLMode: "disable"},
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envBool(key string, fallback bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	switch strings.ToLower(v) {
	case "1", "true", "yes":
		return true
	default:
		return false
	}
}

func envInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}

// fromEnv builds a Config from environment variables, mirroring the fallback
// blocks in main.py and start_dual.py.
func fromEnv() *Config {
	c := defaults()
	c.SSL = SSL{
		Enabled:  envBool("SSL_ENABLED", true),
		CertFile: envOr("SSL_CERT_FILE", "/etc/ssl/certs/tls.crt"),
		KeyFile:  envOr("SSL_KEY_FILE", "/etc/ssl/certs/tls.key"),
		Port:     envInt("SSL_PORT", 8443),
	}
	c.Server = Server{HTTPPort: envInt("HTTP_PORT", 8000)}
	c.LDAP = LDAP{
		URL:            os.Getenv("LDAP_URL"),
		User:           os.Getenv("LDAP_USER"),
		Password:       os.Getenv("LDAP_PASSWORD"),
		BaseDN:         os.Getenv("LDAP_BASE_DN"),
		CommunityGroup: envOr("LDAP_COMMUNITY_GROUP", "community"),
		EveryoneGroup:  os.Getenv("LDAP_EVERYONE_GROUP"),
	}
	c.IRODS = IRODS{
		Host:            os.Getenv("IRODS_HOST"),
		Port:            FlexString(os.Getenv("IRODS_PORT")),
		User:            os.Getenv("IRODS_USER"),
		Password:        os.Getenv("IRODS_PASSWORD"),
		Zone:            os.Getenv("IRODS_ZONE"),
		AdminUser:       envOr("DS_ADMIN_USER", "rodsadmin"),
		IPCServicesUser: envOr("IPCSERVICES_USER", "ipcservices"),
	}
	c.Terrain = Terrain{
		URL:      envOr("TERRAIN_URL", "http://terrain/"),
		User:     os.Getenv("TERRAIN_USER"),
		Password: os.Getenv("TERRAIN_PASSWORD"),
	}
	c.Mailman = Mailman{
		Enabled:  envBool("MAILMAN_ENABLED", false),
		URL:      os.Getenv("MAILMAN_URL"),
		Password: os.Getenv("MAILMAN_PASSWORD"),
	}
	c.PortalDB = PortalDB{
		Host:     os.Getenv("PORTAL_DB_HOST"),
		Port:     FlexString(envOr("PORTAL_DB_PORT", "5432")),
		Name:     os.Getenv("PORTAL_DB_NAME"),
		User:     os.Getenv("PORTAL_DB_USER"),
		Password: os.Getenv("PORTAL_DB_PASSWORD"),
		SSLMode:  envOr("PORTAL_DB_SSLMODE", "disable"),
	}
	c.Formation = Formation{
		BaseURL: os.Getenv("FORMATION_URL"),
		Keycloak: Keycloak{
			ServerURL:    os.Getenv("KEYCLOAK_SERVER_URL"),
			Realm:        os.Getenv("KEYCLOAK_REALM"),
			ClientID:     os.Getenv("KEYCLOAK_CLIENT_ID"),
			ClientSecret: os.Getenv("KEYCLOAK_CLIENT_SECRET"),
		},
		UserDeletionAppID:   os.Getenv("FORMATION_USER_DELETION_APP_ID"),
		UserDeletionAppName: envOr("FORMATION_USER_DELETION_APP_NAME", "portal-delete-user"),
		SystemID:            envOr("FORMATION_SYSTEM_ID", "de"),
		VerifySSL:           envBool("FORMATION_VERIFY_SSL", true),
		Timeout:             60.0,
	}
	return c
}

// Load reads the config file named by PORTAL_CONDUCTOR_CONFIG (default
// config.json), falling back to environment variables when the file is
// missing or unparseable — the same behavior as the Python service.
func Load() *Config {
	return LoadFrom(envOr("PORTAL_CONDUCTOR_CONFIG", "config.json"))
}

// LoadFrom reads the named config file, falling back to environment
// variables when the file is missing or unparseable.
func LoadFrom(configFile string) *Config {
	data, err := os.ReadFile(configFile)
	if err == nil {
		c := defaults()
		if jsonErr := json.Unmarshal(data, c); jsonErr == nil {
			log.Printf("Loaded configuration from %s", configFile)
			return c
		} else {
			log.Printf("Failed to load config from %s: %v", configFile, jsonErr)
			log.Printf("Falling back to environment variables")
		}
	}
	return fromEnv()
}

// Validate checks required fields and returns an error naming the first
// missing one, matching the messages from validate_config in main.py.
func (c *Config) Validate() error {
	required := []struct {
		name  string
		value string
	}{
		{"ldap.url", c.LDAP.URL},
		{"ldap.user", c.LDAP.User},
		{"ldap.password", c.LDAP.Password},
		{"ldap.base_dn", c.LDAP.BaseDN},
		{"ldap.everyone_group", c.LDAP.EveryoneGroup},
		{"irods.host", c.IRODS.Host},
		{"irods.port", string(c.IRODS.Port)},
		{"irods.user", c.IRODS.User},
		{"irods.password", c.IRODS.Password},
		{"irods.zone", c.IRODS.Zone},
		{"terrain.user", c.Terrain.User},
		{"terrain.password", c.Terrain.Password},
	}
	if c.Mailman.Enabled {
		required = append(required,
			struct{ name, value string }{"mailman.url", c.Mailman.URL},
			struct{ name, value string }{"mailman.password", c.Mailman.Password},
		)
	}
	for _, f := range required {
		if f.value == "" {
			return fmt.Errorf("required configuration field '%s' is not set", f.name)
		}
	}
	return nil
}

// FormationConfigured reports whether all settings needed for the Formation
// integration are present.
func (c *Config) FormationConfigured() bool {
	f := c.Formation
	return f.BaseURL != "" && f.Keycloak.ServerURL != "" && f.Keycloak.Realm != "" &&
		f.Keycloak.ClientID != "" && f.Keycloak.ClientSecret != ""
}
