// Package userdel implements the user-deletion sequences shared by the
// synchronous DELETE /users/{username} endpoint and the delete-user batch
// job, so the two paths can't drift apart.
package userdel

import (
	"log"

	"github.com/cyverse-de/portal-conductor/datastore"
	"github.com/cyverse-de/portal-conductor/ldapclient"
)

func logPrefix(dryRun bool) string {
	if dryRun {
		return "[DRY RUN] "
	}
	return ""
}

// FromDatastore deletes the user's home collection and iRODS account. A
// missing user is not an error. With dryRun set, the steps are logged but not
// performed.
func FromDatastore(ds *datastore.DataStore, username string, dryRun bool) error {
	prefix := logPrefix(dryRun)
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

// FromLDAP removes the user from every group they belong to and then deletes
// the user entry. A missing user is not an error. With dryRun set, the steps
// are logged but not performed.
func FromLDAP(client *ldapclient.Client, username string, dryRun bool) error {
	prefix := logPrefix(dryRun)
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
