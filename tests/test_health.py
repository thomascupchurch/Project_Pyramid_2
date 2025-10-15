import json
from app import server

def test_health_ok():
    client = server.test_client()
    resp = client.get('/health')
    assert resp.status_code == 200
    data = json.loads(resp.data.decode('utf-8'))
    assert data.get('status') == 'ok'
