"""Maintainer tool: download upstream license notices, not part of the app."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from urllib.request import urlopen,Request
import json

root=Path(__file__).resolve().parents[1]
dest=root/'licenses/qt'
dest.mkdir(parents=True,exist_ok=True)

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.extend(v for k,v in attrs if k=='href')

def download(url):
    with urlopen(Request(url,headers={'User-Agent':'Faro-PDF-license-notices'}),timeout=45) as response:
        data=response.read()
    name=urlparse(url).path.strip('/').replace('/','_')
    (dest/name).write_bytes(data)
    return data.decode('utf8')

urls=['https://doc.qt.io/qt-6/licenses-used-in-qt.html','https://doc.qt.io/qtforpython-6/licenses.html']
index=download(urls[0]);download(urls[1])
links=Links();links.feed(index)
modules=('qtcore-','qtgui-','qtnetwork-','qtsvg-','qttest-','qtwidgets-','qtconcurrent-')
for href in sorted(set(links.links)):
    name=href.rsplit('/',1)[-1]
    if '-attribution-' in name and name.startswith(modules):
        url=urljoin(urls[0],href)
        if urlparse(url).netloc!='doc.qt.io':continue
        download(url);urls.append(url)
(dest/'SOURCES.json').write_text(json.dumps({'upstream_notice_urls':urls,'note':'Unmodified upstream license notices; see THIRD_PARTY_NOTICES.md for exact linked source versions.'},indent=2),encoding='utf8')
print('Qt license notice pages:',len(urls))
