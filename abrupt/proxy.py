#!/usr/bin/python

import re
import sys
import socket
import BaseHTTPServer
import traceback
import ssl
import functools

from abrupt.http import Request, Response

CERT_FILE = "cert/cert-srv.pem"
KEY_FILE = "cert/key-srv.pem"

class ProxyHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

  def bypass_ssl(self, r):
    """
    SSL bypass, behave like the requested server and provide a certificate.
    """
    l = self.rfile.readline()  # Purge headers
    while l !="\r\n":
      l = self.rfile.readline()
    self.wfile.write("HTTP/1.1 200 Connection established\r\n\r\n") # yes, sure
    self.ssl_sock = ssl.wrap_socket(self.request, server_side=True,
                                    certfile=CERT_FILE, keyfile=KEY_FILE)
    self.rfile = self.ssl_sock.makefile('rb', self.rbufsize)
    self.wfile = self.ssl_sock.makefile('wb', self.wbufsize)
    return Request(self.rfile, hostname=r.hostname, port=r.port, use_ssl=True)
 
  def handle_one_request(self):
    """
    Accept a request, enable the user to modify, drop or forward it.
    """
    try:
      r = Request(self.rfile)
      if r.method == "CONNECT":
        r = self.bypass_ssl(r)
      if not self.server.filter.search(r.url):
        if self.server.prompt:
          e = raw_input(repr(r) + " ? ")
          while True:
            if e == "v":
              print str(r)
            if e == "e":
              r = r.edit()
            if e == "d":
              return
            if e == "" or e == "f":
              break
            if e == "c":
              self.server.prompt = False
              break
            e = raw_input("(v)iew, (e)dit, (f)orward, (d)rop, (c)ontinue [f]? ") 
        else:
          print repr(r)
        r()
        print repr(r.response)
        self.wfile.write(r.response.raw())
        self.server.reqs.append(r)  
      else: 
        r()
        self.wfile.write(r.response.raw())

    except (ssl.SSLError, socket.timeout), e:
      self.close_connection = 1
      return
   
class ProxyHTTPServer(BaseHTTPServer.HTTPServer):
  
  def handle_error(self, request, client_address):
    traceback.print_exc()
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type == KeyboardInterrupt:    
      raise KeyboardInterrupt()

def intercept(port=8080, prompt=True, nb=-1, filter=None):
  """
  Intercept all request on port and forward them. If prompt
  is True, some actions will be displayed to the user for each
  request. nb is the number of request to intercept. If filter
  is provided, it should be a regular expression to filter the path
  requested. By default, it filters .png, .jp(e)g, .gif and .ico.
  See also: p(), w(), p1(), w1()
  """
  e_nb = 0
  if not filter:
    filter = re.compile(r'\.(png|jpg|jpeg|ico|gif)$')
  try:
    print "Running on port", port
    print "Ctrl-C to interrupt the proxy..."
    server_address = ('', port)
    httpd = ProxyHTTPServer(server_address, ProxyHTTPRequestHandler)
    httpd.filter = filter
    httpd.reqs = []
    httpd.prompt = prompt
    while e_nb != nb:
      httpd.handle_request() 
      e_nb += 1
    return httpd.reqs
  except KeyboardInterrupt:
    print "%d request intercepted" % e_nb
    return httpd.reqs 

p = functools.partial(intercept)
w = functools.partial(p, prompt=False)
p1 = functools.partial(p, nb=1) 
w1 = functools.partial(w, nb=1)
