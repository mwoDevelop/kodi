#!/bin/sh

# Stateless QTS CGI bridge to the loopback-only Control Plane browser service.
public_base="/cgi-bin/qpkg/KodiCPGateway/gateway.cgi/control-plane"
backend="http://127.0.0.1:19445"
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
