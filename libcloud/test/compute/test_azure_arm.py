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
        raise NotImplementedError

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
