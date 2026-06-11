package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeConfig(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "config.json")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoadFromFile(t *testing.T) {
	path := writeConfig(t, `{
		"auth": {"username": "admin", "password": "secret"},
		"ldap": {"url": "ldap://x", "user": "u", "password": "p", "base_dn": "dc=x", "everyone_group": "everyone"},
		"irods": {"host": "h", "port": 1247, "user": "u", "password": "p", "zone": "z"},
		"terrain": {"url": "http://t/", "user": "tu", "password": "tp"},
		"smtp": {"port": "587"}
	}`)
	t.Setenv("PORTAL_CONDUCTOR_CONFIG", path)

	cfg := Load()

	tests := []struct {
		name string
		got  any
		want any
	}{
		{"auth enabled defaults true", cfg.Auth.Enabled, true},
		{"auth realm default", cfg.Auth.Realm, "Portal Conductor API"},
		{"auth username from file", cfg.Auth.Username, "admin"},
		{"ldap community group default", cfg.LDAP.CommunityGroup, "community"},
		{"irods numeric port", cfg.IRODS.Port.Int(0), 1247},
		{"irods admin user default", cfg.IRODS.AdminUser, "rodsadmin"},
		{"irods ipcservices default", cfg.IRODS.IPCServicesUser, "ipcservices"},
		{"smtp string port", cfg.SMTP.Port.Int(0), 587},
		{"smtp from default", cfg.SMTP.From, "noreply@cyverse.org"},
		{"ssl disabled by default", cfg.SSL.Enabled, false},
		{"ssl port default", cfg.SSL.Port, 8443},
		{"http port default", cfg.Server.HTTPPort, 8000},
		{"terrain deletion app name default", cfg.Terrain.UserDeletionAppName, "portal-delete-user"},
		{"terrain system id default", cfg.Terrain.SystemID, "de"},
		{"mailman disabled by default", cfg.Mailman.Enabled, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.want {
				t.Errorf("got %v, want %v", tt.got, tt.want)
			}
		})
	}
}

func TestLoadEnvFallback(t *testing.T) {
	t.Setenv("PORTAL_CONDUCTOR_CONFIG", filepath.Join(t.TempDir(), "missing.json"))
	t.Setenv("LDAP_URL", "ldap://env")
	t.Setenv("LDAP_EVERYONE_GROUP", "everyone")
	t.Setenv("MAILMAN_ENABLED", "TRUE")
	t.Setenv("SSL_ENABLED", "no")
	t.Setenv("HTTP_PORT", "9000")
	t.Setenv("TERRAIN_USER_DELETION_APP_NAME", "")

	cfg := Load()

	tests := []struct {
		name string
		got  any
		want any
	}{
		{"ldap url from env", cfg.LDAP.URL, "ldap://env"},
		{"everyone group from env", cfg.LDAP.EveryoneGroup, "everyone"},
		{"mailman enabled case-insensitive", cfg.Mailman.Enabled, true},
		{"ssl disabled via env", cfg.SSL.Enabled, false},
		{"http port from env", cfg.Server.HTTPPort, 9000},
		{"terrain url default", cfg.Terrain.URL, "http://terrain/"},
		{"blanked deletion app name sticks", cfg.Terrain.UserDeletionAppName, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.want {
				t.Errorf("got %v, want %v", tt.got, tt.want)
			}
		})
	}
}

func validConfig() *Config {
	c := defaults()
	c.Auth.Username = "admin"
	c.Auth.Password = "secret"
	c.LDAP = LDAP{URL: "ldap://x", User: "u", Password: "p", BaseDN: "dc=x", CommunityGroup: "community", EveryoneGroup: "everyone"}
	c.IRODS = IRODS{Host: "h", Port: "1247", User: "u", Password: "p", Zone: "z", AdminUser: "rodsadmin", IPCServicesUser: "ipcservices"}
	c.Terrain.URL = "http://t/"
	c.Terrain.User = "tu"
	c.Terrain.Password = "tp"
	return c
}

func TestValidate(t *testing.T) {
	tests := []struct {
		name      string
		mutate    func(*Config)
		wantField string
	}{
		{"valid config", func(c *Config) {}, ""},
		{"missing ldap url", func(c *Config) { c.LDAP.URL = "" }, "ldap.url"},
		{"missing everyone group", func(c *Config) { c.LDAP.EveryoneGroup = "" }, "ldap.everyone_group"},
		{"missing irods zone", func(c *Config) { c.IRODS.Zone = "" }, "irods.zone"},
		{"missing terrain password", func(c *Config) { c.Terrain.Password = "" }, "terrain.password"},
		{"mailman enabled without url", func(c *Config) { c.Mailman.Enabled = true }, "mailman.url"},
		{
			"mailman enabled with url but no password",
			func(c *Config) { c.Mailman.Enabled = true; c.Mailman.URL = "http://m/" },
			"mailman.password",
		},
		{"auth enabled without username", func(c *Config) { c.Auth.Username = "" }, "auth.username"},
		{"auth enabled without password", func(c *Config) { c.Auth.Password = "" }, "auth.password"},
		{"auth disabled needs no credentials", func(c *Config) { c.Auth = Auth{} }, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := validConfig()
			tt.mutate(cfg)
			err := cfg.Validate()
			if tt.wantField == "" {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				return
			}
			if err == nil {
				t.Fatalf("expected error mentioning %q, got nil", tt.wantField)
			}
			if !strings.Contains(err.Error(), tt.wantField) {
				t.Errorf("error %q does not mention field %q", err, tt.wantField)
			}
		})
	}
}

func TestTerrainAsyncConfigured(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*Config)
		want   bool
	}{
		{"configured with app name", func(c *Config) {}, true},
		{"configured with app id only", func(c *Config) {
			c.Terrain.UserDeletionAppName = ""
			c.Terrain.UserDeletionAppID = "app-123"
		}, true},
		{"missing terrain url", func(c *Config) { c.Terrain.URL = "" }, false},
		{"missing terrain password", func(c *Config) { c.Terrain.Password = "" }, false},
		{"both app id and name blank", func(c *Config) {
			c.Terrain.UserDeletionAppID = ""
			c.Terrain.UserDeletionAppName = ""
		}, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := validConfig()
			tt.mutate(cfg)
			if got := cfg.TerrainAsyncConfigured(); got != tt.want {
				t.Errorf("got %v, want %v", got, tt.want)
			}
		})
	}
}

func TestFlexString(t *testing.T) {
	tests := []struct {
		name     string
		json     string
		fallback int
		want     int
	}{
		{"quoted number", `{"port": "1247"}`, 0, 1247},
		{"bare number", `{"port": 1247}`, 0, 1247},
		{"missing uses fallback", `{}`, 25, 25},
		{"garbage uses fallback", `{"port": "abc"}`, 25, 25},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var s struct {
				Port FlexString `json:"port"`
			}
			if err := json.Unmarshal([]byte(tt.json), &s); err != nil {
				t.Fatal(err)
			}
			if got := s.Port.Int(tt.fallback); got != tt.want {
				t.Errorf("got %d, want %d", got, tt.want)
			}
		})
	}
}
