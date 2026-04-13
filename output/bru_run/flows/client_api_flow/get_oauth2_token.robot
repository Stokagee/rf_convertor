*** Settings ***
Library           RequestsLibrary
Resource          ../../shared/variables.robot
Resource          ../../_shared/common_keywords.robot
Suite Setup       Create All Sessions
Suite Teardown    Delete All Sessions

*** Test Cases ***
Get Oauth2 Token
    [Documentation]    Converted from Bruno request: Get OAuth2 Token
    [Tags]    api    client_api_flow    post
    ${headers}=    Create Dictionary    Accept=application/json    Authorization=Bearer ${ACCESS_TOKEN}    Content-Type=application/json
    ${resp}=    POST On Session    alias=api    url=/oauth/token    json={"grantType":"client_credentials"}    headers=${headers}    expected_status=anything
    Should Be True    ${resp.status_code} < 400    Check for 2xx/3xx status
