import os

import libcloud.security
from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider, NodeState
from libcloud.test import LibcloudTestCase, MockHttp
from libcloud.test.file_fixtures import ComputeFileFixtures
from libcloud.utils.py3 import httplib


class AzureArmNodeDriverTests(LibcloudTestCase):
    #  required otherwise we get client side SSL verification
    libcloud.security.VERIFY_SSL_CERT = False

    SUBSCRIPTION_ID = '3s42h548_4f8h_948h_3847_663h35u3905h'
    KEY_FILE = os.path.join(os.path.dirname(__file__), 'fixtures/azure/libcloud.pem')

    def setUp(self):
        Azure_Arm = get_driver(Provider.AZURE_ARM)
        Azure_Arm.connectionCls.conn_classes = (None, AzureArmMockHttp)
        self.driver = Azure_Arm(self.SUBSCRIPTION_ID, self.KEY_FILE)

    def test_locations_returned_successfully(self):
        locations = self.driver.list_locations()
        self.assertEqual(len(locations), 24)
        location_names_result = list(a.country for a in locations)
        location_names_expected = [
            'East Asia',
            'Southeast Asia',
            'Central US',
            'East US',
            'East US 2',
            'West US',
            'North Central US',
            'South Central US',
            'North Europe',
            'West Europe',
            'Japan West',
            'Japan East',
            'Brazil South',
            'Australia East',
            'Australia Southeast',
            'South India',
            'Central India',
            'West India',
            'Canada Central',
            'Canada East',
            'UK South',
            'UK West',
            'West Central US',
            'West US 2'
        ]
        print(location_names_result)

        self.assertListEqual(location_names_result, location_names_expected)

    def test_list_nodes_with_ressouce_group_returned_successfully(self):
        vmimages = self.driver.list_nodes('myapp')
        self.assertEqual(len(vmimages), 1)
        vmimage = vmimages[0]
        self.assertEqual("myvm", vmimage.id)
        self.assertEqual("myvm", vmimage.id)
        self.assertEqual(NodeState.RUNNING, vmimage.state)
        self.assertEqual(["1.1.1.1"], vmimage.public_ips)
        self.assertEqual(["10.1.1.1"], vmimage.private_ips)

    def test_list_nodes_without_resource_group(self):
        vmimages = self.driver.list_nodes()
        self.assertEqual(len(vmimages), 1)
        vmimage = vmimages[0]
        self.assertEqual("myvm", vmimage.id)
        self.assertEqual("myvm", vmimage.id)
        self.assertEqual(NodeState.RUNNING, vmimage.state)
        self.assertEqual(["1.1.1.1"], vmimage.public_ips)
        self.assertEqual(["10.1.1.1"], vmimage.private_ips)

    def test_list_nodes_with_wrong_resource_group(self):
        self.assertRaises(AssertionError, self.driver.list_nodes, 'fakegroup')


    def test_create_node_and_deployment_one_node(self):
        raise NotImplementedError

    def test_create_node_and_deployment_second_node(self):
        raise NotImplementedError

    def test_create_node_and_deployment_second_node_307_response(self):
        raise NotImplementedError

class AzureArmMockHttp(MockHttp):

    fixtures = ComputeFileFixtures('azure_arm')

    def _subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_locations(self, method, url, body, headers):
        """ Requests the list of locations from microsoft azure"""
        if method == "GET":
            body = self.fixtures.load(
                '_subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_locations.json')

        return httplib.OK, body, headers, httplib.responses[httplib.OK]

    def _subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_providers_Microsoft_Compute_virtualMachines(self, method, url, body, headers):
        """ Request for the list of nodes of the subscriber """
        if method == "GET":
            body = self.fixtures.load(
                '_subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_providers_Microsoft_Compute_virtualmachines.json')

        return httplib.OK, body, headers, httplib.responses[httplib.OK]

    def _subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_myapp_providers_Microsoft_Compute_virtualMachines(self, method, url, body, headers):
        """ Requests list of nodes for the resource group """
        if method == "GET":
            body = self.fixtures.load(
                '_subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_myapp_providers_Microsoft_Compute_virtualmachines.json')

        return httplib.OK, body, headers, httplib.responses[httplib.OK]

    def _subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_fakegroup_providers_Microsoft_Compute_virtualMachines(self, method, url, body, headers):
        """ Bad request for nodes in a resource group that not exist """
        if method == "GET":
            body = self.fixtures.load(
                '_subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_fakegroup_providers_Microsoft_Compute_virtualmachines.json')

        return httplib.NOT_FOUND, body, headers, httplib.responses[
            httplib.NOT_FOUND]

    def _subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_myapp_providers_Microsoft_Network_networkInterfaces_user_brazi_40wudhabjn7g_nic(self, method, url, body, headers):
        """ A request for the network interface card information about vm1"""
        if method == "GET":
            body = self.fixtures.load(
                '_subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_myapp_providers_Microsoft_Network_networkInterfaces_user_brazi_40wudhabjn7g_nic.json'
            )

        return httplib.OK, body, headers, httplib.responses[httplib.OK]

    def _subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_myapp_providers_Microsoft_Network_publicIPAddresses_user_brazi_40wudhabjn7g_pip(self, method, url, body, headers):
        """ A request for the public ip information included in the nic above"""
        if method == "GET":
            body = self.fixtures.load(
                '_subscriptions_3s42h548_4f8h_948h_3847_663h35u3905h_resourceGroups_myapp_providers_Microsoft_Network_publicIPAddresses_user_brazi_40wudhabjn7g_pip.json'
            )

        return httplib.OK, body, headers, httplib.responses[httplib.OK]
