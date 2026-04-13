*** Settings ***
Library           RequestsLibrary
Library           ${CURDIR}${/}users_helpers.py
Resource          shared/variables.robot
Suite Setup       Create All Sessions
Suite Teardown    Delete All Sessions

*** Keywords ***
Create Api Session
    Create Session    alias=api    url=${BASE_URL}    verify=${TRUE}
Create All Sessions
    Create Session    alias=api    url=${BASE_URL}    verify=${TRUE}

*** Test Cases ***
Create Random User
    [Documentation]    Converted from Bruno request: Create Random User
    [Tags]    api    post    users
    ${request_body}=    generate_create_random_user_body
    ${resp}=    POST On Session    alias=api    url=/users    json=${request_body}    headers=${DEFAULT_HEADERS}    expected_status=anything
    Should Be True    ${resp.status_code} < 400    Check for 2xx/3xx status
