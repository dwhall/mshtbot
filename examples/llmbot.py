#!/usr/bin/env python3
# coding: unicode_escape
#
# Copyright 2024 Dean Hall, see LICENSE for details

"""Bot that replies to text messages using a local LLM.

REQUIREMENTS:

* Install ollama: https://ollama.com/download
* $ ollama pull <model of your choice>
* Set MODEL to <model of your choice>
"""

import argparse
import collections
import logging
import textwrap

import farc
import meshtastic
import meshtastic.serial_interface
from meshtastic.protobuf.mesh_pb2  import Constants
from ollama import Client
from pubsub import pub


MODEL = "llama3.2"
SER_PORT = "COM5"
SYS_PROMPT = """You are a general AI providing conversation and helpful answers
        in 500 or fewer characters or fewer than 250 characters when possible. Do not use emojis."""
DELAY_BETWEEN_MSGS = 10.0  # seconds.  Allows time to read the message and reduces flooding

logging.basicConfig(level=logging.INFO, datefmt="%Y/%m/%d %H:%M:%S")
logger = logging.getLogger(__name__)

farc.Signal.register("MSG_RECEIVED")
farc.Signal.register("SEND_NOW")
MSG_RECEIVED = farc.Event(farc.Signal.MSG_RECEIVED, None)
SEND_NOW = farc.Event(farc.Signal.SEND_NOW, None)

def main():
    logger.info("main")
    args = parse_args()
    llmbot = MsgBotAhsm(args.port)
    llmbot.start(0)
    pub.subscribe(on_receive, "meshtastic.receive.text", llm_ahsm=llmbot)
    pub.subscribe(on_connection, "meshtastic.connection.established")
    farc.run_forever()

def parse_args():
    parser = argparse.ArgumentParser(description="Meshtastic LLM chat bot")
    parser.add_argument("--port", type=str, default=SER_PORT, help="Serial port to connect to Meshtastic device")
    return parser.parse_args()

def on_connection(interface, topic=pub.AUTO_TOPIC):
    """This procedure is called when a serial connection is established
    between this computer and a Meshtastic node.
    """
    logger.info("Connected to Meshtastic node.")

def on_receive(packet:dict, interface, llm_ahsm):
    """This procedure is called when a Meshtastic text message is received.
    Enqueues messages intended for this node.
    """
    if packet["to"] != interface.myInfo.my_node_num: return
    sender = packet["fromId"]
    msg = packet["decoded"]["text"]
    pkt_id = packet["id"]
    logger.info("Received %d chars from %s.", len(msg), sender)
    llm_ahsm.interface = interface
    llm_ahsm.accept_inbound_msg(sender, msg, pkt_id)

class MsgBotAhsm(farc.Ahsm):
    def __init__(self, ser_port:str):
        super().__init__()
        logger.info("MsgBotAhsm")
        self.ser_port = ser_port

    @farc.Hsm.state
    def _initial(self, event):
        logger.info("_initial")
        self.tm_evt = farc.TimeEvent("TEN_SEC")
        return self.tran(MsgBotAhsm._listening)

    @farc.Hsm.state
    def _running(self, event):
        """Initializes instance fields and starts a periodic timer event.
        The periodic event sends any outbound messages waiting in the queue.
        """
        sig = event.signal
        if sig == farc.Signal.ENTRY:
            logger.info("_running")
            self.msht_intf = meshtastic.serial_interface.SerialInterface(self.ser_port)
            self.inbound_queue = collections.deque()
            self.outbound_queue = collections.deque()
            self.llm_context = {}
            self.llm_client = Client(host="http://localhost:11434")
            self.tm_evt.post_every(self, 10) # seconds
            return self.handled(event)
        elif sig == farc.Signal.TEN_SEC or sig == farc.Signal.SEND_NOW:
            self.send_any_outbound_msg()
            return self.handled(event)
        elif sig == farc.Signal.EXIT:
            logger.info("Exiting _running")
            self.tm_evt.disarm()
            self.msht_intf.close()
            return self.handled(event)
        return self.super(farc.Hsm.top)

    @farc.Hsm.state
    def _listening(self, event):
        """Waits for inbound messages, processes them when they arrive.
        """
        sig = event.signal
        if sig == farc.Signal.ENTRY:
            logger.info("_listening")
            return self.handled(event)
        elif sig == farc.Signal.MSG_RECEIVED:
            self.process_inbound_msg()
            return self.handled(event)
        return self.super(MsgBotAhsm._running)

    # Methods
    def accept_inbound_msg(self, sender, msg:str, pkt_id:int):
        self.inbound_queue.appendleft((sender, msg, pkt_id))
        self.post_fifo(MSG_RECEIVED)

    def process_inbound_msg(self):
        (sender, msg, pkt_id) = self.inbound_queue.pop()
        full_reply = self.generate_reply(sender, msg)
        self.post_outbound_msg(sender, full_reply, pkt_id)

    def generate_reply(self, sender, msg:str) -> str:
        """Gives the sender's message to the LLM and returns the LLM's reply
        or an error message if the LLM fails.
        """
        try:
            context_for_this_sender = self.llm_context.get(sender, None)
            llm_response = self.llm_client.generate(model=MODEL, prompt=msg, context=context_for_this_sender, system=SYS_PROMPT)
            if llm_response["done"]:
                self.llm_context[sender] = llm_response["context"]
            reply = llm_response["response"]
        except Exception as e:
            logger.error("LLM exception: %s", e)
            reply = "LLM exception.  Brain fail.  Beep, boop."
        return reply

    def post_outbound_msg(self, dest_id, msg:str, pkt_id:int):
        """Enqueues a message, in fragments if necessary, to the outbound queue.
        Posts an event to self to send one message immediately.
        """
        SAFETY_MARGIN = 8 # chars
        MAX_HEADER_SIZE = len(optionalHeader(99, 99)) # 8 chars
        payld_sz = Constants.DATA_PAYLOAD_LEN - MAX_HEADER_SIZE - SAFETY_MARGIN
        msg_frags = textwrap.wrap(msg, width=payld_sz, subsequent_indent="…", break_long_words=False)
        for n, msg_frag in enumerate(msg_frags):
            msg_payload = optionalHeader(n+1, len(msg_frags)) + msg_frag
            self.outbound_queue.appendleft((dest_id, msg_payload, pkt_id))
        self.post_lifo(SEND_NOW)

    def send_any_outbound_msg(self):
        if len(self.outbound_queue) > 0:
            (dest_id, msg_payload, pkt_id) = self.outbound_queue.pop()
            # DWH: TODO: try self.msht_intf instead of .interface
            self.interface.sendText(msg_payload, destinationId=dest_id, replyId=pkt_id)
            logger.info("Sent %d byte message in reply to %s.", len(msg_payload), dest_id)

def optionalHeader(n: int, d: int) -> str:
    """Returns a header indicating the message numbering of the reply.
    Or, if the reply fits in one message, the header is empty.
    """
    if d > 1:
        return f"[{n}/{d}] "
    return ""

if __name__ == "__main__":
    main()
    logger.info("Done.")
