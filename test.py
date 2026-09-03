import urllib.request, json, urllib.error
req = urllib.request.Request('http://localhost:5173/api/auth/login', data=json.dumps({'email':'admin@giotag.gov','password':'Admin@123!'}).encode(), headers={'Content-Type': 'application/json'})
try:
    print(urllib.request.urlopen(req).read().decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read())
