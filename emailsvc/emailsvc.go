// Package emailsvc ports email_service.py to Go: SMTP email sending with
// optional implicit TLS or STARTTLS and multipart text/HTML bodies.
package emailsvc

import (
	"crypto/tls"
	"fmt"
	"log"
	"mime/multipart"
	"net"
	"net/smtp"
	"net/textproto"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/cyverse-de/portal-conductor/config"
)

const dialTimeout = 30 * time.Second

// Service sends email through the configured SMTP server.
type Service struct {
	host        string
	port        int
	user        string
	password    string
	useTLS      bool
	useSSL      bool
	defaultFrom string
}

// New returns a Service configured from the smtp section of the config.
func New(cfg config.SMTP) *Service {
	return &Service{
		host:        cfg.Host,
		port:        cfg.Port.Int(25),
		user:        cfg.User,
		password:    cfg.Password,
		useTLS:      cfg.UseTLS,
		useSSL:      cfg.UseSSL,
		defaultFrom: cfg.From,
	}
}

// Send sends an email and reports success, logging failures rather than
// returning them, like EmailService.send_email.
func (s *Service) Send(to []string, subject string, textBody, htmlBody, fromEmail *string, bcc []string) bool {
	if err := s.send(to, subject, textBody, htmlBody, fromEmail, bcc); err != nil {
		log.Printf("Failed to send email: %v", err)
		return false
	}
	return true
}

func (s *Service) send(to []string, subject string, textBody, htmlBody, fromEmail *string, bcc []string) error {
	if (textBody == nil || *textBody == "") && (htmlBody == nil || *htmlBody == "") {
		return fmt.Errorf("either text_body or html_body must be provided")
	}

	from := s.defaultFrom
	if fromEmail != nil && *fromEmail != "" {
		from = *fromEmail
	}

	message, err := buildMessage(from, to, subject, textBody, htmlBody)
	if err != nil {
		return err
	}

	client, err := s.connect()
	if err != nil {
		return err
	}
	defer client.Close() //nolint:errcheck

	if s.user != "" && s.password != "" {
		if err := client.Auth(smtp.PlainAuth("", s.user, s.password, s.host)); err != nil {
			return fmt.Errorf("SMTP authentication failed (bad credentials or server requires a different mechanism?): %w", err)
		}
	}

	if err := client.Mail(from); err != nil {
		return err
	}
	for _, rcpt := range slices.Concat(to, bcc) {
		if err := client.Rcpt(rcpt); err != nil {
			return fmt.Errorf("recipient %s rejected: %w", rcpt, err)
		}
	}

	w, err := client.Data()
	if err != nil {
		return err
	}
	if _, err := w.Write(message); err != nil {
		return err
	}
	if err := w.Close(); err != nil {
		return err
	}
	return client.Quit()
}

func (s *Service) connect() (*smtp.Client, error) {
	addr := net.JoinHostPort(s.host, strconv.Itoa(s.port))
	if s.useSSL {
		conn, err := tls.DialWithDialer(&net.Dialer{Timeout: dialTimeout}, "tcp", addr, &tls.Config{ServerName: s.host})
		if err != nil {
			return nil, fmt.Errorf("connecting to SMTP server %s over TLS: %w", addr, err)
		}
		return smtp.NewClient(conn, s.host)
	}

	conn, err := net.DialTimeout("tcp", addr, dialTimeout)
	if err != nil {
		return nil, fmt.Errorf("connecting to SMTP server %s: %w", addr, err)
	}
	client, err := smtp.NewClient(conn, s.host)
	if err != nil {
		_ = conn.Close()
		return nil, err
	}
	if s.useTLS {
		if err := client.StartTLS(&tls.Config{ServerName: s.host}); err != nil {
			_ = client.Close()
			return nil, fmt.Errorf("STARTTLS with %s failed: %w", addr, err)
		}
	}
	return client, nil
}

// buildMessage assembles a multipart/alternative MIME message with optional
// plain-text and HTML parts, like Python's MIMEMultipart("alternative").
func buildMessage(from string, to []string, subject string, textBody, htmlBody *string) ([]byte, error) {
	var buf strings.Builder
	mw := multipart.NewWriter(&buf)

	fmt.Fprintf(&buf, "Subject: %s\r\n", sanitizeHeader(subject))
	fmt.Fprintf(&buf, "From: %s\r\n", sanitizeHeader(from))
	fmt.Fprintf(&buf, "To: %s\r\n", sanitizeHeader(strings.Join(to, ", ")))
	buf.WriteString("MIME-Version: 1.0\r\n")
	fmt.Fprintf(&buf, "Content-Type: multipart/alternative; boundary=%q\r\n", mw.Boundary())
	buf.WriteString("\r\n")

	writePart := func(contentType, body string) error {
		header := textproto.MIMEHeader{}
		header.Set("Content-Type", contentType+`; charset="utf-8"`)
		part, err := mw.CreatePart(header)
		if err != nil {
			return err
		}
		_, err = part.Write([]byte(body))
		return err
	}

	if textBody != nil && *textBody != "" {
		if err := writePart("text/plain", *textBody); err != nil {
			return nil, err
		}
	}
	if htmlBody != nil && *htmlBody != "" {
		if err := writePart("text/html", *htmlBody); err != nil {
			return nil, err
		}
	}
	if err := mw.Close(); err != nil {
		return nil, err
	}
	return []byte(buf.String()), nil
}

// sanitizeHeader strips CR/LF to prevent header injection from request data.
func sanitizeHeader(v string) string {
	return strings.NewReplacer("\r", "", "\n", "").Replace(v)
}
