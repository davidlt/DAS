#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-
"""
File: dbs_daemon.py
Author: Valentin Kuznetsov <vkuznet@gmail.com>
Description: DBS daemon, which update DAS cache with DBS datasets
"""

# system modules
import re
import time
import thread
import urllib
import urllib2
import itertools

# MongoDB modules
from pymongo.errors import InvalidOperation
from pymongo import ASCENDING

# DAS modules
import DAS.utils.jsonwrapper as json
from DAS.utils.utils import qlxml_parser, dastimestamp, print_exc
from DAS.utils.das_db import db_connection, create_indexes
from DAS.web.utils import db_monitor

def dbs_instance(dbsurl):
    """Parse dbs instance from provided DBS url"""
    if  dbsurl[-1] == '/':
        dbsurl = dbsurl[:-1]
    if  dbsurl.find('DBSServlet') != -1:
        # http://cmsdbsprod.cern.ch/cms_dbs_prod_global/servlet/DBSServlet
        dbsinst = dbsurl.split('/')[-3]
    elif dbsurl.find('DBSReader') != -1:
        # http://vocms09.cern.ch:8989/dbs/DBSReader
        dbsinst = dbsurl.split('/')[-2]
    else:
        msg = 'Unable to parse dbs instance from provided url %s' % dbsurl
        raise Exception(msg)
    return dbsinst

class DBSDaemon(object):
    """
    DBSDaemon fetch list of known datasets from DBS2/DBS3
    and store them in separate collection to be used by
    DAS autocomplete web interface.
    """
    def __init__(self, dbs_url, dburi, dbname='dbs', cache_size=1000,
                        expire=3600):
        self.dburi  = dburi
        self.dbname = dbname
        self.dbcoll = dbs_instance(dbs_url)
        self.cache_size = cache_size
        self.dbs_url = dbs_url
        self.expire = expire
        self.init()
        # Monitoring thread which performs auto-reconnection to MongoDB
        thread.start_new_thread(db_monitor, (dburi, self.init))

    def init(self):
        """
        Init db connection
        """
        try:
            conn = db_connection(self.dburi)
            self.col = conn[self.dbname][self.dbcoll]
            indexes = [('dataset', ASCENDING), ('ts', ASCENDING)]
            create_indexes(self.col, indexes)
            self.col.remove()
        except Exception as _exp:
            self.col = None

    def update(self):
        """
        Update DBS collection with a fresh copy of datasets
        """
        if  self.col:
            time0 = time.time()
            gen = self.datasets()
            if  not self.col.count():
                try: # perform bulk insert operation
                    while True:
                        if  not self.col.insert(\
                                itertools.islice(gen, self.cache_size)):
                            break
                except InvalidOperation:
                    pass
            else: # we already have records, update their ts
                for row in gen:
                    spec = dict(dataset=row['dataset'])
                    self.col.update(spec, {'$set':{'ts':time0}})
            # remove records with old ts
            self.col.remove({'ts':{'$lt':time0-self.expire}})
            print "%s DBSDaemon updated in %s sec, collection=%s, nrec=%s" \
            % (dastimestamp(), self.dbcoll, time.time()-time0, self.col.count())

    def find(self, pattern, idx=0, limit=10):
        """
        Find datasets for a given pattern. The idx/limit parameters 
        control number of retrieved records (aka pagination). The
        limit=-1 means no pagination (get all records).
        """
        if  self.col:
            try:
                if  len(pattern) > 0 and pattern[0] == '/':
                    pattern = '^%s' % pattern
                if  pattern.find('*') != -1:
                    pattern = pattern.replace('*', '.*')
                pat  = re.compile('%s' % pattern, re.I)
                spec = {'dataset':pat}
                if  limit == -1:
                    for row in self.col.find(spec):
                        yield row['dataset']
                else:
                    for row in self.col.find(spec).skip(idx).limit(limit):
                        yield row['dataset']
            except:
                pass

    def datasets(self):
        """
        Retrieve a list of DBS datasets (DBS2)
        """
        if  self.dbs_url.find('DBSServlet') != -1: # DBS2
            for rec in self.datasets_dbs():
                yield rec
        else: # DBS3
            for rec in self.datasets_dbs3():
                yield rec

    def datasets_dbs(self):
        """
        Retrieve a list of DBS datasets (DBS2)
        """
        query = 'find dataset,dataset.status'
        params = {'api': 'executeQuery', 'apiversion': 'DBS_2_0_9', 'query':query}
        encoded_data = urllib.urlencode(params, doseq=True)
        url = self.dbs_url + '?' + encoded_data
        req = urllib2.Request(url)
        try:
            stream = urllib2.urlopen(req)
        except Exception as exc:
            print_exc(exc)
            msg = 'Fail to contact %s' % url
            raise Exception(msg)
        gen = qlxml_parser(stream, 'dataset')
        for row in gen:
            if  row['dataset']['dataset.status'] == 'VALID':
                yield dict(dataset=row['dataset']['dataset'])
        stream.close()

    def datasets_dbs3(self):
        """
        Retrieve a list of DBS datasets (DBS3)
        """
        params = {'dataset_access_type':'PRODUCTION'}
        encoded_data = urllib.urlencode(params, doseq=True)
        url = self.dbs_url + '?' + encoded_data
        req = urllib2.Request(url)
        stream = urllib2.urlopen(req)
        gen = json.load(stream)
        for row in gen:
            yield row
        stream.close()
        
def test(dbs_url):
    uri = 'mongodb://localhost:8230'
    mgr = DBSDaemon(dbs_url, uri)
    mgr.update()
    idx = 0
    limit = 10
    for row in mgr.find('zee*summer', idx, limit):
        print row

if __name__ == '__main__':
    DBS2_URL = 'http://cmsdbsprod.cern.ch/cms_dbs_prod_global/servlet/DBSServlet'
    DBS3_URL = 'http://localhost:8989/dbs/DBSReader/datasets/'
    test(DBS2_URL)