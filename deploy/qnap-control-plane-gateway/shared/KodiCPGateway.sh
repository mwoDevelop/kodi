#!/bin/sh
set -eu

export QNAP_QPKG=KodiCPGateway
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

name=KodiCPGateway
config=/etc/config/qpkg.conf
install_path=$(/sbin/getcfg "$name" Install_Path -d missing -f "$config")
case "$install_path" in
    /share/*/.qpkg/KodiCPGateway) ;;
    *) echo "Invalid QPKG install path" >&2; exit 1 ;;
esac

cgi_root=/home/httpd/cgi-bin/qpkg
cgi_link=$cgi_root/$name
cgi_target=$install_path/www

start_gateway() {
    [ -d "$cgi_target" ] && [ ! -L "$cgi_target" ]
    [ -f "$cgi_target/gateway.cgi" ] && [ ! -L "$cgi_target/gateway.cgi" ]
    [ -x "$cgi_target/gateway.cgi" ]
    mkdir -p "$cgi_root"
    if [ -L "$cgi_link" ]; then
        if [ "$(readlink "$cgi_link")" != "$cgi_target" ]; then
            echo "Refusing to replace foreign CGI symlink: $cgi_link" >&2
            return 1
        fi
    elif [ -e "$cgi_link" ]; then
        echo "Refusing to replace non-symlink CGI path: $cgi_link" >&2
        return 1
    fi
    rm -f -- "$cgi_link"
    ln -s "$cgi_target" "$cgi_link"
    [ "$(readlink "$cgi_link")" = "$cgi_target" ]
}

stop_gateway() {
    if [ -L "$cgi_link" ] && [ "$(readlink "$cgi_link")" = "$cgi_target" ]; then
        rm -f -- "$cgi_link"
    fi
}

case ${1:-} in
    start) start_gateway ;;
    stop) stop_gateway ;;
    restart) stop_gateway; start_gateway ;;
    *) echo "Usage: $0 {start|stop|restart}" >&2; exit 2 ;;
esac
