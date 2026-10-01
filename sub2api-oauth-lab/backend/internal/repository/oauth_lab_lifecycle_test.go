//go:build oauthlab

package repository

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/service"
)

func (f *oauthLabFixture) prepare(p *oauthLabProcess, op string, n int) {
	p.send(f.t, oauthLabCommand{Kind: "prepare", Op: op, Count: n})
	e := p.await(f.t, f.ctx, "prepared", op)
	f.check(e.Count == n, "all request snapshots must be read from actual PostgreSQL before release")
	f.barriers = append(f.barriers, "postgres_snapshots_prepared:" + op)
}
func (f *oauthLabFixture) release(p *oauthLabProcess, op string) {
	p.send(f.t, oauthLabCommand{Kind: "release", Op: op})
	p.await(f.t, f.ctx, "released", op)
}
func (f *oauthLabFixture) results(p *oauthLabProcess, op string, n int) []oauthLabEvent {
	out := []oauthLabEvent{}
	for k := 0; k < n; k++ { out = append(out, p.await(f.t, f.ctx, "result", fmt.Sprintf("%s-%d", op, k))) }
	p.await(f.t, f.ctx, "batch_done", op)
	return out
}
func (f *oauthLabFixture) request(p *oauthLabProcess, op string, scheduled bool) oauthLabEvent {
	p.send(f.t, oauthLabCommand{Kind: "request", Op: op, Scheduled: scheduled})
	return p.await(f.t, f.ctx, "result", op)
}
func (f *oauthLabFixture) rotated() {
	row := f.row()
	f.check(f.issuer.phase(row.GetCredential("access_token")) == "A1", "durable access credential must be the rotated issuer result")
	f.check(f.issuer.phase(row.GetCredential("refresh_token")) == "R1", "durable refresh credential must be the single-use successor")
	f.check(row.GetCredential("email") == f.issuer.id + "@oauth-lab.invalid" && row.GetCredential("chatgpt_account_id") == f.issuer.id && row.GetCredential("plan_type") == "synthetic-plan", "real ID-token parser must preserve fabricated issuer identity fields")
	expires := row.GetCredentialAsTime("expires_at")
	f.check(expires != nil && time.Until(*expires) > 50*time.Minute, "actual OAuth response expires_in must become a usable persisted expiration")
	f.check(row.GetCredentialAsInt64("_token_version") > 0, "rotated credentials need a persisted version")
}
func (f *oauthLabFixture) accepted(e oauthLabEvent, phase string) {
	f.check(!e.Error && !e.Denied && e.Phase == phase && e.HTTPStatus == 200, "actual gateway auth selector and synthetic HTTP resource must agree on " + phase)
}
func (f *oauthLabFixture) counts(requests, rotations int) {
	f.issuer.mu.Lock(); defer f.issuer.mu.Unlock()
	f.check(len(f.issuer.attempts) == requests, "issuer request count violates single-use refresh contract")
	f.check(f.issuer.rotations == rotations, "effective issuer rotation count violates single-use refresh contract")
	f.check(f.issuer.malformed == 0, "actual OAuth client sent malformed synthetic issuer form")
}
func (f *oauthLabFixture) background(p *oauthLabProcess, op string) {
	p.send(f.t, oauthLabCommand{Kind: "background", Op: op})
}
func (f *oauthLabFixture) backgroundDone(p *oauthLabProcess, op string) {
	e := p.await(f.t, f.ctx, "background_done", op)
	f.check(!e.Error, "actual background service did not complete its bounded cycle")
	f.barriers = append(f.barriers, "actual_background_cycle_completed:" + op)
}
func (f *oauthLabFixture) redisBarrier(ctx context.Context, predicate func() bool, label string) {
	f.t.Helper()
	ticker := time.NewTicker(10*time.Millisecond)
	defer ticker.Stop()
	for {
		if predicate() { f.barriers = append(f.barriers, label); return }
		select { case <-ticker.C: case <-ctx.Done(): f.t.Fatal("actual Redis state barrier not reached: " + label) }
	}
}

func TestOAuthLabLifecycle(t *testing.T) {
	s := oauthLabSetup(t)

	// Red: split coordinators both consume R0, lose R1, or select expired A0.
	t.Run("normal_8_concurrent", func(t *testing.T) {
		f := s.fixture(t)
		p1, p2 := f.process(s.redisURL, 60*time.Second, false), f.process(s.redisURL, 60*time.Second, false)
		f.prepare(p1, "left", 4); f.prepare(p2, "right", 4)
		f.release(p1, "left")
		a := f.issuer.next(t, f.ctx)
		f.check(a.Accepted, "first synthetic rotation must consume R0 exactly once")
		f.release(p2, "right")
		p2.await(t, f.ctx, "lock_contended", "")
		f.barriers = append(f.barriers, "issuer_consumed_R0", "other_process_actual_redis_contention")
		a.release()
		for _, e := range append(f.results(p1, "left", 4), f.results(p2, "right", 4)...) { f.accepted(e, "A1") }
		f.rotated()
		f.accepted(f.request(p2, "subsequent", true), "A1")
		f.counts(1, 1)
	})

	// Red: the real startup background cycle and request path use separate locks,
	// or an old request snapshot republishes A0 after the background rotated it.
	for _, backgroundFirst := range []bool{true, false} {
		name := "background_then_request"
		if !backgroundFirst { name = "request_then_background" }
		t.Run(name, func(t *testing.T) {
			f := s.fixture(t)
			p1, p2 := f.process(s.redisURL, 60*time.Second, false), f.process(s.redisURL, 60*time.Second, false)
			if backgroundFirst {
				f.prepare(p2, "request", 1)
				f.background(p1, "background")
				a := f.issuer.next(t, f.ctx)
				f.release(p2, "request")
				p2.await(t, f.ctx, "lock_contended", "")
				f.barriers = append(f.barriers, "background_issuer_inflight", "request_actual_redis_contention")
				a.release()
				f.backgroundDone(p1, "background")
				f.accepted(f.results(p2, "request", 1)[0], "A1")
			} else {
				f.prepare(p1, "request", 1); f.release(p1, "request")
				a := f.issuer.next(t, f.ctx)
				f.background(p2, "background")
				p2.await(t, f.ctx, "lock_contended", "")
				f.backgroundDone(p2, "background")
				f.barriers = append(f.barriers, "request_issuer_inflight", "background_actual_redis_contention")
				a.release()
				f.accepted(f.results(p1, "request", 1)[0], "A1")
			}
			f.rotated()
			f.accepted(f.request(p2, "subsequent", true), "A1")
			f.counts(1, 1)
		})
	}

	// Red: unconditional OpenAI UpdateCredentials overwrites a reconnect completed
	// after refresh started; background cache publication then restores that stale identity.
	t.Run("reconnect_while_refresh", func(t *testing.T) {
		f := s.fixture(t)
		p1, p2 := f.process(s.redisURL, 60*time.Second, false), f.process(s.redisURL, 60*time.Second, false)
		f.background(p1, "background")
		a := f.issuer.next(t, f.ctx)
		f.check(a.Accepted, "rotation must precede reconnect barrier")
		updater, ok := s.repo.(interface { UpdateCredentials(context.Context, int64, map[string]any) error })
		oauthLabNeed(t, ok, "real repository credential-update capability missing")
		oauthLabNeed(t, updater.UpdateCredentials(f.ctx, f.account.ID, f.issuer.credentials(true)) == nil, "real reconnect persistence failed")
		reconnected := f.row()
		oauthLabNeed(t, f.issuer.phase(reconnected.GetCredential("refresh_token")) == "REAUTH_REFRESH", "reconnect durable barrier failed")
		oauthLabNeed(t, service.NewCompositeTokenCacheInvalidator(NewGeminiTokenCache(s.rdb)).InvalidateToken(f.ctx, reconnected) == nil, "reconnect cache invalidation failed")
		oauthLabNeed(t, NewSchedulerCache(s.rdb).SetAccount(f.ctx, reconnected) == nil, "reconnect scheduler publication failed")
		f.barriers = append(f.barriers, "issuer_consumed_R0", "postgres_reconnect_committed", "redis_reconnect_published")
		a.release()
		f.backgroundDone(p1, "background")
		row := f.row()
		f.check(f.issuer.phase(row.GetCredential("refresh_token")) == "REAUTH_REFRESH", "FAIL: stale refresh overwrote durable reauthorization")
		cached, err := NewSchedulerCache(s.rdb).GetAccount(f.ctx, f.account.ID)
		f.check(err == nil && cached != nil && f.issuer.phase(cached.GetCredential("access_token")) == "REAUTH", "FAIL: stale refresh republished scheduler identity over reconnect")
		f.accepted(f.request(p2, "subsequent", true), "REAUTH")
		f.counts(1, 1)
	})

	// Red: post-refresh stale active snapshot re-enables a disabled account in Redis,
	// even when credentials-only persistence leaves the durable disabled row intact.
	t.Run("disable_while_refresh", func(t *testing.T) {
		f := s.fixture(t)
		p1, p2 := f.process(s.redisURL, 60*time.Second, false), f.process(s.redisURL, 60*time.Second, false)
		f.background(p1, "background")
		a := f.issuer.next(t, f.ctx)
		row := f.row(); row.Status = service.StatusDisabled; row.Schedulable = false
		oauthLabNeed(t, s.repo.Update(f.ctx, row) == nil, "real repository disable failed")
		disabled := f.row()
		oauthLabNeed(t, !disabled.IsActive() && !disabled.Schedulable && !f.scheduled(), "disable durable scheduling barrier failed")
		oauthLabNeed(t, NewSchedulerCache(s.rdb).SetAccount(f.ctx, disabled) == nil, "real Redis disabled scheduler publication failed")
		f.barriers = append(f.barriers, "issuer_rotation_inflight", "postgres_disable_committed", "redis_disable_published")
		a.release()
		f.backgroundDone(p1, "background")
		row = f.row()
		f.check(!row.IsActive() && !row.Schedulable && !f.scheduled(), "disabled account must remain excluded by actual repository scheduling")
		cached, err := NewSchedulerCache(s.rdb).GetAccount(f.ctx, f.account.ID)
		f.check(err == nil && (cached == nil || !cached.IsActive() || !cached.Schedulable), "FAIL: stale background refresh republished an active schedulable Redis account")
		e := f.request(p2, "new_work", true)
		f.check(e.Denied && e.HTTPStatus == 0, "disabled account must deny new synthetic gateway bearer work")
		f.counts(1, 1)
	})

	// Red: expired lease permits another R0 attempt; the previous owner DEL then
	// destroys a still-live successor lease. Lease expiry is observed from Redis.
	t.Run("lock_ttl_expiry", func(t *testing.T) {
		f := s.fixture(t)
		p1, p2 := f.process(s.redisURL, 700*time.Millisecond, false), f.process(s.redisURL, 20*time.Second, false)
		f.prepare(p1, "first", 1); f.prepare(p2, "successor", 1)
		f.release(p1, "first")
		a := f.issuer.next(t, f.ctx)
		key := oauthRefreshLockKeyPrefix + service.OpenAITokenCacheKey(f.account)
		remaining, err := s.rdb.PTTL(f.ctx, key).Result()
		oauthLabNeed(t, err == nil && remaining > 0, "first real Redis lease must be observed live")
		f.redisBarrier(f.ctx, func() bool { ttl, err := s.rdb.PTTL(f.ctx, key).Result(); return err == nil && ttl == -2*time.Nanosecond }, "actual_first_redis_lease_expired")
		f.release(p2, "successor")
		b := f.issuer.next(t, f.ctx)
		p2.await(t, f.ctx, "lock_acquired", "")
		remaining, err = s.rdb.PTTL(f.ctx, key).Result()
		oauthLabNeed(t, err == nil && remaining > 10*time.Second, "successor lease live barrier failed")
		f.barriers = append(f.barriers, "successor_issuer_attempt_held", "successor_redis_lease_observed_live")
		f.check(!b.Accepted, "single-use issuer must refuse second R0 consumption")
		a.release()
		f.accepted(f.results(p1, "first", 1)[0], "A1")
		remaining, err = s.rdb.PTTL(f.ctx, key).Result()
		f.check(err == nil && remaining > 0, "FAIL: old refresh owner erased a successor Redis lease")
		b.release()
		f.accepted(f.results(p2, "successor", 1)[0], "A1")
		f.rotated()
		f.accepted(f.request(p2, "subsequent", true), "A1")
		f.counts(1, 1) // A second request with consumed R0 is itself a regression.
	})

	// Red: removing the local coordinator mutex allows 8 attempts despite real
	// Redis connection errors; local serialization must still publish R1 once.
	t.Run("redis_outage_process_local_8", func(t *testing.T) {
		f := s.fixture(t)
		outage := oauthLabRedisOutage(t)
		p1, p2 := f.process(outage, 60*time.Second, false), f.process(outage, 60*time.Second, false)
		f.prepare(p1, "batch", 8); f.release(p1, "batch")
		a := f.issuer.next(t, f.ctx)
		p1.await(t, f.ctx, "lock_error", "")
		f.barriers = append(f.barriers, "actual_redis_tcp_failure", "issuer_rotation_inflight")
		a.release()
		for _, e := range f.results(p1, "batch", 8) { f.accepted(e, "A1") }
		f.rotated()
		f.accepted(f.request(p2, "subsequent", true), "A1")
		f.counts(1, 1)
	})

	// Red: per-instance local mutexes cannot serialize across separate processes
	// when Redis is unreachable. Record this actual race as FAIL, never mock green.
	t.Run("redis_outage_two_process_race", func(t *testing.T) {
		f := s.fixture(t)
		outage := oauthLabRedisOutage(t)
		p1, p2 := f.process(outage, 60*time.Second, false), f.process(outage, 60*time.Second, false)
		f.prepare(p1, "first", 1); f.prepare(p2, "other", 1)
		f.release(p1, "first")
		a := f.issuer.next(t, f.ctx)
		p1.await(t, f.ctx, "lock_error", "")
		f.release(p2, "other")
		b := f.issuer.next(t, f.ctx)
		p2.await(t, f.ctx, "lock_error", "")
		f.barriers = append(f.barriers, "both_processes_actual_redis_failure", "both_processes_issuer_attempt_inflight")
		b.release()
		e := f.results(p2, "other", 1)[0]
		f.check(e.Error && e.HTTPStatus == 0, "FAIL: cross-process refresh race fell back to stale synthetic bearer")
		a.release()
		f.accepted(f.results(p1, "first", 1)[0], "A1")
		f.rotated()
		f.accepted(f.request(p2, "subsequent", true), "A1")
		f.counts(1, 1)
	})

	// Red: request-path invalid_grant is swallowed by OpenAI's fallback policy,
	// leaving the revoked account schedulable and selecting A0 for new work.
	for _, background := range []bool{false, true} {
		name := "revocation_request_path"
		if background { name = "revocation_background_path" }
		t.Run(name, func(t *testing.T) {
			f := s.fixture(t)
			f.issuer.mu.Lock(); f.issuer.revoked = true; f.issuer.mu.Unlock()
			p1, p2 := f.process(s.redisURL, 60*time.Second, false), f.process(s.redisURL, 60*time.Second, false)
			if background { f.background(p1, "background") } else { f.prepare(p1, "request", 1); f.release(p1, "request") }
			a := f.issuer.next(t, f.ctx)
			f.check(!a.Accepted, "revoked single-use issuer must return invalid_grant")
			f.barriers = append(f.barriers, "issuer_confirmed_invalid_grant")
			a.release()
			if background { f.backgroundDone(p1, "background") } else {
				e := f.results(p1, "request", 1)[0]
				f.check(e.Error && e.HTTPStatus == 0, "FAIL: confirmed revocation selected a stale gateway bearer")
			}
			f.check(!f.scheduled(), "FAIL: confirmed revoked account remains in actual scheduling repository")
			f.issuer.releaseAll() // Any erroneous automatic/new-work attempt is answered, never hidden by a hang.
			e := f.request(p2, "new_work", true)
			f.check(e.Denied && e.HTTPStatus == 0, "confirmed revocation must deny new gateway bearer work before issuer/resource effects")
			f.counts(1, 0)
			f.issuer.mu.Lock(); resources := f.issuer.resourceRequests; f.issuer.mu.Unlock()
			f.check(resources == 0, "revoked identity must not be sent to the synthetic gateway resource")
		})
	}

	// Red: swallowing a real commit acknowledgement loss causes replay of consumed
	// R0 or false non-durable success. Independent PostgreSQL reread must show R1.
	t.Run("issuer_rotation_lost_db_commit_ack", func(t *testing.T) {
		f := s.fixture(t)
		p1, p2 := f.process(s.redisURL, 60*time.Second, true), f.process(s.redisURL, 60*time.Second, false)
		f.background(p1, "background")
		a := f.issuer.next(t, f.ctx)
		f.issuer.releaseAll()
		a.release()
		p1.await(t, f.ctx, "db_commit_ack_lost", "")
		f.backgroundDone(p1, "background")
		f.barriers = append(f.barriers, "issuer_consumed_R0", "actual_postgresql_commit_ack_hidden", "independent_postgresql_reread")
		f.rotated()
		f.check(f.scheduled(), "durably rotated identity must not be falsely revoked by a lost acknowledgement")
		f.accepted(f.request(p2, "subsequent", true), "A1")
		f.counts(1, 1)
	})

	// Red: actual PostgreSQL credential-write rejection AFTER R0 was consumed
	// triggers a background retry with that same R0. A trigger causes a real DB
	// failure; no stub, imaginary commit, or fabricated durable state is involved.
	t.Run("issuer_rotation_db_write_rejected", func(t *testing.T) {
		f := s.fixture(t)
		name := "oauth_lab_reject_" + strings.ReplaceAll(f.issuer.id, "-", "")
		functionDDL := fmt.Sprintf("CREATE FUNCTION %s() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id = %d AND NEW.credentials IS DISTINCT FROM OLD.credentials THEN RAISE EXCEPTION 'synthetic credential write rejected'; END IF; RETURN NEW; END $$", name, f.account.ID)
		_, err := s.db.ExecContext(f.ctx, functionDDL)
		oauthLabNeed(t, err == nil, "owned PostgreSQL fault function creation failed")
		t.Cleanup(func() { ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second); defer cancel(); _, e := s.db.ExecContext(ctx, "DROP FUNCTION IF EXISTS " + name + "() CASCADE"); if e != nil { t.Error("owned PostgreSQL fault cleanup failed") } })
		_, err = s.db.ExecContext(f.ctx, "CREATE TRIGGER " + name + " BEFORE UPDATE OF credentials ON accounts FOR EACH ROW EXECUTE FUNCTION " + name + "()")
		oauthLabNeed(t, err == nil, "owned PostgreSQL rejection trigger creation failed")
		p1, p2 := f.process(s.redisURL, 60*time.Second, false), f.process(s.redisURL, 60*time.Second, false)
		f.background(p1, "background")
		a := f.issuer.next(t, f.ctx)
		f.check(a.Accepted, "issuer must consume R0 before the real PostgreSQL write fault")
		f.barriers = append(f.barriers, "issuer_consumed_R0", "real_postgresql_rejection_trigger_installed")
		f.issuer.releaseAll()
		f.backgroundDone(p1, "background")
		row := f.row()
		f.check(f.issuer.phase(row.GetCredential("refresh_token")) == "R0", "rejected DB write must not fabricate persistence of R1")
		f.check(!f.scheduled(), "uncertain consumed refresh credential must be contained before new gateway work")
		e := f.request(p2, "new_work", true)
		f.check(e.Denied && e.HTTPStatus == 0, "consumed uncertain refresh must deny subsequent gateway work")
		f.counts(1, 1) // Any automatic issuer retry with consumed R0 makes this red.
	})
}
