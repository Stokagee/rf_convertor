# Stav implementace OAuth 2.0 a mTLS

## Datum: 5. 4. 2026

## ✅ Dokončeno

### 1. Nové Python knihovny
- **`library/oauth2_client.py`** - OAuth2Client s podporou:
  - Client Credentials flow
  - Resource Owner Password flow
  - Authorization Code flow
  - PKCE (code_verifier, code_challenge generování)
  - Client Assertion (JWT Bearer)
  - Token Exchange (RFC 8693)
  - Token refresh
  - Token management (expiry tracking)

- **`library/cert_manager.py`** - CertManager s podporou:
  - PEM certifikátů
  - PKCS#12 (.p12/.pfx) konverze
  - Certificate chain loading
  - SSL verify konfigurace
  - Certificate info/expiry checking

### 2. Rozšířené modely
- **`models/bruno.py`** - Nové třídy:
  - `OAuth2Flow` - enum pro grant types
  - `OAuth2Credentials` - client_id, client_secret, placement
  - `OAuth2TokenConfig` - token placement config
  - `OAuth2Settings` - auto_fetch_token, auto_refresh_token
  - `BrunoOAuth2Config` - kompletní OAuth2 konfigurace
  - `BrunoAuth` - rozšířen o `oauth2` field

### 3. Parser
- **`parser/yaml_parser.py`** - `_parse_oauth2_config()` metoda
  - Parsuje OAuth2 blok z Bruno YAML
  - Podporuje flow, credentials, PKCE, client_assertion

### 4. Auth Mapper
- **`mapper/auth_mapper.py`** - Přepsáno s OAuth2 podporou:
  - `_map_oauth2_auth()` - detekce flow typu
  - `_map_client_credentials()` - generování keywordů
  - `_map_password_flow()` - password flow keywords
  - `_map_pkce_flow()` - PKCE flow keywords
  - `_map_cert_auth()` - mTLS s PKCS#12 podporou
  - `get_auth_variables()` - OAuth2 proměnné
  - `get_oauth2_keywords()` - custom OAuth2 keywords

### 5. Závislosti
- **`pyproject.toml`** - Přidáno:
  - `requests>=2.31`
  - `requests-oauthlib>=1.3`
  - `cryptography>=41.0`
  - Volitelně: `authlib>=1.2` (pro JWT assertion)

## ⚠️ Částečně implementováno

### Integrace do request_mapper.py
Aktuálně `request_mapper.py` stále používá hardcoded Authorization headers z Bruno souboru.
Potřebuje:
1. Detekovat OAuth2 auth na requestu
2. Ignorovat hardcoded Authorization header
3. Generovat OAuth2 token setup keywords
4. Používat `${ACCESS_TOKEN}` proměnnou

## 📋 TODO - Priorita

### Vysoká priorita
1. **Integrovat auth_mapper do request_mapper**
   - Detekovat OAuth2 auth na requestech
   - Generovat OAuth2 setup v Suite Setup
   - Nahradit hardcoded tokeny proměnnými

2. **Vygenerovat variables.yaml**
   - CLI option `--generate-variables`
   - Výstup: variables.yaml s environment variable references

### Střední priorita
3. **Unit testy**
   - `tests/unit/test_oauth2_client.py`
   - `tests/unit/test_cert_manager.py`
   - `tests/unit/test_auth_mapper_oauth2.py`

4. **Integrační testy**
   - `tests/integration/test_oauth2_flow.robot`
   - Mock OAuth2 server

### Nízká priorita
5. **Dokumentace**
   - README aktualizace
   - Příklady použití
   - Changelog

## Příklad generovaného výstupu (cílový stav)

```robotframework
*** Settings ***
Library           RequestsLibrary
Library           bruno_to_robot.library.oauth2_client.OAuth2Client    AS    OAuth2

*** Variables ***
${BASE_URL}           http://localhost:20300/api/v1
${TOKEN_URL}          http://localhost:5105/oauth2/token
${CLIENT_ID}          %{CLIENT_ID}
${CLIENT_SECRET}      %{CLIENT_SECRET}
${ACCESS_TOKEN}       ${NONE}
&{DEFAULT_HEADERS}    Accept=application/json    Content-Type=application/json

*** Keywords ***
Get Client Credentials Token
    [Documentation]    Get OAuth2 token using client_credentials flow
    ${token}=    OAuth2.Get Client Credentials Token
    ...    token_url=${TOKEN_URL}
    ...    client_id=${CLIENT_ID}
    ...    client_secret=${CLIENT_SECRET}
    Set Suite Variable    ${ACCESS_TOKEN}    ${token}
    [Return]    ${token}

Ensure Valid Token
    ${expired}=    OAuth2.Is Token Expired
    Run Keyword If    ${expired}    Get Client Credentials Token

Create API Session
    Ensure Valid Token
    Set To Dictionary    ${DEFAULT_HEADERS}    Authorization=Bearer ${ACCESS_TOKEN}
    Create Session    api    ${BASE_URL}    headers=${DEFAULT_HEADERS}

*** Test Cases ***
Get Orders
    [Setup]    Create API Session
    ${resp}=    GET On Session    api    /orders
    Should Be Equal As Integers    ${resp.status_code}    200
```

## Jak pokračovat

1. **Spustit existující testy:**
   ```bash
   pytest tests/unit/ -v
   ```

2. **Otestovat parsování OAuth2:**
   ```bash
   python -c "
   from bruno_to_robot.parser.yaml_parser import YamlParser
   parser = YamlParser()
   collection = parser.parse_file('path/to/oauth2_collection.yml')
   for req in collection.requests:
       if req.http.auth and req.http.auth.oauth2:
           print(f'{req.name}: {req.http.auth.oauth2.flow}')
   "
   ```

3. **Implementovat integraci do request_mapper:**
   - Upravit `_build_request_step()` pro detekci OAuth2
   - Přidat OAuth2 keywords do suite
   - Nahradit hardcoded headers proměnnými
