import os
import sys

from app import create_app


def main() -> int:
    os.environ.setdefault("WTF_CSRF_ENABLED", "false")
    os.environ.setdefault("AMW_FAST_PWHASH", "1")
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, LOGIN_DISABLED=False, AUTHZ_DISABLED=False)

    checks = []
    with app.test_client() as client:
        resp = client.get("/")
        checks.append(("anon_home_redirect", resp.status_code in (302, 401)))
        resp_api = client.get("/api/overview/summary")
        checks.append(("anon_api_401", resp_api.status_code == 401))

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("RBAC smoke failed:", ", ".join(failed))
        return 1
    print("RBAC smoke ok.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
