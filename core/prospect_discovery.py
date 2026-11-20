"""Bounded Google-result discovery through SerpApi, without visiting result pages.

Uses the HTTP transport directly so httpx's client request logger never records
the private api_key query parameter. Never return provider errors or metadata.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import ipaddress
import json
import asyncio
from contextlib import suppress
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

SCOPES={'web':None,'linkedin':'linkedin.com','facebook':'facebook.com','instagram':'instagram.com'}

class DiscoveryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    query:str=Field(min_length=3,max_length=300)
    scope:Literal['web','linkedin','facebook','instagram']='web'

class DiscoveryUnavailable(Exception):pass
class DiscoveryLimit(Exception):pass

def configured(settings):
    key=settings.prospect_search_api_key
    value=key.get_secret_value() if key else ''
    return settings.prospect_search_provider=='serpapi' and 20<=len(value)<=256 and not any(c.isspace() for c in value)

def safe_result_url(value,scope):
    if not isinstance(value,str) or len(value)>1500:return None
    try:
        parsed=urlsplit(value);host=(parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or '.' not in host or host.rsplit('.',1)[-1].isdigit() or host.endswith(('.local','.localhost','.internal','.test','.invalid')):return None
        try:ipaddress.ip_address(host);return None
        except ValueError:pass
        domain=SCOPES[scope]
        if domain and not (host==domain or host.endswith('.'+domain)):return None
        if any(ord(c)<32 for c in value):return None
        return value
    except Exception:return None

def parse_results(body,scope,key=''):
    if not isinstance(body,dict) or body.get('error') or not isinstance(body.get('search_metadata'),dict) or body['search_metadata'].get('status')!='Success':raise DiscoveryUnavailable()
    raw=body.get('organic_results',[])
    if not isinstance(raw,list):raise DiscoveryUnavailable()
    results=[];seen=set()
    for row in raw[:50]:
        if not isinstance(row,dict):continue
        url=safe_result_url(row.get('link'),scope)
        title=row.get('title');snippet=row.get('snippet','')
        if not url or not isinstance(title,str) or not title.strip() or not isinstance(snippet,str):continue
        if key and any(key in item for item in (url,title,snippet)):continue
        identity=url.split('#',1)[0]
        if identity in seen:continue
        seen.add(identity)
        results.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:24],'title':title.strip()[:200],'url':url,'snippet':snippet.strip()[:1000]})
        if len(results)==10:break
    return results

async def search_once(settings,body,transport=None):
    if not configured(settings):raise DiscoveryUnavailable()
    key=settings.prospect_search_api_key.get_secret_value()
    query=body.query
    if SCOPES[body.scope]:query=f'site:{SCOPES[body.scope]} {query}'
    request=httpx.Request('GET','https://serpapi.com/search.json',params={'engine':'google','q':query,'api_key':key,'hl':'en','gl':'ae','output':'json'},headers={'Accept':'application/json','Accept-Encoding':'identity'},extensions={'timeout':{'connect':8,'read':15,'write':8,'pool':8}})
    connection=transport or httpx.AsyncHTTPTransport(retries=0,trust_env=False)
    response=None
    try:
        async with asyncio.timeout(20):
            response=await connection.handle_async_request(request)
            if response.status_code!=200:raise DiscoveryUnavailable()
            data=bytearray()
            async for chunk in response.aiter_raw():
                data.extend(chunk)
                if len(data)>2_000_000:raise DiscoveryUnavailable()
            results=parse_results(json.loads(data),body.scope,key)
        return {'provider':'serpapi','engine':'google','scope':body.scope,'query':body.query,'searched_at':datetime.now(timezone.utc).isoformat(),'results':results,'contacts_saved':False,'outreach_enabled':False,'automatic_collection':False}
    except Exception:raise DiscoveryUnavailable() from None
    finally:
        with suppress(Exception):
            if response:await response.aclose()
        with suppress(Exception):await connection.aclose()

async def reserve_search(settings,tenant_id):
    """Consume one daily attempt before any provider request; fail closed on Redis loss."""
    from redis.asyncio import Redis
    date=datetime.now(timezone(timedelta(hours=4))).strftime('%Y-%m-%d')
    tenant=hashlib.sha256(tenant_id.encode()).hexdigest()
    key=f'prospect-discovery:v1:{tenant}:{date}'
    client=None
    try:
        client=Redis.from_url(settings.redis_url.get_secret_value(),socket_connect_timeout=3,socket_timeout=3,retry_on_timeout=False)
        used=await client.eval('local n=redis.call("INCR",KEYS[1]); if n==1 then redis.call("EXPIRE",KEYS[1],172800) end; return n',1,key)
        if int(used)>settings.prospect_search_daily_limit:raise DiscoveryLimit()
    except DiscoveryLimit:raise
    except Exception:raise DiscoveryUnavailable() from None
    finally:
        with suppress(Exception):
            if client:await client.aclose()
