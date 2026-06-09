package emailsvc

import (
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
				`Content-Type: text/plain; charset="utf-8"`,
				"plain text",
				`Content-Type: text/html; charset="utf-8"`,
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
