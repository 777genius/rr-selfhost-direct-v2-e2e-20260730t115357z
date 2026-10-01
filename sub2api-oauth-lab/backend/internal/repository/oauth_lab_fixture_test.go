//go:build oauthlab

package repository

import (
	"bufio"
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"entgo.io/ent/dialect"
	entsql "entgo.io/ent/dialect/sql"
	dbent "github.com/Wei-Shaw/sub2api/ent"
	_ "github.com/Wei-Shaw/sub2api/ent/runtime"
	"github.com/Wei-Shaw/sub2api/internal/service"
	"github.com/google/uuid"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
)

const oauthLabEnable = "disposable-synthetic-only"
const oauthLabEventPrefix = "OAUTH_LAB_EVENT "

// All receipt fields are allowlisted. No token, DSN, raw error, or HTTP body is logged.
type oauthLabEvent struct {
	Kind string `json:"kind"`
	Op string `json:"op,omitempty"`
	PID int `json:"pid,omitempty"`
	Phase string `json:"phase,omitempty"`
	Error bool `json:"error,omitempty"`
	Denied bool `json:"denied,omitempty"`
	HTTPStatus int `json:"http_status,omitempty"`
	Count int `json:"count,omitempty"`
}

type oauthLabCommand struct {
	Kind string `json:"kind"`
	Op string `json:"op"`
	Count int `json:"count,omitempty"`
	Scheduled bool `json:"scheduled,omitempty"`
}

type oauthLabSuite struct {
	db *sql.DB
	client *dbent.Client
	repo service.AccountRepository
	rdb *redis.Client
	dsn string
	redisURL string
	issuerRequests atomic.Int64
	pgVersion string
	redisVersion string
}

func oauthLabNeed(t *testing.T, ok bool, message string) {
	t.Helper()
	if !ok { t.Fatal(message) }
}

func oauthLabOpenDB(dsn string) (*sql.DB, *dbent.Client, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil { return nil, nil, err }
	db.SetMaxOpenConns(12)
	db.SetMaxIdleConns(4)
	return db, dbent.NewClient(dbent.Driver(entsql.OpenDB(dialect.Postgres, db))), nil
}

func oauthLabRedis(raw string) (*redis.Client, error) {
	opts, err := redis.ParseURL(raw)
	if err != nil { return nil, err }
	if opts.DB < 1 { return nil, fmt.Errorf("dedicated nonzero Redis database required") }
	opts.MaxRetries = -1
	opts.DialTimeout = 300 * time.Millisecond
	opts.ReadTimeout = 300 * time.Millisecond
	opts.WriteTimeout = 300 * time.Millisecond
	return redis.NewClient(opts), nil
}

func oauthLabSetup(t *testing.T) *oauthLabSuite {
	t.Helper()
	dsn, rawRedis := os.Getenv("OAUTH_LAB_PG_DSN"), os.Getenv("OAUTH_LAB_REDIS_URL")
	if os.Getenv("OAUTH_LAB_ENABLE") != oauthLabEnable || dsn == "" || rawRedis == "" {
		t.Skip("NOT RUN: requires explicit disposable synthetic PostgreSQL and Redis configuration")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	db, client, err := oauthLabOpenDB(dsn)
	oauthLabNeed(t, err == nil, "NOT RUN: PostgreSQL initialization failed (details withheld)")
	t.Cleanup(func() { _ = client.Close() })
	oauthLabNeed(t, db.PingContext(ctx) == nil, "NOT RUN: supplied disposable PostgreSQL unreachable")
	var dbName, schema string
	err = db.QueryRowContext(ctx, "SELECT current_database(), current_schema()").Scan(&dbName, &schema)
	oauthLabNeed(t, err == nil && strings.HasPrefix(dbName, "oauth_lab_") && schema == "public", "requires dedicated oauth_lab_* database with public schema")
	// Never migrate a populated account database. Operator creates a fresh dedicated DB.
	var exists bool
	err = db.QueryRowContext(ctx, "SELECT to_regclass('public.accounts') IS NOT NULL").Scan(&exists)
	oauthLabNeed(t, err == nil, "database isolation inspection failed")
	if exists {
		var n int
		err = db.QueryRowContext(ctx, "SELECT count(*) FROM accounts").Scan(&n)
		oauthLabNeed(t, err == nil && n == 0, "refusing account-populated database")
	}
	rdb, err := oauthLabRedis(rawRedis)
	oauthLabNeed(t, err == nil, "invalid disposable Redis configuration")
	t.Cleanup(func() { _ = rdb.Close() })
	oauthLabNeed(t, rdb.Ping(ctx).Err() == nil, "NOT RUN: supplied disposable Redis unreachable")
	size, err := rdb.DBSize(ctx).Result()
	oauthLabNeed(t, err == nil && size == 0, "refusing populated Redis database")
	oauthLabNeed(t, ApplyMigrations(ctx, db) == nil, "NOT RUN: pinned migrations failed (details withheld)")
	s := &oauthLabSuite{db: db, client: client, repo: NewAccountRepository(client, db, nil), rdb: rdb, dsn: dsn, redisURL: rawRedis}
	_ = db.QueryRowContext(ctx, "SHOW server_version").Scan(&s.pgVersion)
	if info, err := rdb.Info(ctx, "server").Result(); err == nil {
		for _, line := range strings.Split(info, "\n") {
			if strings.HasPrefix(line, "redis_version:") { s.redisVersion = strings.TrimSpace(strings.TrimPrefix(line, "redis_version:")) }
		}
	}
	return s
}

type oauthLabAttempt struct {
	Index int
	Accepted bool
	gate chan struct{}
	once sync.Once
}
func (a *oauthLabAttempt) release() { a.once.Do(func() { close(a.gate) }) }

type oauthLabIssuer struct {
	suite *oauthLabSuite
	id string
	server *httptest.Server
	mu sync.Mutex
	consumed bool
	revoked bool
	autoRelease bool
	attempts []*oauthLabAttempt
	entered chan *oauthLabAttempt
	resourceRequests int
	rotations int
	malformed int
}

func (i *oauthLabIssuer) token(phase string) string { return "fabricated-oauth-lab-" + i.id + "-" + phase }
func (i *oauthLabIssuer) phase(token string) string {
	for _, p := range []string{"A0", "A1", "REAUTH", "R0", "R1", "REAUTH_REFRESH"} {
		if token == i.token(p) { return p }
	}
	if token == "" { return "empty" }
	return "unknown"
}
func (i *oauthLabIssuer) credentials(reauth bool) map[string]any {
	access, refresh := "A0", "R0"
	expires := time.Now().Add(-time.Minute)
	version := int64(0)
	if reauth { access, refresh, expires, version = "REAUTH", "REAUTH_REFRESH", time.Now().Add(time.Hour), time.Now().Add(time.Hour).UnixMilli() }
	return map[string]any{"access_token": i.token(access), "refresh_token": i.token(refresh), "expires_at": expires.Format(time.RFC3339), "client_id": "oauth-lab-fabricated-client", "_token_version": version}
}
func (i *oauthLabIssuer) idToken() string {
	payload, _ := json.Marshal(map[string]any{"email": i.id + "@oauth-lab.invalid", "exp": time.Now().Add(time.Hour).Unix(), "https://api.openai.com/auth": map[string]any{"chatgpt_account_id": i.id, "chatgpt_user_id": "synthetic-user", "chatgpt_plan_type": "synthetic-plan"}})
	return base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"none"}`)) + "." + base64.RawURLEncoding.EncodeToString(payload) + ".fabricated"
}
func (i *oauthLabIssuer) serve(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	if r.URL.Path == "/resource" {
		i.mu.Lock()
		i.resourceRequests++
		phase := i.phase(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
		allowed := !i.revoked && (phase == "A1" || phase == "REAUTH")
		i.mu.Unlock()
		if !allowed { w.WriteHeader(http.StatusUnauthorized) }
		_ = json.NewEncoder(w).Encode(map[string]any{"phase": phase, "accepted": allowed})
		return
	}
	if r.URL.Path != "/token" || r.Method != http.MethodPost { w.WriteHeader(http.StatusNotFound); return }
	if i.suite.issuerRequests.Add(1) > 128 { w.WriteHeader(http.StatusTooManyRequests); _, _ = io.WriteString(w, `{"error":"synthetic_budget_exhausted"}`); return }
	_ = r.ParseForm()
	i.mu.Lock()
	validForm := r.Form.Get("grant_type") == "refresh_token" && r.Form.Get("client_id") == "oauth-lab-fabricated-client" && r.Form.Get("scope") != ""
	if !validForm { i.malformed++ }
	accepted := validForm && !i.revoked && !i.consumed && r.Form.Get("refresh_token") == i.token("R0")
	if accepted { i.consumed = true; i.rotations++ }
	a := &oauthLabAttempt{Index: len(i.attempts)+1, Accepted: accepted, gate: make(chan struct{})}
	i.attempts = append(i.attempts, a)
	auto := i.autoRelease
	i.mu.Unlock()
	if auto { a.release() }
	select { case i.entered <- a: case <-r.Context().Done(): return }
	// Barrier is AFTER single-use issuer consumption and BEFORE its HTTP reply.
	select { case <-a.gate: case <-r.Context().Done(): return }
	if !accepted {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = io.WriteString(w, `{"error":"invalid_grant","error_description":"synthetic refresh credential revoked or already consumed"}`)
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]any{"access_token": i.token("A1"), "refresh_token": i.token("R1"), "id_token": i.idToken(), "token_type": "Bearer", "expires_in": 3600})
}

func (i *oauthLabIssuer) next(t *testing.T, ctx context.Context) *oauthLabAttempt {
	t.Helper()
	select { case a := <-i.entered: return a; case <-ctx.Done(): t.Fatal("issuer barrier not reached before bound"); return nil }
}
func (i *oauthLabIssuer) releaseAll() {
	i.mu.Lock(); defer i.mu.Unlock()
	i.autoRelease = true
	for _, a := range i.attempts { a.release() }
}

type oauthLabFixture struct {
	t *testing.T
	suite *oauthLabSuite
	ctx context.Context
	cancel context.CancelFunc
	issuer *oauthLabIssuer
	account *service.Account
	workers []*oauthLabProcess
	start time.Time
	barriers []string
}
func (s *oauthLabSuite) fixture(t *testing.T) *oauthLabFixture {
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	i := &oauthLabIssuer{suite: s, id: uuid.NewString(), entered: make(chan *oauthLabAttempt, 128)}
	i.server = httptest.NewServer(http.HandlerFunc(i.serve))
	f := &oauthLabFixture{t: t, suite: s, ctx: ctx, cancel: cancel, issuer: i, start: time.Now()}
	// Receipt is emitted after worker termination and before deletion. Assertions never rewrite state.
	t.Cleanup(f.close)
	a := &service.Account{Name: "oauth-lab-" + i.id, Platform: service.PlatformOpenAI, Type: service.AccountTypeOAuth, Credentials: i.credentials(false), Extra: map[string]any{}, Concurrency: 8, Priority: 1, Status: service.StatusActive, Schedulable: true}
	oauthLabNeed(t, s.repo.Create(ctx, a) == nil, "real PostgreSQL account creation failed")
	f.account = a
	return f
}
func (f *oauthLabFixture) row() *service.Account {
	f.t.Helper()
	a, err := f.suite.repo.GetByID(f.ctx, f.account.ID)
	oauthLabNeed(f.t, err == nil && a != nil, "durable account reread failed")
	return a
}
func (f *oauthLabFixture) scheduled() bool {
	f.t.Helper()
	rows, err := f.suite.repo.ListSchedulableByPlatform(f.ctx, service.PlatformOpenAI)
	oauthLabNeed(f.t, err == nil, "actual scheduling repository query failed")
	for _, row := range rows { if row.ID == f.account.ID { return true } }
	return false
}
func (f *oauthLabFixture) check(ok bool, name string) {
	f.t.Helper()
	if !ok { f.t.Error(name) }
}
func (f *oauthLabFixture) close() {
	if f.account == nil { f.issuer.releaseAll(); f.issuer.server.Close(); f.cancel(); return }
	f.issuer.releaseAll()
	for _, p := range f.workers { p.stop(f.t) }
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	f.issuer.mu.Lock()
	counts := map[string]int{"issuer_requests": len(f.issuer.attempts), "effective_rotations": f.issuer.rotations, "gateway_bearer_requests": f.issuer.resourceRequests, "malformed_token_requests": f.issuer.malformed}
	f.issuer.mu.Unlock()
	pids := []int{}
	events := []oauthLabEvent{}
	for _, p := range f.workers { pids = append(pids, p.cmd.Process.Pid); events = append(events, p.transcript...) }
	row, err := f.suite.repo.GetByID(ctx, f.account.ID)
	state := map[string]any{"reread_ok": err == nil && row != nil}
	if row != nil { state["access_phase"] = f.issuer.phase(row.GetCredential("access_token")); state["refresh_phase"] = f.issuer.phase(row.GetCredential("refresh_token")); state["status"] = row.Status; state["schedulable"] = row.Schedulable }
	if f.suite.issuerRequests.Load() > 128 { f.t.Error("suite issuer request budget exceeded") }
	f.issuer.server.Close()
	cleanupOK := true
	if e := NewGeminiTokenCache(f.suite.rdb).DeleteAccessToken(ctx, service.OpenAITokenCacheKey(f.account)); e != nil { cleanupOK = false }
	if e := NewGeminiTokenCache(f.suite.rdb).ReleaseRefreshLock(ctx, service.OpenAITokenCacheKey(f.account)); e != nil { cleanupOK = false }
	if e := NewSchedulerCache(f.suite.rdb).DeleteAccount(ctx, f.account.ID); e != nil { cleanupOK = false }
	_, e1 := f.suite.db.ExecContext(ctx, "DELETE FROM scheduler_outbox WHERE account_id = $1", f.account.ID)
	e2 := f.suite.client.Account.DeleteOneID(f.account.ID).Exec(ctx)
	cleanupOK = cleanupOK && e1 == nil && e2 == nil
	if !cleanupOK { f.t.Error("owned PostgreSQL/Redis fixture cleanup failed") }
	exitsOK := true
	for _, p := range f.workers { exitsOK = exitsOK && p.exitOK }
	status := "PASS"
	if f.t.Failed() { status = "FAIL" }
	receipt, _ := json.Marshal(map[string]any{"case_id": f.t.Name(), "synthetic_account_id": f.account.ID, "synthetic_identity_id": f.issuer.id, "status": status, "evidence_kind": "synthetic-http-real-postgresql-redis-two-process", "duration_ms": time.Since(f.start).Milliseconds(), "child_pids": pids, "child_exits_ok": exitsOK, "owned_cleanup_ok": cleanupOK, "counts": counts, "barriers": f.barriers, "durable_state": state, "events": events, "postgres_version": f.suite.pgVersion, "redis_version": f.suite.redisVersion, "go_version": runtime.Version(), "suite_issuer_requests": f.suite.issuerRequests.Load()})
	f.t.Log("OAUTH_LAB_RECEIPT " + string(receipt))
	f.cancel()
}

type oauthLabProcess struct {
	cmd *exec.Cmd
	stdin io.WriteCloser
	encoder *json.Encoder
	events chan oauthLabEvent
	pending []oauthLabEvent
	transcript []oauthLabEvent
	exit chan error
	cancel context.CancelFunc
	exitOK bool
}
func (f *oauthLabFixture) process(redisURL string, ttl time.Duration, ackFault bool) *oauthLabProcess {
	f.t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	cmd := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestOAuthLabProcess$", "-test.count=1", "-test.timeout=29s")
	// Explicit allowlist: no auth homes, parent provider environment, or proxy inheritance.
	cmd.Env = []string{"PATH=" + os.Getenv("PATH"), "TZ=UTC", "GOMAXPROCS=2", "OAUTH_LAB_ENABLE=" + oauthLabEnable, "OAUTH_LAB_CHILD=1", "OAUTH_LAB_PG_DSN=" + f.suite.dsn, "OAUTH_LAB_REDIS_URL=" + redisURL, "OAUTH_LAB_ISSUER_URL=" + f.issuer.server.URL, "OAUTH_LAB_ACCOUNT_ID=" + strconv.FormatInt(f.account.ID, 10), "OAUTH_LAB_ID=" + f.issuer.id, "OAUTH_LAB_TTL=" + ttl.String(), "OAUTH_LAB_ACK_FAULT=" + strconv.FormatBool(ackFault)}
	stdin, err := cmd.StdinPipe()
	oauthLabNeed(f.t, err == nil, "child input pipe unavailable")
	stdout, err := cmd.StdoutPipe()
	oauthLabNeed(f.t, err == nil, "child output pipe unavailable")
	cmd.Stderr = io.Discard
	p := &oauthLabProcess{cmd: cmd, stdin: stdin, encoder: json.NewEncoder(stdin), events: make(chan oauthLabEvent, 256), exit: make(chan error, 1), cancel: cancel}
	oauthLabNeed(f.t, cmd.Start() == nil, "child process launch failed")
	f.workers = append(f.workers, p)
	go func() {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			line := scanner.Text()
			if !strings.HasPrefix(line, oauthLabEventPrefix) { continue }
			var e oauthLabEvent
			if json.Unmarshal([]byte(strings.TrimPrefix(line, oauthLabEventPrefix)), &e) == nil { p.events <- e }
		}
		p.exit <- cmd.Wait()
		close(p.events)
	}()
	p.await(f.t, f.ctx, "ready", "")
	return p
}
func (p *oauthLabProcess) send(t *testing.T, c oauthLabCommand) {
	t.Helper()
	oauthLabNeed(t, p.encoder.Encode(c) == nil, "child command delivery failed")
}
func (p *oauthLabProcess) await(t *testing.T, ctx context.Context, kind, op string) oauthLabEvent {
	t.Helper()
	matches := func(e oauthLabEvent) bool { return e.Kind == kind && (op == "" || e.Op == op) }
	for idx, e := range p.pending {
		if matches(e) { p.pending = append(p.pending[:idx], p.pending[idx+1:]...); return e }
	}
	for {
		select {
		case e, ok := <-p.events:
			if !ok { t.Fatal("child ended before observable " + kind + " barrier"); return oauthLabEvent{} }
			p.transcript = append(p.transcript, e)
			if matches(e) { return e }
			p.pending = append(p.pending, e)
		case <-ctx.Done(): t.Fatal("bounded child observation expired before " + kind); return oauthLabEvent{}
		}
	}
}
func (p *oauthLabProcess) stop(t *testing.T) {
	t.Helper()
	_ = p.encoder.Encode(oauthLabCommand{Kind: "stop"})
	_ = p.stdin.Close()
	select {
	case err := <-p.exit:
		p.exitOK = err == nil
		if err != nil { t.Error("child did not terminate successfully") }
	case <-time.After(3*time.Second):
		p.cancel()
		<-p.exit
		t.Error("child required forced termination")
	}
	p.cancel()
	for e := range p.events { p.transcript = append(p.transcript, e) }
}

// Real TCP connection failure, confined to this fixture. No fake cache implementation.
func oauthLabRedisOutage(t *testing.T) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	oauthLabNeed(t, err == nil, "synthetic Redis fault listener unavailable")
	t.Cleanup(func() { _ = listener.Close() })
	go func() { for { conn, err := listener.Accept(); if err != nil { return }; _ = conn.Close() } }()
	return "redis://" + listener.Addr().String() + "/1"
}
