# Notifications & Alerts Runbook

## Flags

- `NOTIFICATIONS_ENABLED=1`: enables the user-facing `/notifications` page and the runner.
- `ADMIN_NOTIF_DEFAULTS=1`: exposes the read-only `/admin/notifications-defaults` catalog view.

## Safe rollout

1. Deploy the app code and let startup run the additive auth DB migrations.
2. Set `NOTIFICATIONS_ENABLED=1`.
3. Restart `amw_analytics.service`.
4. Leave `amw_analytics-alerts.timer` disabled at first.
5. Run `python scripts/alerts_runner.py --dry-run`.
6. Run `python scripts/alerts_runner.py` once after confirming SMTP and user preferences.
7. Enable and start `amw_analytics-alerts.timer`.

## Rollback

1. Set `NOTIFICATIONS_ENABLED=0`.
2. Disable `amw_analytics-alerts.timer`.
3. Stop `amw_analytics-alerts.service` if it is running.
4. Restart `amw_analytics.service`.

The DB tables are additive and can remain in place safely during rollback.
