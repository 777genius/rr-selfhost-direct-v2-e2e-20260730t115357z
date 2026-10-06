Offline source producer; controller owns Go/race/netHTTP/image, runtime faults and independent critical review. Normal scanner MUST stay ON. Package <=60 plain files, no source waiver.

Regenerate/check the package:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-native-merged/build.py
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-native-merged/seal.py
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-native-merged/verify.py
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-native-merged/seal.py
```

Prepare an exact original combined source (the backend under supplied `original-inputs/original-inputs/actual-source`, NOT the already merged `actual-source`) in a new external output:

```sh
python3 sub2api-native-merged/prepare.py --source /absolute/exact-original-combined-source --out /tmp/native-merged-w3-green
```

Public route remains exact official Wei-Shaw/sub2api 96f4c115c9749078f90cbf210a01d39baf3f53b6 (v0.2.11), no worker download/Git authentication:

```sh
python3 sub2api-native-merged/prepare.py --source /absolute/official-96f4-source --source-kind official --out /tmp/native-merged-w3-public
```

Both routes hash-check every backend file, apply canonical patches only when required, then apply production/regression. `--production-only` omits the new regression overlay. `W2-to-W3.patch` is an alternative exact patch for the actual supplied merged W2 tree only; do not apply the full production overlay there. Fullsource ledgers and all patch pins remain mandatory. Existing output/wrong bytes/extra source/symlinks/fuzz/offset/duplicate application are rejected. Source is read only.

Controller commands (not run by worker), with absolute pinned Go executable/cache and fresh external receipt directory:

```sh
for suite in memory cancel35 gaps interaction native probe nearest; do
  python3 sub2api-native-merged/run-controller.py --suite "$suite" --tree /tmp/native-merged-w3-green --go "$NATIVE_MERGED_GO" --gomodcache "$NATIVE_MERGED_MODCACHE" --out /tmp/native-merged-w3-receipts
  python3 sub2api-native-merged/run-controller.py --suite "$suite" --race --tree /tmp/native-merged-w3-green --go "$NATIVE_MERGED_GO" --gomodcache "$NATIVE_MERGED_MODCACHE" --out /tmp/native-merged-w3-receipts
done
```

Required original counts remain memory35, cancel35, native292, probe63; zero skips. Gaps require the four original W3 roots/all cases with exactly the approved c43c856 intcast. Interaction requires its one repaired real-transport contract. Receipts verify full trees before/after and retain raw JSONL/failures. Supplied standalone W3 527 PASS and memory W2 35 PASS are history, not merged evidence.

Prepare TWO additional fresh outputs with the same prepare CLI, `/tmp/native-merged-w3-replay-red` and `/tmp/native-merged-w3-drain-red`. Apply ONLY the named source fault to each; tests remain identical:

```sh
(cd /tmp/native-merged-w3-replay-red && patch --batch --fuzz=0 -p1 -i /absolute/package/sub2api-native-merged/interaction-replay-loss.RED-only.patch)
(cd /tmp/native-merged-w3-drain-red && patch --batch --fuzz=0 -p1 -i /absolute/package/sub2api-native-merged/default-drain-loss.RED-only.patch)
python3 sub2api-native-merged/run-controller.py --suite interaction-red --tree /tmp/native-merged-w3-replay-red --go "$NATIVE_MERGED_GO" --gomodcache "$NATIVE_MERGED_MODCACHE" --out /tmp/native-merged-w3-red-receipts
python3 sub2api-native-merged/run-controller.py --suite default-drain-red --tree /tmp/native-merged-w3-drain-red --go "$NATIVE_MERGED_GO" --gomodcache "$NATIVE_MERGED_MODCACHE" --out /tmp/native-merged-w3-red-receipts
```

Replay RED requires the specific held-forward behavioral oracle failure, after the fixture proves actual spool/comment replay AND confirms a live held body Read, live caller, held server/body and one dispatch/effect. The SSE blank separator is held upstream; it cannot trigger the intact next-iteration disconnect guard. Drain RED requires exactly the old two default boundary failures plus parent and the actual billing/held-release messages. Build/setup failures, skips and unrelated timing failures cannot count as RED. Pair with identical-test GREEN and race on unmutated W3, then independent critical review of exact hashes and receipts.

Controller must bind final source/image to official parent, canonical/production/regression hashes; run netHTTP/load/fault/billing and real Redis account/user slot/waiter cleanup plus genuine protected canaries. Retain failures. No deployed stability/live provider/five-second RSS return/indefinite reliability claim. OAuth/migrations remain another lane. Producer stops after bounded patch handoff.
