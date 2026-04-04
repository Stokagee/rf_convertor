*** Settings ***
Library           RequestsLibrary
Suite Setup       Create API Session
Suite Teardown    Delete All Sessions

*** Variables ***
${BASE_URL}           https://api.eshop.example.com
${ACCESS_TOKEN}       %{ACCESS_TOKEN}    # Secret - set via environment
&{DEFAULT_HEADERS}    Content-Type=application/json    Accept=application/json    Authorization=Bearer ${ACCESS_TOKEN}

*** Keywords ***
Create API Session
    Create Session    api    ${BASE_URL}

*** Test Cases ***
Add Item To Cart
    [Documentation]    Converted from Bruno request: Add Item to Cart
    [Tags]    api    cart    post
    ${body}=    Create Dictionary    productId=123    quantity=2
    ${resp}=    POST On Session    api    /v1/cart/items    json=${body}    headers=${DEFAULT_HEADERS}
    Should Be Equal As Integers    ${resp.status_code}    201
    Dictionary Should Contain Key    ${resp.json()}    itemId

Get Cart Contents
    [Documentation]    Converted from Bruno request: Get Cart Contents
    [Tags]    api    cart    get
    ${resp}=    GET On Session    api    /v1/cart    headers=${DEFAULT_HEADERS}
    Should Be Equal As Integers    ${resp.status_code}    200
