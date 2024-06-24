#!/usr/bin/env python3
#
# Copyright 2024 Dean Hall, see LICENSE for details

"""Bot that replies to text messages.
If the received message does not have the substring "test" in it,
the bot replies with a suggestion to try "test".
If the received message arrives directly, the bot replies with RF stats.
If the received message arrives multihop, the bot replies with the hop count.
For every received text message, the script prints to command line
the (number of messages with "test" in it) / (number of messages received).
"""

import time

from pubsub import pub

import meshtastic
import meshtastic.serial_interface

total_count = 0
test_count = 0

def on_connection(interface, topic=pub.AUTO_TOPIC):
    """called when we (re)connect to the radio"""
    print("Ready.")

def on_receive(packet:dict, interface):
    """called when a message arrives"""
    # This script uses the name "msg" but pubsub calls
    # this procedure with the first arg named "packet"
    msg = packet
    reply = process_msg(msg)
    if reply:
        origin = msg['from']
        interface.sendText(reply, destinationId=origin)
        print(format_stats_reply())

def process_msg(rx_msg:dict) -> str:
    global total_count
    global test_count

    if is_text_msg(rx_msg):
        total_count += 1
        if is_in_msg("test", rx_msg):
            test_count += 1
            return format_test_reply(rx_msg)
        elif is_in_msg("stats", rx_msg):
            return format_stats_reply()
        return help_reply()
    return ""

def is_text_msg(msg:dict) -> bool:
    return msg["decoded"]["portnum"] == "TEXT_MESSAGE_APP"

def is_in_msg(substr:str, msg:dict) -> bool:
    return substr in msg["decoded"]["text"].lower()

def format_test_reply(msg:dict) -> str:
    intermediate_node_count = msg['hopStart'] - msg['hopLimit']
    if intermediate_node_count == 0:
        return f"I heard you!\nSNR: {msg['rxSnr']}, RSSI: {msg['rxRssi']}"
    else:
        return f"I heard you!\nthrough {intermediate_node_count} nodes."

def format_stats_reply() -> str:
    global total_count
    global test_count
    return f"{test_count}/{total_count}"

def help_reply():
    return "Put the word \"test\" in your message and see what happens."

def main():
    pub.subscribe(on_receive, "meshtastic.receive")
    pub.subscribe(on_connection, "meshtastic.connection.established")
    with meshtastic.serial_interface.SerialInterface() as _:
        try:
            while True:
                time.sleep(500)
        finally:
            print("Done.")

if __name__ == "__main__":
    main()
