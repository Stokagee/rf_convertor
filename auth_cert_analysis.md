# Analýza současné implementace autentizace a certifikátů

**Datum:** 5. 4. 2026
**Autor:** Analýza kódu bruno-to-robot konvertoru

---

## 1. Současná implementace konvertoru – Autentizace

### 1.1 Jak konvertor zpracovává autentizaci

Konvertor implementuje autentizaci v modulu `src/bruno_to_robot/mapper/auth_mapper.py`. Zpoby zpracování se liší podle typu autentizace:

| Typ autentizace | Implementace | Kód |
|-----------------|--------------|-----|
| **Basic Auth** | `Create Session ... auth=${USER}:${PASS}` | `auth_mapper.py:53-68` |
| **Bearer Token** | `Set To Dictionary ${DEFAULT_HEADERS} Authorization 'Bearer ${TOKEN}'` | `auth_mapper.py:70-83` |
| **API Key** | Header nebo query param podle konfigurace | `auth_mapper.py:85-107` |
| **OAuth 2.0** | Placeholder s TODO komentářem | `auth_mapper.py:109-130` |
| **Client Cert** | `Create Session ... cert=(${CERT}, ${KEY})` | `auth_mapper.py:132-146` |
| **Inherit** | Použije collection-level auth | `auth_mapper.py:35-37` |

#### Bearer Token – detail implementace

```python
def _map_bearer_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
    token = auth.token or "${BEARER_TOKEN}"
    return [
        RobotStep(keyword="Create Session", args=[session_name, "${BASE_URL}"]),
        RobotStep(
            keyword="Set To Dictionary",
            args=["${DEFAULT_HEADERS}", "Authorization", f"'Bearer {token}'"],
        ),
    ]
```

**Výstup v .robot souboru:**
```robotframework
*** Variables ***
${BEARER_TOKEN}    %{BEARER_TOKEN}    # Secret - set via environment
&{DEFAULT_HEADERS}    Content-Type=application/json    Authorization=Bearer ${BEARER_TOKEN}
```

### 1.2 Podpora OAuth 2.0 flow

**Aktuální stav:** POUZE PLACEHOLDER – není implementováno

```python
def _map_oauth2_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
    return [
        RobotStep(keyword="Create Session", args=[session_name, "${BASE_URL}"]),
        RobotStep(
            keyword="Get OAuth Token",
            args=[session_name],
            assign="${token}",
            comment="TODO: Implement OAuth2 token retrieval keyword",  # <-- PLACEHOLDER
        ),
        RobotStep(
            keyword="Set To Dictionary",
            args=["${DEFAULT_HEADERS}", "Authorization", "'Bearer ${token}'"],
        ),
    ]
```

**Chybějící OAuth 2.0 flow implementace:**

| Flow | Stav | Poznámka |
|------|------|----------|
| **Client Credentials** | ❌ Neimplementováno | Potřebuje `POST /token` s `grant_type=client_credentials` |
| **Resource Owner Password** | ❌ Neimplementováno | Potřebuje `POST /token` s `grant_type=password` |
| **Authorization Code** | ❌ Neimplementováno | Vyžaduje redirect URI, code exchange |
| **Authorization Code + PKCE** | ❌ Neimplementováno | S `code_verifier` a `code_challenge` |
| **Refresh Token** | ❌ Neimplementováno | Viz sekce 1.3 |

**Pouze generované placeholder proměnné:**
```robotframework
${OAUTH_TOKEN_URL}    https://auth.example.com/oauth/token
${OAUTH_CLIENT_ID}    your_client_id
${OAUTH_CLIENT_SECRET}    your_client_secret
```

### 1.3 Automatické obnovování tokenů

**Aktuální stav:** ❌ NENÍ IMPLEMENTOVÁNO

Konvertor momentálně:
1. Neřeší expiraci tokenů
2. Nemá mechanismus pro refresh token flow
3. Neošetřuje `401 Unauthorized` odpovědi

**Co by bylo potřeba implementovat:**

```robotframework
*** Keywords ***
Get Valid Token
    [Documentation]    Returns valid token, refreshes if expired
    ${token_valid}=    Run Keyword And Return Status    Should Not Be Empty    ${TOKEN_EXPIRY}
    ${expired}=    Run Keyword If    ${token_valid}    Is Token Expired    ${TOKEN_EXPIRY}
    ${needs_refresh}=    Set Variable If    ${expired}    ${TRUE}    ${FALSE}
    Run Keyword If    ${needs_refresh}    Refresh OAuth Token
    [Return]    ${ACCESS_TOKEN}

Refresh OAuth Token
    [Documentation]    Refresh access token using refresh_token
    ${body}=    Create Dictionary    grant_type=refresh_token    refresh_token=${REFRESH_TOKEN}
    ${resp}=    POST On Session    auth    /oauth/token    data=${body}
    Set Suite Variable    ${ACCESS_TOKEN}    ${resp.json()}[access_token]
    Set Suite Variable    ${REFRESH_TOKEN}    ${resp.json()}[refresh_token]
```

---

## 2. Certifikáty a mTLS

### 2.1 Podpora klientských certifikátů (mTLS)

**Aktuální stav:** ✅ ČÁSTEČNĚ IMPLEMENTOVÁNO

```python
def _map_cert_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
    cert_path = auth.cert_path or "${CERT_PATH}"
    key_path = auth.key_path or "${KEY_PATH}"
    return [
        RobotStep(
            keyword="Create Session",
            args=[
                session_name,
                "${BASE_URL}",
                f"cert=({cert_path}, {key_path})",  # Tuple syntax pro RequestsLibrary
            ],
        ),
    ]
```

**Vygenerovaný výstup:**
```robotframework
*** Variables ***
${CERT_PATH}    /path/to/client.crt
${KEY_PATH}    /path/to/client.key

*** Keywords ***
Create Api Session
    Create Session    alias=api    url=${BASE_URL} cert=(${CERT_PATH}, ${KEY_PATH})
```

**Omezení současné implementace:**
- ❌ Nepodporuje kombinaci certifikát + další auth (např. Bearer)
- ❌ Nevaliduje existenci souborů před spuštěním
- ❌ Nepodporuje heslo k privátnímu klíči

### 2.2 Ověřování serverových certifikátů (CA bundle)

**Aktuální stav:** ✅ IMPLEMENTOVÁNO (výchozí chování)

V `request_mapper.py:241-252`:
```python
RobotStep(
    keyword="Create Session",
    args=[
        f"alias={alias}",
        f"url=${{{var_name}}}",
        "verify=${TRUE}",  # <-- Výchozí ověřování server certifikátu
    ],
)
```

**Možnosti konfigurace:**
```robotframework
# Výchozí - ověřuje pomocí system CA bundle
Create Session    api    ${BASE_URL}    verify=${TRUE}

# Vlastní CA bundle
Create Session    api    ${BASE_URL}    verify=/path/to/ca-bundle.crt

# Zakázat ověření (NEBEZPEČNÉ, pouze pro testování)
Create Session    api    ${BASE_URL}    verify=${FALSE}
```

**⚠️ POZOR:** Konvertor aktuálně hardcoduje `verify=${TRUE}` – neumožňuje konfiguraci vlastního CA bundle přes vstupní YAML.

### 2.3 Formáty certifikátů

**Aktuální stav:** Podporován pouze PEM

| Formát | Podpora | Poznámka |
|--------|---------|----------|
| **PEM** | ✅ | `.crt` + `.key` soubory (výchozí) |
| **PKCS#12 (.p12/.pfx)** | ❌ | Vyžaduje konverzi nebo extra logiku |
| **DER** | ❌ | Binární formát, není podporován |

**Pro PKCS#12 by bylo potřeba:**
```robotframework
*** Keywords ***
Convert P12 To PEM
    [Arguments]    ${p12_path}    ${password}
    Run Process    openssl    pkcs12    -in    ${p12_path}    -out    cert.pem    -nodes    -passin    pass:${password}
    [Return]    cert.pem
```

---

## 3. Shrnutí – Co chybí

### Kritické nedostatky

| Oblast | Priorita | Popis |
|--------|----------|-------|
| **OAuth 2.0 flow** | VYSOKÁ | Pouze placeholder, žádný skutečný flow |
| **Token refresh** | VYSOKÁ | Žádná podpora automatického obnovování |
| **CA bundle konfigurace** | STŘEDNÍ | Hardcodované `verify=${TRUE}` |
| **PKCS#12 certifikáty** | STŘEDNÍ | Pouze PEM formát |

### Doporučení pro další vývoj

1. **Implementovat OAuth 2.0 Client Credentials flow** jako první – nejjednodušší a nejčastěji používaný pro API testování

2. **Přidat konfiguraci `verify` parametru** do vstupního YAML:
   ```yaml
   settings:
     ssl_verify: /path/to/ca-bundle.crt  # nebo true/false
   ```

3. **Implementovat token refresh mechanismus** jako samostatný keyword volaný před každým requestem

4. **Podpora PKCS#12** – buď konverze v runtime, nebo dokumentace pro uživatele

---

## 4. Příklad kompletní implementace (návrh)

### OAuth 2.0 Client Credentials s automatickým refresh

```robotframework
*** Variables ***
${TOKEN_URL}         https://auth.example.com/oauth/token
${CLIENT_ID}         %{CLIENT_ID}
${CLIENT_SECRET}     %{CLIENT_SECRET}
${TOKEN_EXPIRY}      ${NONE}
${ACCESS_TOKEN}      ${NONE}

*** Keywords ***
Get Access Token
    [Documentation]    Get valid access token, refresh if expired
    ${needs_token}=    Set Variable    ${TRUE}
    IF    '${ACCESS_TOKEN}' != '${NONE}'
        ${expired}=    Is Token Expired    ${TOKEN_EXPIRY}
        ${needs_token}=    Set Variable If    ${expired}    ${TRUE}    ${FALSE}
    END
    IF    ${needs_token}
        Request New Token
    END
    [Return]    ${ACCESS_TOKEN}

Request New Token
    [Documentation]    Request new token using client credentials
    ${body}=    Create Dictionary
    ...    grant_type=client_credentials
    ...    client_id=${CLIENT_ID}
    ...    client_secret=${CLIENT_SECRET}
    ${resp}=    POST    ${TOKEN_URL}    data=${body}    expected_status=200
    ${json}=    Set Variable    ${resp.json()}
    Set Suite Variable    ${ACCESS_TOKEN}    ${json}[access_token]
    ${expires_in}=    Set Variable    ${json}[expires_in]
    ${expiry_time}=    Evaluate    time.time() + ${expires_in} - 60    modules=time
    Set Suite Variable    ${TOKEN_EXPIRY}    ${expiry_time}

Is Token Expired
    [Arguments]    ${expiry_time}
    ${current}=    Evaluate    time.time()    modules=time
    [Return]    ${current} >= ${expiry_time}
```

---

## 5. Reference

- `src/bruno_to_robot/mapper/auth_mapper.py` – Hlavní logika autentizace
- `src/bruno_to_robot/models/bruno.py` – Definice `BrunoAuth` modelu
- `src/bruno_to_robot/mapper/request_mapper.py` – Session management
- `.env.example` – Příklad proměnných prostředí
- `output/security_lab.robot` – Reálný výstup s PKCE a token exchange testy
