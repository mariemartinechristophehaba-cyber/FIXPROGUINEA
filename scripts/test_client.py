from app import app
with app.test_client() as c:
    resp = c.get('/artisans')
    print('STATUS', resp.status_code)
    print(resp.data.decode()[:2000])
