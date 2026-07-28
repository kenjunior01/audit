
import sqlite3
import os

db_path = 'db.sqlite3'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    tables_to_drop = ['dashboard_auditcaseattachment', 'dashboard_riskagent']
    for table in tables_to_drop:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"Dropped {table}")
        except Exception as e:
            print(f"Error dropping {table}: {e}")
    conn.commit()
    conn.close()
else:
    print("db.sqlite3 not found")
