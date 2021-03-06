import json

import requests
from django.conf import settings
from django.utils.encoding import smart_text
from josepy.jws import JWS, Header
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from mozilla_django_oidc.utils import import_from_settings



class CustomOIDCBackend(OIDCAuthenticationBackend):
    """
    Provide OpenID Connect authentication
    """
    def retrieve_matching_jwk(self, token):
        """Get the signing key by exploring the JWKS endpoint of the OP."""

        # This method is overridden to provide a fix for "alg" potentially not
        # being present in the response (it is optional in the spec, and not
        # provided by Azure)

        # The latest version of mozilla-django-oidc provides this fix, but we
        # cannot currently use it due to being on Django 1.8. Once we are on a
        # recent Django version and using mozilla_django_oidc>=1.1.0 then we
        # can discard this override.
        response_jwks = requests.get(
            self.OIDC_OP_JWKS_ENDPOINT,
            verify=import_from_settings("OIDC_VERIFY_SSL", True),
        )
        response_jwks.raise_for_status()
        jwks = response_jwks.json()

        # Compute the current header from the given token to find a match
        jws = JWS.from_compact(token)
        json_header = jws.signature.protected
        header = Header.json_loads(json_header)

        key = None
        for jwk in jwks["keys"]:
            if jwk["kid"] != smart_text(header.kid):
                continue
            if "alg" in jwk and jwk["alg"] != smart_text(header.alg):
                raise SuspiciousOperation("alg values do not match.")
            key = jwk
        if key is None:
            raise SuspiciousOperation("Could not find a valid JWKS.")
        return key

    def get_userinfo(self, access_token, id_token, verified_id):
        """
        Extract user details from JSON web tokens
        These map to fields on the user field.
        """
        id_info = json.loads(JWS.from_compact(id_token).payload.decode("utf-8"))
        access_info = json.loads(JWS.from_compact(access_token).payload.decode("utf-8"))

        info = {}

        for oidc_attr, user_attr in settings.OIDC_ACCESS_ATTRIBUTE_MAP.items():
            info[user_attr] = access_info[oidc_attr]

        for oidc_attr, user_attr in settings.OIDC_ID_ATTRIBUTE_MAP.items():
            info[user_attr] = id_info[oidc_attr]

        return info

    def create_user(self, user_info):
        user = super(CustomOIDCBackend, self).create_user(user_info)
        for attr, value in user_info.items():
            setattr(user, attr, value)
        user.save()
        return user
