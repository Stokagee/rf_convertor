*** Settings ***
Library           RequestsLibrary
Resource          ../../shared/variables.robot
Resource          ../../_shared/common_keywords.robot
Suite Setup       Create All Sessions
Suite Teardown    Delete All Sessions

*** Test Cases ***
List Customers
    [Documentation]    Converted from Bruno request: List Customers
    [Tags]    api    client_api_flow    get
    ${resp}=    GET On Session    alias=api    url=/customers    headers=${DEFAULT_HEADERS}    params=&{size=20}    expected_status=anything
    Should Be True    ${resp.status_code} < 400    Check for 2xx/3xx status
