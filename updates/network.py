"""Anonymous public GitHub consumer; redirects never carry credentials."""
import json
import uuid
import http.client
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime,timezone
from pathlib import Path
from release import Error,need,parse,encode,read,write_new,sha,metadata,verify_signature,verify_delivery,safe_path,LIMIT,version

class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self,allowed):self.allowed=allowed
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.allowed(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class Source:
    def __init__(self,trust,lab_http=None,timeout=12):
        self.trust=trust;self.timeout=timeout;self.lab=lab_http
        if lab_http:
            p=urllib.parse.urlsplit(lab_http)
            need(trust['kind']=='heartchy-lab-trust' and p.scheme=='http' and p.hostname=='127.0.0.1' and p.port and p.path in ('','/') and not p.username and not p.query,'laboratory HTTP requires separate loopback trust')
        else:need(trust['kind']=='heartchy-trust','lab trust cannot query production GitHub')
        self.base=lab_http.rstrip('/') if lab_http else 'https://api.github.com'
        self.repo=trust['repository']

    def allowed(self,url,asset=False):
        p=urllib.parse.urlsplit(url)
        need(not p.username and not p.password and not p.fragment,'unsafe URL')
        if self.lab:
            origin=urllib.parse.urlsplit(self.lab)
            need(p.scheme=='http' and p.netloc==origin.netloc,'laboratory redirect outside loopback source')
        else:
            hosts={'api.github.com'} if not asset else {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
            need(p.scheme=='https' and p.hostname in hosts and p.port in (None,443),'untrusted redirect/source')

    def get(self,url,limit,asset=False):
        self.allowed(url,asset)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),Redirects(lambda u:self.allowed(u,asset)))
        for attempt in range(3):
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'Heartchy-test-client/1','Accept':'application/octet-stream' if asset else 'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10'})
                with opener.open(req,timeout=self.timeout) as response:
                    declared=response.headers.get('Content-Length')
                    need(declared is None or int(declared)<=limit,'remote size exceeds limit')
                    data=response.read(limit+1)
                    need(len(data)<=limit,'download too large')
                    need(declared is None or len(data)==int(declared),'TRUNCATED_DOWNLOAD')
                    return data
            except urllib.error.HTTPError as exc:
                if exc.code in (403,429):raise Error('RATE_LIMIT: retry later; no channel/version fallback') from exc
                if exc.code==404:raise Error('release/asset not found') from exc
                if exc.code<500 or attempt==2:raise Error('HTTP error '+str(exc.code)) from exc
            except (TimeoutError,ConnectionError,urllib.error.URLError,http.client.IncompleteRead) as exc:
                if attempt==2:raise Error('NETWORK_UNAVAILABLE: no automatic cached or older release') from exc
            time.sleep(.15*(attempt+1))
        raise Error('network unavailable')

    def asset_url(self,tag,name):
        need(tag.startswith('v') and '/' not in tag,'invalid tag')
        version(tag[1:])
        prefix=self.lab if self.lab else 'https://github.com'
        return prefix+'/'+self.repo+'/releases/download/'+tag+'/'+name

    def signed(self,tag):
        raw=self.get(self.asset_url(tag,'release.json'),200000,True)
        sig=self.get(self.asset_url(tag,'release.json.sig'),4096,True)
        verify_signature(raw,sig,self.trust);m=metadata(raw,self.trust)
        need(tag=='v'+m['version'],'tag/version mismatch')
        return m,raw,sig

    def catalog(self,channel):
        need(channel in ('stable','test'),'explicit channel required')
        releases=[];seen=set()
        for page in range(1,21):
            url=self.base+'/repos/'+self.repo+'/releases?per_page=100&page='+str(page)
            rows=parse(self.get(url,2_000_000))
            need(isinstance(rows,list) and len(rows)<=100,'invalid GitHub list')
            for row in rows:
                need(isinstance(row,dict),'invalid release row')
                if row.get('draft') is not False:continue
                tag=row.get('tag_name','')
                if not isinstance(tag,str) or not tag.startswith('v'):continue
                try:version(tag[1:])
                except Error:continue
                if channel=='stable' and row.get('prerelease') is True:continue
                # The mutable GitHub flag cannot promote signed test metadata.
                m,raw,sig=self.signed(tag)
                if m['channel']!=channel:continue
                need(tag not in seen,'duplicate release tag across pages');seen.add(tag)
                published=row.get('published_at')
                need(isinstance(published,str) and datetime.fromisoformat(published.replace('Z','+00:00')).tzinfo is not None,'missing published_at')
                releases.append({'metadata':m,'published_at':published,'signed':raw.decode(),'signature':sig.decode()})
            if len(rows)<100:break
        else:raise Error('catalog pagination limit reached; incomplete listing refused')
        releases.sort(key=lambda r:version(r['metadata']['version']),reverse=True)
        return {'repository':self.repo,'channel':channel,'fetched_at':datetime.now(timezone.utc).isoformat(),'freshness':'NETWORK','releases':releases}

    def fetch(self,selected,output,channel):
        version(selected);m,raw,sig=self.signed('v'+selected)
        need(m['channel']==channel,'selected release outside explicit channel')
        out=safe_path(output);need(not out.exists(),'download destination already exists')
        partial=out.with_name(out.name+'.'+uuid.uuid4().hex+'.partial');partial.mkdir(parents=True,mode=0o700)
        try:
            write_new(partial/'release.json',raw);write_new(partial/'release.json.sig',sig)
            archive=self.get(self.asset_url('v'+selected,m['archive']['name']),m['archive']['bytes'],True)
            need(len(archive)==m['archive']['bytes'] and sha(archive)==m['archive']['sha256'],'archive hash/size mismatch')
            write_new(partial/m['archive']['name'],archive)
            verify_delivery(partial,self.trust)
            need(not out.exists(),'download destination appeared')
            partial.rename(out)
        except BaseException:
            # Retained explicitly incomplete evidence; never installed/executed.
            raise
        return m

def cached_catalog(path,trust,channel):
    c=parse(read(path,2_000_000))
    need(isinstance(c,dict) and c.get('repository')==trust['repository'] and c.get('channel')==channel and isinstance(c.get('releases'),list),'cache identity mismatch')
    need(len(c['releases'])<=2000,'oversized cache')
    for row in c['releases']:
        raw=row['signed'].encode();verify_signature(raw,row['signature'].encode(),trust)
        m=metadata(raw,trust);need(m==row['metadata'] and m['channel']==channel,'cache altered or wrong channel')
    c['freshness']='CACHE_EXPLICIT_NOT_CURRENT'
    return c
