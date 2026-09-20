"""
fix_admin_render.py
===================
Run this script to IMMEDIATELY fix the super admin login on the hosted Render DB.

HOW TO USE:
  1. Go to Render dashboard → your giotag-db Postgres → "Connect" tab
  2. Copy the "External Connection String" (starts with postgres://...)
  3. Paste it below as DATABASE_URL
  4. Run:  python fix_admin_render.py

This script will:
  - Find or CREATE the super admin user
  - Reset is_active = true
  - Clear deleted_at
  - Set role = SUPER_ADMIN
  - Reset password hash to match: Admin@123!

After running, login with:
  Email:    admin@giotag.gov
  Password: Admin@123!
"""

import sys
import os

# ─── PASTE YOUR RENDER POSTGRES CONNECTION STRING HERE ───────────────────────
# Example: postgres://giotaguser:xxxx@dpg-xxxx.oregon-postgres.render.com/giotag
DATABASE_URL = os.environ.get("DATABASE_URL", "")
# ─────────────────────────────────────────────────────────────────────────────

if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set!")
    print()
    print("Run like this:")
    print('  $env:DATABASE_URL="postgres://giotaguser:PASS@dpg-xxxx.oregon-postgres.render.com/giotag"')
    print("  python fix_admin_render.py")
    print()
    print("Or paste your connection string directly into this script at line 33.")
    sys.exit(1)

# Fix legacy postgres:// → postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"[INFO] Connecting to: {DATABASE_URL[:60]}...")

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=10)
    new_hash = pwd_context.hash("Admin@123!")
    print(f"[OK]  New bcrypt hash generated")
except ImportError:
    print("ERROR: passlib not installed. Run: pip install passlib[bcrypt]")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")
    conn.autocommit = False
    cur = conn.cursor()

    # ── Check current state ───────────────────────────────────────────────────
    cur.execute("""
        SELECT id, email, username, role, is_active, deleted_at
        FROM users
        WHERE email = 'admin@giotag.gov'
    """)
    row = cur.fetchone()

    if row:
        user_id, email, username, role, is_active, deleted_at = row
        print(f"\n[FOUND] Super admin exists:")
        print(f"  id         = {user_id}")
        print(f"  email      = {email}")
        print(f"  username   = {username}")
        print(f"  role       = {role}")
        print(f"  is_active  = {is_active}")
        print(f"  deleted_at = {deleted_at}")

        # ── Patch the existing account ────────────────────────────────────────
        cur.execute("""
            UPDATE users
            SET
                is_active        = true,
                deleted_at       = NULL,
                role             = 'SUPER_ADMIN',
                hashed_password  = %s,
                is_verified      = true
            WHERE email = 'admin@giotag.gov'
        """, (new_hash,))

        print("\n[FIX] Applied:")
        print("  ✓ is_active = true")
        print("  ✓ deleted_at = NULL")
        print("  ✓ role = SUPER_ADMIN")
        print("  ✓ hashed_password reset to: Admin@123!")

    else:
        print("\n[NOT FOUND] Super admin does not exist — creating it...")

        # We need a department_id
        cur.execute("SELECT id FROM departments WHERE code = 'ADMIN' LIMIT 1")
        dept_row = cur.fetchone()

        if not dept_row:
            import uuid
            dept_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO departments (id, name, code, description, is_active)
                VALUES (%s, 'Administration', 'ADMIN', 'Administrative staff', true)
            """, (dept_id,))
            print(f"  [CREATE] Department ADMIN created: {dept_id}")
        else:
            dept_id = dept_row[0]
            print(f"  [OK] Using existing department: {dept_id}")

        import uuid
        user_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO users (
                id, email, username, full_name, phone,
                hashed_password, role, department_id,
                is_active, is_verified, deleted_at
            ) VALUES (
                %s, 'admin@giotag.gov', 'superadmin', 'System Administrator', '+1-555-0100',
                %s, 'SUPER_ADMIN', %s,
                true, true, NULL
            )
        """, (user_id, new_hash, dept_id))
        print(f"  [CREATE] Super admin created: id={user_id}")

    conn.commit()
    print("\n" + "="*55)
    print("✅  SUCCESS! Super admin is now fixed.")
    print("="*55)
    print("  Email:    admin@giotag.gov")
    print("  Password: Admin@123!")
    print("="*55)

    # ── Verify ────────────────────────────────────────────────────────────────
    cur.execute("""
        SELECT email, role, is_active, deleted_at
        FROM users
        WHERE email = 'admin@giotag.gov'
    """)
    final = cur.fetchone()
    print(f"\n[VERIFY] Final state: {final}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    print("\nCommon fixes:")
    print("  - Make sure SSL is enabled: add ?sslmode=require to the URL")
    print("  - Check the connection string is the External URL (not Internal)")
    print("  - Ensure psycopg2-binary is installed: pip install psycopg2-binary")
    sys.exit(1)
