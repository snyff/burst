import re
import urllib
import urlparse
import httplib
import traceback
import functools
import glob
import os.path
import Cookie

from abrupt.http import Request, RequestSet
from abrupt.color import *

payloads = {}
for f_name in glob.glob(os.path.join(os.path.dirname(__file__), "payloads/*")):
  k = os.path.basename(f_name)
  plds = open(f_name).read().splitlines()
  payloads[k] = plds

class PayloadNotFound(Exception): pass
class NoInjectionPointFound(Exception): pass
class NonUniqueInjectionPoint(Exception): pass

def e(s):
  return urllib.quote_plus(s)  

def ee(s):
  return e(e(s))

def d(s):
  return urllib.unquote_plus(s)

def _get_payload(name, kwds):
  pds = []
  try:
    if name in kwds:
      if isinstance(kwds[name], list):
        pds = kwds[name]
      else:
        pds = payloads[kwds[name]]
    return pds
  except KeyError:
    raise PayloadNotFound("Possible values are: " +", ".join(payloads.keys()))

def _inject_query(r, pre_func=e, **kwds):
  rs = []
  parsed_url = urlparse.urlparse(r.url)
  i_pts = urlparse.parse_qs(r.query, True)
  for i_pt in i_pts:
    nq = i_pts.copy()
    pds = _get_payload(i_pt, kwds)
    for p in pds:
      nq[i_pt] = [pre_func(p),]
      s = list(parsed_url)
      s[4] = urllib.urlencode(nq, True)
      r_new = r.copy()
      r_new.url = urlparse.urlunparse(s)
      r_new.payload = i_pt + "=" + p
      rs.append(r_new)
  return rs

def _inject_cookie(r, pre_func=e, **kwds):
  rs = []
  b = r.cookies
  n_headers = [(x,v) for x,v in r.headers if x != "Cookie"]
  for i_pt in b:
    nb = Cookie.SimpleCookie()
    nb.load(b.output(header=""))
    pds = _get_payload(i_pt, kwds)
    for p in pds:
      nb[i_pt] = pre_func(p)
      r_new = r.copy()
      nbs =  nb.output(header="", sep=";").strip()
      r_new.headers = n_headers + [("Cookie", nbs),]
      r_new.payload = i_pt + "=" + p
      rs.append(r_new)
  return rs

def _inject_post(r, pre_func=e, **kwds):
  rs = []
  i_pts = urlparse.parse_qs(r.content, True)
  for i_pt in i_pts:
    nc = i_pts.copy()
    pds = _get_payload(i_pt, kwds)
    for p in pds:
      nc[i_pt] = [pre_func(p),]
      n_content = urllib.urlencode(nc, True)
      r_new = r.copy()
      r_new.content = n_content
      r_new.payload = i_pt + "=" + p
      r_new._update_content_length()
      rs.append(r_new)
  return rs

def _inject_offset(r, offset, payload, pre_func=e):
  rs = []
  orig = str(r)
  pds = _get_payload("offset", {"offset":payload})
  if isinstance(offset, (list,tuple)): 
    off_b, off_e = offset
  elif isinstance(offset, basestring):
    ct = str(r).count(offset)
    if ct > 1: raise NonUniqueInjectionPoint("The pattern is not unique in the request")
    elif ct < 1: raise NoInjectionPointFound("Could not find the pattern")
    idx = str(r).find(offset)
    off_b, off_e = idx, idx+len(offset)
  else:
    off_b = off_e = offset
  for p in pds:
    ct = orig[:off_b] + pre_func(p) + orig[off_e:]
    ct = re.sub("Content-Length:.*\n", "", ct)
    r_new = Request(ct, hostname=r.hostname, port=r.port, use_ssl=r.use_ssl)
    r_new._update_content_length()
    r_new.payload = "@" + str(offset) + "=" + p
    rs.append(r_new)
  return rs
  
def i(r, **kwds):
  """ Inject a request.
  For each keyword, this function will try to find the key in the request
  at the following locations:

    * URL parameters
    * Cookies
    * Content for a POST or PUT request

  Then, each value will be injected at the parameter location and a set
  of request returned. The values could be either a list of payload
  (e.g., id=[1,2,3]) or a key of the global dictionnary :data:`payloads`
  (e.g., name="default").

  See also: payloads, i_at
  """
  rqs = RequestSet(_inject_query(r, **kwds))
  if r.method in ("POST", "PUT"):
    rqs += RequestSet(_inject_post(r, **kwds))
  if "Cookie" in zip(*r.headers)[0]:
    rqs += RequestSet(_inject_cookie(r, **kwds))
  if not rqs:
    raise NoInjectionPointFound()
  return rqs 

def i_at(r, offset, payload, **kwds):
  """Surgically inject a request.

  This function inject the request at a specific offset, between two offset 
  position or instead a token. If *offset* is an integer, the payload will 
  be inserted at this position. If *offset* is a range (e.g., (23,29)) this 
  range will be erased with the payload. If *offset* is a string, it will be 
  replaced by the payloads. In the latter scenario, if the string is not 
  found or if more than one occurrence exists, an exception will be raised.

  See also: payloads, i
  """
  return RequestSet(_inject_offset(r, offset, payload, **kwds))

