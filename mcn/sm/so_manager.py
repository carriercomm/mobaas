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

from distutils import dir_util
import httplib # TODO replace with requests lib
import os
import shutil
import tempfile
from urlparse import urlparse

from mcn.sm import CONFIG
from mcn.sm import LOG
from oshift import Openshift

NBAPI_URL = CONFIG.get('cloud_controller', 'nb_api')
OPS_URL = CONFIG.get('cloud_controller', 'ops_api')

create_app_headers={'Content-Type': 'text/occi',
            'Category': 'app; scheme="http://schemas.ogf.org/occi/platform#", '
            'python-2.7; scheme="http://schemas.openshift.com/template/app#", '
            'small; scheme="http://schemas.openshift.com/template/app#"',
            }


class SOManager():

    def __init__(self):
        self.uri_app = ""
        nburl = urlparse(NBAPI_URL)
        LOG.info('CloudController Northbound API: ' + nburl.hostname + ':' + str(nburl.port))
        self.conn = httplib.HTTPConnection(host=nburl.hostname, port=nburl.port)


    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        # clean up connection
        LOG.debug('Closing connection to CloudController Northbound API')
        self.conn.close()

    def deploy(self, entity, extras):
        LOG.debug('Ensuring SM SSH Key...')
        self.__ensure_ssh_key()

        # create an app for the new SO instance
        LOG.debug('Creating SO container...')
        self.uri_app, repo_uri = self.__create_app(entity, extras)

        # get the code of the bundle and push it to the git facilities
        # offered by OpenShift
        LOG.debug('Deploying SO Bundle...')
        self.__deploy_app(repo_uri)

        # XXX Provision is done without any control by the client...
        # otherwise we won't be able to hand back a working service!
        # self.provision(entity, extras)

    def provision(self, entity, extras):
        # make call to the SO's endpoint to execute the provision command
        #TODO error handling
        #TODO this call is incorrect
        #TODO pass the tenant ID so heat template can be provisioned
        self.conn.request('POST',
                          self.uri_app+"?action=provision",
                          headers={'Content-Type': 'text/occi',
                                   'Category': 'provision; scheme=""; kind="action"'})

    def dispose(self, entity, extras):
        #XXX prob don't need self.uri_app - get it from entity
        LOG.info('Disposing service instance: ' + self.uri_app)
        resp = self.conn.request('DELETE',
                          self.uri_app,
                          headers={'Content-Type': 'text/occi'})
        #TODO error handling

    def so_details(self, entity, extras):
        pass

    def __create_app(self, entity, extras):
        '''
            create an app
            how if:
                SLA == bronze, size of gear should be small
                SLA == silver, size of gear should be medium
                SLA == gold, size of gear should be large
        '''

        #TODO - check sting, ALPHANUM only
        # re.match('[a-zA-Z0-9_]', MYSTR)
        create_app_headers['X-OCCI-Attribute'] = 'occi.app.name=serviceinstance'
        LOG.debug('Requesting container to execute SO Bundle')
        #TODO requests should be placed on a queue as this is a blocking call
        self.conn.request('POST', '/app/', headers=create_app_headers)
        resp = self.conn.getresponse()
        #TODO error handling
        from urlparse import urlparse
        app_uri_path = urlparse(resp.getheader('Location')).path
        LOG.debug('SO container created: ' + app_uri_path)
        # get git uri
        self.conn.request('GET', app_uri_path, headers={'Accept': 'text/occi'})
        resp = self.conn.getresponse()
        attrs = resp.getheader('X-OCCI-Attribute')
        repo_uri = ''
        for attr in attrs.split(', '):
            if attr.find('occi.app.repo') != -1:
                repo_uri = attr.split('=')[1]
                break

        LOG.debug('SO container repository: ' + repo_uri)
        return app_uri_path, repo_uri

    def __deploy_app(self, repo):
        """
            Deploy the local SO bundle
            assumption here
            - a git repo is returned
            - the bundle is not managed by git
        """

        # XXX assumes that git is installed
        # create temp dir...and clone the remote repo provided by OpS
        dir = tempfile.mkdtemp()
        LOG.debug('Cloning git repository: ' + repo + ' to: ' + dir)
        os.system(' '.join(['git', 'clone', repo, dir]))

        # Get the SO bundle
        bundle_loc = CONFIG.get('service_manager', 'bundle_location')
        LOG.debug('Bundle to add to repo: ' + bundle_loc)
        dir_util.copy_tree(bundle_loc, dir)

        # put OpenShift stuff in place
        # build and pre_start_python comes from 'support' directory in bundle
        # TODO this needs to be improved - could use from mako.template import Template?
        LOG.debug('Adding OpenShift support files from: ' + bundle_loc + '/support')
        shutil.copyfile(bundle_loc+'/support/build', os.path.join(dir, '.openshift', 'action_hooks', 'build'))
        shutil.copyfile(bundle_loc+'/support/pre_start_python', os.path.join(dir, '.openshift', 'action_hooks', 'pre_start_python'))

        os.system(' '.join(['chmod', '+x', os.path.join(dir, '.openshift', 'action_hooks', '*')]))

        # add & push to OpenShift
        os.system(' '.join(['cd', dir, '&&', 'git', 'add', '-A']))
        os.system(' '.join(['cd', dir, '&&', 'git', 'commit', '-m', '"deployment of SO for tenant X"', '-a']))
        LOG.debug('Pushing new code to remote repository...')
        os.system(' '.join(['cd', dir, '&&', 'git', 'push']))

        shutil.rmtree(dir)

    def __ensure_ssh_key(self):
        # TODO replace with new call to NBAPI
        # https://jira.mobile-cloud-networking.eu/browse/SM-17
        # key is an OCCI Kind
        # XXX THIS IS A HACK - it goes _inside_ the CC implementation... BAD!!!!
        #
        # variables in config file are: ssh_key_location, ops_api
        # KEY_ATTR = {'occi.key.name': '',
        #             'occi.key.content': 'required'}
        #
        # KEY_KIND = occi.core_model.Kind('http://schemas.ogf.org/occi/security/'
        #                                 'credentials#',
        #                                 'public_key', title='A ssh key.',
        #                                 attributes=KEY_ATTR,
        #                                 related=[occi.core_model.Resource.kind])
        #
        # self.conn.request('GET', app_uri_path, headers={'Accept': 'text/occi'})
        # resp = self.conn.getresponse()
        # attrs = resp.getheader('X-OCCI-Attribute')
        # repo_uri = ''
        #
        # if x:
        #     create_app_headers['X-OCCI-Attribute'] = 'occi.app.name=serviceinstance'
        #     LOG.debug('Requesting container to execute SO Bundle')
        #     #TODO requests should be placed on a queue as this is a blocking call
        #     self.conn.request('POST', '/app/', headers=create_app_headers)
        #     resp = self.conn.getresponse()

        LOG.debug('Ensuring valid SM SSH is registered with OpenShift...')
        ops_url = urlparse(OPS_URL)
        LOG.debug('OpenShift endpoint: ' + ops_url)
        ops = Openshift(ops_url.hostname, ops_url.username, ops_url.password)

        if len(ops.keys_list()[1]['data']) == 0:
            # this adds the default key
            # TODO use the key specified in the config file, if it exists
            LOG.debug('No SM SSH regsitered. Registering default SM SSH key.')
            ops.key_add({
                'name': 'ServiceManager'
            })
