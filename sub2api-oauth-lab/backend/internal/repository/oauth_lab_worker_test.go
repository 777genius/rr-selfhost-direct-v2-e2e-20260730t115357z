//go:build oauthlab

package repository

import (
	"bufio"
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"entgo.io/ent/dialect"
	entsql "entgo.io/ent/dialect/sql"
	dbent "github.com/Wei-Shaw/sub2api/ent"
	"github.com/Wei-Shaw/sub2api/internal/config"
	"github.com/Wei-Shaw/sub2api/internal/service"
	"github.com/lib/pq"
	"github.com/redis/go-redis/v9"
)

// Observe actual Redis command results, without replacing locking or storage.
type oauthLabRedisObserver struct { emit func(oauthLabEvent) }
func (h oauthLabRedisObserver) DialHook(next redis.DialHook) redis.DialHook { return next }
func (h oauthLabRedisObserver) ProcessPipelineHook(next redis.ProcessPipelineHook) redis.ProcessPipelineHook { return next }
func (h oauthLabRedisObserver) ProcessHook(next redis.ProcessHook) redis.ProcessHook {
	return func(ctx context.Context, cmd redis.Cmder) error {
		err := next(ctx, cmd)
		args := cmd.Args()
		if cmd.Name() == "set" && len(args) > 1 && strings.HasPrefix(fmt.Sprint(args[1]), oauthRefreshLockKeyPrefix) {
			if err != nil && err != redis.Nil { h.emit(oauthLabEvent{Kind: "lock_error"}) } else if b, ok := cmd.(*redis.BoolCmd); ok {
				if b.Val() { h.emit(oauthLabEvent{Kind: "lock_acquired"}) } else { h.emit(oauthLabEvent{Kind: "lock_contended"}) }
			}
		}
		return err
	}
}

// The real background service exposes cycle completion through its structured log.
// All other log records and all attributes are discarded in this synthetic child.
type oauthLabCycleObserver struct { done chan struct{} }
func (h *oauthLabCycleObserver) Enabled(context.Context, slog.Level) bool { return true }
func (h *oauthLabCycleObserver) Handle(_ context.Context, r slog.Record) error {
	if r.Message == "token_refresh.cycle_completed" { select { case h.done <- struct{}{}: default: } }
	return nil
}
func (h *oauthLabCycleObserver) WithAttrs([]slog.Attr) slog.Handler { return h }
func (h *oauthLabCycleObserver) WithGroup(string) slog.Handler { return h }

// This is an explicitly injected test transport fault, not a repository stub:
// the actual PostgreSQL transaction commits durably, but the driver acknowledgement
// is hidden from the coordinator. The independent parent rereads the real row.
type oauthLabAckFault struct { used atomic.Bool; emit func(oauthLabEvent) }
type oauthLabConnector struct { driver.Connector; fault *oauthLabAckFault }
func (c oauthLabConnector) Connect(ctx context.Context) (driver.Conn, error) {
	conn, err := c.Connector.Connect(ctx)
	if err != nil { return nil, err }
	return &oauthLabConn{Conn: conn, fault: c.fault}, nil
}
type oauthLabConn struct { driver.Conn; fault *oauthLabAckFault }
func (c *oauthLabConn) Begin() (driver.Tx, error) {
	tx, err := c.Conn.Begin()
	if err != nil { return nil, err }
	return &oauthLabTx{Tx: tx, fault: c.fault}, nil
}
func (c *oauthLabConn) BeginTx(ctx context.Context, opts driver.TxOptions) (driver.Tx, error) {
	if next, ok := c.Conn.(driver.ConnBeginTx); ok {
		tx, err := next.BeginTx(ctx, opts)
		if err != nil { return nil, err }
		return &oauthLabTx{Tx: tx, fault: c.fault}, nil
	}
	if err := ctx.Err(); err != nil { return nil, err }
	if opts.Isolation != 0 || opts.ReadOnly { return nil, errors.New("unsupported synthetic transaction options") }
	return c.Begin()
}
func (c *oauthLabConn) ExecContext(ctx context.Context, q string, args []driver.NamedValue) (driver.Result, error) {
	if next, ok := c.Conn.(driver.ExecerContext); ok { return next.ExecContext(ctx, q, args) }
	return nil, driver.ErrSkip
}
func (c *oauthLabConn) QueryContext(ctx context.Context, q string, args []driver.NamedValue) (driver.Rows, error) {
	if next, ok := c.Conn.(driver.QueryerContext); ok { return next.QueryContext(ctx, q, args) }
	return nil, driver.ErrSkip
}
func (c *oauthLabConn) Ping(ctx context.Context) error {
	if next, ok := c.Conn.(driver.Pinger); ok { return next.Ping(ctx) }
	return ctx.Err()
}
type oauthLabTx struct { driver.Tx; fault *oauthLabAckFault }
func (tx *oauthLabTx) Commit() error {
	if err := tx.Tx.Commit(); err != nil { return err }
	if tx.fault.used.CompareAndSwap(false, true) {
		tx.fault.emit(oauthLabEvent{Kind: "db_commit_ack_lost"})
		return errors.New("synthetic committed PostgreSQL acknowledgement lost")
	}
	return nil
}

func TestOAuthLabProcess(t *testing.T) {
	if os.Getenv("OAUTH_LAB_CHILD") != "1" || os.Getenv("OAUTH_LAB_ENABLE") != oauthLabEnable {
		t.Skip("NOT RUN: helper process requires explicit synthetic configuration")
	}
	var outputMu sync.Mutex
	emit := func(e oauthLabEvent) {
		e.PID = os.Getpid()
		b, _ := json.Marshal(e)
		outputMu.Lock(); defer outputMu.Unlock()
		fmt.Println(oauthLabEventPrefix + string(b))
	}
	log.SetOutput(io.Discard)
	cycle := &oauthLabCycleObserver{done: make(chan struct{}, 4)}
	slog.SetDefault(slog.New(cycle))
	ctx, cancel := context.WithTimeout(context.Background(), 27*time.Second)
	defer cancel()
	issuerURL, err := url.Parse(os.Getenv("OAUTH_LAB_ISSUER_URL"))
	oauthLabNeed(t, err == nil && issuerURL.Scheme == "http" && net.ParseIP(issuerURL.Hostname()) != nil && net.ParseIP(issuerURL.Hostname()).IsLoopback() && issuerURL.User == nil, "child requires exact loopback synthetic issuer")
	id, err := strconv.ParseInt(os.Getenv("OAUTH_LAB_ACCOUNT_ID"), 10, 64)
	oauthLabNeed(t, err == nil && id > 0, "missing independent fixture account ID")
	ttl, err := time.ParseDuration(os.Getenv("OAUTH_LAB_TTL"))
	oauthLabNeed(t, err == nil && ttl > 0, "missing explicit synthetic lock TTL")
	var db *sql.DB
	var client *dbent.Client
	if os.Getenv("OAUTH_LAB_ACK_FAULT") == "true" {
		connector, e := pq.NewConnector(os.Getenv("OAUTH_LAB_PG_DSN"))
		oauthLabNeed(t, e == nil, "synthetic PostgreSQL connector initialization failed")
		db = sql.OpenDB(oauthLabConnector{Connector: connector, fault: &oauthLabAckFault{emit: emit}})
		client = dbent.NewClient(dbent.Driver(entsql.OpenDB(dialect.Postgres, db)))
	} else { db, client, err = oauthLabOpenDB(os.Getenv("OAUTH_LAB_PG_DSN")); oauthLabNeed(t, err == nil, "child PostgreSQL initialization failed") }
	defer func() { _ = client.Close() }()
	var dbName string
	err = db.QueryRowContext(ctx, "SELECT current_database()").Scan(&dbName)
	oauthLabNeed(t, err == nil && strings.HasPrefix(dbName, "oauth_lab_"), "child PostgreSQL isolation verification failed")
	rdb, err := oauthLabRedis(os.Getenv("OAUTH_LAB_REDIS_URL"))
	oauthLabNeed(t, err == nil, "child Redis configuration rejected")
	defer func() { _ = rdb.Close() }()
	rdb.AddHook(oauthLabRedisObserver{emit: emit})
	cache := NewGeminiTokenCache(rdb)
	schedulerCache := NewSchedulerCache(rdb)
	repo := NewAccountRepository(client, db, nil)
	// Existing same-package seam: the actual upstream HTTP issuer/parser is used.
	oauth := service.NewOpenAIOAuthService(nil, &openaiOAuthService{tokenURL: issuerURL.String() + "/token"})
	defer oauth.Stop()
	executor := service.NewOpenAITokenRefresher(oauth, repo)
	api := service.NewOAuthRefreshAPI(repo, cache, ttl)
	provider := service.NewOpenAITokenProvider(repo, cache, oauth)
	provider.SetRefreshAPI(api, executor)
	// Leave the actual upstream OpenAI refresh policy unchanged, including failures.
	gateway := service.NewOpenAIGatewayService(
		repo, // accountRepo
		nil, // usageLogRepo
		nil, // usageBillingRepo
		nil, // userRepo
		nil, // userSubRepo
		nil, // userGroupRateRepo
		nil, // cache
		&config.Config{}, // cfg
		nil, // schedulerSnapshot
		nil, // concurrencyService
		nil, // billingService
		nil, // rateLimitService
		nil, // billingCacheService
		nil, // httpUpstream: Forward is deliberately outside this auth-selection boundary
		nil, // deferredService
		provider,
		nil, // grokTokenProvider
		nil, // resolver
		nil, // channelService
		nil, // balanceNotifyService
		nil, // settingService
		nil, // userPlatformQuotaRepo
	)
	phase := func(token string) string {
		for _, p := range []string{"A0", "A1", "REAUTH"} { if token == "fabricated-oauth-lab-" + os.Getenv("OAUTH_LAB_ID") + "-" + p { return p } }
		if token == "" { return "empty" }; return "unknown"
	}
	httpClient := &http.Client{Timeout: 4*time.Second, Transport: &http.Transport{Proxy: nil}}
	defer httpClient.CloseIdleConnections()
	request := func(op string, account *service.Account, scheduled bool) {
		e := oauthLabEvent{Kind: "result", Op: op}
		if scheduled {
			rows, e1 := repo.ListSchedulableByPlatform(ctx, service.PlatformOpenAI)
			if e1 != nil { e.Error = true; emit(e); return }
			found := false
			for _, row := range rows { if row.ID == id { found = true; break } }
			if !found { e.Denied = true; emit(e); return }
		}
		token, mode, e1 := gateway.GetAccessToken(ctx, account)
		e.Phase = phase(token)
		if e1 != nil || mode != "oauth" { e.Error = true; emit(e); return }
		req, e1 := http.NewRequestWithContext(ctx, http.MethodGet, issuerURL.String() + "/resource", nil)
		if e1 != nil { e.Error = true; emit(e); return }
		req.Header.Set("Authorization", "Bearer " + token)
		resp, e1 := httpClient.Do(req)
		if e1 != nil { e.Error = true; emit(e); return }
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 2048)); _ = resp.Body.Close()
		e.HTTPStatus = resp.StatusCode
		emit(e)
	}
	load := func() *service.Account {
		account, e := repo.GetByID(ctx, id)
		oauthLabNeed(t, e == nil && account != nil, "child durable account read failed")
		return account
	}
	prepared := map[string][]*service.Account{}
	var work sync.WaitGroup
	var background *service.TokenRefreshService
	emit(oauthLabEvent{Kind: "ready"})
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		var cmd oauthLabCommand
		oauthLabNeed(t, json.Unmarshal(scanner.Bytes(), &cmd) == nil, "invalid synthetic child command")
		switch cmd.Kind {
		case "prepare":
			oauthLabNeed(t, cmd.Count > 0 && cmd.Count <= 8, "request batch outside bound")
			for n := 0; n < cmd.Count; n++ { prepared[cmd.Op] = append(prepared[cmd.Op], load()) }
			emit(oauthLabEvent{Kind: "prepared", Op: cmd.Op, Count: cmd.Count})
		case "release":
			accounts := prepared[cmd.Op]
			oauthLabNeed(t, len(accounts) > 0, "missing actual DB snapshot preparation")
			delete(prepared, cmd.Op)
			work.Add(1)
			go func(c oauthLabCommand, batch []*service.Account) {
				defer work.Done()
				var batchWG sync.WaitGroup
				start := make(chan struct{})
				for n, account := range batch {
					batchWG.Add(1)
					go func(n int, account *service.Account) { defer batchWG.Done(); <-start; request(c.Op + "-" + strconv.Itoa(n), account, c.Scheduled) }(n, account)
				}
				close(start)
				emit(oauthLabEvent{Kind: "released", Op: c.Op, Count: len(batch)})
				batchWG.Wait()
				emit(oauthLabEvent{Kind: "batch_done", Op: c.Op})
			}(cmd, accounts)
		case "request":
			account := load()
			work.Add(1)
			go func(c oauthLabCommand, a *service.Account) { defer work.Done(); request(c.Op, a, c.Scheduled) }(cmd, account)
		case "background":
			oauthLabNeed(t, background == nil, "background cycle may start only once per child")
			cfg := &config.Config{}
			cfg.TokenRefresh = config.TokenRefreshConfig{Enabled: true, CheckIntervalMinutes: 5, RefreshBeforeExpiryHours: 0.1, MaxRetries: 3, RetryBackoffSeconds: 1, CandidatePageSize: 8, ProviderConcurrency: 1, ProviderQPS: 16, ProviderFailureThreshold: 3, AttemptTimeoutSeconds: 5, CycleTimeoutSeconds: 12}
			background = service.NewTokenRefreshService(repo, nil, oauth, nil, nil, service.NewCompositeTokenCacheInvalidator(cache), schedulerCache, cfg, nil)
			background.SetRefreshAPI(api)
			background.Start()
			work.Add(1)
			go func(op string, bg *service.TokenRefreshService) {
				defer work.Done()
				select {
				case <-cycle.done:
					bg.Stop()
					emit(oauthLabEvent{Kind: "background_done", Op: op})
				case <-ctx.Done():
					bg.Stop()
					emit(oauthLabEvent{Kind: "background_done", Op: op, Error: true})
				}
			}(cmd.Op, background)
		case "stop":
			if background != nil { background.Stop() }
			work.Wait()
			emit(oauthLabEvent{Kind: "stopped"})
			return
		default: t.Fatal("unknown synthetic child command")
		}
	}
	if background != nil { background.Stop() }
	work.Wait()
}
