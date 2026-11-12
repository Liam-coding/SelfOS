"""Attribute-only upgrade for older generated dashboards; keep literal content."""
import json
import re
from html import escape
from html.parser import HTMLParser
from selfos.web.i18n import catalogs


def upgrade_legacy_markup(page):
    messages=catalogs()['locales']['en']['messages']
    by_text={value:key for key,value in messages.items()}
    changes=[]
    offsets=[0]
    for line in page.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
    class Tags(HTMLParser):
        pending_score = None
        def handle_data(self, value):
            if self.pending_score is None:
                return
            start, raw, tag, attrs = self.pending_score
            self.pending_score = None
            text = value.strip()
            if not re.fullmatch(r'-?\d+(?:\.\d+)?', text):
                return
            attrs['data-i18n'] = 'ui.common.value'
            attrs['data-i18n-params'] = json.dumps({'value':float(text) if '.' in text else int(text)})
            rebuilt = '<'+tag+''.join(' '+name if value is None else ' '+name+'="'+escape(value,quote=True)+'"' for name,value in attrs.items())+'>'
            changes[:]=[change for change in changes if change[0]!=start]
            changes.append((start,start+len(raw),rebuilt))
        def handle_endtag(self, tag):
            self.pending_score = None
        def handle_starttag(self,tag,attributes):
            attrs=dict(attributes);original=dict(attrs)
            self.pending_score=None
            if attrs.get('class') in ('ring-score','overall-ring-num') and 'data-i18n' not in attrs:
                line,column=self.getpos()
                self.pending_score=(offsets[line-1]+column,self.get_starttag_text(),tag,dict(attrs))
            identity=attrs.get('id')
            if 'data-zh' in attrs and 'data-en' in attrs:
                key=by_text.get(attrs['data-en'])
                if identity=='greeting-text' and attrs['data-en'].startswith('Hello, '):
                    key='ui.dashboard.greeting'
                    attrs['data-i18n-params']=json.dumps({'name':attrs['data-en'][7:]})
                if identity=='overall-count':
                    count=re.fullmatch(r'(\d+) dimensions scored',attrs['data-en'])
                    if count:key='ui.dashboard.scored';attrs['data-i18n-params']=json.dumps({'count':int(count[1])})
                if identity=='overall-date':
                    date=re.fullmatch(r'Updated (\d{4}-\d{2}-\d{2})',attrs['data-en'])
                    if date:attrs['data-date']=date[1]
                if key:attrs['data-i18n']=key;attrs.pop('data-en',None);attrs.pop('data-zh',None)
            if 'card' in attrs.get('class','').split() and attrs.get('data-key'):
                key='ui.dimension.'+attrs['data-key']
                if key in messages:attrs['data-label-key']=key
                for prefix,namespace in [('status','ui.status.'),('sugg','ui.suggestion.')]:
                    value=attrs.get('data-'+prefix+'-en')
                    key=next((key for key,text in messages.items() if key.startswith(namespace) and text==value),None)
                    if key:attrs['data-'+prefix+'-key']=key
            for field in ('title','placeholder','aria-label'):
                value=attrs.get(field)
                key=by_text.get(value)
                if key:attrs['data-i18n-'+field]=key
            if self.pending_score is not None:
                start,raw,pending_tag,_=self.pending_score
                self.pending_score=(start,raw,pending_tag,dict(attrs))
            if attrs==original:return
            raw=self.get_starttag_text();line,column=self.getpos();start=offsets[line-1]+column
            ending='/>' if raw.endswith('/>') else '>'
            rebuilt='<'+tag+''.join(' '+name if value is None else ' '+name+'="'+escape(value,quote=True)+'"' for name,value in attrs.items())+ending
            changes.append((start,start+len(raw),rebuilt))
        handle_startendtag=handle_starttag
    parser=Tags(convert_charrefs=False);parser.feed(page)
    for start,end,replacement in reversed(changes):page=page[:start]+replacement+page[end:]
    return page
