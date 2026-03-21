import os, pandas as pd
from app import create_app

os.environ['ENV']='development'
os.environ['FLASK_ENV']='development'
os.environ['TESTING']='1'
os.environ['SECRET_KEY']='dev'
os.environ['SESSION_COOKIE_SECURE']='False'
os.environ['REMEMBER_COOKIE_SECURE']='False'
os.environ['PYTEST_CURRENT_TEST']='1'

# ensure sample parquet exists
start = pd.date_range(start='2023-01-01', periods=24, freq='M')
rows=[{'date':d,'product_id':'SKU-001','product_name':'Product SKU-001','customer_id':'ID-A','customer_name':'A','region':'North','supplier':'Supplier-1','order_id':f'ORD-{i}','qty':10,'weight':100,'revenue':1000,'discount':0} for i,d in enumerate(start)]
path=os.path.abspath('tmp_sales.parquet')
pd.DataFrame(rows).to_parquet(path)

os.environ['PRODUCTS_SALES_PARQUET']=path
app=create_app()
app.config.update(TESTING=True, LOGIN_DISABLED=True, AUTHZ_DISABLED=True, PRODUCTS_SALES_PARQUET=path)
client=app.test_client()
resp=client.get('/products/SKU-001/drilldown')
print('status', resp.status_code)
print(resp.data.decode('utf-8')[:800])
