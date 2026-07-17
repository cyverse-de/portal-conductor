// Package datastore ports portal_datastore.py to Go using go-irodsclient.
package datastore

import (
	"errors"
	"fmt"
	"log"
	"path"
	"sync"
	"time"

	irodsfs "github.com/cyverse/go-irodsclient/fs"
	"github.com/cyverse/go-irodsclient/irods/common"
	"github.com/cyverse/go-irodsclient/irods/types"
)

const applicationName = "portal-conductor"

// irodsAdminMode runs iRODS ACL and inheritance changes in rodsadmin ("-M")
// mode. The connecting account provisions and re-permissions other users' home
// collections, which iRODS creates owned by the user rather than by us; without
// admin mode the ownership grants fail with CAT_NO_ACCESS_PERMISSION. The
// service already requires this account to be a rodsadmin for user creation and
// password changes, so admin mode adds no new privilege requirement.
const irodsAdminMode = true

// DataStore performs the iRODS operations needed by the portal. The
// underlying connection is established lazily on first use so the service
// can start while iRODS is unavailable, matching python-irodsclient's lazy
// sessions.
type DataStore struct {
	host     string
	port     int
	user     string
	password string
	zone     string

	mu sync.Mutex
	fs *irodsfs.FileSystem
}

// New returns a DataStore for the given iRODS endpoint without connecting.
func New(host string, port int, user, password, zone string) *DataStore {
	return &DataStore{host: host, port: port, user: user, password: password, zone: zone}
}

func (d *DataStore) filesystem() (*irodsfs.FileSystem, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.fs != nil {
		return d.fs, nil
	}

	account, err := types.CreateIRODSAccount(d.host, d.port, d.user, d.zone, types.AuthSchemeNative, d.password, "")
	if err != nil {
		return nil, fmt.Errorf("creating iRODS account: %w", err)
	}

	fsConfig := irodsfs.NewFileSystemConfig(applicationName)
	// The Python service had no metadata cache; disable it so existence
	// checks observe deletions made by external jobs immediately.
	fsConfig.Cache.NoCache = true
	// The Python service disabled the connection timeout entirely; the
	// library's 1m/5m defaults are too short for deleting large home
	// collections, so raise them well past any expected operation.
	fsConfig.MetadataConnection.OperationTimeout = types.Duration(30 * time.Minute)
	fsConfig.MetadataConnection.LongOperationTimeout = types.Duration(12 * time.Hour)
	fsConfig.IOConnection.OperationTimeout = types.Duration(30 * time.Minute)
	fsConfig.IOConnection.LongOperationTimeout = types.Duration(12 * time.Hour)

	fs, err := irodsfs.NewFileSystem(account, fsConfig)
	if err != nil {
		return nil, fmt.Errorf("connecting to iRODS at %s:%d failed (server down or bad credentials?): %w", d.host, d.port, err)
	}
	d.fs = fs
	return d.fs, nil
}

// HealthCheck reports whether the datastore is reachable.
func (d *DataStore) HealthCheck() bool {
	log.Printf("Checking datastore service health at: %s:%d", d.host, d.port)
	fs, err := d.filesystem()
	if err == nil {
		_, err = fs.GetServerVersion()
	}
	if err != nil {
		log.Printf("Datastore health check failed: %v", err)
		return false
	}
	log.Printf("Datastore health check: OK")
	return true
}

// UserHome returns the iRODS home collection path for username.
func (d *DataStore) UserHome(username string) string {
	return fmt.Sprintf("/%s/home/%s", d.zone, username)
}

// UserExists reports whether username exists in the configured zone.
func (d *DataStore) UserExists(username string) (bool, error) {
	fs, err := d.filesystem()
	if err != nil {
		return false, err
	}
	_, err = fs.GetUser(username, d.zone, types.IRODSUserRodsUser)
	if err != nil {
		if types.IsUserNotFoundError(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

// CreateUser creates username as a rodsuser.
func (d *DataStore) CreateUser(username string) error {
	fs, err := d.filesystem()
	if err != nil {
		return err
	}
	if _, err := fs.CreateUser(username, d.zone, types.IRODSUserRodsUser); err != nil {
		return fmt.Errorf("creating datastore user '%s': %w", username, err)
	}
	return nil
}

// DeleteUser removes username from iRODS.
func (d *DataStore) DeleteUser(username string) error {
	fs, err := d.filesystem()
	if err != nil {
		return err
	}
	user, err := fs.GetUser(username, d.zone, types.IRODSUserRodsUser)
	if err != nil {
		return err
	}
	return fs.RemoveUser(username, d.zone, user.Type)
}

// DeleteHome removes the user's home collection and everything in it. If the
// server refuses to remove a non-empty home collection (home-coll protection),
// the contents are deleted individually first.
func (d *DataStore) DeleteHome(username string) error {
	fs, err := d.filesystem()
	if err != nil {
		return err
	}
	home := d.UserHome(username)
	if !fs.ExistsDir(home) {
		return nil
	}
	err = fs.RemoveDir(home, true, true)
	if err != nil && isErrorCode(err, common.CANT_RM_NON_EMPTY_HOME_COLL) {
		log.Printf("Home directory protection triggered, manually deleting contents of %s", home)
		if err := d.deleteContents(fs, home); err != nil {
			return err
		}
		return fs.RemoveDir(home, false, false)
	}
	return err
}

func isErrorCode(err error, code common.ErrorCode) bool {
	var irodsErr *types.IRODSError
	return errors.As(err, &irodsErr) && irodsErr.Code == code
}

func (d *DataStore) deleteContents(fs *irodsfs.FileSystem, collection string) error {
	entries, err := fs.List(collection)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() {
			log.Printf("Deleting subcollection: %s", entry.Path)
			if err := d.deleteContents(fs, entry.Path); err != nil {
				return err
			}
			if err := fs.RemoveDir(entry.Path, true, true); err != nil {
				return err
			}
		} else {
			log.Printf("Deleting file: %s", entry.Path)
			if err := fs.RemoveFile(entry.Path, true); err != nil {
				return err
			}
		}
	}
	return nil
}

// ChangePassword sets the user's iRODS password.
func (d *DataStore) ChangePassword(username, newPassword string) error {
	fs, err := d.filesystem()
	if err != nil {
		return err
	}
	if err := fs.ChangeUserPassword(username, d.zone, newPassword); err != nil {
		return fmt.Errorf("changing datastore password for '%s': %w", username, err)
	}
	return nil
}

func (d *DataStore) setOwnerIfNeeded(fs *irodsfs.FileSystem, currentPerms []*types.IRODSAccess, username, irodsPath string) error {
	for _, perm := range currentPerms {
		if perm.UserName == username && perm.AccessLevel == types.IRODSAccessLevelOwner {
			log.Printf("User %s already owns %s", username, irodsPath)
			return nil
		}
	}
	log.Printf("Setting owner permission for %s on %s", username, irodsPath)
	return fs.ChangeACLs(irodsPath, types.IRODSAccessLevelOwner, username, d.zone, false, irodsAdminMode)
}

func (d *DataStore) setInheritIfNeeded(fs *irodsfs.FileSystem, irodsPath string) error {
	inheritance, err := fs.GetDirACLInheritance(irodsPath)
	if err == nil && inheritance != nil && inheritance.Inheritance {
		return nil
	}
	return fs.ChangeDirACLInheritance(irodsPath, true, false, irodsAdminMode)
}

// EnsureUserExists creates the user and their home collection if necessary.
func (d *DataStore) EnsureUserExists(username string) error {
	exists, err := d.UserExists(username)
	if err != nil {
		return err
	}
	if !exists {
		if err := d.CreateUser(username); err != nil {
			return err
		}
	}

	fs, err := d.filesystem()
	if err != nil {
		return err
	}
	home := d.UserHome(username)
	if !fs.ExistsDir(home) {
		if err := fs.MakeDir(home, true); err != nil {
			return err
		}
		if err := fs.ChangeACLs(home, types.IRODSAccessLevelOwner, username, d.zone, false, irodsAdminMode); err != nil {
			return err
		}
	}
	return nil
}

// CreateUserWithPermissions creates the user with their home collection and
// grants ownership to the ipcservices and admin users. All steps except the
// password update are idempotent; the password is always set so this doubles
// as a password-reset operation.
func (d *DataStore) CreateUserWithPermissions(username, password, ipcservicesUser, adminUser string) error {
	log.Printf("Creating data store user: %s", username)
	if err := d.EnsureUserExists(username); err != nil {
		return err
	}

	log.Printf("Setting data store password for: %s", username)
	if err := d.ChangePassword(username, password); err != nil {
		return err
	}

	fs, err := d.filesystem()
	if err != nil {
		return err
	}
	home := d.UserHome(username)
	currentPerms, err := fs.ListACLs(home)
	if err != nil {
		return err
	}
	if err := d.setOwnerIfNeeded(fs, currentPerms, ipcservicesUser, home); err != nil {
		return err
	}
	return d.setOwnerIfNeeded(fs, currentPerms, adminUser, home)
}

// RegisterService creates a service directory under the user's home and sets
// inherit plus owner permissions, creating the user first if needed.
func (d *DataStore) RegisterService(username, irodsPath string, irodsUser *string) error {
	if err := d.EnsureUserExists(username); err != nil {
		return fmt.Errorf("failed to prepare user %s: %w", username, err)
	}
	log.Printf("User %s is ready for service registration", username)

	fs, err := d.filesystem()
	if err != nil {
		return err
	}
	// Match the Python os.path.join contract: an absolute irodsPath is used
	// as-is rather than nested under the user's home collection.
	fullPath := irodsPath
	if !path.IsAbs(irodsPath) {
		fullPath = path.Join(d.UserHome(username), irodsPath)
	}

	// A pre-existing data object at the path also counts as existing; the
	// Python service skipped creation and just set permissions on it.
	if !fs.Exists(fullPath) {
		if err := fs.MakeDir(fullPath, true); err != nil {
			return err
		}
	}

	currentPerms, err := fs.ListACLs(fullPath)
	if err != nil {
		return err
	}
	// ACL inheritance only applies to collections, not data objects.
	if fs.ExistsDir(fullPath) {
		if err := d.setInheritIfNeeded(fs, fullPath); err != nil {
			return err
		}
	}
	if err := d.setOwnerIfNeeded(fs, currentPerms, username, fullPath); err != nil {
		return err
	}
	if irodsUser != nil {
		if err := d.setOwnerIfNeeded(fs, currentPerms, *irodsUser, fullPath); err != nil {
			return err
		}
	}
	return nil
}
