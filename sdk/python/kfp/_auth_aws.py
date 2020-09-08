# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import requests
import json
import base64
import hmac
import hashlib



def _cognito_idp_endpoint(region):
    """Return the AWS cognito idp endpoint.

    Args:
        region (str): Region where the cognito user pool is created (e.g. ap-southeast-1).

    Returns:
        str: AWS cognito-idp API endpoint.
    """
    return "https://cognito-idp.%s.amazonaws.com/" % region


def _get_token_from_response(payload):
    """Extract the access token from the JSON response to AWS cognito-idp endpoint.

    Args:
        payload (Union[str, dict]): Response body from the API call to AWS cognito-idp endpoint.

    Returns:
        Tuple[str, str]: tuple of idToken and accessToken
    """
    payload = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(payload, dict):
        raise TypeError("argument 'payload' must be either a dict or a JSON string.")

    if "AuthenticationResult" not in payload:
        raise ValueError(
            "argument 'payload' is malformed, should have field 'AuthenticationResult'."
        )

    results = payload["AuthenticationResult"]
    return {
        "id_token": results["IdToken"],
        "access_token": results["AccessToken"],
        "expires_in": results["ExpiresIn"],
        "token_type": results["TokenType"],
    }


def _secret_hash(username, client_id, client_secret):
    """Calculate the secret hash required to authenticate with the cognito-idp endpoint.

    Args:
        username (str): username
        client_id (str): app client id
        client_secret (str): app client secret

    Returns:
        str: secret hash string
    """
    # A keyed-hash message authentication code (HMAC) calculated using
    # the secret key of a user pool client and username plus the client
    # ID in the message.
    message = username + client_id
    dig = hmac.new(
        bytearray(client_secret, "utf-8"),
        msg=message.encode("UTF-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(dig).decode()


def config_aws_auth(client_id, client_secret):

    def get_aws_tokens(username, password):

        payload = dict(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
                "SECRET_HASH": _secret_hash(username, client_id, client_secret),
            },
            ClientId=client_id,
        )
        headers = {
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "Content-Type": "application/x-amz-json-1.1",
        }

        resp = requests.post(endpoint, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        return _get_token_from_response(resp.json())

jar = requests.cookies.RequestsCookieJar()
>>> jar.set('tasty_cookie', 'yum', domain='httpbin.org', path='/cookies')
    return get_aws_tokens
