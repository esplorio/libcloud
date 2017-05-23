import json
import sys

import time

from libcloud.common.azure import AzureResourceManagerConnection, \
    AzureRedirectException
from libcloud.common.exceptions import RateLimitReachedError
from libcloud.compute.base import NodeDriver, NodeLocation, NodeSize, Node, \
    NodeImage
from libcloud.compute.drivers.azure import AzureHTTPRequest
from libcloud.compute.drivers.vcloud import urlparse
from libcloud.compute.types import Provider, NodeState

from libcloud.utils.py3 import urlquote as url_quote, ensure_string

AZURE_RESOURCE_MANAGEMENT_HOST = 'management.azure.com'
DEFAULT_API_VERSION = '2016-07-01'
MAX_RETRIES = 5
if sys.version_info < (3,):
    _unicode_type = unicode

    def _str(value):
        if isinstance(value, unicode):
            return value.encode('utf-8')

        return str(value)
else:
    _str = str
    _unicode_type = str


class AzureImage(NodeImage):
    def __init__(self, publisher, offer, sku, os, version, location, driver):
        self.publisher = publisher
        self.offer = offer
        self.sku = sku
        self.os = os
        self.version = version
        self.location = location
        self.driver = driver
        urn = "%s:%s:%s:%s:%s" % (self.publisher, self.offer,
                                  self.sku, self.os, self.version)
        name = "%s %s %s %s %s" % (self.publisher, self.offer,
                                   self.sku, self.os, self.version)
        super(AzureImage, self).__init__(urn, name, driver)

    def __repr__(self):
        return ('<AzureImage: id=%s, name=%s, location=%s>'
                % (self.id, self.name, self.location))

    def _get_image_reference(self):
        return {
            'publisher': self.publisher,
            'offer': self.offer,
            'sku': self.sku,
            'version': self.version
        }


class AzureVirtualNetwork(object):
    def __init__(self, id, name, location, driver, snets=None):
        self.id = id
        self.name = name
        self.location = location
        self.driver = driver
        if snets:
            self.snets = snets
        else:
            self.snets = self.driver.ex_list_subnets(self.id)

    def __repr__(self):
        return ('<AzureNetwork: id=%s, name=%s, location=%s>'
                % (self.id, self.name, self.location))


class AzureSubNet(object):
    def __init__(self, id, name, driver):
        self.id = id
        self.name = name
        self.driver = driver

    def __repr__(self):
        return ('<AzureNetwork: id=%s, name=%s'
                % (self.id, self.name))


class AzureNetworkConfig(object):
    def __init__(self, virtual_network, subnet, public_ip_allocation,
                 public_ip_address=None):
        snet_names = [snet.name for snet in virtual_network.snets]
        if subnet.name not in snet_names:
            raise AssertionError(
                "Invalid Subnet: Subnet is part of the Virtual Network given")

        self.virtual_network = virtual_network
        self.subnet = subnet
        self.public_ip_alllocation = public_ip_allocation
        self.public_ip_adress = public_ip_address


class AzureARMNodeDriver(NodeDriver):
    connectionCls = AzureResourceManagerConnection
    name = 'Azure Virtual machines'
    website = 'http://azure.microsoft.com/en-us/services/virtual-machines/'
    type = Provider.AZURE_ARM

    def __init__(self, subscription_id=None, token=None, **kwargs):
        """
        subscription_id contains the Azure subscription id in the form of GUID
        token is an OAuth 2 token to authenticate with ARM

        Steps to produce a token (won't work straight away on Macs):
        https://blogs.msdn.microsoft.com/arsen/2015/09/18/certificate-based
        -auth-with-azure-service-principals-from-linux-command-line/
        Now to make the above to work with Macs, you'd need to make these
        changes:
            - The call to generate base64 fingerprint should be:
            `echo $(openssl x509 -in esplorio-azure-ad-cert.pem
                -fingerprint -noout) | sed 's/SHA1 Fingerprint=//g' |
                    sed 's/://g' | xxd -r -ps | base64`
            - Instead of `head`, use `ghead` from `brew install coreutils`, and
                then do: `tail -n+2 esplorio-azure-ad-cert.pem | ghead -n-1`
            - To create the AD app:
            `azure ad app create --name "esplorio-cli-tools"
                --home-page "http://esplorio-cli-tools/"
                --identifier-uris "http://esplorio-cli-tools/"
                --key-usage "Verify"
                --end-date "2020-01-01"
                --key-value
                "$(tail -n+2 esplorio-azure-ad-cert.pem | ghead -n-1)"`
            - Use `-a` option in `azure ad sp create -a
                <Copy and Paste Application Id GUID Here>`
            - Command to fetch the Tenant ID: `azure account show`
        """
        self.subscription_id = subscription_id
        self.token = token
        self.follow_redirects = kwargs.get('follow_redirects', True)
        super(AzureARMNodeDriver, self).__init__(
            self.subscription_id,
            self.token,
            secure=True,
            **kwargs
        )

    def list_nodes(self, ex_resource_group=None):
        """
        List all nodes in a resource group
        """
        if ex_resource_group:
            path = '%sresourceGroups/%s/providers' \
                   '/Microsoft.Compute/virtualMachines' % \
                   (self._default_path_prefix, ex_resource_group)
        else:
            path = '%sproviders/Microsoft.Compute/virtualMachines' \
                   % self._default_path_prefix

        json_response = self._perform_get(path, api_version='2016-03-30')
        raw_data = json_response.parse_body()
        if (int(json_response.status)) != 200:
            raise AssertionError('%s' % raw_data['error']['message'] )
        return [self._to_node(x) for x in raw_data['value']]

    def list_sizes(self, location):
        """
        List all image sizes available for location
        """
        path = '%sproviders/Microsoft.Compute/locations/%s/vmSizes' % (
            self._default_path_prefix, location)
        json_response = self._perform_get(path, api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return [self._to_size(x) for x in raw_data['value']]

    def list_locations(self):
        """
        Lists all locations

        :rtype: ``list`` of :class:`NodeLocation`
        """
        path = '%slocations' % self._default_path_prefix
        json_response = self._perform_get(path)
        raw_data = json_response.parse_body()
        return [self._to_location(x) for x in raw_data['value']]

    def create_node(self, name, location, node_size,
                    ex_resource_group_name,
                    ex_network_config,
                    ex_admin_username,
                    ex_marketplace_image,
                    ex_os_disk,
                    ex_data_disks=None,
                    ex_availability_set=None,
                    ex_public_ip_address=None,
                    ex_public_key=None):

        """
        Create Azure Virtual Machine using Resource Management model.

        For now this only creates a Linux machine, always default to public IP
        address, and only support 1 data disk.

        It also assumes you have created these things:
        - A resource group
        - A storage account
        - A virtual network
        - A valid subnet inside the virtual network

        @inherits: :class:`NodeDriver.create_node`

        :keyword     name: Required. The name given to this node
        :type        name:  `str`

        :keyword     location: Required.  The location of the node to create
        :type        location: `NodeLocation`

        :keyword     node_size: Required.  The size of the node to create
        :type        node_size: `NodeSize`

        :keyword     ex_resource_group_name: Required.
                     The name of the resource group the node belongs to
        :type        ex_resource_group_name: `str`

        :keyword     ex_storage_account_name: Required.
                     The name of the storage account the disks on the node
                                              belongs to
        :type        ex_storage_account_name: `str`

        :keyword     ex_network_config: Required
                     Class holds the network information needed to create a
                     a node e.g. the virtual network and subnet the node is
                     connected to
        :type        ex_network_config: `AzureNetworkConfig`

        :keyword     ex_admin_username: Required.
                     The name of the default admin user on the node
        :type        ex_admin_username: `str`

        :keyword     ex_marketplace_image: Required.
                     The image from market place to be used for setting up the
                     OS disk.
        :type        ex_marketplace_image: `AzureImage`

        :keyword     ex_os_disk: a dictionary containing the desired OS Disk
                     config including the storage account (`account`) and the
                     size in GB (`size`)
        :type        ex_os_disk: `dict`

        :keyword     ex_data_disks: Optional.
                     A list of dictionaries containing the desired data disk
                     config including the storage profile (`profile`) and the
                     (`size`)
        :type        ex_data_disks: `list`

        :keyword     ex_availability_set: Optional.
                     The availability set that the node lives in
        :type        ex_availability_set: `int`

        :keyword     ex_public_ip_address: Optional.
                     User can provide one will be created for them
        :type        ex_public_ip_address: 'string'

        :keyword     ex_public_key: Optional.
                     The content of the SSH public key to be deployed on the
                     box
        :type        ex_public_key: `str`
        """
        if not ex_network_config:
            raise AssertionError(' Network configuration needed. Can be'
                                 'like this, AzureNetworkConfig(vm, snet, '
                                 'public_ip_allocation, public_ip_address')

        if ex_resource_group_name not in ex_network_config.virtual_network.id:
            raise AssertionError(' Resource group and virtual network do not '
                                 'match. Enter networks within the resource'
                                 'group')

        # Create the network interface card with that public IP address
        nic = self._create_network_interface(name, ex_resource_group_name,
                                             location, ex_network_config)
        # Create the machine
        node_payload = {
            'name': name,
            'location': location.id,
        }

        os_disk_name = '%s-os-disk' % name

        node_payload['properties'] = {
            'hardwareProfile': {
                'vmSize': node_size.id
            },
            'storageProfile': {
                'imageReference': ex_marketplace_image._get_image_reference(),
                'osDisk': {
                    'name': os_disk_name,
                    'vhd': {
                        'uri': 'http://%s.blob.core.windows.net/vhds/%s.vhd' %
                               (ex_os_disk['account'], os_disk_name)
                    },
                    'caching': 'ReadWrite',
                    'createOption': 'fromImage',
                    'diskSizeGB': ex_os_disk['size']
                }
            },
            'osProfile': {
                'computerName': name,
                'adminUsername': ex_admin_username,
                'linuxConfiguration': {
                    'disablePasswordAuthentication': True,
                    'ssh': {
                        'publicKeys': [
                            {
                                'path': '/home/%s/.ssh/authorized_keys' %
                                        ex_admin_username,
                                'keyData': ex_public_key
                            }
                        ]
                    }
                }
            },
            'networkProfile': {
                'networkInterfaces': [
                    {
                        'id': nic['id'],
                        'properties': {
                            'primary': True
                        }
                    }
                ]
            }
        }

        if ex_data_disks:
            for i, disk in enumerate(ex_data_disks):
                data_disk_name = '%s-data-disk-%d' % (name, i)
                # Attach an empty data disk if value this is given
                node_payload['properties']['storageProfile']['dataDisks'] = [
                    {
                        'name': data_disk_name,
                        'diskSizeGB': disk['size'],
                        'lun': 0,
                        'vhd': {
                            'uri': 'http://%s.blob.core.windows.net/vhds/%s.vhd' %
                                   (disk['account'], data_disk_name)
                        },
                        'caching': 'ReadWrite',
                        'createOption': 'empty'
                    }
                ]

        if ex_availability_set:
            availability_set_id = \
                '/subscriptions/%s/resourceGroups/%s/providers/' \
                'Microsoft.Compute/availabilitySets/%s' % \
                (self.subscription_id, ex_resource_group_name,
                 ex_availability_set)
            node_payload['properties']['availabilitySet'] = {
                'id': availability_set_id
            }

        path = '%sresourceGroups/%s/providers/' \
               'Microsoft.Compute/virtualMachines/%s' % \
               (self._default_path_prefix, ex_resource_group_name, name)

        output = self._perform_put(path, node_payload,
                                   api_version='2016-03-30')
        output = output.parse_body()

        if 'error' in output:
            raise Exception('Error encountered: %s' % output['error'])

        return Node(
            id=output['id'],
            name=name,
            state=NodeState.PENDING,
            public_ips=[],
            private_ips=[],
            driver=self.connection.driver,
        )

    def reboot_node(self, node):
        """
        Reboot a node.

        :param node: The node to be rebooted
        :type node: :class:`.Node`

        :return: True if the reboot was successful, otherwise False
        :rtype: ``bool``
        """
        state = self.ex_get_state_of_node(node)
        if state == NodeState.RUNNING:
            raise AssertionError("Node is already running")
        if state == NodeState.STOPPED:
            raise AssertionError("Node has been deallocated, "
                                 "cannot be rebooted")

        path = '%s/restart' % node.id
        json_response = self._perform_post(path, api_version="2015-06-15")

        return int(json_response.status) == 200

    def destroy_node(self, node):
        """
        Destroy a node.

        Depending upon the provider, this may destroy all data associated with
        the node, including backups.

        :param node: The node to be destroyed
        :type node: :class:`.Node`

        :return: True if the destroy was successful, False otherwise.
        :rtype: ``bool``
        """

        json_response = self._perform_delete(node.id, api_version='2016-03-30')
        return json_response.success()

    def list_images(self, location=None, publisher=None):
        images = []
        if location:
            locations = [location]
        else:
            locations = [loc.name for loc in self.list_locations()]

        for loc in locations:
            path = '%sproviders/Microsoft.Compute/locations/%s/publishers'\
                   % (self._default_path_prefix, loc)
            publishers = self.ex_list_publishers(path)

            if publisher:
                publishers = [x for x in publishers
                              if x['id'].lower() == publisher.lower() or
                              x['name'].lower() == publisher.lower()]

            for pub in publishers:
                offers = self.ex_list_offers(pub['id'])

                for offer in offers:
                    skus = self.ex_list_skus(offer['id'])

                    for sku in skus:
                        versions = self.ex_list_versions(sku['id'])

                        for version in versions:
                            os = self._get_os_from_version(version['id'])
                            azure_image = AzureImage(pub['name'],
                                                     offer['name'],
                                                     sku['name'], os,
                                                     version['name'], loc,
                                                     self.connection.driver)
                            images.append(azure_image)

        # Finally, return the images
        return images

    def ex_list_publishers(self, path):
        json_response = self._perform_get(path, api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return [{'name': pub['name'], 'id': pub['id']} for pub in raw_data]

    def ex_list_offers(self, path):
        json_response = self._perform_get(
            '%s/artifacttypes/vmimage/offers' % path, api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return [{'name': offer['name'], 'id': offer['id']} for offer in
                raw_data]

    def ex_list_skus(self, path):
        json_response = self._perform_get('%s/skus' % path,
                                          api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return [{'name': sku['name'], 'id': sku['id']} for sku in raw_data]

    def ex_list_versions(self, path):
        json_response = self._perform_get('%s/versions' % path,
                                          api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return [{'name': sku['name'], 'id': sku['id']} for sku in raw_data]

    def ex_list_virtual_networks(self):
        json_response = self._perform_get(
            '%sproviders/Microsoft.Network/virtualnetworks' %
            self._default_path_prefix,
            api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return [self._to_virtual_network(x) for x in raw_data['value']]

    def ex_list_subnets(self, path):
        json_response = self._perform_get('%s/subnets' % path,
                                          api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return [self._to_subnet(x) for x in raw_data['value']]

    def _get_os_from_version(self, path):
        json_response = self._perform_get(path, api_version='2016-03-30')
        raw_data = json_response.parse_body()
        return raw_data['properties']['osDiskImage']['operatingSystem']

    def _create_network_interface(self, node_name, resource_group_name,
                                  location, network_config):
        nic_name = '%s-nic' % node_name

        payload = {
            'location': location.id,
            'properties': {
                'ipConfigurations': [{
                    'name': '%s-ip' % node_name,
                    'properties': {
                        'subnet': {
                            'id': network_config.subnet.id
                        },
                        'privateIPAllocationMethod': 'Dynamic'
                    }
                }]
            }
        }

        if network_config.public_ip_alllocation:
            if network_config.public_ip_adress:
                public_ip_address = network_config.public_ip_adress
            else:
                pip = self._create_public_ip_address(
                    node_name, resource_group_name, location)
                public_ip_address = pip['id']

            payload['properties']['ipConfigurations'][0]['properties'][
                'publicIPAddress'] = {
                'id': public_ip_address
            }

        path = '%sresourceGroups/%s/providers/Microsoft.Network/' \
               'networkInterfaces/%s' % \
               (self._default_path_prefix, resource_group_name, nic_name)
        output = self._perform_put(path, payload)

        return output.parse_body()

    def _create_public_ip_address(self, node_name, resource_group_name,
                                  location):
        public_ip_address_name = '%s-public-ip' % node_name
        payload = {
            'location': location.id,
            'properties': {
                'publicIPAllocationMethod': 'Dynamic',
                'publicIPAddressVersion': "IPv4",
                'idleTimeoutInMinutes': 5,
                "dnsSettings": {
                    "domainNameLabel": node_name
                }
            }
        }
        path = '%sresourceGroups/%s/providers/Microsoft.Network/' \
               'publicIPAddresses/%s' % \
               (self._default_path_prefix, resource_group_name,
                public_ip_address_name)

        output = self._perform_put(path, payload)
        return output.parse_body()

    def _to_node(self, node_data):
        """
        Take the azure raw data and turn into a Node class
        """
        network_interfaces = node_data.get('properties', {}).get(
            'networkProfile', {}).get(
            'networkInterfaces', [])
        network_interface_urls = ['%s' % x.get('id') for x in
                                  network_interfaces if x.get('id')]
        public_ips = []
        private_ips = []
        for network_interface_url in network_interface_urls:
            _public_ips, _private_ips = self._get_public_and_private_ips(
                network_interface_url)
            public_ips.extend(_public_ips)
            private_ips.extend(_private_ips)

        provisioning_state = node_data.get('properties', {}).get(
            'provisioningState')
        node_state = NodeState.RUNNING if provisioning_state == 'Succeeded' \
            else NodeState.PENDING

        return Node(
            id=node_data.get('id'),
            name=node_data.get('name'),
            state=node_state,
            public_ips=public_ips,
            private_ips=private_ips,
            driver=self.connection.driver,
            extra={
                'provisioningState': node_data.get('properties', {}).get(
                    'provisioningState')
            }
        )

    def _get_public_and_private_ips(self, network_interace_url):
        """
        Get public and and private ips of the virtual machine by following the
         urls provided.
        :param network_interace_url:
        :return:
        """
        json_response = self._perform_get(network_interace_url)
        raw_data = json_response.parse_body()
        ip_configurations = raw_data.get('properties', {}).get(
            'ipConfigurations', [])
        public_ips = []
        private_ips = []
        for ip_configuration in ip_configurations:
            private_ips.append(
                ip_configuration['properties']['privateIPAddress'])
            public_ips.append(
                self._get_public_ip(
                    ip_configuration['properties']['publicIPAddress']['id']))
        return public_ips, private_ips

    def _get_public_ip(self, public_ip_url):
        """
        Using the public ip url we can query the azure api and get the public
        ip adrewss
        """
        json_response = self._perform_get(public_ip_url)
        raw_data = json_response.parse_body()
        return raw_data.get('properties', {}).get('ipAddress', None)

    def _to_location(self, location_data):
        """
        Convert the data from a Azure response object into a location.
        Commented out code is from the classic Azure driver, not sure if we
        need those fields.
        """
        return NodeLocation(
            id=location_data.get('name'),
            name=location_data.get('name'),
            country=location_data.get('displayName'),
            driver=self.connection.driver,
            # available_services=data.available_services,
            # virtual_machine_role_sizes=vm_role_sizes
        )

    def _to_size(self, size_data):
        """
        Convert the data from a Azure response object into a size

        Sample raw data:
        {
            'maxDataDiskCount': 32,
            'memoryInMB': 114688,
            'name': 'Standard_D14',
            'numberOfCores': 16,
            'osDiskSizeInMB': 1047552,
            'resourceDiskSizeInMB': 819200
        }
        """
        return NodeSize(
            id=size_data.get('name'),
            name=size_data.get('name'),
            ram=size_data.get('memoryInMB'),
            disk=size_data.get('osDiskSizeInMB'),
            driver=self,
            price=-1,
            bandwidth=-1,
            extra=size_data
        )

    def _to_virtual_network(self, network_data):
        snets = [self._to_subnet(x) for x in network_data['properties'][
            'subnets']]
        return AzureVirtualNetwork(
            id=network_data.get('id'),
            name=network_data.get('name'),
            location=network_data.get('location'),
            snets=snets,
            driver=self.connection.driver
        )

    def _to_subnet(self, snet_data):
        return AzureSubNet(
            id=snet_data.get('id'),
            name=snet_data.get('name'),
            driver=self.connection.driver
        )

    def ex_get_state_of_node(self, Node):
        """
        Returns the state of a virtual machine
        """
        path = '%s/InstanceView' % Node.id
        json_response = self._perform_get(path, api_version='2016-03-30')
        raw_date = json_response.parse_body()
        raw_state = raw_date.get('statuses')[1].get('code')
        if raw_state == 'PowerState/stopped':
            return NodeState.SUSPENDED
        if raw_state == 'PowerState/running':
            return NodeState.RUNNING
        if raw_state == 'PowerState/deallocated':
                return NodeState.STOPPED

    @property
    def _default_path_prefix(self):
        """Everything starts with the subscription prefix"""
        return '/subscriptions/%s/' % self.subscription_id

    def _perform_put(self, path, body, api_version=None):
        request = AzureHTTPRequest()
        request.method = 'PUT'
        request.host = AZURE_RESOURCE_MANAGEMENT_HOST
        request.path = path
        request.body = ensure_string(self._get_request_body(body))
        request.path, request.query = self._update_request_uri_query(
            request, api_version)
        return self._perform_request(request)

    def _get_request_body(self, request_body):
        if request_body is None:
            return b''

        if isinstance(request_body, dict):
            return json.dumps(request_body)

        if isinstance(request_body, bytes):
            return request_body

        if isinstance(request_body, _unicode_type):
            return request_body.encode('utf-8')

        request_body = str(request_body)
        if isinstance(request_body, _unicode_type):
            return request_body.encode('utf-8')

        return request_body

    def _perform_get(self, path, api_version=None):
        request = AzureHTTPRequest()
        request.method = 'GET'
        request.host = AZURE_RESOURCE_MANAGEMENT_HOST
        request.path = path
        request.path, request.query = self._update_request_uri_query(
            request, api_version)
        return self._perform_request(request)

    def _perform_post(self, path, api_version=None, body=None):
        request = AzureHTTPRequest()
        request.method = 'POST'
        request.body = body
        request.host = AZURE_RESOURCE_MANAGEMENT_HOST
        request.path = path
        request.path, request.query = self._update_request_uri_query(
            request, api_version)
        return self._perform_request(request)

    def _perform_delete(self, path, api_version=None, body=None):
        request = AzureHTTPRequest()
        request.method = 'DELETE'
        request.body = body
        request.host = AZURE_RESOURCE_MANAGEMENT_HOST
        request.path = path
        request.path, request.query = self._update_request_uri_query(
            request, api_version)
        return self._perform_request(request)

    def _update_request_uri_query(self, request, api_version=None):
        """
        pulls the query string out of the URI and moves it into
        the query portion of the request object.  If there are already
        query parameters on the request the parameters in the URI will
        appear after the existing parameters
        """
        if '?' in request.path:
            request.path, _, query_string = request.path.partition('?')
            if query_string:
                query_params = query_string.split('&')
                for query in query_params:
                    if '=' in query:
                        name, _, value = query.partition('=')
                        request.query.append((name, value))

        request.path = url_quote(request.path, '/()$=\',')

        # Add the API version
        if not api_version:
            api_version_query = ('api-version', DEFAULT_API_VERSION)
        else:
            api_version_query = ('api-version', api_version)

        if request.query:
            request.query.append(api_version_query)
        else:
            request.query = [api_version_query]

        # add encoded queries to request.path.
        request.path += '?'
        for name, value in request.query:
            if value is not None:
                request.path += '%s=%s%s' % (
                    name,
                    url_quote(value, '/()$=\','),
                    '&'
                )
        request.path = request.path[:-1]

        return request.path, request.query

    def _perform_request(self, request, retries=0):
        if retries > MAX_RETRIES:
            # We have retried more than enough, let's quit
            raise Exception(
                'Maximum retries (%d) reached. Please try again later' %
                MAX_RETRIES)
        try:
            return self.connection.request(
                action=request.path,
                data=request.body,
                headers=request.headers,
                method=request.method
            )
        except AzureRedirectException:
            e = sys.exc_info()[1]
            parsed_url = urlparse.urlparse(e.location)
            request.host = parsed_url.netloc
            return self._perform_request(request)
        except RateLimitReachedError as e:
            if e.retry_after is not None:
                time.sleep(e.retry_after)
                # Redo the request but with retries value incremented
                return self._perform_request(request, retries=retries + 1)
            else:
                raise e
        except Exception as e:
            raise e
