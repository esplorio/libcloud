import sys

from libcloud.common.azure import AzureResourceManagerConnection, AzureRedirectException
from libcloud.compute.base import NodeDriver
from libcloud.compute.drivers.azure import AzureHTTPRequest
from libcloud.compute.drivers.vcloud import urlparse
from libcloud.compute.types import Provider

from libcloud.utils.py3 import urlquote as url_quote

AZURE_RESOURCE_MANAGEMENT_HOST = 'management.azure.com'
API_VERSION = '2016-03-30'


class AzureARMNodeDriver(NodeDriver):
    connectionCls = AzureResourceManagerConnection
    name = 'Azure Virtual machines'
    website = 'http://azure.microsoft.com/en-us/services/virtual-machines/'
    type = Provider.AZURE_ARM

    def __init__(self, subscription_id=None, token=None, **kwargs):
        """
        subscription_id contains the Azure subscription id in the form of GUID
        key_file contains the Azure X509 certificate in .pem form
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

    def _perform_get(self, path):
        request = AzureHTTPRequest()
        request.method = 'GET'
        request.host = AZURE_RESOURCE_MANAGEMENT_HOST
        request.path = path
        request.path, request.query = self._update_request_uri_query(request)
        return self._perform_request(request)

    def _update_request_uri_query(self, request):
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

        # add encoded queries to request.path.
        if request.query:
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

    def _perform_request(self, request):
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
        except Exception as e:
            raise e

    def _ex_connection_class_kwargs(self):
        """
        Return extra connection keyword arguments which are passed to the
        Connection class constructor.
        """
        return {
            'token': self.token
        }
