// Command delete-user removes a user account from all CyVerse systems:
// mailing lists, the iRODS datastore, LDAP, and the portal database. It is a
// Go port of scripts/delete-user.py and runs as a Formation batch job.
//
// Usage: delete-user username [--config path/to/config.json] [--dry-run]
//
// Exit codes: 0 success, 1 configuration error, 3 deletion error.
package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"os"
	"strings"

	"github.com/cyverse-de/portal-conductor/config"
	"github.com/cyverse-de/portal-conductor/datastore"
	"github.com/cyverse-de/portal-conductor/ldapclient"
	"github.com/cyverse-de/portal-conductor/mailman"
	"github.com/cyverse-de/portal-conductor/portaldb"
)

const (
	exitSuccess       = 0
	exitConfigError   = 1
	exitDeletionError = 3
)

const sectionDivider = "============================================================"

const usage = `usage: delete-user [-h] [--config CONFIG] [--dry-run] username

Delete a user from LDAP, iRODS datastore, mailing lists, and portal database

positional arguments:
  username         Username to delete

options:
  -h, --help       show this help message and exit
  --config CONFIG  Path to config file (default: PORTAL_CONDUCTOR_CONFIG env var or config.json)
  --dry-run        Show what would be deleted without actually deleting

Example: delete-user testuser --dry-run`

// cliArgs holds the parsed command line.
type cliArgs struct {
	username   string
	configPath string
	dryRun     bool
	help       bool
}

// parseArgs accepts flags before or after the username, like Python's
// argparse, so existing Formation app invocations keep working.
func parseArgs(argv []string) (cliArgs, error) {
	args := cliArgs{
		configPath: envOr("PORTAL_CONDUCTOR_CONFIG", "config.json"),
	}
	for i := 0; i < len(argv); i++ {
		arg := argv[i]
		switch {
		case arg == "-h" || arg == "--help":
			args.help = true
		case arg == "--dry-run":
			args.dryRun = true
		case arg == "--config":
			if i+1 >= len(argv) {
				return args, fmt.Errorf("argument --config: expected one argument")
			}
			i++
			args.configPath = argv[i]
		case strings.HasPrefix(arg, "--config="):
			args.configPath = strings.TrimPrefix(arg, "--config=")
		case strings.HasPrefix(arg, "-"):
			return args, fmt.Errorf("unrecognized arguments: %s", arg)
		case args.username != "":
			return args, fmt.Errorf("unrecognized arguments: %s", arg)
		default:
			args.username = arg
		}
	}
	if !args.help && args.username == "" {
		return args, fmt.Errorf("the following arguments are required: username")
	}
	return args, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// validateConfig checks the fields the deletion job needs, matching
// delete-user.py's validate_config.
func validateConfig(cfg *config.Config) error {
	required := []struct {
		name  string
		value string
	}{
		{"ldap.url", cfg.LDAP.URL},
		{"ldap.user", cfg.LDAP.User},
		{"ldap.password", cfg.LDAP.Password},
		{"ldap.base_dn", cfg.LDAP.BaseDN},
		{"irods.host", cfg.IRODS.Host},
		{"irods.port", string(cfg.IRODS.Port)},
		{"irods.user", cfg.IRODS.User},
		{"irods.password", cfg.IRODS.Password},
		{"irods.zone", cfg.IRODS.Zone},
		{"portal_db.host", cfg.PortalDB.Host},
		{"portal_db.port", string(cfg.PortalDB.Port)},
		{"portal_db.name", cfg.PortalDB.Name},
		{"portal_db.user", cfg.PortalDB.User},
		{"portal_db.password", cfg.PortalDB.Password},
	}
	var missing []string
	for _, f := range required {
		if f.value == "" {
			missing = append(missing, f.name)
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("missing required configuration fields: %s", strings.Join(missing, ", "))
	}
	return nil
}

func main() {
	args, err := parseArgs(os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, usage)
		fmt.Fprintf(os.Stderr, "delete-user: error: %v\n", err)
		os.Exit(exitConfigError)
	}
	if args.help {
		fmt.Println(usage)
		os.Exit(exitSuccess)
	}

	cfg := config.LoadFrom(args.configPath)
	if err := validateConfig(cfg); err != nil {
		log.Printf("Configuration error: %v", err)
		log.Printf("Make sure you have a valid config.json or set environment variables:")
		log.Printf("  LDAP_URL, LDAP_USER, LDAP_PASSWORD, LDAP_BASE_DN")
		log.Printf("  IRODS_HOST, IRODS_PORT, IRODS_USER, IRODS_PASSWORD, IRODS_ZONE")
		log.Printf("  PORTAL_DB_HOST, PORTAL_DB_PORT, PORTAL_DB_NAME, PORTAL_DB_USER, PORTAL_DB_PASSWORD")
		log.Printf("  MAILMAN_ENABLED, MAILMAN_URL, MAILMAN_PASSWORD (optional)")
		os.Exit(exitConfigError)
	}

	ctx := context.Background()
	deleter, db, err := initConnections(ctx, cfg)
	if err != nil {
		log.Printf("Failed to initialize connections: %v", err)
		os.Exit(exitConfigError)
	}
	defer db.Close() //nolint:errcheck

	if deleteUser(ctx, deleter, db, args.username, args.dryRun) {
		if args.dryRun {
			log.Printf("Dry run completed for user: %s", args.username)
			log.Printf("No changes were made. Run without --dry-run to perform actual deletion.")
		} else {
			fmt.Printf("Successfully deleted user: %s\n", args.username)
		}
		os.Exit(exitSuccess)
	}
	log.Printf("Failed to delete user: %s", args.username)
	os.Exit(exitDeletionError)
}

// deleter bundles the per-system clients used by the deletion phases.
type deleter struct {
	ldap    *ldapclient.Client
	ds      *datastore.DataStore
	mailman *mailman.Client // nil when the Mailman integration is disabled
}

func initConnections(ctx context.Context, cfg *config.Config) (*deleter, *sql.DB, error) {
	log.Printf("Initializing connections...")

	ldapClient, err := ldapclient.New(cfg.LDAP.URL, cfg.LDAP.User, cfg.LDAP.Password, cfg.LDAP.BaseDN)
	if err != nil {
		return nil, nil, err
	}
	log.Printf("Connected to LDAP: %s", cfg.LDAP.URL)

	ds := datastore.New(cfg.IRODS.Host, cfg.IRODS.Port.Int(1247), cfg.IRODS.User, cfg.IRODS.Password, cfg.IRODS.Zone)
	log.Printf("Connected to iRODS: %s", cfg.IRODS.Host)

	var mailmanClient *mailman.Client
	if cfg.Mailman.Enabled {
		mailmanClient, err = mailman.New(cfg.Mailman.URL, cfg.Mailman.Password)
		if err != nil {
			log.Printf("Warning: Failed to initialize Mailman connection: %v", err)
			log.Printf("Mailing list removal will be skipped")
		} else {
			log.Printf("Connected to Mailman: %s", cfg.Mailman.URL)
		}
	} else {
		log.Printf("Mailman not enabled, mailing list removal will be skipped")
	}
	log.Println(sectionDivider)

	db, err := portaldb.Connect(ctx, cfg.PortalDB)
	if err != nil {
		return nil, nil, err
	}

	return &deleter{ldap: ldapClient, ds: ds, mailman: mailmanClient}, db, nil
}

// deleteUser runs the deletion phases in order: portal-database lookup,
// mailing lists, datastore, LDAP, then portal-database records. Returns
// whether the deletion (or dry run) succeeded.
func deleteUser(ctx context.Context, d *deleter, db *sql.DB, username string, dryRun bool) bool {
	prefix := ""
	if dryRun {
		prefix = "[DRY RUN] "
	}
	log.Printf("%sStarting deletion for user: %s", prefix, username)
	log.Println(sectionDivider)

	log.Printf("%sPhase 0: Querying portal database", prefix)
	userInfo, err := lookupUser(ctx, db, username)
	if err != nil {
		log.Printf("User deletion failed for %s: %v", username, err)
		return false
	}
	if userInfo == nil {
		log.Printf("User %s not found in portal database", username)
		return false
	}
	log.Printf("%sFound user ID %d with %d email address(es)", prefix, userInfo.ID, len(userInfo.Emails))
	log.Println(sectionDivider)

	if d.mailman != nil && len(userInfo.Emails) > 0 {
		log.Printf("%sPhase 1: Mailing list removal", prefix)
		removeFromMailingLists(d.mailman, userInfo.Emails, dryRun)
	} else {
		log.Printf("%sPhase 1: Skipping mailing list removal (mailman not enabled or no emails)", prefix)
	}
	log.Println(sectionDivider)

	log.Printf("%sPhase 2: Datastore deletion", prefix)
	if err := deleteFromDatastore(d.ds, username, dryRun); err != nil {
		log.Printf("User deletion failed for %s: %v", username, err)
		return false
	}
	log.Println(sectionDivider)

	log.Printf("%sPhase 3: LDAP deletion", prefix)
	if err := deleteFromLDAP(d.ldap, username, dryRun); err != nil {
		log.Printf("User deletion failed for %s: %v", username, err)
		return false
	}
	log.Println(sectionDivider)

	log.Printf("%sPhase 4: Portal database deletion", prefix)
	if err := deleteFromPortalDatabase(ctx, db, userInfo.ID, dryRun); err != nil {
		log.Printf("User deletion failed for %s: %v", username, err)
		return false
	}
	log.Println(sectionDivider)

	log.Printf("%sUser deletion completed successfully: %s", prefix, username)
	return true
}

func lookupUser(ctx context.Context, db *sql.DB, username string) (*portaldb.UserInfo, error) {
	tx, err := db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, err
	}
	defer tx.Rollback() //nolint:errcheck

	return portaldb.GetUser(ctx, tx, username)
}

// removeFromMailingLists unsubscribes each of the user's email addresses
// from its mailing lists. Failures are logged but don't abort the deletion.
func removeFromMailingLists(client *mailman.Client, emails []portaldb.EmailInfo, dryRun bool) {
	prefix := ""
	if dryRun {
		prefix = "[DRY RUN] "
	}
	for _, email := range emails {
		for _, subscription := range email.MailingLists {
			if subscription.ListName == "" {
				continue
			}
			log.Printf("%sRemoving %s from mailing list %s", prefix, email.Email, subscription.ListName)
			if !dryRun {
				if err := client.RemoveMember(subscription.ListName, email.Email); err != nil {
					log.Printf("%sFailed to remove %s from mailing list %s: %v", prefix, email.Email, subscription.ListName, err)
					continue
				}
			}
			log.Printf("%sRemoved %s from mailing list %s", prefix, email.Email, subscription.ListName)
		}
	}
}

func deleteFromDatastore(ds *datastore.DataStore, username string, dryRun bool) error {
	prefix := ""
	if dryRun {
		prefix = "[DRY RUN] "
	}
	log.Printf("%sChecking if user exists in datastore: %s", prefix, username)
	exists, err := ds.UserExists(username)
	if err != nil {
		return err
	}
	if !exists {
		log.Printf("%sUser %s does not exist in datastore, skipping datastore deletion", prefix, username)
		return nil
	}

	log.Printf("%sDeleting home directory for user: %s", prefix, username)
	if !dryRun {
		if err := ds.DeleteHome(username); err != nil {
			return err
		}
	}
	log.Printf("%sDeleted home directory for user: %s", prefix, username)

	log.Printf("%sDeleting datastore user: %s", prefix, username)
	if !dryRun {
		if err := ds.DeleteUser(username); err != nil {
			return err
		}
	}
	log.Printf("%sDeleted datastore user: %s", prefix, username)
	return nil
}

func deleteFromLDAP(client *ldapclient.Client, username string, dryRun bool) error {
	prefix := ""
	if dryRun {
		prefix = "[DRY RUN] "
	}
	log.Printf("%sChecking if user %s exists in LDAP", prefix, username)
	entry, err := client.GetUser(username)
	if err != nil {
		return err
	}
	if entry == nil {
		log.Printf("%sUser %s does not exist in LDAP, skipping LDAP deletion", prefix, username)
		return nil
	}

	log.Printf("%sGetting LDAP groups for user: %s", prefix, username)
	groups, err := client.GetUserGroups(username)
	if err != nil {
		return err
	}
	log.Printf("%sUser %s is in %d groups", prefix, username, len(groups))

	for _, group := range groups {
		if len(group.Attrs["cn"]) == 0 {
			continue
		}
		groupName := group.Attrs["cn"][0]
		log.Printf("%sRemoving user %s from group %s", prefix, username, groupName)
		if !dryRun {
			if err := client.RemoveUserFromGroup(username, groupName); err != nil {
				return err
			}
		}
		log.Printf("%sRemoved user %s from group %s", prefix, username, groupName)
	}

	log.Printf("%sDeleting user %s from LDAP", prefix, username)
	if !dryRun {
		if err := client.DeleteUser(username); err != nil {
			return err
		}
	}
	log.Printf("%sDeleted LDAP user: %s", prefix, username)
	return nil
}

// deleteFromPortalDatabase removes the user's database records in a single
// transaction, committing only when every delete succeeds.
func deleteFromPortalDatabase(ctx context.Context, db *sql.DB, userID int64, dryRun bool) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback() //nolint:errcheck

	if err := portaldb.DeleteUser(ctx, tx, userID, dryRun); err != nil {
		return err
	}

	if dryRun {
		log.Printf("[DRY RUN] Would delete user record (dry run, no commit)")
		return nil
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	log.Printf("Database deletion committed")
	return nil
}
