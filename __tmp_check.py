import os, traceback
os.environ['"'"'PRODUCTS_FORCE_PARQUET'"'"'] = '"'"'1'"'"'
from app import create_app
import app.auth.models as models

class Dummy:
    is_authenticated = True
    is_active = True
    role = '"'"'admin'"'"'
    def get_id(self):
        return '"'"'dummy'"'"'

dummy = Dummy()
models.get_user_by_id = lambda uid: dummy
app = create_app()
app.testing=True
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['_user_id'] = '"'"'dummy'"'"'
    resp = client.get('"'"'/products/api/overview'"'"')
    print('"'"'status'"'"', resp.status_code)
    print('"'"'location'"'"', resp.headers.get('"'"'Location'"'"'))
    print('"'"'data'"'"', resp.data[:200])
