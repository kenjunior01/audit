
import sqlite3
import os

db_path = 'audit_v2.db' # relative to C:\Users\data entry 5\Documents\trae_projects\audit\django_app ?
# Actually settings.py says os.path.join(os.path.dirname(BASE_DIR), 'audit_v2.db')
# BASE_DIR is django_app/auditportal
# dirname(BASE_DIR) is django_app
# So audit_v2.db is in django_app ?
# Wait, BASE_DIR = Path(__file__).resolve().parent.parent
# If settings.py is in auditportal/, parent is auditportal, parent.parent is django_app.
# So os.path.dirname(BASE_DIR) is ... wait.
# If BASE_DIR is django_app.
# dirname(BASE_DIR) is parent of django_app -> root.
# So audit_v2.db is in root?
# Let's check settings.py again.
# I will just try to find audit_v2.db in current dir or parent.

if os.path.exists('audit_v2.db'):
    conn = sqlite3.connect('audit_v2.db')
elif os.path.exists('../audit_v2.db'):
    conn = sqlite3.connect('../audit_v2.db')
else:
    print("audit_v2.db not found")
    exit(1)

cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for table in tables:
    print(table[0])
