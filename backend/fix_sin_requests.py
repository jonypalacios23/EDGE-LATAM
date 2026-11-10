import pathlib
p = pathlib.Path("backend/pipeline_dia.py")
t = p.read_text(encoding="utf-8")
# Quitamos requests y lo cambiamos por urllib, que ya viene instalado
t = t.replace("import json, pathlib, os, unicodedata, re, requests, time", "import json, pathlib, os, unicodedata, re, time, urllib.request, urllib.parse")
t = t.replace(
    'def api_get(endpoint, params):\n    r = requests.get(f"{BASE}/{endpoint}", headers=HEADERS, params=params, timeout=20)\n    return r.json().get("response", [])',
    '''def api_get(endpoint, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}/{endpoint}?{qs}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode()).get("response", [])'''
)
p.write_text(t, encoding="utf-8")
print("Parche listo: pipeline ya no necesita 'requests', usa lo que trae tu Mac")
