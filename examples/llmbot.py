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


MODEL = "llama3.2"
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
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Finished.")

def on_connection(interface, topic=pub.AUTO_TOPIC):
    """This procedure is called when a serial connection is established
    between this computer and a Meshtastic node.
    """
    logger.info("Started.")

def on_receive(packet:dict, interface, llm_client, llm_context:dict):
    """This procedure is called when a Meshtastic text message is received.
    Checks that the message was intended for this node,
    dispatches the message to the LLM and sends the LLM's reply
    back to the sender over Meshtastic.
    """
    if packet["to"] != interface.myInfo.my_node_num: return
    sender = packet["fromId"]
    msg_payld = packet["decoded"]["text"]
    logger.info("Received %d chars from %s.", len(msg_payld), sender)
    reply = get_llm_reply(packet["fromId"], msg_payld, llm_client, llm_context)
    send_msht_msg(interface, sender, reply)

def get_llm_reply(sender, msg:str, llm_client, llm_context:dict) -> str:
    """Issues the message to the LLM client using the given context
    and storing the resulting context.  Returns the LLM reply as a text string.
    """
    context_for_this_sender = llm_context.get(sender, None)
    llm_response = llm_client.generate(model=MODEL, prompt=msg, context=context_for_this_sender, system=SYS_PROMPT)
    if llm_response["done"]:
        llm_context[sender] = llm_response["context"]
    return llm_response["response"]

def send_msht_msg(interface, dest_id, msg:str):
    """Sends a message, fragmented into chunks if necessary, over the Meshtastic
    interface to the destination ID
    """
    MAX_HEADER_SIZE = 7 # chars
    n = 0
    payld_sz = Constants.DATA_PAYLOAD_LEN - MAX_HEADER_SIZE
    sent_char_cnt = 0
    approx_chunk_cnt = ceildiv(len(msg), payld_sz)  # approx because not accounting for header
    # Fragment msg into 1+ chunk(s) that fit in the meshtastic payload
    for chunk in textwrap.wrap(msg, width=payld_sz, subsequent_indent="�", break_long_words=False):
        n += 1
        text = optionalHeader(n, approx_chunk_cnt) + chunk
        interface.sendText(text, destinationId=dest_id)
        if approx_chunk_cnt > 1:
            time.sleep(10.0)    # TODO: make non-blocking
        sent_char_cnt += len(text)
    logger.info("Sent %d chars in %d message(s) in reply to %s.", sent_char_cnt, n, dest_id)

def optionalHeader(n: int, d: int) -> str:
    """Returns a header indicating the chunk-numbering of the reply.
    Or, if the reply fits in one message, the header is empty.
    """
    if d > 1:
        return f"[{n}/{d}] "
    return ""

def ceildiv(a, b):
    """Perform upside-down floor division to get ceiling division
    https://stackoverflow.com/questions/14822184/is-there-a-ceiling-equivalent-of-operator-in-python
    """
    return -(a // -b)

if __name__ == "__main__":
    main()
