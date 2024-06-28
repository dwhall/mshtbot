#!/usr/bin/env python3
#
# Copyright 2024 Dean Hall, see LICENSE for details

"""Bot that replies to text messages.
If the received message does not have the substring "test" in it,
the bot replies with a suggestion to try "test".
If the received message arrives directly, the bot replies with RF SNR and RSSI.
If the received message arrives multihop, the bot replies with the number
of intermediate nodes that conveyed the message.
For every received text message, the script logs the (number of messages with
a supported command in it) / (number of text messages received).
"""

import logging
import time

from pubsub import pub

import meshtastic
import meshtastic.serial_interface

logger = logging.getLogger(__name__)

rcvd_text_msg_count = 0
rcvd_command_count = 0

def main():
    logging.basicConfig(level=logging.INFO, datefmt="%Y/%m/%d %H:%M%S")
    pub.subscribe(on_receive, "meshtastic.receive")
    pub.subscribe(on_connection, "meshtastic.connection.established")
    with meshtastic.serial_interface.SerialInterface() as _:
        try:
            while True:
                time.sleep(500)
        finally:
            logger.info('Finished')

def on_connection(interface, topic=pub.AUTO_TOPIC):
    """called when we (re)connect to the radio"""
    logger.info('Started.')

def on_receive(packet:dict, interface):
    """called when a message arrives"""
    # This script uses the name "rx_msg" but pubsub calls
    # this procedure with the named arg "packet"
    rx_msg = packet
    reply = process_received_message(rx_msg)
    if reply:
        origin = rx_msg['from']
        interface.sendText(reply, destinationId=origin)
        logger.info(get_diagnostic_counts_message())

def process_received_message(rx_msg:dict) -> str:
    global rcvd_text_msg_count, rcvd_command_count

    if is_text_message(rx_msg):
        rcvd_text_msg_count += 1
        if is_in_message("test", rx_msg):
            rcvd_command_count += 1
            return get_reply_to_test_command(rx_msg)
        elif is_in_message("counts", rx_msg):
            rcvd_command_count += 1
            return get_diagnostic_counts_message()
        return help_reply()
    return ""

def is_text_message(msg:dict) -> bool:
    return msg["decoded"]["portnum"] == "TEXT_MESSAGE_APP"

def is_in_message(substr:str, msg:dict) -> bool:
    return substr in msg["decoded"]["text"].lower()

def get_reply_to_test_command(msg:dict) -> str:
    msg_keys = msg.keys()
    if "hopStart" not in msg_keys or "hopLimit" not in msg_keys:
        return "I heard you, but can't count the hops your message took."
    else:
        intermediate_node_count = msg['hopStart'] - msg['hopLimit']
        if intermediate_node_count == 0:
            if "rxSnr" not in msg_keys or "rxRssi" not in msg_keys:
                return "I heard you, but didn't get any RF stats to share."
            else:
                return f"I heard you!\nSNR: {msg['rxSnr']}, RSSI: {msg['rxRssi']}"
        else:
            return f"I heard you!\nthrough {intermediate_node_count} nodes."

def get_diagnostic_counts_message() -> str:
    global rcvd_text_msg_count, rcvd_command_count
    return f"{rcvd_command_count} commands / {rcvd_text_msg_count} messages"

def help_reply():
    return "Put the word \"test\" in your message and see what happens."

if __name__ == "__main__":
    main()
