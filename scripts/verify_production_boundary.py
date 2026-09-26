"""Bounded, classified public boundary check; no nested curl retries."""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def classify(status, body, version, commit=None):
    if status == 429:
        return 'EXTERNAL_RATE_LIMIT'
    if status != 200:
        return 'EXTERNAL_SERVICE_UNAVAILABLE'
    if not isinstance(body, dict) or 'version' not in body:
        return 'MALFORMED_HEALTH_RESPONSE'
    if body['version'] != version or (commit and body.get('release_commit') != commit):
        return 'PRODUCTION_VERSION_STALE'
    if (body.get('oauth', {}).get('durable_store_reachable') is not True
            or body.get('documents', {}).get('durable_store_reachable') is not True):
        return 'DURABLE_STORE_UNAVAILABLE'
    return 'READY'


def request(url, post=False):
    data = b'{"jsonrpc":"2.0","id":1,"method":"ping"}' if post else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json', 'Accept':'application/json, text/event-stream'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw=r.read(100_000); status=r.status; retry=r.headers.get('Retry-After')
    except urllib.error.HTTPError as e:
        status=e.code; raw=e.read(100_000); retry=e.headers.get('Retry-After')
    except (OSError, TimeoutError):
        return 0, None, None
    try: body=json.loads(raw)
    except (ValueError, UnicodeError): body=None
    return status, body, retry


def verify(base, version, commit, fetch=request, sleep=time.sleep):
    observations=[]
    # At most 8 health calls over ~6 minutes, followed by three boundary calls.
    for attempt in range(8):
        status, body, retry=fetch(base+'/health')
        state=classify(status,body,version,commit)
        observations.append({'attempt':attempt+1,'http_status':status,'state':state,
                             'observed_version':body.get('version') if isinstance(body,dict) else None,
                             'observed_commit':body.get('release_commit') if isinstance(body,dict) else None})
        print(json.dumps(observations[-1]),flush=True)
        if state=='READY': break
        if attempt<7:
            delay=min(60,10*2**attempt)
            if retry and str(retry).isdigit(): delay=max(delay,min(60,int(retry)))
            sleep(delay)
    if state!='READY': return {'ok':False,'classification':state,'observations':observations}
    checks=[('/.well-known/oauth-protected-resource/mcp',False),('/.well-known/oauth-authorization-server',False),('/mcp',True)]
    for path,post in checks:
        status,body,_=fetch(base+path,post=post)
        valid=(status==401) if post else status==200 and isinstance(body,dict)
        if valid and 'protected-resource' in path:
            valid=body.get('resource')==base+'/mcp' and 'hwpx' in body.get('scopes_supported',[])
        elif valid and 'authorization-server' in path:
            valid=all(body.get(k) for k in ('authorization_endpoint','token_endpoint','registration_endpoint')) and 'offline_access' in body.get('scopes_supported',[])
        if not valid:
            return {'ok':False,'classification':'EXTERNAL_RATE_LIMIT' if status==429 else 'PROTECTED_BOUNDARY_FAILURE','path':path,'status':status,'observations':observations}
    return {'ok':True,'classification':'PRODUCTION_BOUNDARY_PASS','observations':observations}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--version',default='0.24.0-p3.47');p.add_argument('--commit');p.add_argument('--receipt',default='production-boundary.json');a=p.parse_args()
    result=verify(a.base_url.rstrip('/'),a.version,a.commit)
    Path(a.receipt).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
