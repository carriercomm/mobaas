# Copyright 2014 Zuercher Hochschule fuer Angewandte Wissenschaften
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

__author__ = 'andy'

import multiprocessing
from threading import Thread

from mcn.sm import LOG


class StateUpdater(Thread):

    def __init__(self, results_q, registry):
        super(StateUpdater, self).__init__()
        self.results_q = results_q
        self.registry = registry

    def run(self):
        super(StateUpdater, self).run()
        LOG.debug('Starting StateUpdater thread')
        entity = self.results_q.get()[0]['entity']
        LOG.debug('Received entity on the queue...')
        LOG.debug('Updating entity state')
        # this param should be provided
        entity.attributes['mcn.service.state'] = 'provisioning'
        LOG.debug('Updating entity in registry')
        self.registry.add_resource(key=entity.identifier, resource=entity, extras=None)


class Executor(multiprocessing.Process):
    def __init__(self, group_name, task_queue, result_queue):
        multiprocessing.Process.__init__(self)
        LOG.debug('executor: ' + self.name + ' is part of group: ' + group_name)
        self.group_name = group_name
        self.task_queue = task_queue
        self.result_queue = result_queue

    def run(self):
        super(Executor, self).run()
        task = self.task_queue.get()
        LOG.debug('task received')
        #blocking op
        LOG.debug('running async task...')
        res = task.run()
        LOG.debug('sending async result...')
        self.result_queue.put(res)

class ProMgr():
    def __init__(self, num_executors=1):
        multiprocessing.log_to_stderr(LOG.level)
        self.num_executors = num_executors  # should be a multiple of cores multiprocessing.cpu_count() * 2
        self.executors = []

        # create i/o queues
        LOG.debug('creating async task in queues...')
        self.async_tasks = multiprocessing.Queue()

        LOG.debug('creating async task return queues...')
        self.async_ret_vals = multiprocessing.Queue()

    def run(self):
        LOG.debug('creating executors...')
        self.executors = [ Executor('creator', self.async_tasks, self.async_ret_vals) for i in xrange(self.num_executors)]

        LOG.debug('number of async executors to start: ' + str(len(self.executors)))
        for executor in self.executors:
            executor.start()
