"""
Check admin user RBAC scoping - diagnose why admin sees zeros.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("ADMIN RBAC DIAGNOSTIC")
print("=" * 70)

# 1. Check admin user in database
print("\n[1] Checking admin user in database...")
try:
    from app.auth.models import User, get_session
    s = get_session()
    admin = s.query(User).filter_by(username='admin').first()
    if admin:
        print(f"    Username: {admin.username}")
        print(f"    Role: {admin.role}")
        print(f"    Sales Rep ID: {admin.sales_rep_id}")
        print(f"    First Name: {admin.first_name}")
        print(f"    Last Name: {admin.last_name}")
    else:
        print("    ERROR: Admin user not found!")
    s.close()
except Exception as e:
    print(f"    ERROR: {e}")

# 2. Test RBAC functions directly
print("\n[2] Testing RBAC functions with admin user...")
try:
    from app.core.rbac import roles_for, can_manage_visibility, scope_dataframe
    from app.auth.models import User, get_session

    s = get_session()
    admin = s.query(User).filter_by(username='admin').first()

    if admin:
        roles = roles_for(admin)
        print(f"    Roles detected: {roles}")
        print(f"    Can manage visibility: {can_manage_visibility(admin)}")

        # Check if admin is in the superuser set
        from app.core.rbac import _superuser_roles
        superusers = _superuser_roles()
        print(f"    Superuser roles configured: {superusers}")
        print(f"    Admin has superuser role: {bool(roles & superusers)}")
    s.close()
except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

# 3. Test data scoping
print("\n[3] Testing data scoping with admin user...")
try:
    import data_loader as loader
    from app.core.rbac import scope_dataframe
    from app.auth.models import User, get_session

    # Load data
    df = loader.get_fact_df()
    rows_before = len(df)
    print(f"    Rows before scoping: {rows_before:,}")

    # Get admin user
    s = get_session()
    admin = s.query(User).filter_by(username='admin').first()

    # Apply scoping
    scoped = scope_dataframe(df, admin)
    rows_after = len(scoped) if scoped is not None else 0
    print(f"    Rows after scoping: {rows_after:,}")

    if rows_after == 0 and rows_before > 0:
        print("    ERROR: Admin user is being filtered out!")
        print("    This is the root cause of the zeros issue.")
    elif rows_after == rows_before:
        print("    OK: Admin sees all data (no filtering)")
    else:
        print(f"    WARNING: Admin sees partial data ({rows_after}/{rows_before})")

    s.close()
except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

# 4. Check environment config
print("\n[4] Checking RBAC configuration...")
try:
    import os
    authz_disabled = os.getenv('AUTHZ_DISABLED', 'false').lower()
    login_disabled = os.getenv('LOGIN_DISABLED', 'false').lower()
    print(f"    AUTHZ_DISABLED: {authz_disabled}")
    print(f"    LOGIN_DISABLED: {login_disabled}")
except Exception as e:
    print(f"    ERROR: {e}")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
