#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
DBS service
"""
__revision__ = "$Id: dbs_service.py,v 1.24 2010/04/09 19:41:23 valya Exp $"
__version__ = "$Revision: 1.24 $"
__author__ = "Valentin Kuznetsov"

import re
import time
from DAS.services.abstract_service import DASAbstractService
from DAS.utils.utils import map_validator, json_parser

class DBS3Service(DASAbstractService):
    """
    Helper class to provide DBS service
    """
    def __init__(self, config):
        DASAbstractService.__init__(self, 'dbs3', config)
        self.reserved = ['api', 'apiversion']
        self.map = self.dasmapping.servicemap(self.name)
        map_validator(self.map)
        self.prim_instance = 'cms_dbs_prod_global'
        self.instances = ['cms_dbs_prod_global', 'cms_dbs_caf_analysis_01',
                'cms_dbs_ph_analysis_01', 'cms_dbs_ph_analysis_02']

    def url_instance(self, url, instance):
        """
        Adjust URL for a given instance
        """
        if  instance in self.instances:
            return url.replace(self.prim_instance, instance)
        return url
            
    def adjust_params(self, api, kwds, inst=None):
        """
        Adjust DBS2 parameters for specific query requests
        """
        if  api == 'acquisitioneras':
            try:
                del kwds['era']
            except:
                pass
        if  api == 'datasets':
            if  kwds['dataset'] == '*' and kwds['block_name']:
                kwds['dataset'] = kwds['block_name'].split('#')[0]
            try:
                del kwds['block_name']
            except:
                pass
        if  api == 'runs':
            val = kwds['minrun']
            if  isinstance(val, dict): # we got a run range
                if  val.has_key('$in'):
                    kwds['minrun'] = val['$in'][0]
                    kwds['maxrun'] = val['$in'][-1]
                if  val.has_key('$lte'):
                    kwds['minrun'] = val['$gte']
                    kwds['maxrun'] = val['$lte']

    def parser(self, query, dformat, source, api):
        """
        DBS3 data-service parser.
        """
        if  api == 'site4dataset':
            sites = set()
            for rec in json_parser(source, self.logger):
                if  isinstance(rec, list):
                    for row in rec:
                        orig_site = row['origin_site_name']
                        if  orig_site not in sites:
                            sites.add(orig_site)
                else:
                    orig_site = row['origin_site_name']
                    if  orig_site not in sites:
                        sites.add(orig_site)
            for site in sites:
                yield {'site': {'name': site}}
        elif api == 'filesummaries':
            gen = DASAbstractService.parser(self, query, dformat, source, api)
            for row in gen:
                yield row['dataset']
        elif api == 'blockparents':
            gen = DASAbstractService.parser(self, query, dformat, source, api)
            for row in gen:
                try:
                    del row['parent']['this_block_name']
                except:
                    pass
                yield row
        else:
            gen = DASAbstractService.parser(self, query, dformat, source, api)
            for row in gen:
                yield row

