import traceback
from app import create_app
from types import SimpleNamespace
import pandas as pd

app = create_app()
app.config['TESTING'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True
app.config['LOGIN_DISABLED'] = True

# Prepare fake user and fake loader
_sales_user = SimpleNamespace(
    username='sales.alex', role='sales', sales_rep_id='GUID-1', region_id=None, is_authenticated=True, get_id=lambda: 'sales.alex'
)

# Monkeypatch rbac current_user
from app.core import rbac
rbac.current_user = _sales_user
# Monkeypatch flask_login._get_user
import flask_login.utils as fl_utils
fl_utils._get_user = lambda: _sales_user

# Monkeypatch data_loader.get_dataframe_for_user
import data_loader as loader

def _fake_df(**kw):
    return pd.DataFrame([{
        'OrderId':'O1','OrderLineId':'L1','SalesRepId':'GUID-1','SalesRepName':'Alex',
        'ProductId':'P1','ProductName':'Chicken Breast','Revenue':100.0,'Profit':25.0,'ShipDate':'2024-01-01','QuantityShipped':10,'OrderStatus':'Shipped'
    }])
    # Simulate test-level patch first
    loader.get_dataframe_for_user = _fake_df

    # Then simulate autouse fixture that may run afterwards and override to an empty DataFrame
    loader.get_dataframe_for_user = (lambda *args, **kwargs: pd.DataFrame())

# Make request
client = app.test_client()
try:
    resp = client.get('/sales/rep')
    print('STATUS', resp.status_code)
    data = resp.get_data(as_text=True)
    print('LEN HTML', len(data))
    print(data[:4000])
except Exception as e:
    print('EXCEPTION RAISED')
    traceback.print_exc()
