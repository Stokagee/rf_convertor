*** Variables ***


*** Keywords ***

Create Api Session
    Create Session    alias=api    url=${BASE_URL}    verify=${TRUE}

Create All Sessions
    Create Session    alias=api    url=${BASE_URL}    verify=${TRUE}
