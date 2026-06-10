package main

import (
	"testing"

	"github.com/cyverse-de/portal-conductor/config"
)

func TestParseArgs(t *testing.T) {
	tests := []struct {
		name    string
		argv    []string
		want    cliArgs
		wantErr bool
	}{
		{
			"username only",
			[]string{"jdoe"},
			cliArgs{username: "jdoe", configPath: "config.json"},
			false,
		},
		{
			"flags after username",
			[]string{"jdoe", "--dry-run", "--config", "/etc/cfg.json"},
			cliArgs{username: "jdoe", configPath: "/etc/cfg.json", dryRun: true},
			false,
		},
		{
			"flags before username",
			[]string{"--dry-run", "--config=/etc/cfg.json", "jdoe"},
			cliArgs{username: "jdoe", configPath: "/etc/cfg.json", dryRun: true},
			false,
		},
		{
			"help without username",
			[]string{"--help"},
			cliArgs{help: true, configPath: "config.json"},
			false,
		},
		{"missing username", []string{"--dry-run"}, cliArgs{}, true},
		{"unknown flag", []string{"jdoe", "--frobnicate"}, cliArgs{}, true},
		{"two usernames", []string{"jdoe", "other"}, cliArgs{}, true},
		{"config without value", []string{"jdoe", "--config"}, cliArgs{}, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := parseArgs(tt.argv)
			if tt.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if got != tt.want {
				t.Errorf("got %+v, want %+v", got, tt.want)
			}
		})
	}
}

func TestValidateConfig(t *testing.T) {
	valid := func() *config.Config {
		cfg := &config.Config{}
		cfg.LDAP = config.LDAP{URL: "ldap://x", User: "u", Password: "p", BaseDN: "dc=x"}
		cfg.IRODS = config.IRODS{Host: "h", Port: "1247", User: "u", Password: "p", Zone: "z"}
		cfg.PortalDB = config.PortalDB{Host: "db", Port: "5432", Name: "portal", User: "u", Password: "p"}
		return cfg
	}

	tests := []struct {
		name    string
		mutate  func(*config.Config)
		wantErr bool
	}{
		{"valid", func(c *config.Config) {}, false},
		{"missing portal db name", func(c *config.Config) { c.PortalDB.Name = "" }, true},
		{"missing ldap base dn", func(c *config.Config) { c.LDAP.BaseDN = "" }, true},
		{"missing irods zone", func(c *config.Config) { c.IRODS.Zone = "" }, true},
		{"mailman not required", func(c *config.Config) { c.Mailman = config.Mailman{} }, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := valid()
			tt.mutate(cfg)
			err := validateConfig(cfg)
			if (err != nil) != tt.wantErr {
				t.Errorf("got err=%v, wantErr=%v", err, tt.wantErr)
			}
		})
	}
}
