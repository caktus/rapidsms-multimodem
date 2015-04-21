# coding: utf-8
from __future__ import unicode_literals
from mock import patch, MagicMock

from django.test import TestCase

from rapidsms.tests.harness import CreateDataMixin

from rapidsms_multimodem.outgoing import MultiModemBackend, ISMS_ASCII, ISMS_UNICODE


class SendTest(CreateDataMixin, TestCase):

    def setUp(self):
        config = {
            'sendsms_url': 'http://192.168.170.200:81/sendmsg',
            'sendsms_user': 'admin',
            'sendsms_pass': 'admin',
            'modem_port': 1,
            'server_slug': 'isms-lebanon',
        }
        self.backend = MultiModemBackend(None, "multimodem", **config)

    def test_required_fields(self):
        """Multimodem backend requires Gateway URL and credentials."""
        self.assertRaises(TypeError, MultiModemBackend, None, "multimodem")

    def test_prepare_querystring(self):
        message = self.create_outgoing_message(data={'text': 'a message'})
        query_string = self.backend.prepare_querystring(id_=message.id,
                                                        text=message.text,
                                                        identities=message.connections[0].identity,
                                                        context={})
        self.assertIn('user=admin', query_string)
        self.assertIn('passwd=admin', query_string)
        self.assertIn('enc={}'.format(ISMS_ASCII), query_string)
        self.assertIn('modem=1', query_string)
        # just ensure the text param is there. content is tested in test_utils.py
        self.assertIn('text=', query_string)

    def test_prepare_unicode_querystring(self):
        unicode_string = 'Щнпзнмгмжнм'
        message = self.create_outgoing_message(data={'text': unicode_string})
        query_string = self.backend.prepare_querystring(id_=message.id,
                                                        text=message.text,
                                                        identities=message.connections[0].identity,
                                                        context={})
        self.assertIn('enc={}'.format(ISMS_UNICODE), query_string)
        # just ensure the text param is there. content is tested in test_utils.py
        self.assertIn('text=', query_string)

    @patch('rapidsms_multimodem.outgoing.requests')
    def test_send_one(self, mock_requests):
        message = self.create_outgoing_message(data={'text': 'a message'})
        # Fake an OK response
        mock_requests.get.return_value.status_code = mock_requests.codes.ok
        self.backend.send(id_=message.id,
                          text=message.text,
                          identities=[message.connections[0].identity],
                          context={})
        self.assertTrue(mock_requests.get.called)
        self.assertEqual(mock_requests.get.call_count, 1)

    @patch('rapidsms_multimodem.outgoing.requests')
    def test_send_multiple(self, mock_requests):
        conn1 = self.create_connection()
        conn2 = self.create_connection(data={'backend': conn1.backend})
        message = self.create_outgoing_message(data={'text': 'a message',
                                                     'connections': [conn1, conn2]})
        # Fake an OK response
        mock_requests.get.return_value.status_code = mock_requests.codes.ok
        self.backend.send(id_=message.id,
                          text=message.text,
                          identities=[conn.identity for conn in message.connections],
                          context={})
        self.assertTrue(mock_requests.get.called)
        # Since multimodem only accepts 1 identity per request, it should get called twice
        self.assertEqual(mock_requests.get.call_count, 2)

    @patch('rapidsms_multimodem.outgoing.requests')
    def test_send_multiple_with_one_http_error(self, mock_requests):
        conn1 = self.create_connection()
        conn2 = self.create_connection(data={'backend': conn1.backend})
        message = self.create_outgoing_message(data={'text': 'a message',
                                                     'connections': [conn1, conn2]})
        # Fake one BAD (400) and one OK (200) response
        rsp1 = MagicMock(status_code=mock_requests.codes.bad)
        rsp2 = MagicMock(status_code=mock_requests.codes.ok)
        # each time requests is called, mock will return the next side_effect in the list
        # https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock
        mock_requests.get.side_effect = [rsp1, rsp2]
        with self.assertRaises(Exception) as cm:
            self.backend.send(id_=message.id,
                              text=message.text,
                              identities=[conn.identity for conn in message.connections],
                              context={})
        # even though the first message raised an error, requests gets called twice
        # i.e. bad message doesn't block the good message
        self.assertEqual(mock_requests.get.call_count, 2)
        error_string, failures = cm.exception.args
        self.assertEqual(len(failures), 1)
        self.assertIn(conn1.identity, failures)
        self.assertNotIn(conn2.identity, failures)

    @patch('rapidsms_multimodem.outgoing.requests')
    def test_send_multiple_with_one_multimodem_error(self, mock_requests):
        conn1 = self.create_connection()
        conn2 = self.create_connection(data={'backend': conn1.backend})
        message = self.create_outgoing_message(data={'text': 'a message',
                                                     'connections': [conn1, conn2]})
        # Fake one multimodem error and one multimodem success response
        rsp1 = MagicMock(
            status_code=mock_requests.codes.ok,
            text="Err: blah"
        )
        rsp2 = MagicMock(
            status_code=mock_requests.codes.ok,
            text="Success"
        )
        # each time requests is called, mock will return the next side_effect in the list
        # https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock
        mock_requests.get.side_effect = [rsp1, rsp2]
        with self.assertRaises(Exception) as cm:
            self.backend.send(id_=message.id,
                              text=message.text,
                              identities=[conn.identity for conn in message.connections],
                              context={})
        # even though the first message raised an error, requests gets called twice
        # i.e. bad message doesn't block the good message
        self.assertEqual(mock_requests.get.call_count, 2)
        error_string, failures = cm.exception.args
        self.assertEqual(len(failures), 1)
        self.assertIn(conn1.identity, failures)
        self.assertNotIn(conn2.identity, failures)
