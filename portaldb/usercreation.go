package portaldb

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"strings"
	"time"
)

// CreateUserData holds the fields required to insert a new user into the
// portal database's account_user table.
type CreateUserData struct {
	Username        string
	Email           string
	Password        string
	FirstName       string
	LastName        string
	Institution     string
	Department      string
	OccupationID    int
	FundingAgencyID int
	GenderID        int
	EthnicityID     int
	RegionID        int
	ResearchAreaID  int
	AwareChannelID  int
	GridInstitutionID *int
	HasVerifiedEmail bool
}

// UserExistsByUsername checks whether a username already exists in account_user.
func UserExistsByUsername(ctx context.Context, db *sql.DB, username string) (bool, error) {
	var exists bool
	err := db.QueryRowContext(ctx,
		"SELECT EXISTS(SELECT 1 FROM account_user WHERE LOWER(username) = $1)",
		strings.ToLower(username),
	).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("checking username existence: %w", err)
	}
	return exists, nil
}

// IsRestrictedUsername checks whether a username is in the restricted list.
func IsRestrictedUsername(ctx context.Context, db *sql.DB, username string) (bool, error) {
	var exists bool
	err := db.QueryRowContext(ctx,
		"SELECT EXISTS(SELECT 1 FROM account_restrictedusername WHERE LOWER(username) = $1)",
		strings.ToLower(username),
	).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("checking restricted username: %w", err)
	}
	return exists, nil
}

// EmailExists checks whether an email address exists in account_emailaddress
// (case-insensitive).
func EmailExists(ctx context.Context, db *sql.DB, email string) (bool, error) {
	var exists bool
	err := db.QueryRowContext(ctx,
		"SELECT EXISTS(SELECT 1 FROM account_emailaddress WHERE LOWER(email) = LOWER($1))",
		strings.ToLower(email),
	).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("checking email existence: %w", err)
	}
	return exists, nil
}

// GetOccupationName returns the name for an occupation ID, or empty string if
// not found.
func GetOccupationName(ctx context.Context, db *sql.DB, occupationID int) (string, error) {
	var name string
	err := db.QueryRowContext(ctx,
		"SELECT name FROM account_occupation WHERE id = $1",
		occupationID,
	).Scan(&name)
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("looking up occupation name: %w", err)
	}
	return name, nil
}

// CreateUserWithEmail creates a user record and its associated email address
// in a single transaction. Returns the new user's database ID.
// The email address is marked verified if and only if data.HasVerifiedEmail is true.
func CreateUserWithEmail(ctx context.Context, db *sql.DB, data CreateUserData) (int64, error) {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return 0, fmt.Errorf("beginning transaction: %w", err)
	}
	defer tx.Rollback() //nolint:errcheck

	userID, err := createUserTx(ctx, tx, data)
	if err != nil {
		return 0, err
	}

	if err := createEmailAddressTx(ctx, tx, userID, data.Email, true, data.HasVerifiedEmail); err != nil {
		return 0, err
	}

	if err := tx.Commit(); err != nil {
		return 0, fmt.Errorf("committing user creation transaction: %w", err)
	}
	return userID, nil
}

// DeleteUserByID removes a user and their email addresses from the portal
// database. This is used as a best-effort compensation when downstream
// provisioning (LDAP, DataStore) fails after the portal DB insert succeeded.
func DeleteUserByID(ctx context.Context, db *sql.DB, userID int64) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("beginning compensation transaction: %w", err)
	}
	defer tx.Rollback() //nolint:errcheck

	if _, err := tx.ExecContext(ctx, "DELETE FROM account_emailaddress WHERE user_id = $1", userID); err != nil {
		return fmt.Errorf("deleting email addresses for user %d: %w", userID, err)
	}
	if _, err := tx.ExecContext(ctx, "DELETE FROM account_user WHERE id = $1", userID); err != nil {
		return fmt.Errorf("deleting user %d: %w", userID, err)
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("committing compensation transaction: %w", err)
	}
	log.Printf("Compensation: removed portal DB records for user ID %d", userID)
	return nil
}

// createUserTx inserts a new user within an existing transaction.
func createUserTx(ctx context.Context, tx *sql.Tx, data CreateUserData) (int64, error) {
	now := time.Now().UTC()
	var userID int64
	err := tx.QueryRowContext(ctx, `
		INSERT INTO account_user (
			username, email, password, first_name, last_name,
			institution, department, occupation_id, funding_agency_id,
			gender_id, ethnicity_id, region_id, research_area_id,
			aware_channel_id, is_superuser, is_staff, is_active,
			has_verified_email, participate_in_study, subscribe_to_newsletter,
			orcid_id, date_joined, updated_at, grid_institution_id
		) VALUES (
			$1, $2, $3, $4, $5,
			$6, $7, $8, $9,
			$10, $11, $12, $13,
			$14, $15, $16, $17,
			$18, $19, $20,
			$21, $22, $23, $24
		) RETURNING id`,
		data.Username,
		strings.ToLower(data.Email),
		data.Password,
		data.FirstName,
		data.LastName,
		data.Institution,
		data.Department,
		data.OccupationID,
		data.FundingAgencyID,
		data.GenderID,
		data.EthnicityID,
		data.RegionID,
		data.ResearchAreaID,
		data.AwareChannelID,
		false,                 // is_superuser
		false,                 // is_staff
		true,                  // is_active
		data.HasVerifiedEmail, // has_verified_email
		true,                  // participate_in_study
		true,                  // subscribe_to_newsletter
		"",                    // orcid_id
		now,                   // date_joined
		now,                   // updated_at
		data.GridInstitutionID,
	).Scan(&userID)
	if err != nil {
		return 0, fmt.Errorf("inserting user into portal database: %w", err)
	}
	return userID, nil
}

// createEmailAddressTx inserts an email address record within an existing transaction.
func createEmailAddressTx(ctx context.Context, tx *sql.Tx, userID int64, email string, primary bool, verified bool) error {
	now := time.Now().UTC()
	_, err := tx.ExecContext(ctx, `
		INSERT INTO account_emailaddress (
			user_id, email, "primary", verified, created_at, updated_at
		) VALUES ($1, $2, $3, $4, $5, $6)`,
		userID,
		strings.ToLower(email),
		primary,
		verified,
		now,
		now,
	)
	if err != nil {
		return fmt.Errorf("inserting email address for user %d: %w", userID, err)
	}
	return nil
}
