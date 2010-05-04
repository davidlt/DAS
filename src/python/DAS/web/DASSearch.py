#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
DAS web interface, based on WMCore/WebTools
"""

__revision__ = "$Id: DASSearch.py,v 1.20 2009/09/17 18:51:39 valya Exp $"
__version__ = "$Revision: 1.20 $"
__author__ = "Valentin Kuznetsov"

# system modules
import os
import time
import types
import urllib
from cherrypy import expose
from cherrypy.lib.static import serve_file

import cherrypy
try:
    # Python 2.6
    import json
    from json import JSONDecoder
except:
    # Prior to 2.6 requires simplejson
    import simplejson as json
    from simplejson import JSONDecoder

# WMCore/WebTools modules
from WMCore.WebTools.Page import TemplatedPage
from WMCore.WebTools.Page import exposedasjson, exposedasxml, exposetext
from WMCore.WebTools.Page import exposejson, exposexml, exposedasplist

# DAS modules
from DAS.core.das_core import DASCore
from DAS.utils.utils import getarg
from DAS.web.utils import urllib2_request, json2html

import sys
if sys.version_info < (2, 5):
    raise Exception("DAS requires python 2.5 or greater")

def ajax_response_orig(msg, tag="_response", element="object"):
    """AJAX response wrapper"""
    page  = """<ajax-response><response type="%s" id="%s">""" % (element, tag)
    page += msg
    page += "</response></ajax-response>"
    print page
    return page

def ajax_response(msg):
    """AJAX response wrapper"""
    page  = """<ajax-response>"""
    page += "<div>" + msg + "</div>"
    page += "</ajax-response>"
    return page

class DASSearch(TemplatedPage):
    """
    DAS web interface.
    """
    def __init__(self, config):
        TemplatedPage.__init__(self, config)
        cdict          = self.config.dictionary_()
        self.cachesrv  = getarg(cdict, 'cache_server_url', 'http://localhost:8011')
        self.dasmgr = DASCore()
        self.pageviews = ['xml', 'list', 'table', 'plain', 'json', 'yuijson'] 
        self.cleantime = 60 # in seconds
        self.lastclean = time.time()
        self.decoder   = JSONDecoder()
        self.counter = 0 # TMP stuff, see request, TODO: remove

    def top(self):
        """
        Define masthead for all DAS web pages
        """
        return self.templatepage('das_top')

    def bottom(self, response_div=True):
        """
        Define footer for all DAS web pages
        """
        return self.templatepage('das_bottom', div=response_div)

    def page(self, content, ctime=None, response_div=True):
        """
        Define footer for all DAS web pages
        """
        page  = self.top()
        page += content
        timestamp = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        services = self.dasmgr.keys()
        srv = ""
        for key in services.keys():
            srv += "%s, " % key
        srv = srv[:-2] # remove last comma
        page += self.templatepage('das_bottom', ctime=ctime, services=srv,
                                  timestamp=timestamp, div=response_div)
        return page

    @expose
    def faq(self, *args, **kwargs):
        """
        represent DAS FAQ.
        """
        page = self.templatepage('das_faq')
        return self.page(page, response_div=False)

    @expose
    def help(self, *args, **kwargs):
        """
        represent DAS help
        """
        page = self.templatepage('das_help')
        return self.page(page, response_div=False)

    @expose
    def cli(self, *args, **kwargs):
        """
        Serve DAS CLI file download.
        """
        clifile = os.path.join(os.environ['DAS_ROOT'], 
                'src/python/DAS/tools/das_cache_client.py')
        return serve_file(clifile, content_type='text/plain')

    @expose
    def create_view(self, *args, **kwargs):
        """
        create DAS view.
        """
        msg   = ''
        if  kwargs.has_key('name') and kwargs.has_key('query'):
            name  = kwargs['name']
            query = kwargs['query']
            try:
                self.dasmgr.create_view(name, query)
                msg = "View '%s' has been created" % name
            except Exception, exc:
                msg = "Fail to create view '%s' with query '%s'" \
                % (name, query)
                msg += '</br>Reason: <span class="box_blue">' 
                msg += exc.message + '</span>'
                pass
        views = self.dasmgr.get_view()
        page  = self.templatepage('das_views', views=views, msg=msg)
        return self.page(page, response_div=False)

    @expose
    def views(self, *args, **kwargs):
        """
        represent DAS views.
        """
        views = self.dasmgr.get_view()
        page  = self.templatepage('das_views', views=views, msg='')
        return self.page(page, response_div=False)

    @expose
    def services(self, *args, **kwargs):
        """
        represent DAS services
        """
        keys = self.dasmgr.keys()
        page = self.templatepage('das_services', service_keys=keys)
        return self.page(page, response_div=False)

    @expose
    def index(self, *args, **kwargs):
        """
        represents DAS web interface. 
        It uses das_searchform template for
        input form and yui_table for output Table widget.
        """
        if  not args and not kwargs:
            page = self.form()
            return self.page(page)
        view = getarg(kwargs, 'view', 'table')
        if  args:
            return getattr(self, args[0][0])(args[1])
        if  view not in self.pageviews:
            raise Exception("Page view '%s' is not supported" % view)
        return getattr(self, '%sview' % view)(kwargs)

    @expose
    def form(self, uinput=None, msg=None):
        """
        provide input DAS search form
        """
        page = self.templatepage('das_searchform', input=uinput, msg=msg)
        return page

    def nresults(self, kwargs):
        """
        invoke DAS search call, parse results and return them to
        web methods
        """
        url     = self.cachesrv
        uinput  = getarg(kwargs, 'input', '')
        params  = {'query':uinput}
        path    = '/rest/nresults'
        headers = {"Accept": "application/json"}
        result  = self.decoder.decode(
        urllib2_request('GET', url+path, params, headers=headers))
        if  type(result) is types.StringType:
            data = json.loads(result)
        else:
            data = result
        if  data['results']['status'] == 'success':
            return data['results']['nresults']
        self.send_request('POST', kwargs)
        return 0

    def send_request(self, method, kwargs):
        "Send POST request to server with provided parameters"
        url     = self.cachesrv
        uinput  = getarg(kwargs, 'input', '')
        format  = getarg(kwargs, 'format', '')
        idx     = getarg(kwargs, 'idx', 0)
        limit   = getarg(kwargs, 'limit', 10)
        skey    = getarg(kwargs, 'sort', '')
        sdir    = getarg(kwargs, 'dir', 'asc')
        params  = {'query':uinput, 'idx':idx, 'limit':limit, 
                  'skey':skey, 'order':sdir}
        if  method == 'POST':
            path    = '/rest/create'
        elif  method == 'GET':
            path    = '/rest/request'
        else:
            raise Exception('Unsupported method %s' % method)
        headers = {"Accept": "application/json", "Content-type":"application/json"} 
        res     = self.decoder.decode(
        urllib2_request(method, url+path, params, headers=headers))
        return res

    def result(self, kwargs):
        """
        invoke DAS search call, parse results and return them to
        web methods
        """
        result  = self.send_request('GET', kwargs)
        if  type(result) is types.StringType:
            data = json.loads(result)
        else:
            data = result
        data   = data['results'] # DAS header contains results section
        if  data['status'] == 'success':
            res    = data['data']
        elif data['status'] == 'not found':
            res  = []
        return res
        
    @exposedasplist
    def xmlview(self, kwargs):
        """
        provide DAS XML
        """
        rows = self.result(kwargs)
        return rows

    @exposejson
    def jsonview(self, kwargs):
        """
        provide DAS JSON
        """
        rows = self.result(kwargs)
        return rows

    @expose
    def listview(self, kwargs):
        """
        provide DAS list view
        """
        time0   = time.time()
        ajaxreq = getarg(kwargs, 'ajax', 0)
        uinput  = getarg(kwargs, 'input', '')
        limit   = getarg(kwargs, 'limit', 10)
        form    = self.form(uinput=uinput)
        total   = self.nresults(kwargs)
        if  not total:
            ctime   = (time.time()-time0)
            page    = self.templatepage('not_ready')
            page    = self.page(form + page, ctime=ctime)
            return page

        rows    = self.result(kwargs)
        nrows   = len(rows)
        page    = ""
        ndict   = {'nrows':total, 'limit':limit}
        page    = self.templatepage('das_nrecords', **ndict)
        for nrecord in range(0, len(rows)):
            row = rows[nrecord]
            if  nrecord % 2:
                style = "white"
            else:
                style = "blue" 
            page += '<div class="%s"><hr class="line" /><b>Record #%s</b><br />' % (style, nrecord)
            das = row['das']
            if  type(das) is types.DictType:
                das = [das]
            for jdx in range(0, len(das)):
                item = das[jdx]
                for idx in range(0, len(item['system'])):
                    api    = item['api'][idx]
                    system = item['system'][idx]
                    key    = item['selection_keys'][idx]
                    data   = row[key]
                    if  type(data) is types.ListType:
                        data = data[jdx]
                    if  type(data) is types.ListType:
                        data = data[idx]
                    pad = ""
                    jsoncode = {'jsoncode': json2html(data, pad)}
                    jsonhtml = self.templatepage('das_json', **jsoncode)
                    jsondict = dict(system=system, api=api, daskey=key, data=jsonhtml)
                    page += self.templatepage('das_row', **jsondict)
            page += '</div>'
        ctime   = (time.time()-time0)
        return self.page(form + page, ctime=ctime)

    @exposetext
    def plainview(self, kwargs):
        """
        provide DAS plain view
        """
        rows, total, form = self.result(kwargs)
        page = ""
        for item in rows:
            item  = str(item).replace('[','').replace(']','')
            page += "%s\n" % item.replace("'","")
        return page

    @exposejson
    def yuijson(self, **kwargs):
        """
        provide JSON in YUI compatible format to be used in DynamicData table
        widget, see
        http://developer.yahoo.com/yui/examples/datatable/dt_dynamicdata.html
        """
        rows = self.result(kwargs)
        rowlist = []
        id = 0
        for row in rows:
            das = row['das']
            if  type(das) is types.DictType:
                das = [das]
            for jdx in range(0, len(das)):
                item = das[jdx]
                for idx in range(0, len(item['system'])):
                    api    = item['api'][idx]
                    system = item['system'][idx]
                    key    = item['selection_keys'][idx]
                    data   = row[key]
                    if  type(data) is types.ListType:
                        data = data[jdx]
                    if  type(data) is types.ListType:
                        data = data[idx]
                    pad = ""
                    jsoncode = {'jsoncode': json2html(data, pad)}
                    jsonhtml = self.templatepage('das_json', **jsoncode)
                    jsondict = {'id':id, 'system':system, 'api':api, key:jsonhtml}
                    if  jsondict not in rowlist:
                        rowlist.append(jsondict)
                    id += 1
        idx      = getarg(kwargs, 'idx', 0)
        limit    = getarg(kwargs, 'limit', 10)
        total    = len(rowlist) 
        jsondict = {'recordsReturned': len(rowlist),
                   'totalRecords': total, 'startIndex':idx,
                   'sort':'true', 'dir':'asc',
                   'pageSize': limit,
                   'records': rowlist}
        return jsondict

    @expose
    def tableview(self, kwargs):
        """
        provide DAS table view
        """
        kwargs['format'] = 'html'
        uinput  = getarg(kwargs, 'input', '')
        ajaxreq = getarg(kwargs, 'ajax', 0)
        form    = self.form(uinput=uinput)
        time0   = time.time()
        total   = self.nresults(kwargs)
        if  not total:
            ctime   = (time.time()-time0)
            form    = self.form(uinput)
            page    = self.templatepage('not_ready')
            page    = self.page(form + page, ctime=ctime)
            return page

        # find out which selection keys were used
        selkeys = uinput.replace('find ', '').split(' where ')[0].split(',')
        titles  = ["id", "system", "api"] + selkeys
        coldefs = ""
        for title in titles:
            coldefs += '{key:"%s",label:"%s",sortable:true,resizeable:true},' \
                        % (title, title)
        coldefs = "[%s]" % coldefs[:-1] # remove last comma
        coldefs = coldefs.replace("},{","},\n{")
        limit   = getarg(kwargs, 'limit', 10)
        names   = {'titlelist':titles,
                   'coldefs':coldefs, 'rowsperpage':limit,
                   'total':total, 'tag':'mytag', 'ajax':ajaxreq,
                   'input':urllib.urlencode(dict(input=uinput))}
        page    = self.templatepage('das_table', **names)
        ctime   = (time.time()-time0)
        page    = self.page(form + page, ctime=ctime)
        return page

    @expose
    def default(self, *args, **kwargs):
        """
        default method
        """
        return self.index(args, kwargs)

    @expose
    def request(self, **kwargs):
        """
        Place request to obtain status about given query
        """
        cherrypy.response.headers['Content-Type'] = 'text/xml'
        img = """<img src="/dascontrollers/images/loading.gif" alt="loading" /> """
        req = """<script type="application/javascript">setTimeout('ajaxRequest()', 3000)</script>"""

        def send_post(idict):
            "Send POST request to server with provided parameters"
            params = {'query':idict['query']}
            url  = self.cachesrv
            path = '/rest/create'
            headers = {"Accept": "application/json", "Content-type":"application/json"} 
            res  = self.decoder.decode(
            urllib2_request('POST', url+path, params, headers=headers))
        def set_header():
            "Set HTTP header parameters"
            timestamp = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
            cherrypy.response.headers['Expire'] = timestamp
            cherrypy.response.headers['Cache-control'] = 'no-cache'

        uinput  = getarg(kwargs, 'input', '')
        uinput  = urllib.unquote_plus(uinput)
        view    = getarg(kwargs, 'view', 'table')
        params  = {'query':uinput, 'idx':0, 'limit':1}
        path    = '/rest/request'
        url     = self.cachesrv
        headers = {"Accept": "application/json"}
        result  = self.decoder.decode(
        urllib2_request('GET', url+path, params, headers=headers))
        if  type(result) is types.StringType:
            data  = json.loads(result)
        else:
            data  = result
        data = data['results'] # DAS output stored in results
        if  data['status'] == 'success':
            page  = """<script type="application/javascript">reload()</script>"""
        elif data['status'] == 'in raw cache':
            page  = img + 'data found in raw cache'
            page += req
            send_post(params)
            set_header()
        elif data['status'] == 'requested':
            page  = img + 'data has been requested'
            page += req
            set_header()
        elif data['status'] == 'waiting in queue':
            page  = img + 'your request is waiting in queue'
            page += req
            set_header()
        elif data['status'] == 'not found':
            page  = 'data not in DAS yet, please retry'
            send_post(params)
            set_header()
        elif data['status'] == 'no cache':
            page  = 'DAS server has no hotcache'
            send_post(params)
            set_header()
        else:
            page  = 'unknown status, %s' % urllib.urlencode(str(data))
        page = ajax_response(page)
        print "\n### AJAX response",page
        return page

