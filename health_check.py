import urllib.request, json, sys

try:
    with urllib.request.urlopen("http://127.0.0.1:8001/api/health", timeout=5) as r:
        data = json.load(r)
    print(json.dumps(data, indent=2))
except Exception as e:
    print('ERROR:', e)
    sys.exit(2)
