# packet_utils.py
import struct
from constants import *

# =============================================================================
# Packet formats (network byte order)
# =============================================================================
# ! = network (big-endian)
# I = 4-byte unsigned int  (magic cookie)
# B = 1-byte unsigned char (message type / result / rounds)
# H = 2-byte unsigned short (TCP port / rank)
# 32s / 5s = fixed-length bytes

OFFER_FMT = f"!IBH{SERVER_NAME_SIZE}s"
OFFER_SIZE = struct.calcsize(OFFER_FMT)

REQUEST_FMT = f"!IBB{TEAM_NAME_SIZE}s"
REQUEST_SIZE = struct.calcsize(REQUEST_FMT)

CLIENT_PAYLOAD_FMT = f"!IB{PLAYER_DECISION_SIZE}s"
CLIENT_PAYLOAD_SIZE = struct.calcsize(CLIENT_PAYLOAD_FMT)

# Server payload:
# cookie(4) + type(1) + result(1) + rank(2) + suit(1)
SERVER_PAYLOAD_FMT = "!IBBHB"
SERVER_PAYLOAD_SIZE = struct.calcsize(SERVER_PAYLOAD_FMT)


# =============================================================================
# Offer (server -> client, UDP)
# =============================================================================
def create_offer_packet(tcp_port: int, server_name: str) -> bytes:
    """
    Offer format:
      cookie(4) | type(1=0x2) | tcp_port(2) | server_name(32)
    """
    name_bytes = server_name.encode("utf-8")[:SERVER_NAME_SIZE].ljust(SERVER_NAME_SIZE, b"\x00")
    return struct.pack(OFFER_FMT, MAGIC_COOKIE, MSG_TYPE_OFFER, tcp_port, name_bytes)


def parse_offer_packet(data: bytes):
    """
    Return {"port": int, "server_name": str} or None if invalid.
    """
    if len(data) < OFFER_SIZE:
        return None

    cookie, m_type, port, name_bytes = struct.unpack(OFFER_FMT, data[:OFFER_SIZE])
    if cookie != MAGIC_COOKIE or m_type != MSG_TYPE_OFFER:
        return None

    return {
        "port": port,
        "server_name": name_bytes.decode("utf-8", errors="ignore").rstrip("\x00")
    }


# =============================================================================
# Request (client -> server, TCP)
# =============================================================================
def create_request_packet(num_rounds: int, team_name: str) -> bytes:
    """
    Request format:
      cookie(4) | type(1=0x3) | rounds(1) | team_name(32)

    IMPORTANT:
    Per the protocol text you sent, this is a fixed-size binary struct.
    We do NOT append '\\n' here.
    """
    if not (1 <= num_rounds <= 255):
        raise ValueError("num_rounds must fit in 1 byte (1..255)")

    name_bytes = team_name.encode("utf-8")[:TEAM_NAME_SIZE].ljust(TEAM_NAME_SIZE, b"\x00")
    return struct.pack(REQUEST_FMT, MAGIC_COOKIE, MSG_TYPE_REQUEST, num_rounds, name_bytes)


def parse_request_packet(data: bytes):
    """
    Return {"rounds": int, "team_name": str} or None if invalid.
    """
    if len(data) < REQUEST_SIZE:
        return None

    cookie, m_type, rounds, name_bytes = struct.unpack(REQUEST_FMT, data[:REQUEST_SIZE])
    if cookie != MAGIC_COOKIE or m_type != MSG_TYPE_REQUEST:
        return None

    return {
        "rounds": rounds,
        "team_name": name_bytes.decode("utf-8", errors="ignore").rstrip("\x00")
    }


# =============================================================================
# Payload (TCP) - client and server share type=0x4 but different body
# =============================================================================
def create_client_payload(decision: str) -> bytes:
    """
    Client payload format:
      cookie(4) | type(1=0x4) | decision(5)
    decision must be "Hittt" or "Stand"
    """
    if decision not in ("Hittt", "Stand"):
        raise ValueError("decision must be 'Hittt' or 'Stand'")

    d = decision.encode("utf-8")[:PLAYER_DECISION_SIZE].ljust(PLAYER_DECISION_SIZE, b"\x00")
    return struct.pack(CLIENT_PAYLOAD_FMT, MAGIC_COOKIE, MSG_TYPE_PAYLOAD, d)


def parse_client_payload(data: bytes):
    """
    Return {"decision": str} or None if invalid.
    """
    if len(data) < CLIENT_PAYLOAD_SIZE:
        return None

    cookie, m_type, dbytes = struct.unpack(CLIENT_PAYLOAD_FMT, data[:CLIENT_PAYLOAD_SIZE])
    if cookie != MAGIC_COOKIE or m_type != MSG_TYPE_PAYLOAD:
        return None

    decision = dbytes.decode("utf-8", errors="ignore").rstrip("\x00")
    if decision not in ("Hittt", "Stand"):
        return None
    return {"decision": decision}


def create_server_payload(result: int, rank: int, suit: int) -> bytes:
    """
    Server payload format:
      cookie(4) | type(1=0x4) | result(1) | rank(2) | suit(1)
    """
    return struct.pack(SERVER_PAYLOAD_FMT, MAGIC_COOKIE, MSG_TYPE_PAYLOAD, result, rank, suit)


def parse_server_payload(data: bytes):
    """
    Return {"result": int, "rank": int, "suit": int} or None if invalid.
    """
    if len(data) < SERVER_PAYLOAD_SIZE:
        return None

    cookie, m_type, result, rank, suit = struct.unpack(SERVER_PAYLOAD_FMT, data[:SERVER_PAYLOAD_SIZE])

    if cookie != MAGIC_COOKIE or m_type != MSG_TYPE_PAYLOAD:
        return None
    if result not in (0, 1, 2, 3):
        return None
    if not (1 <= rank <= 13):
        return None
    if not (0 <= suit <= 3):
        return None

    return {"result": result, "rank": rank, "suit": suit}
