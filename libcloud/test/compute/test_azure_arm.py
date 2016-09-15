import os

import libcloud.resolve

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider
from libcloud.test import LibcloudTestCase, MockHttp


class AzureNodeDriverTests(LibcloudTestCase):
    #  required otherwise we get client side SSL verification
    libcloud.security.VERIFY_SSL_CERT = False

    SUBSCRIPTION_ID = ''
    KEY_FILE = os.path.join(os.path.dirname(__file__), 'fixtures/azure/libcloud.pem')

    def setUp(self):
        Azure_Arm = get_driver(Provider.AZURE_ARM)
        Azure_Arm.connectionCls.conn_classes = (None, AzureArmMockHttp)
        self.driver = Azure_Arm(self.SUBSCRIPTION_ID, self.KEY_FILE)

    def test_locations_returned_successfully(self):
        locations = self.driver.list_locations()
        self.assertEqual(len(locations), 7)

        location_names_result = list(a.name for a in locations)
        location_names_expected = [
            'East Asia',
            'Southeast Asia',
            'North Europe',
            'West Europe',
            'East US',
            'North Central US',
            'West US'
        ]

        self.assertListEqual(location_names_result, location_names_expected)

        matched_location = next(
            location for location in locations
            if location.name == 'Southeast Asia'
        )
        services_result = matched_location.available_services
        services_expected = [
            'Compute',
            'Storage',
            'PersistentVMRole',
            'HighMemory'
        ]
        self.assertListEqual(services_result, services_expected)

        vm_role_sizes_result = matched_location.virtual_machine_role_sizes

        vm_role_sizes_expected = [
            'A5',
            'A6',
            'A7',
            'Basic_A0',
            'Basic_A1',
            'Basic_A2',
            'Basic_A3',
            'Basic_A4',
            'ExtraLarge',
            'ExtraSmall',
            'Large',
            'Medium',
            'Small'
        ]
        self.assertListEqual(vm_role_sizes_result, vm_role_sizes_expected)

    def test_list_nodes_returned_successfully(self):
        raise NotImplementedError

    def test_list_nodes_returned_no_deployments(self):
        raise NotImplementedError

    def test_create_node_and_deployment_one_node(self):
        raise NotImplementedError

    def test_create_node_and_deployment_second_node(self):
        raise NotImplementedError

    def test_create_node_and_deployment_second_node_307_response(self):
        raise NotImplementedError

class AzureArmMockHttp(MockHttp):

    fixtures = None
