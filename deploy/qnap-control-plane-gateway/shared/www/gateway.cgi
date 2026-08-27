#!/bin/sh

# Stateless QTS CGI bridge to the loopback-only Control Plane browser service.
public_base="/cgi-bin/qpkg/KodiCPGateway/gateway.cgi/control-plane"
backend="http://127.0.0.1:19445"
qts_auth="https://127.0.0.1/cgi-bin/authLogin.cgi"
max_body=16384

send_json_error() {
    code="$1"
    label="$2"
    body="$3"
    printf 'Status: %s %s\r\n' "$code" "$label"
    printf 'Content-Type: application/json\r\n'
    printf 'Cache-Control: no-store\r\n'
    printf 'Content-Length: %s\r\n\r\n' "${#body}"
    [ "${REQUEST_METHOD:-GET}" = "HEAD" ] || printf '%s' "$body"
    exit 0
}

case "${REQUEST_METHOD:-}" in
    GET|HEAD|POST) ;;
    *) send_json_error 405 'Method Not Allowed' '{"error":"method_not_allowed"}' ;;
esac

case "${REQUEST_URI:-}" in
    "$public_base"|"$public_base/"*) ;;
    *) send_json_error 404 'Not Found' '{"error":"not_found"}' ;;
esac
case "$REQUEST_URI" in
    *..*|*%0a*|*%0A*|*%0d*|*%0D*)
        send_json_error 400 'Bad Request' '{"error":"invalid_path"}'
        ;;
esac
case "${HTTP_HOST:-}" in
    ""|*[!A-Za-z0-9.:-]*)
        send_json_error 400 'Bad Request' '{"error":"invalid_host"}'
        ;;
esac

if [ "${HTTPS:-}" != "on" ] && [ "${SERVER_PORT:-}" != "443" ]; then
    https_host="${HTTP_HOST%%:*}"
    printf 'Status: 308 Permanent Redirect\r\n'
    printf 'Location: https://%s%s\r\n' "$https_host" "$REQUEST_URI"
    printf 'Cache-Control: no-store\r\nContent-Length: 0\r\n\r\n'
    exit 0
fi

content_length="${CONTENT_LENGTH:-0}"
case "$content_length" in
    ""|*[!0-9]*)
        send_json_error 400 'Bad Request' '{"error":"invalid_content_length"}'
        ;;
esac
[ "$content_length" -le "$max_body" ] || \
    send_json_error 413 'Content Too Large' '{"error":"invalid_content_length"}'

curl_bin=""
for candidate in /sbin/curl /usr/bin/curl /usr/local/bin/curl; do
    if [ -x "$candidate" ]; then
        curl_bin="$candidate"
        break
    fi
done
[ -n "$curl_bin" ] || \
    send_json_error 503 'Service Unavailable' '{"error":"gateway_unavailable"}'

work_dir="/tmp/KodiCPGateway.$$"
(umask 077 && mkdir "$work_dir") || \
    send_json_error 503 'Service Unavailable' '{"error":"gateway_unavailable"}'
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM
headers="$work_dir/headers"
body="$work_dir/body"

script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd -P)
private_dir=$(dirname "$script_dir")/private

cookie_value() {
    cookie_name="$1"
    previous_ifs=$IFS
    IFS=';'
    for cookie_part in ${HTTP_COOKIE:-}; do
        cookie_part=${cookie_part#"${cookie_part%%[! ]*}"}
        case "$cookie_part" in
            "$cookie_name="*)
                printf '%s' "${cookie_part#*=}"
                IFS=$previous_ifs
                return 0
                ;;
        esac
    done
    IFS=$previous_ifs
    return 1
}

qts_admin_session() {
    qts_sid=$(cookie_value NAS_SID) || return 1
    case "$qts_sid" in ""|*[!A-Za-z0-9]*) return 1 ;; esac
    [ "${#qts_sid}" -ge 6 ] && [ "${#qts_sid}" -le 64 ] || return 1
    qts_body="$work_dir/qts-auth"
    printf 'sid=%s' "$qts_sid" | "$curl_bin" --silent --insecure --max-time 5 \
        --request POST --output "$qts_body" --header "Host: $HTTP_HOST" \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-binary @- "$qts_auth" || return 1
    grep -Eq '<authPassed>(<!\[CDATA\[)?1(\]\]>)?</authPassed>' "$qts_body" || return 1
    grep -Eq '<isAdmin>(<!\[CDATA\[)?1(\]\]>)?</isAdmin>' "$qts_body"
}

base32_hex() {
    awk -v encoded="$1" 'BEGIN {
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        bits=""
        for (position=1; position<=length(encoded); position++) {
            value=index(alphabet, substr(encoded, position, 1))-1
            if (value < 0) exit 1
            for (power=4; power>=0; power--)
                bits=bits int(value/(2^power))%2
            while (length(bits) >= 8) {
                byte=substr(bits, 1, 8)
                number=0
                for (bit=1; bit<=8; bit++) number=number*2+substr(byte, bit, 1)
                printf "%02x", number
                bits=substr(bits, 9)
            }
        }
    }'
}

hex_binary() {
    binary_escapes=$(awk -v encoded="$1" 'BEGIN {
        digits="0123456789abcdef"
        for (position=1; position<=length(encoded); position+=2) {
            high=index(digits, substr(encoded, position, 1))-1
            low=index(digits, substr(encoded, position+1, 1))-1
            if (high < 0 || low < 0) exit 1
            printf "\\%03o", high*16+low
        }
    }') || return 1
    printf '%b' "$binary_escapes"
}

totp_code() {
    totp_secret="$1"
    timestamp="$2"
    key_hex=$(base32_hex "$totp_secret") || return 1
    [ -n "$key_hex" ] || return 1
    counter=$((timestamp / 30))
    counter_hex=$(printf '%016x' "$counter")
    digest=$(hex_binary "$counter_hex" | \
        "$openssl_bin" dgst -sha1 -mac HMAC -macopt "hexkey:$key_hex" 2>/dev/null | \
        awk '{print $NF}') || return 1
    case "$digest" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
        *) return 1 ;;
    esac
    awk -v digest="$digest" 'BEGIN {
        digits="0123456789abcdef"
        offset=index(digits, substr(digest, 40, 1))-1
        chunk=substr(digest, offset*2+1, 8)
        value=0
        for (position=1; position<=8; position++) {
            nibble=index(digits, substr(chunk, position, 1))-1
            if (nibble < 0) exit 1
            value=value*16+nibble
        }
        if (value >= 2147483648) value-=2147483648
        printf "%06d", value%1000000
    }'
}

control_plane_auto_login() {
    username_file="$private_dir/operator-username"
    credential_file="$private_dir/operator-credential"
    totp_file="$private_dir/totp-secret"
    for item in "$username_file" "$credential_file" "$totp_file"; do
        [ -f "$item" ] && [ ! -L "$item" ] || return 1
    done
    IFS= read -r operator_username < "$username_file" || return 1
    IFS= read -r operator_credential < "$credential_file" || return 1
    IFS= read -r operator_totp < "$totp_file" || return 1
    case "$operator_username" in ""|*[!A-Za-z0-9._-]*) return 1 ;; esac
    printf '%s' "$operator_credential" | \
        grep -Eq '^[A-Za-z0-9._~!@#$%^&*+=:/?-]+$' || return 1
    case "$operator_totp" in ""|*[!A-Z2-7]*) return 1 ;; esac
    [ "${#operator_credential}" -ge 14 ] && [ "${#operator_credential}" -le 128 ] || return 1
    [ "${#operator_totp}" -ge 16 ] && [ "${#operator_totp}" -le 128 ] || return 1

    status_headers="$work_dir/status-headers"
    status_body="$work_dir/status-body"
    "$curl_bin" --silent --max-time 10 --request GET \
        --dump-header "$status_headers" --output "$status_body" \
        --header "Host: $HTTP_HOST" --header 'Accept-Encoding: identity' \
        "$backend$public_base/auth/status" || return 1
    [ "$(awk '/^HTTP\// { code=$2 } END { print code }' "$status_headers")" = 200 ] || return 1
    csrf=$(sed -n 's/.*"csrf"[[:space:]]*:[[:space:]]*"\([A-Za-z0-9_-]*\)".*/\1/p' "$status_body")
    case "$csrf" in ""|*[!A-Za-z0-9_-]*) return 1 ;; esac
    csrf_set_cookie=$(awk -F': ' '/^Set-Cookie: mwo_cp_csrf=/ { sub(/\r$/, "", $2); print $2; exit }' "$status_headers")
    [ -n "$csrf_set_cookie" ] || return 1
    csrf_cookie=${csrf_set_cookie%%;*}
    code=$(totp_code "$operator_totp" "$(date +%s)") || return 1
    case "$code" in [0-9][0-9][0-9][0-9][0-9][0-9]) ;; *) return 1 ;; esac

    login_headers="$work_dir/login-headers"
    login_body="$work_dir/login-body"
    printf '{"username":"%s","password":"%s","code":"%s"}' \
        "$operator_username" "$operator_credential" "$code" | \
        "$curl_bin" --silent --max-time 10 --request POST \
        --dump-header "$login_headers" --output "$login_body" \
        --header "Host: $HTTP_HOST" --header "Origin: https://$HTTP_HOST" \
        --header "Cookie: $csrf_cookie" --header "X-CSRF-Token: $csrf" \
        --header 'Content-Type: application/json' --data-binary @- \
        "$backend$public_base/auth/login" || return 1
    [ "$(awk '/^HTTP\// { code=$2 } END { print code }' "$login_headers")" = 200 ] || return 1
    grep -Eq '^Set-Cookie: mwo_cp_session=' "$login_headers" || return 1

    printf 'Status: 303 See Other\r\n'
    printf '%s\n' "$csrf_set_cookie" | awk '{
        gsub(/SameSite=Strict/, "SameSite=Lax")
        printf "Set-Cookie: %s\r\n", $0
    }'
    awk '/^Set-Cookie: mwo_cp_session=/ {
        sub(/\r$/, "")
        gsub(/SameSite=Strict/, "SameSite=Lax")
        print $0 "\r"
    }' "$login_headers"
    printf 'Location: %s/\r\n' "$public_base"
    printf 'Cache-Control: no-store\r\nContent-Length: 0\r\n\r\n'
    exit 0
}

openssl_bin=""
for candidate in /usr/bin/openssl /usr/local/bin/openssl; do
    if [ -x "$candidate" ]; then
        openssl_bin="$candidate"
        break
    fi
done

case "${REQUEST_METHOD:-}:${REQUEST_URI:-}" in
    "GET:$public_base"|"GET:$public_base/")
        if [ -n "$openssl_bin" ] && ! cookie_value mwo_cp_session >/dev/null && qts_admin_session; then
            control_plane_auto_login || true
        fi
        ;;
esac

set -- "$curl_bin" --silent --show-error --max-time 15 \
    --request "$REQUEST_METHOD" --dump-header "$headers" --output "$body" \
    --header "Host: $HTTP_HOST" --header 'Accept-Encoding: identity'
[ -z "${HTTP_ACCEPT:-}" ] || set -- "$@" --header "Accept: $HTTP_ACCEPT"
[ -z "${HTTP_COOKIE:-}" ] || set -- "$@" --header "Cookie: $HTTP_COOKIE"
[ -z "${HTTP_ORIGIN:-}" ] || set -- "$@" --header "Origin: $HTTP_ORIGIN"
[ -z "${HTTP_X_CSRF_TOKEN:-}" ] || \
    set -- "$@" --header "X-CSRF-Token: $HTTP_X_CSRF_TOKEN"
[ -z "${CONTENT_TYPE:-}" ] || \
    set -- "$@" --header "Content-Type: $CONTENT_TYPE"

if [ "$REQUEST_METHOD" = "POST" ]; then
    "$@" --data-binary @- "$backend$REQUEST_URI" || \
        send_json_error 502 'Bad Gateway' '{"error":"gateway_unavailable"}'
else
    "$@" "$backend$REQUEST_URI" || \
        send_json_error 502 'Bad Gateway' '{"error":"gateway_unavailable"}'
fi

status="$(awk '/^HTTP\// { code=$2 } END { print code }' "$headers")"
case "$status" in
    2??|3??|4??|5??) ;;
    *) send_json_error 502 'Bad Gateway' '{"error":"invalid_gateway_response"}' ;;
esac

printf 'Status: %s\r\n' "$status"
awk '/^(Content-Type|Cache-Control|Content-Security-Policy|X-Content-Type-Options|X-Frame-Options|Referrer-Policy|Permissions-Policy|Location|Set-Cookie):/ {
        sub(/\r$/, ""); print $0 "\r"
    }' "$headers"
size="$(wc -c < "$body" | tr -d ' ')"
printf 'Content-Length: %s\r\n\r\n' "$size"
[ "$REQUEST_METHOD" = "HEAD" ] || /bin/cat "$body"
