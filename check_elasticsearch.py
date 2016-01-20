#!/usr/bin/python
"""Nagios plugin to check ElasticSearch."""

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

import argparse
import logging
import nagiosplugin
import urllib2
import json

_log = logging.getLogger('nagiosplugin')


class ESCheck(nagiosplugin.Resource):

    path = None

    def __init__(self, hostname, port):
        self.host = hostname
        self.port = port

    def get_json(self):
        try:
            response = urllib2.urlopen(r'http://%s:%d/%s'
                                       % (self.host, self.port, self.path))
        except urllib2.HTTPError, e:
            raise  nagiosplugin.CheckError("urllib2.HTTPError: %s" % str(e))
        except urllib2.URLError, e:
            raise nagiosplugin.CheckError("urllib2.URLError: %s" % str(e.reason))

        response_body = response.read()

        try:
            return json.loads(response_body)
        except ValueError:
            raise nagiosplugin.CheckError("Error decoding JSON")

class ESClusterHealthStatusContext(nagiosplugin.Context):
    def evaluate(self, metric, resource):
        hint = "status is %s" % metric.value
        if metric.value == 'green':
            return nagiosplugin.result.Result(nagiosplugin.state.Ok, hint, metric)
        elif metric.value == 'yellow':
            return nagiosplugin.result.Result(nagiosplugin.state.Warn, hint, metric)
        elif metric.value == 'red':
            return nagiosplugin.result.Result(nagiosplugin.state.Critical, hint, metric)
        else:
            return nagiosplugin.result.Result(nagiosplugin.state.Unknown, hint, metric)

class ESClusterHealthCheck(ESCheck):
    """Check ElasticSearch health.
    """

    path = '/_cluster/health'

    def probe(self):
        json = self.get_json()
        for k, v in json.iteritems():
          if k == 'status':
               yield nagiosplugin.Metric(k, v)
          elif k == 'number_of_nodes':
              yield nagiosplugin.Metric(k, v, context='nodes')
          elif k == 'number_of_data_nodes':
              yield nagiosplugin.Metric(k, v, context='data_nodes')
          elif k in ['active_primary_shards', 'active_shards', 'relocating_shards', 'initializing_shards', 'unassigned_shards', 'delayed_unassigned_shards', 'number_of_pending_tasks', 'number_of_in_flight_fetch']:
              yield nagiosplugin.Metric(k, v, context='default')
          elif k in ['task_max_waiting_in_queue_millis']:
              yield nagiosplugin.Metric(k, v, uom='ms', context='default')
          elif k in ['active_shards_percent_as_number']:
              yield nagiosplugin.Metric(k, v, uom='%', context='default')

class ESNodesStatsJVMCheck(ESCheck):
    """Check ElasticSearch JVM stats.
    """

    path = '/_nodes/_local/stats/jvm'

    def probe(self):
        json = self.get_json()
        nodes = json['nodes']
        for node in nodes:
            jvm_percentage = nodes[node]['jvm']['mem']['heap_used_percent']
            node_name = nodes[node]['name']
            yield nagiosplugin.Metric(node_name, jvm_percentage, uom='%', context='heap_used_percent')

@nagiosplugin.guarded
def main():
    argp = argparse.ArgumentParser()
    argp.add_argument('-H', '--hostname', metavar='ADDRESS',
                      help='Host name or IP Address (default: localhost)',
                      default='localhost')
    argp.add_argument('-p', '--port', metavar='INTEGER',
                      help='Port number (default: 9200)',
                      default=9200)

    argp.add_argument('-w', '--warning', metavar='RANGE',
                      help='warning if RESULT is outside RANGE (RESULT being number of data nodes, or percent heap used)')
    argp.add_argument('-c', '--critical', metavar='RANGE',
                      help='critical if RESULT is outside RANGE')
    argp.add_argument('-v', '--verbose', action='count', default=0,
                      help='increase output verbosity (use up to 3 times)')
    argp.add_argument('-t', '--timeout', default=10,
                      help='abort execution after TIMEOUT seconds')

    argp.add_argument('check', metavar='CHECK', nargs='?',
                      help='Check performed (One of cluster-health, jvm-heap)',
                      default='cluster-health')

    args = argp.parse_args()
    if args.check == 'cluster-health':
        check = nagiosplugin.Check(
            ESClusterHealthCheck(args.hostname, args.port),
            ESClusterHealthStatusContext('status'),
            nagiosplugin.ScalarContext('nodes',
                                       fmt_metric='{value} nodes'),
            nagiosplugin.ScalarContext('data_nodes', args.warning, args.critical,
                                       fmt_metric='{value} data nodes'),
            nagiosplugin.ScalarContext('count'))
    elif args.check == 'jvm-heap':
        check = nagiosplugin.Check(
            ESNodesStatsJVMCheck(args.hostname, args.port),
            nagiosplugin.ScalarContext('heap_used_percent', args.warning, args.critical,
                                       fmt_metric='{value}% heap used on {name}'))
    else:
        check = nagiosplugin.Check(
            nagiosplugin.CheckError("Unknown check: %s" % args.check))
    check.main(args.verbose, args.timeout)

if __name__ == '__main__':
    main()

