// Package portaldb queries and deletes portal-database (PostgreSQL) records
// for the delete-user batch job, porting the database logic from
// scripts/delete-user.py.
package portaldb

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"

	_ "github.com/lib/pq" // postgres driver

	"github.com/cyverse-de/portal-conductor/config"
)

// MailingListSubscription is one mailing-list membership of an email address.
type MailingListSubscription struct {
	ListName     string `json:"list_name"`
	IsSubscribed bool   `json:"is_subscribed"`
}

// EmailInfo is an email address with its mailing-list subscriptions.
type EmailInfo struct {
	Email        string                    `json:"email"`
	MailingLists []MailingListSubscription `json:"mailing_lists"`
}

// UserInfo is the portal-database record for a user.
type UserInfo struct {
	ID           int64
	Username     string
	PrimaryEmail string
	Emails       []EmailInfo
}

// Connect opens a connection pool to the portal database and verifies it.
func Connect(ctx context.Context, cfg config.PortalDB) (*sql.DB, error) {
	sslMode := cfg.SSLMode
	if sslMode == "" {
		sslMode = "disable"
	}
	dsn := fmt.Sprintf("host=%s port=%d dbname=%s user=%s password=%s sslmode=%s",
		cfg.Host, cfg.Port.Int(5432), cfg.Name, cfg.User, cfg.Password, sslMode)
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	if err := db.PingContext(ctx); err != nil {
		db.Close() //nolint:errcheck
		return nil, fmt.Errorf("connecting to portal database at %s failed (server down or bad credentials?): %w", cfg.Host, err)
	}
	return db, nil
}

// userQuery matches the lookup in delete-user.py: the user row plus a JSON
// aggregate of their email addresses and mailing-list subscriptions.
const userQuery = `
	SELECT
		u.id,
		u.username,
		u.email as primary_email,
		json_agg(
			json_build_object(
				'email', e.email,
				'mailing_lists', (
					SELECT json_agg(
						json_build_object(
							'list_name', ml.list_name,
							'is_subscribed', eml.is_subscribed
						)
					)
					FROM api_emailaddressmailinglist eml
					JOIN api_mailinglist ml ON ml.id = eml.mailing_list_id
					WHERE eml.email_address_id = e.id
				)
			)
		) FILTER (WHERE e.id IS NOT NULL) as emails
	FROM account_user u
	LEFT JOIN account_emailaddress e ON e.user_id = u.id
	WHERE LOWER(u.username) = LOWER($1)
	GROUP BY u.id, u.username, u.email
`

// GetUser returns the user's portal-database record, or nil if the user does
// not exist.
func GetUser(ctx context.Context, tx *sql.Tx, username string) (*UserInfo, error) {
	var user UserInfo
	var primaryEmail sql.NullString
	var emailsJSON []byte

	err := tx.QueryRowContext(ctx, userQuery, username).Scan(&user.ID, &user.Username, &primaryEmail, &emailsJSON)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("querying portal database for user '%s': %w", username, err)
	}

	user.PrimaryEmail = primaryEmail.String
	if len(emailsJSON) > 0 {
		if err := json.Unmarshal(emailsJSON, &user.Emails); err != nil {
			return nil, fmt.Errorf("parsing email aggregate for user '%s': %w", username, err)
		}
	}
	return &user, nil
}

// deleteStep is one DELETE statement in the FK-constraint-safe ordering.
type deleteStep struct {
	description string
	statement   string
}

// deleteSteps removes the user's records in an order that satisfies the
// foreign-key constraints: logs before their parent request records, email
// mailing-list links before email addresses, and the user row last.
var deleteSteps = []deleteStep{
	// Legacy tables (from v1, no longer used)
	{"django_cyverse_auth_token", `DELETE FROM django_cyverse_auth_token WHERE user_id = $1`},
	{"django_admin_log", `DELETE FROM django_admin_log WHERE user_id = $1`},
	{"warden_atmosphereinternationalrequest", `DELETE FROM warden_atmosphereinternationalrequest WHERE user_id = $1`},
	{"warden_atmospherestudentrequest", `DELETE FROM warden_atmospherestudentrequest WHERE user_id = $1`},

	{"enrollment request logs", `
		DELETE FROM api_workshopenrollmentrequestlog
		WHERE workshop_enrollment_request_id IN (
			SELECT id FROM api_workshopenrollmentrequest WHERE user_id = $1
		)`},
	{"access request logs", `
		DELETE FROM api_accessrequestlog
		WHERE access_request_id IN (
			SELECT id FROM api_accessrequest WHERE user_id = $1
		)`},

	// Core tables
	{"account_passwordreset", `DELETE FROM account_passwordreset WHERE user_id = $1`},
	{"account_passwordresetrequest", `DELETE FROM account_passwordresetrequest WHERE user_id = $1`},
	{"api_userservice", `DELETE FROM api_userservice WHERE user_id = $1`},
	{"api_formsubmission", `DELETE FROM api_formsubmission WHERE user_id = $1`},
	{"api_workshopenrollmentrequest", `DELETE FROM api_workshopenrollmentrequest WHERE user_id = $1`},
	{"api_accessrequest", `DELETE FROM api_accessrequest WHERE user_id = $1`},

	{"api_workshoporganizer", `DELETE FROM api_workshoporganizer WHERE organizer_id = $1`},
	{"api_emailaddressmailinglist", `
		DELETE FROM api_emailaddressmailinglist
		WHERE email_address_id IN (
			SELECT id FROM account_emailaddress WHERE user_id = $1
		)`},
	{"account_emailaddress", `DELETE FROM account_emailaddress WHERE user_id = $1`},
	{"user record from account_user", `DELETE FROM account_user WHERE id = $1`},
}

// DeleteUser removes all of the user's portal-database records inside tx.
// With dryRun set it only logs the steps that would run.
func DeleteUser(ctx context.Context, tx *sql.Tx, userID int64, dryRun bool) error {
	prefix := ""
	if dryRun {
		prefix = "[DRY RUN] "
	}
	log.Printf("%sDeleting user ID %d from portal database", prefix, userID)

	for _, step := range deleteSteps {
		log.Printf("%sDeleting %s", prefix, step.description)
		if dryRun {
			continue
		}
		if _, err := tx.ExecContext(ctx, step.statement, userID); err != nil {
			return fmt.Errorf("deleting %s: %w", step.description, err)
		}
	}
	return nil
}
