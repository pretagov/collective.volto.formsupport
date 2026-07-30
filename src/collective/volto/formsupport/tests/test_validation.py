# -*- coding: utf-8 -*-
"""
@submit-form runs each field's authored `validations`.

A field names validators in `validations` and parameterises them in a flat
`validationSettings` keyed `<validatorId>-<settingName>`; the post adapter folds
that back into `{validator: {setting: value}}`, decides which fields the skip
logic actually showed, runs the named validators from the Products.validation
registry and answers

    400 {"error": {"type": "Invalid",
                   "errors": {"<field_id>": {"<validatorId>": "<message>"}}}}

These tests exist because the service used to read the adapter's `form_data`
attribute — the raw request body — instead of calling the adapter, so none of
this ran, and neither did `validate_form` (the CAPTCHA included).
"""

import unittest

import transaction
from plone import api
from plone.app.testing import (
    SITE_OWNER_NAME,
    SITE_OWNER_PASSWORD,
    TEST_USER_ID,
    setRoles,
)
from plone.registry.interfaces import IRegistry
from plone.restapi.testing import RelativeSession
from Products.MailHost.interfaces import IMailHost
from zope.component import getUtility

from collective.volto.formsupport.testing import (  # noqa: E501,
    VOLTO_FORMSUPPORT_API_FUNCTIONAL_TESTING,
)
from collective.volto.formsupport.validation import getValidations


def field(field_id, **kwargs):
    """A form field. `id` mirrors `field_id`, as the Volto widget writes it."""
    return {
        "field_id": field_id,
        "id": field_id,
        "field_type": "text",
        "label": field_id,
        "required": False,
        **kwargs,
    }


class TestFieldValidation(unittest.TestCase):
    layer = VOLTO_FORMSUPPORT_API_FUNCTIONAL_TESTING

    def setUp(self):
        self.app = self.layer["app"]
        self.portal = self.layer["portal"]
        self.portal_url = self.portal.absolute_url()
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

        self.mailhost = getUtility(IMailHost)
        registry = getUtility(IRegistry)
        registry["plone.email_from_address"] = "site_addr@plone.com"
        registry["plone.email_from_name"] = "Plone test site"

        self.api_session = RelativeSession(self.portal_url)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)

        self.document = api.content.create(
            type="Document",
            title="Example context",
            container=self.portal,
        )
        self.document_url = self.document.absolute_url()
        transaction.commit()

    def tearDown(self):
        self.api_session.close()
        self.document.blocks = {}
        transaction.commit()

    def set_form(self, subblocks, **block):
        self.document.blocks = {
            "form-id": {
                "@type": "form",
                "store": True,
                "subblocks": subblocks,
                **block,
            }
        }
        transaction.commit()

    def submit(self, data):
        response = self.api_session.post(
            "{}/@submit-form".format(self.document_url),
            json={"block_id": "form-id", "data": data},
        )
        transaction.commit()
        return response

    def errors(self, response):
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error"]["type"], "Invalid")
        return body["error"]["errors"]

    # ── the registry ──

    def test_the_settable_validators_are_registered(self):
        names = {name for name, _util in getValidations()}
        # The four custom ones, which are the only validators taking a setting.
        self.assertTrue(
            {"maxCharacters", "minCharacters", "maxWords", "minWords"} <= names
        )
        # A representative Products.validation base validator.
        self.assertIn("isEmail", names)
        # Explicitly excluded by VALIDATIONS_TO_IGNORE.
        self.assertNotIn("inNumericRange", names)

    # ── a rule with a setting ──

    def test_a_value_over_maxCharacters_is_rejected(self):
        self.set_form(
            [
                field(
                    "note",
                    validations=["maxCharacters"],
                    validationSettings={"maxCharacters-characters": 10},
                )
            ]
        )
        errors = self.errors(self.submit([{"field_id": "note", "value": "x" * 11}]))
        self.assertIn("note", errors)
        self.assertIn("maxCharacters", errors["note"])
        self.assertIn("10 characters", errors["note"]["maxCharacters"])

    def test_a_value_within_maxCharacters_is_accepted(self):
        self.set_form(
            [
                field(
                    "note",
                    validations=["maxCharacters"],
                    validationSettings={"maxCharacters-characters": 10},
                )
            ]
        )
        self.assertEqual(
            self.submit([{"field_id": "note", "value": "x" * 10}]).status_code, 200
        )

    def test_maxWords_counts_words_not_characters(self):
        self.set_form(
            [
                field(
                    "note",
                    field_type="textarea",
                    validations=["maxWords"],
                    validationSettings={"maxWords-words": 3},
                )
            ]
        )
        self.assertEqual(
            self.submit([{"field_id": "note", "value": "one two three"}]).status_code,
            200,
        )
        errors = self.errors(
            self.submit([{"field_id": "note", "value": "one two three four"}])
        )
        self.assertIn("maxWords", errors["note"])

    # ── the settings key format ──

    def test_a_setting_for_a_validator_not_chosen_is_ignored(self):
        # `validationSettings` is a flat bag; only the entries whose prefix is in
        # `validations` apply. An author who picks a rule, sets its limit, then
        # unpicks the rule leaves the setting behind.
        self.set_form(
            [
                field(
                    "note",
                    validations=["maxCharacters"],
                    validationSettings={
                        "maxCharacters-characters": 10,
                        "minCharacters-characters": 8,
                    },
                )
            ]
        )
        # Three characters would fail minCharacters, which was not chosen.
        self.assertEqual(
            self.submit([{"field_id": "note", "value": "abc"}]).status_code, 200
        )

    # ── several rules, several fields ──

    def test_every_failing_rule_on_a_field_is_reported(self):
        self.set_form(
            [
                field(
                    "note",
                    validations=["minCharacters", "isInt"],
                    validationSettings={"minCharacters-characters": 5},
                )
            ]
        )
        errors = self.errors(self.submit([{"field_id": "note", "value": "ab"}]))
        self.assertEqual({"minCharacters", "isInt"}, set(errors["note"]))

    def test_errors_are_keyed_by_field_so_each_lands_on_its_own_question(self):
        self.set_form(
            [
                field(
                    "one",
                    validations=["minCharacters"],
                    validationSettings={"minCharacters-characters": 5},
                ),
                field(
                    "two",
                    validations=["minCharacters"],
                    validationSettings={"minCharacters-characters": 5},
                ),
            ]
        )
        errors = self.errors(
            self.submit(
                [
                    {"field_id": "one", "value": "ab"},
                    {"field_id": "two", "value": "abcdef"},
                ]
            )
        )
        self.assertEqual(["one"], list(errors))

    # ── skip logic ──

    def test_a_field_the_conditions_hid_is_not_validated(self):
        # The trigger is resolved by `id`, which is why every field carries one.
        self.set_form(
            [
                field("about", field_type="select", input_values=["A page", "Other"]),
                field(
                    "which-page",
                    validations=["minCharacters"],
                    validationSettings={"minCharacters-characters": 5},
                    show_when_when="about",
                    show_when_is="value_is",
                    show_when_to="A page",
                ),
            ]
        )
        # The condition is not met, so the empty answer is not measured.
        self.assertEqual(
            self.submit(
                [
                    {"field_id": "about", "value": "Other"},
                    {"field_id": "which-page", "value": ""},
                ]
            ).status_code,
            200,
        )
        # Met, and now it is.
        errors = self.errors(
            self.submit(
                [
                    {"field_id": "about", "value": "A page"},
                    {"field_id": "which-page", "value": "ab"},
                ]
            )
        )
        self.assertIn("which-page", errors)

    # ── what the deserializer allows to be authored ──

    def test_validations_are_cleared_for_field_types_that_cannot_carry_them(self):
        # The block deserializer drops them on save for anything but
        # text / textarea / from, so a rule on a date field never reaches here.
        self.api_session.patch(
            self.document_url,
            json={
                "blocks": {
                    "form-id": {
                        "@type": "form",
                        "store": True,
                        "subblocks": [
                            field(
                                "when",
                                field_type="date",
                                validations=["minCharacters"],
                                validationSettings={"minCharacters-characters": 5},
                            )
                        ],
                    }
                }
            },
        )
        transaction.commit()
        stored = self.document.blocks["form-id"]["subblocks"][0]
        self.assertEqual(stored["validations"], [])
        self.assertEqual(stored["validationSettings"], {})

    # ── the catalogue the editor builds its widget from ──

    def test_a_read_carries_the_validation_settings_catalogue(self):
        self.set_form([field("note")])
        block = self.api_session.get(self.document_url).json()["blocks"]["form-id"]
        catalogue = block["validationSettings"]
        self.assertIn("maxCharacters-characters", catalogue)
        self.assertEqual(catalogue["maxCharacters-characters"]["title"], "characters")

    # ── the checks that were skipped along with the validations ──

    def test_a_form_with_neither_send_nor_store_is_refused(self):
        # From `validate_form`, which the service used to bypass entirely.
        self.document.blocks = {
            "form-id": {"@type": "form", "subblocks": [field("note")]}
        }
        transaction.commit()
        response = self.submit([{"field_id": "note", "value": "hello"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least one form action", response.json()["message"])
