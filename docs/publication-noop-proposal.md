# Unchanged-output publication proposal — approval required

Status: design and offline tests only. Production does not import the prototype.
The existing publisher, public source grants and 18:00 / 18:15 / 18:30 KST
schedule are unchanged by this PR.

## Observed behavior

The second and third scheduled runs on October 28–30, 2026 each committed
only `data/public-market.json.checkedAt`. Existing reports, original manuscripts,
archive dates and latest-report links did not change. All nine runs passed
23 Python tests and deployed successfully. This is redundant publication,
not a duplicate dated report.

## Proposed decision

After public validation/build in each disposable worktree, compare the complete
publication output map against the latest main. Ignore only a valid top-level
`checkedAt` value in `data/public-market.json`. If all substantive outputs are
unchanged, restore that JSON from the baseline and return `changed=false`.
Otherwise retain the current bounded fast-forward commit/push procedure.
On a push race, rebuild and compare again against the newly fetched main.

The standalone `experiments/publication_noop_proposal.py` models that comparison.
It has no CLI, workflow import, network calls, writes, source activation, or
connection to the production publisher. Its test simulates three scheduled
attempts producing one publication. Other tests ensure quote/date/status,
permission fields, archive changes, added/removed files and malformed data
cannot be suppressed as timestamp-only changes.

## Time meanings and observability

- Last check attempt: record UTC/KST attempt time, trigger cron, workflow creation
  time, actual job start, resulting `changed`/`unchanged` decision, and published
  revision in Actions logs or summaries. Do not log market responses or secrets.
- Public JSON `checkedAt`: under the proposal this remains the check associated
  with the last published snapshot; it no longer claims to represent every retry.
  The UI label is “데이터 상태 확인”. Do not call it the last scheduled check.
- Last publication: use the successful publication commit and Pages deployment
  time. A future explicit `publishedAt` field must be assigned only after deciding
  to publish, or it would itself create perpetual differences. No field is added
  to the production schema in this PR.

## Deployment and race risks

Skipping the commit alone is insufficient: the workflow currently uploads and
deploys on every successful run. A separately approved implementation must pass
`changed` and the published SHA as job outputs, then skip upload/deploy only if
the same revision is already successfully deployed. A failed deployment followed
by an unchanged build must still retry deployment. Inspecting only `changed`
would otherwise strand a generated report that never reached Pages.

Keep the shared concurrency group and non-cancelling publication behavior.
Never suppress validation failures or meaningful state changes (including a
source becoming unavailable or an approval being withdrawn). Preserve public
grant validation before staging and compare the entire output set. Add tests
for a racing editor, failed deployment recovery, first publication, changed
report/quote/status, unchanged retry and restored invalid snapshots before
activating the workflow gate.

## Execution timing limitation

On November 2 at 17:47 KST no scheduled run existed yet; all three requested
times were still in the future. October 28–30 run creation preceded runner start
by only 2–3 seconds. Ordered correspondence to the three cron entries suggests
roughly 39–47 minutes of upstream scheduling delay, but the triggering cron was
not logged, so exact per-cron attribution and GitHub's internal cause are not
proven. Add safe trigger/time metadata before claiming exact latency metrics.
