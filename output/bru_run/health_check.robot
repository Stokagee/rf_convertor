*** Settings ***
Library           RequestsLibrary
Resource          shared/variables.robot
Resource          _shared/common_keywords.robot
Suite Setup       Create All Sessions
Suite Teardown    Delete All Sessions

*** Test Cases ***
Health Check
    [Documentation]    Converted from Bruno request: Health Check
    [Tags]    api    get
    ${resp}=    GET On Session    alias=api    url=/health    headers=${DEFAULT_HEADERS}    expected_status=anything
    Should Be True    ${resp.status_code} < 400    Check for 2xx/3xx status
