#!/usr/bin/env python3
#
# Copyright 2024 Dean Hall, see LICENSE for details

"""Bot that replies to text messages using a local LLM.

REQUIREMENTS:

* Install ollama: https://ollama.com/download
* ollama pull <model of your choice>
* Set MODEL to <model of your choice>
"""

import logging
import time

import meshtastic
import meshtastic.serial_interface
from meshtastic.mesh_pb2 import Constants
from ollama import Client
from pubsub import pub


logger = logging.getLogger(__name__)


MODEL = "phi_55"
SYS = """You are a general AI providing conversation and helpful answers
        in 500 or fewer characters or fewer than 250 characters when possible."""

context = {}
ollama_client = Client(host="http://localhost:11434")


def main():
    logging.basicConfig(level=logging.INFO, datefmt="%Y/%m/%d %H:%M%S")
    pub.subscribe(on_receive, "meshtastic.receive.text")
    pub.subscribe(on_connection, "meshtastic.connection.established")
    with meshtastic.serial_interface.SerialInterface() as _:
        try:
            while True:
                time.sleep(500)
        finally:
            logger.info("Finished.")

def on_connection(interface, topic=pub.AUTO_TOPIC):
    logger.info("Started.")

def on_receive(packet:dict, interface):
    rx_msg = packet
    if rx_msg["to"] == interface.myInfo.my_node_num:
        reply = process_received_text_message(rx_msg)
        if reply:
            sender = rx_msg["fromId"]
            interface.sendText(reply, destinationId=sender)
            logger.info("Sent %d char reply to %s.", len(reply), sender)

def process_received_text_message(rx_msg:dict) -> str:
    reply = get_ollama_reply(rx_msg["fromId"], rx_msg["decoded"]["text"])
    if len(reply) > Constants.DATA_PAYLOAD_LEN:
        index_of_last_period = reply[:Constants.DATA_PAYLOAD_LEN].rfind(".")
        return reply[:index_of_last_period + 1]
    return reply

def get_ollama_reply(sender, msg:str) -> str:
    global context, ollama_client
    ctx = context.get(sender, None)
    llm_response = ollama_client.generate(model=MODEL, prompt=msg, context=ctx, system=SYS)
    if llm_response["done"]:
        context[sender] = llm_response["context"]
    return llm_response["response"]


if __name__ == "__main__":
    main()
