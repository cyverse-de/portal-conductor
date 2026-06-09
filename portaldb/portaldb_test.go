package portaldb

import (
	"encoding/json"
	"testing"
)

// TestEmailAggregateParsing checks that the json_agg payload produced by the
// user query unmarshals into EmailInfo, including null mailing-list arrays
// for addresses with no subscriptions.
func TestEmailAggregateParsing(t *testing.T) {
	payload := `[
		{"email": "a@b.com", "mailing_lists": [
			{"list_name": "announce", "is_subscribed": true},
			{"list_name": "news", "is_subscribed": false}
		]},
		{"email": "c@d.com", "mailing_lists": null}
	]`

	var emails []EmailInfo
	if err := json.Unmarshal([]byte(payload), &emails); err != nil {
		t.Fatal(err)
	}

	if len(emails) != 2 {
		t.Fatalf("got %d emails, want 2", len(emails))
	}
	if emails[0].Email != "a@b.com" || len(emails[0].MailingLists) != 2 {
		t.Errorf("first email parsed incorrectly: %+v", emails[0])
	}
	if emails[0].MailingLists[0].ListName != "announce" || !emails[0].MailingLists[0].IsSubscribed {
		t.Errorf("first subscription parsed incorrectly: %+v", emails[0].MailingLists[0])
	}
	if emails[1].Email != "c@d.com" || emails[1].MailingLists != nil {
		t.Errorf("null mailing_lists should parse as nil: %+v", emails[1])
	}
}
