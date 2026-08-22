#!/bin/sh

case "${1:-}" in
    start|stop|restart)
        exit 0
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}" >&2
        exit 1
        ;;
esac
