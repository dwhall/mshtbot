#!/usr/bin/env python3
# coding: unicode_escape
#
# Copyright 2024 Dean Hall, see LICENSE for details

"""Bot that replies to text messages using a local LLM.

REQUIREMENTS:

* Install ollama: https://ollama.com/download
* $ ollama pull <model of your choice>
* Set MODEL to <model of your choice>
* $ pip install poetry
* $ poetry install
"""

import logging
import textwrap
import time

import meshtastic
import meshtastic.serial_interface
from meshtastic.mesh_pb2 import Constants
from ollama import Client
from pubsub import pub


logger = logging.getLogger(__name__)


MODEL = "llama3.1"
SYS_PROMPT = """You are a general AI providing conversation and helpful answers
        in 500 or fewer characters or fewer than 250 characters when possible."""


def main():
    llm_context = {}
    ollama_client = Client(host="http://localhost:11434")
    logging.basicConfig(level=logging.INFO, datefmt="%Y/%m/%d %H:%M%S")
    pub.subscribe(on_receive, "meshtastic.receive.text", llm_client=ollama_client, llm_context=llm_context)
    pub.subscribe(on_connection, "meshtastic.connection.established")
    with meshtastic.serial_interface.SerialInterface() as _:
        try:
            while True:
                time.sleep(100)
        finally:
            logger.info("Finished.")

def on_connection(interface, topic=pub.AUTO_TOPIC):
    logger.info("Started.")

def on_receive(packet:dict, interface, llm_client, llm_context:dict):
    rx_msg = packet
    if rx_msg["to"] == interface.myInfo.my_node_num:
        sender = rx_msg["fromId"]
        reply = get_llm_reply(rx_msg["fromId"], rx_msg["decoded"]["text"], llm_client, llm_context)
        for reply_chunk in textwrap.wrap(reply, width=Constants.DATA_PAYLOAD_LEN, subsequent_indent="…", break_long_words=False):
            interface.sendText(reply_chunk, destinationId=sender)
            logger.info("Sent %d char reply to %s.", len(reply_chunk), sender)

def get_llm_reply(sender, msg:str, llm_client, llm_context:dict) -> str:
    context_for_this_sender = llm_context.get(sender, None)
    llm_response = llm_client.generate(model=MODEL, prompt=msg, context=context_for_this_sender, system=SYS_PROMPT)
    if llm_response["done"]:
        llm_context[sender] = llm_response["context"]
    return llm_response["response"]

if __name__ == "__main__":
    main()
