# -*- coding: utf-8 -*-
import csv
import unittest
from datetime import datetime
from io import StringIO

import transaction
from plone import api
from plone.app.testing import (
    SITE_OWNER_NAME,
    SITE_OWNER_PASSWORD,
    TEST_USER_ID,
    setRoles,
)
from plone.restapi.testing import RelativeSession
from Products.MailHost.interfaces import IMailHost
from zope.component import getUtility

from collective.volto.formsupport.testing import (  # noqa: E501,
    VOLTO_FORMSUPPORT_API_FUNCTIONAL_TESTING,
)


class TestMailSend(unittest.TestCase):
    layer = VOLTO_FORMSUPPORT_API_FUNCTIONAL_TESTING

    def setUp(self):
        self.app = self.layer["app"]
        self.portal = self.layer["portal"]
        self.portal_url = self.portal.absolute_url()
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

        self.mailhost = getUtility(IMailHost)

        self.api_session = RelativeSession(self.portal_url)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        self.anon_api_session = RelativeSession(self.portal_url)
        self.anon_api_session.headers.update({"Accept": "application/json"})

        self.document = api.content.create(
            type="Document",
            title="Example context",
            container=self.portal,
        )

        self.document.blocks = {
            "text-id": {"@type": "text"},
            "form-id": {"@type": "form"},
        }
        self.document_url = self.document.absolute_url()
        transaction.commit()

    def tearDown(self):
        self.api_session.close()
        self.anon_api_session.close()

        # set default block
        self.document.blocks = {
            "text-id": {"@type": "text"},
            "form-id": {"@type": "form"},
        }
        transaction.commit()

    def submit_form(self, data):
        url = "{}/@submit-form".format(self.document_url)
        response = self.api_session.post(
            url,
            json=data,
        )
        transaction.commit()
        return response

    def export_data(self):
        url = "{}/@form-data".format(self.document_url)
        response = self.api_session.get(url)
        return response

    def export_csv(self):
        url = "{}/@form-data-export".format(self.document_url)
        response = self.api_session.get(url)
        return response

    def clear_data(self):
        url = "{}/@form-data-clear".format(self.document_url)
        response = self.api_session.get(url)
        # transaction.commit()
        return response

    def test_unable_to_store_data(self):
        """form schema not defined, unable to store data"""
        self.document.blocks = {
            "form-id": {"@type": "form", "store": True},
        }
        transaction.commit()

        response = self.submit_form(
            data={
                "from": "john@doe.com",
                "data": [
                    {"label": "Message", "value": "just want to say hi"},
                    {"label": "Name", "value": "John"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )
        transaction.commit()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Unable to store data")
        response = self.export_csv()

    def test_store_data(self):
        self.document.blocks = {
            "form-id": {
                "@type": "form",
                "store": True,
                "subblocks": [
                    {
                        "label": "Message",
                        "field_id": "message",
                        "field_type": "text",
                    },
                    {
                        "label": "Name",
                        "field_id": "name",
                        "field_type": "text",
                        "display_values": "Custom name",
                    },
                ],
            },
        }
        transaction.commit()

        response = self.submit_form(
            data={
                "from": "john@doe.com",
                "data": [
                    {"field_id": "message", "value": "just want to say hi"},
                    {"field_id": "name", "value": "John"},
                    {"field_id": "foo", "value": "skip this"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )
        transaction.commit()
        self.assertEqual(response.status_code, 204)
        response = self.export_data()
        data = response.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(
            sorted(data["items"][0].keys()),
            ["block_id", "date", "id", "message", "name"],
        )
        self.assertEqual(
            data["items"][0]["message"],
            {"label": "Message", "value": "just want to say hi"},
        )
        self.assertEqual(data["items"][0]["name"], {"label": "Name", "value": "John"})
        response = self.submit_form(
            data={
                "from": "sally@doe.com",
                "data": [
                    {"field_id": "message", "value": "bye"},
                    {"field_id": "name", "value": "Sally"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )
        transaction.commit()
        self.assertEqual(response.status_code, 204)
        response = self.export_data()
        data = response.json()
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(
            sorted(data["items"][0].keys()),
            ["block_id", "date", "id", "message", "name"],
        )
        self.assertEqual(
            sorted(data["items"][1].keys()),
            ["block_id", "date", "id", "message", "name"],
        )
        sorted_data = sorted(data["items"], key=lambda x: x["name"]["value"])
        self.assertEqual(sorted_data[0]["name"]["value"], "John")
        self.assertEqual(sorted_data[0]["message"]["value"], "just want to say hi")
        self.assertEqual(sorted_data[1]["name"]["value"], "Sally")
        self.assertEqual(sorted_data[1]["message"]["value"], "bye")

        # clear data
        response = self.clear_data()
        self.assertEqual(response.status_code, 204)
        response = self.export_csv()
        data = [*csv.reader(StringIO(response.text), delimiter=",")]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0], ["date"])

    def test_export_csv(self):
        self.document.blocks = {
            "form-id": {
                "@type": "form",
                "store": True,
                "subblocks": [
                    {
                        "label": "Message",
                        "field_id": "message",
                        "field_type": "text",
                    },
                    {
                        "label": "Name",
                        "field_id": "name",
                        "field_type": "text",
                    },
                ],
            },
        }
        transaction.commit()
        response = self.submit_form(
            data={
                "from": "john@doe.com",
                "data": [
                    {"field_id": "message", "value": "just want to say hi"},
                    {"field_id": "name", "value": "John"},
                    {"field_id": "foo", "value": "skip this"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )

        response = self.submit_form(
            data={
                "from": "sally@doe.com",
                "data": [
                    {"field_id": "message", "value": "bye"},
                    {"field_id": "name", "value": "Sally"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )

        self.assertEqual(response.status_code, 204)
        response = self.export_csv()
        data = [*csv.reader(StringIO(response.text), delimiter=",")]
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0], ["Message", "Name", "date"])
        sorted_data = sorted(data[1:])
        self.assertEqual(sorted_data[0][:-1], ["bye", "Sally"])
        self.assertEqual(sorted_data[1][:-1], ["just want to say hi", "John"])

        # check date column. Skip seconds because can change during test
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
        self.assertTrue(sorted_data[0][-1].startswith(now))
        self.assertTrue(sorted_data[1][-1].startswith(now))

    def test_data_id_mapping(self):
        self.document.blocks = {
            "form-id": {
                "@type": "form",
                "store": True,
                "test-field": "renamed-field",
                "subblocks": [
                    {
                        "field_id": "message",
                        "label": "Message",
                        "field_type": "text",
                    },
                    {
                        "field_id": "test-field",
                        "label": "Test field",
                        "field_type": "text",
                    },
                ],
            },
        }
        transaction.commit()
        response = self.submit_form(
            data={
                "from": "john@doe.com",
                "data": [
                    {"field_id": "message", "value": "just want to say hi"},
                    {"field_id": "test-field", "value": "John"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )

        response = self.submit_form(
            data={
                "from": "sally@doe.com",
                "data": [
                    {"field_id": "message", "value": "bye"},
                    {"field_id": "test-field", "value": "Sally"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )

        self.assertEqual(response.status_code, 204)
        response = self.export_csv()
        data = [*csv.reader(StringIO(response.text), delimiter=",")]
        self.assertEqual(len(data), 3)
        # Check that 'test-field' got correctly mapped to it's label
        self.assertEqual(data[0], ["Message", "Test field", "date"])
        sorted_data = sorted(data[1:])
        self.assertEqual(sorted_data[0][:-1], ["bye", "Sally"])
        self.assertEqual(sorted_data[1][:-1], ["just want to say hi", "John"])

        # check date column. Skip seconds because can change during test
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
        self.assertTrue(sorted_data[0][-1].startswith(now))
        self.assertTrue(sorted_data[1][-1].startswith(now))

    def test_display_values(self):
        self.document.blocks = {
            "form-id": {
                "@type": "form",
                "store": True,
                "test-field": "renamed-field",
                "subblocks": [
                    {
                        "field_id": "message",
                        "label": "Message",
                        "field_type": "text",
                    },
                    {
                        "field_id": "test-field",
                        "label": "Test field",
                        "field_type": "text",
                        "display_values": {"John": "Paul", "Sally": "Jack"},
                    },
                ],
            },
        }
        transaction.commit()
        response = self.submit_form(
            data={
                "from": "john@doe.com",
                "data": [
                    {"field_id": "message", "value": "just want to say hi"},
                    {"field_id": "test-field", "value": "John"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )

        response = self.submit_form(
            data={
                "from": "sally@doe.com",
                "data": [
                    {"field_id": "message", "value": "bye"},
                    {"field_id": "test-field", "value": "Sally"},
                ],
                "subject": "test subject",
                "block_id": "form-id",
            },
        )

        self.assertEqual(response.status_code, 204)
        response = self.export_csv()
        data = [*csv.reader(StringIO(response.text), delimiter=",")]
        self.assertEqual(len(data), 3)
        # Check that 'test-field' got correctly mapped to it's label
        self.assertEqual(data[0], ["Message", "Test field", "date"])
        sorted_data = sorted(data[1:])
        self.assertEqual(sorted_data[0][:-1], ["bye", "Sally"])
        self.assertEqual(sorted_data[1][:-1], ["just want to say hi", "John"])

        # check date column. Skip seconds because can change during test
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
        self.assertTrue(sorted_data[0][-1].startswith(now))
        self.assertTrue(sorted_data[1][-1].startswith(now))
