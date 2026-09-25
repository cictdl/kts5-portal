"""
KTS 5.0 · Plesk "Python support" probe (CGI).
If Hosting Settings offers a Python checkbox, tick it, upload this file to the
subdomain folder and open https://<subdomain>/pyinfo.py . It prints which
interpreter Plesk uses and how it is invoked, which decides whether a
CGI/FastCGI fallback is possible when HttpPlatformHandler is unavailable.
"""
import os
import sys

print("Content-Type: text/plain; charset=utf-8")
print()
print("python    :", sys.version)
print("executable:", sys.executable)
print("argv      :", sys.argv)
print("cwd       :", os.getcwd())
print("script    :", __file__)
keys = ["GATEWAY_INTERFACE", "SERVER_SOFTWARE", "FCGI_ROLE", "SCRIPT_NAME", "PATH_INFO", "DOCUMENT_ROOT",
        "APPL_PHYSICAL_PATH", "SERVER_NAME", "HTTPS", "REQUEST_METHOD", "PATH"]
for k in keys:
    if k in os.environ:
        print(f"{k:18}: {os.environ[k]}")
