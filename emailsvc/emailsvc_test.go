package emailsvc

import (
	"regexp"
	"strings"
	"testing"
)

func ptr(s string) *string { return &s }

func TestBuildMessage(t *testing.T) {
	tests := []struct {
		name        string
		to          []string
		textBody    *string
		htmlBody    *string
		wantParts   []string
		rejectParts []string
	}{
		{
			"text and html",
			[]string{"a@b.com", "c@d.com"},
			ptr("plain text"), ptr("<b>html</b>"),
			[]string{
				"Subject: Hi there",
				"From: noreply@site.org",
				"To: a@b.com, c@d.com",
				"Content-Type: multipart/alternative",
				`Content-Type: text/plain; charset="us-ascii"`,
				"Content-Transfer-Encoding: 7bit",
				"plain text",
				`Content-Type: text/html; charset="us-ascii"`,
				"<b>html</b>",
			},
			nil,
		},
		{
			"text only",
			[]string{"a@b.com"},
			ptr("just text"), nil,
			[]string{"just text"},
			[]string{"text/html"},
		},
		{
			"non-ascii body uses quoted-printable utf-8",
			[]string{"a@b.com"},
			ptr("héllo wörld"), nil,
			[]string{
				`Content-Type: text/plain; charset="utf-8"`,
				"Content-Transfer-Encoding: quoted-printable",
				"h=C3=A9llo w=C3=B6rld",
			},
			[]string{"héllo"},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			msg, err := buildMessage("noreply@site.org", tt.to, "Hi there", tt.textBody, tt.htmlBody)
			if err != nil {
				t.Fatal(err)
			}
			for _, want := range tt.wantParts {
				if !strings.Contains(string(msg), want) {
					t.Errorf("message missing %q:\n%s", want, msg)
				}
			}
			for _, reject := range tt.rejectParts {
				if strings.Contains(string(msg), reject) {
					t.Errorf("message should not contain %q:\n%s", reject, msg)
				}
			}
		})
	}
}

// Date and Message-ID must be present; their absence is a common
// SpamAssassin penalty (MISSING_DATE, MISSING_MID).
func TestBuildMessageSpamRelevantHeaders(t *testing.T) {
	msg, err := buildMessage("noreply@site.org", []string{"a@b.com"}, "Hi", ptr("body"), nil)
	if err != nil {
		t.Fatal(err)
	}

	if !regexp.MustCompile(`\r\nDate: [A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2} \d{4}`).Match(msg) {
		t.Errorf("missing or malformed Date header:\n%s", msg)
	}
	if !regexp.MustCompile(`\r\nMessage-ID: <\d+\.[0-9a-f]+@site\.org>\r\n`).Match(msg) {
		t.Errorf("missing or malformed Message-ID header:\n%s", msg)
	}
}

func TestGenerateMessageIDUnique(t *testing.T) {
	first := generateMessageID("noreply@site.org")
	second := generateMessageID("noreply@site.org")
	if first == second {
		t.Errorf("expected unique message IDs, got %s twice", first)
	}
	if !strings.HasSuffix(first, "@site.org>") {
		t.Errorf("expected sender domain in message ID, got %s", first)
	}
}

func TestBuildMessageSanitizesHeaders(t *testing.T) {
	msg, err := buildMessage("noreply@site.org", []string{"a@b.com"}, "Subject\r\nBcc: evil@x.com", ptr("body"), nil)
	if err != nil {
		t.Fatal(err)
	}
	// The CRLF must be stripped so the injected text stays inside the
	// Subject value instead of starting a new header line.
	if strings.Contains(string(msg), "\nBcc: evil@x.com") {
		t.Errorf("header injection not sanitized:\n%s", msg)
	}
}
