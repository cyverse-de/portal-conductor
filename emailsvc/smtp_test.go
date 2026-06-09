package emailsvc

import (
	"bufio"
	"fmt"
	"net"
	"strconv"
	"strings"
	"testing"

	"github.com/cyverse-de/portal-conductor/config"
)

// fakeSMTPServer accepts one SMTP session and records the client's commands
// and message data.
type fakeSMTPServer struct {
	listener net.Listener
	commands chan string
	data     chan string
}

func newFakeSMTPServer(t *testing.T) *fakeSMTPServer {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := &fakeSMTPServer{
		listener: listener,
		commands: make(chan string, 32),
		data:     make(chan string, 1),
	}
	t.Cleanup(func() { listener.Close() }) //nolint:errcheck

	go server.serve()
	return server
}

func (s *fakeSMTPServer) port() int {
	return s.listener.Addr().(*net.TCPAddr).Port
}

func (s *fakeSMTPServer) serve() {
	conn, err := s.listener.Accept()
	if err != nil {
		return
	}
	defer conn.Close() //nolint:errcheck

	write := func(line string) { fmt.Fprintf(conn, "%s\r\n", line) } //nolint:errcheck
	write("220 fake.test ESMTP")

	reader := bufio.NewReader(conn)
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return
		}
		line = strings.TrimRight(line, "\r\n")
		s.commands <- line

		verb := strings.ToUpper(strings.SplitN(line, " ", 2)[0])
		switch verb {
		case "EHLO", "HELO":
			write("250 fake.test")
		case "MAIL", "RCPT":
			write("250 OK")
		case "DATA":
			write("354 go ahead")
			var body strings.Builder
			for {
				dataLine, err := reader.ReadString('\n')
				if err != nil {
					return
				}
				if strings.TrimRight(dataLine, "\r\n") == "." {
					break
				}
				body.WriteString(dataLine)
			}
			s.data <- body.String()
			write("250 accepted")
		case "QUIT":
			write("221 bye")
			return
		default:
			write("250 OK")
		}
	}
}

func TestSendUsesHostnameForEHLO(t *testing.T) {
	server := newFakeSMTPServer(t)

	svc := New(config.SMTP{
		Host: "127.0.0.1",
		Port: config.FlexString(strconv.Itoa(server.port())),
		From: "noreply@site.org",
	})
	if ok := svc.Send([]string{"someone@example.org"}, "Hello", ptr("body text"), nil, nil, nil); !ok {
		t.Fatal("Send reported failure")
	}

	ehlo := <-server.commands
	if !strings.HasPrefix(ehlo, "EHLO ") && !strings.HasPrefix(ehlo, "HELO ") {
		t.Fatalf("expected EHLO first, got %q", ehlo)
	}
	name := strings.TrimSpace(strings.SplitN(ehlo, " ", 2)[1])
	if name == "localhost" || name == "" {
		t.Errorf("EHLO used %q; expected the machine hostname (localhost is a spam signal)", name)
	}

	message := <-server.data
	for _, header := range []string{"Date: ", "Message-ID: <", "Subject: Hello", "To: someone@example.org"} {
		if !strings.Contains(message, header) {
			t.Errorf("delivered message missing %q:\n%s", header, message)
		}
	}
}
