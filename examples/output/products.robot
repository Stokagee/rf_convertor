*** Settings ***
Library           RequestsLibrary
Suite Setup       Create API Session
Suite Teardown    Delete All Sessions

*** Variables ***
${BASE_URL}           https://api.eshop.example.com
${API_VERSION}        v1
${ACCESS_TOKEN}       %{ACCESS_TOKEN}    # Secret - set via environment
&{DEFAULT_HEADERS}    Content-Type=application/json    Accept=application/json    Authorization=Bearer ${ACCESS_TOKEN}

*** Keywords ***
Create API Session
    Create Session    api    ${BASE_URL}

*** Test Cases ***
Get Product Details
    [Documentation]    Converted from Bruno request: Get Product Details
    [Tags]    api    products    get
    ${resp}=    GET On Session    api    /v1/products/123    headers=${DEFAULT_HEADERS}
    Should Be Equal As Integers    ${resp.status_code}    200
    Should Be Equal As Integers    ${resp.json()['id']}    123

Health Check
    [Documentation]    Converted from Bruno request: Health Check
    [Tags]    api    get
    ${resp}=    GET On Session    api    /health    headers=${DEFAULT_HEADERS}
    Should Be Equal As Integers    ${resp.status_code}    200
    Should Be Equal    ${resp.json()['status']}    healthy

List All Products
    [Documentation]    Converted from Bruno request: List All Products
    [Tags]    api    products    get
    ${params}=    Create Dictionary    page=1    limit=20    sort=name
    ${resp}=    GET On Session    api    /v1/products    params=${params}    headers=${DEFAULT_HEADERS}
    Should Be Equal As Integers    ${resp.status_code}    200
