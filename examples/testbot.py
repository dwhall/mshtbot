#!/usr/bin/env python3
#
# Copyright 2024 Dean Hall, see LICENSE for details


"""Bot that replies to messages if "test" is anywhere in the message.
If the received message does not have the substring "test" in it,
it replies with a suggestion to try "test".
If the received message arrived directly, replies with RF stats.
If the received message arrived multihop, replies with the hop count.
Prints the (number of messages with "test" in it) / (number of messages received).
"""

import time

from pubsub import pub

import meshtastic
import meshtastic.serial_interface

tries = 0
replies = 0


def onConnection(interface, topic=pub.AUTO_TOPIC):
    """called when we (re)connect to the radio"""
    print("Ready.")

def onReceive(packet:dict, interface):
    """called when a message arrives"""
    global tries
    global replies

    reply = process_msg(packet)
    if reply:
        origin = packet['from']
        interface.sendText(reply, destinationId=origin)
        print(f"{replies}/{tries}")

def process_msg(rx_msg:dict) -> str:
    global tries
    global replies

    if is_text_msg(rx_msg):
        tries += 1
        if is_test_msg(rx_msg):
            replies += 1
            return format_test_reply(rx_msg)
        return help_reply()
    return ""

def is_text_msg(msg:dict) -> bool:
    return msg["decoded"]["portnum"] == "TEXT_MESSAGE_APP"

def is_test_msg(msg:dict) -> bool:
    return "test" in msg["decoded"]["text"].lower()

def format_test_reply(msg:dict) -> str:
    intermediateNodeCount = msg['hopStart'] - msg['hopLimit']
    if intermediateNodeCount == 0:
        return f"I heard you!\nSNR: {msg['rxSnr']}, RSSI: {msg['rxRssi']}"
    else:
        return f"I heard you!\nthrough {intermediateNodeCount} nodes."

def help_reply():
    return "Put the word \"test\" in your message and see what happens."

def main():
    pub.subscribe(onReceive, "meshtastic.receive")
    pub.subscribe(onConnection, "meshtastic.connection.established")
    with meshtastic.serial_interface.SerialInterface() as _:
        try:
            while True:
                time.sleep(500)
        finally:
            print("Done.")

if __name__ == "__main__":
    main()
