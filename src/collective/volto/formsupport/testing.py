from plone.app.contenttypes.testing import PLONE_APP_CONTENTTYPES_FIXTURE
from plone.app.testing import applyProfile
from plone.app.testing import FunctionalTesting
from plone.app.testing import IntegrationTesting
from plone.app.testing import PloneSandboxLayer
from plone.app.testing import quickInstallProduct
from plone.restapi.testing import PloneRestApiDXLayer
from plone.testing import z2

# The validators register themselves with provideUtility when
# collective.volto.formsupport.validation is first imported, into whatever
# component registry is current then. plone.testing's LayerCleanup replaces
# that registry when a layer sets up, so by the time a test issues a request
# getUtilitiesFor(IFieldValidator) is EMPTY and every validation silently
# passes -- a form whose field may be at most 5 characters long accepted
# "far too long" and answered 200. A real Zope instance keeps the registry the
# import wrote to, which is why the vocabulary serves 15 validators there.
# Each layer below re-registers them so that tests see what production sees.
from collective.volto.formsupport.validation import _update_validators

import collective.honeypot
import collective.MockMailHost
import collective.volto.formsupport
import collective.volto.otp
import plone.restapi


class VoltoFormsupportLayer(PloneSandboxLayer):
    defaultBases = (PLONE_APP_CONTENTTYPES_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        # Load any other ZCML that is required for your tests.
        # The z3c.autoinclude feature is disabled in the Plone fixture base
        # layer.
        import plone.restapi

        self.loadZCML(package=plone.restapi)
        self.loadZCML(package=collective.volto.formsupport)
        self.loadZCML(package=collective.volto.otp)
        _update_validators()

    def setUpPloneSite(self, portal):
        applyProfile(portal, "plone.restapi:blocks")
        applyProfile(portal, "collective.volto.formsupport:default")

        # Mock the validate email tocken function
        def validate_email_token_mock(*args, **kwargs):
            return True

        from collective.volto.formsupport import utils

        utils.validate_email_token = validate_email_token_mock


VOLTO_FORMSUPPORT_FIXTURE = VoltoFormsupportLayer()


VOLTO_FORMSUPPORT_INTEGRATION_TESTING = IntegrationTesting(
    bases=(VOLTO_FORMSUPPORT_FIXTURE,),
    name="VoltoFormsupportLayer:IntegrationTesting",
)


VOLTO_FORMSUPPORT_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(VOLTO_FORMSUPPORT_FIXTURE,),
    name="VoltoFormsupportLayer:FunctionalTesting",
)


class VoltoFormsupportRestApiLayer(PloneRestApiDXLayer):
    defaultBases = (PLONE_APP_CONTENTTYPES_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        super().setUpZope(app, configurationContext)
        self.loadZCML(package=collective.MockMailHost)
        self.loadZCML(package=plone.restapi)
        self.loadZCML(package=collective.honeypot)
        self.loadZCML(package=collective.volto.formsupport)
        self.loadZCML(package=collective.volto.otp)
        _update_validators()

    def setUpPloneSite(self, portal):
        applyProfile(portal, "collective.volto.formsupport:default")
        applyProfile(portal, "plone.restapi:blocks")
        quickInstallProduct(portal, "collective.MockMailHost")
        applyProfile(portal, "collective.MockMailHost:default")


VOLTO_FORMSUPPORT_API_FIXTURE = VoltoFormsupportRestApiLayer()
VOLTO_FORMSUPPORT_API_INTEGRATION_TESTING = IntegrationTesting(
    bases=(VOLTO_FORMSUPPORT_API_FIXTURE,),
    name="VoltoFormsupportRestApiLayer:Integration",
)

VOLTO_FORMSUPPORT_API_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(VOLTO_FORMSUPPORT_API_FIXTURE, z2.ZSERVER_FIXTURE),
    name="VoltoFormsupportRestApiLayer:Functional",
)
