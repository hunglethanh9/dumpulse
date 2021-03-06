#!/usr/bin/python3
# -*- coding: utf-8 -*- (for Python2)
"UDP client for Dumpulse, primarily for debuggging."
from __future__ import print_function

import argparse
import socket
import struct
import zlib


# The query packet to send to Dumpulse server to get a health report.
query_packet = b"AreyouOK"


def _variable_settings(p):
    "Yields tuples like those of variable_settings, without checking checksums."

    for v in range(len(p)//4-1):
        timestamp, sender, value = struct.unpack(">HBB", p[4*(v+1):][:4])
        yield v, timestamp, sender, value


def adler32(data):
    """Can you believe zlib.adler32 is signed in Python2, unsigned in Python3‽

    This fixes that.

    """
    return zlib.adler32(data) % 2**32


def parse_health_report(health_report_bytes):
    """Return a variable settings list and the expected and received checksum.

    The variable settings list is the same list returned by the
    variable_settings function, which you should probably call instead
    for most non-debugging purposes.

    """
    p = health_report_bytes
    checksum, = struct.unpack(">L", p[:4])
    return list(_variable_settings(p)), adler32(p[4:]), checksum


def variable_settings(health_report_bytes):
    """Returns a list of (variable number, timestamp, sender, value) tuples.

    Raises ValueError if this is not a valid health report packet.

    """
    settings, expected, received = parse_health_report(health_report_bytes)
    if expected != received:
        raise ValueError(health_report_bytes, expected, received)
    return settings


def get_health_report(socket_object):
    "Request a health report from a Dumpulse server."
    # Round-trip latencies on internet across the US are currently a
    # bit under 50ms, but sometimes bufferbloat can push that quite a
    # bit higher.  This starts at 250ms and does 4 more retries before
    # getting to one second, and gives up after 9 more retries in a
    # little under a minute, which is a bit more aggressive than
    # traditional TCP/IP settings but still has the exponential
    # backoff needed to avoid some pathological emergent behaviors.
    retry_interval, retry_delay_factor, max_retry_interval = 0.25, 1.4142, 16

    timeout = socket_object.gettimeout()
    try:
        while True:
            socket_object.settimeout(retry_interval)
            try:
                socket_object.send(query_packet)
                p = socket_object.recv(2048)
            except socket.timeout:
                retry_interval *= retry_delay_factor
                if retry_interval > max_retry_interval:
                    return None         # timeout
            else:
                return p
    finally:
        socket_object.settimeout(timeout)


def show_health_report(socket_object):
    p = get_health_report(socket_object)
    if p is None:
        print("Timeout polling", socket_object.getpeername())
        return

    print("Health report of {} bytes:".format(len(p)))

    settings, expected, checksum = parse_health_report(p)
    if checksum == expected:
        print("checksum {:08x} checks OK".format(checksum))
    else:
        print("checksum {:08x} doesn’t match {:08x} in packet".format(
            expected, checksum))

    for v, timestamp, sender, value in settings:
        print("v{} = {} at {} from {}".format(v, value, timestamp, sender))


def set_packet(variable, sender, value):
    "Construct a set-variable request packet and return it as bytes."
    payload = struct.pack("BBBB", 0xf1, variable, sender, value)
    return struct.pack(">L", adler32(payload)) + payload


def set_variable(socket_object, variable, sender, value):
    "Send a set-variable request to a Dumpulse server."
    socket_object.send(set_packet(variable, sender, value))


def main():
    parser = argparse.ArgumentParser(
        description="With no value to set, displays a health report.")
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    parser.add_argument('-n', '--variable', type=int, default=0,
                        help="ID of variable to set (0–63)")
    parser.add_argument('-s', '--sender', type=int, default=76,
                        help="ID of sender")
    parser.add_argument('-v', '--value', type=int, help="(0–255)")
    args = parser.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((args.host, args.port))

    if args.value is None:
        show_health_report(s)
    else:
        set_variable(s, args.variable, args.sender, args.value)


if __name__ == '__main__':
    main()
