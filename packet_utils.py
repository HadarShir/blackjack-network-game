# packet_utils.py
import struct
from constants import *

# =============================================================================
# Struct formats + sizes (avoid magic numbers)
# =============================================================================

OFFER_FMT = f"!IBH{SERVER_NAME_SIZE}s"
OFFER_SIZE = struct.calcsize(OFFER_FMT)

REQUEST_FMT = f"!IBB{TEAM_NAME_SIZE}s"
REQUEST_SIZE = struct.calcsize(REQUEST_FMT)

CLIENT_PAYLOAD_FMT = f"!IB{PLAYER_DECISION_SIZE}s"
CLIENT_PAYLOAD_SIZE = struct.calcsize(CLIENT_PAYLOAD_FMT)

# Server payload: cookie(4) + type(1) + result(1) + rank(2) + suit(1)
SERVER_PAYLOAD_FMT = "!IBBHB"
SERVER_PAYLOAD_SIZE = struct.calcsize(SERVER_PAYLOAD_FMT)


# =============================================================================
# OFFER PACKET (Server -> Client, UDP)
# =============================================================================
def create_offer_packet(tcp_port, server_name):
    """
    Encodes an offer message for UDP broadcast.
    Format: Magic Cookie (4), Msg Type (1), TCP Port (2), Server Name (32)
    """
    name_bytes = server_name.encode('utf-8')[:SERVER_NAME_SIZE].ljust(SERVER_NAME_SIZE, b'\x00')
    return struct.pack(OFFER_FMT, MAGIC_COOKIE, MSG_TYPE_OFFER, tcp_port, name_bytes)


def parse_offer_packet(data):
    """
    Decodes an incoming UDP offer packet.
    Returns a dictionary with port and name, or None if invalid.
    """
    if len(data) < OFFER_SIZE:
        return None

    cookie, m_type, port, name = struct.unpack(OFFER_FMT, data[:OFFER_SIZE])

    if cookie != MAGIC_COOKIE or m_type != MSG_TYPE_OFFER:
        return None

    return {"port": port, "server_name": name.decode('utf-8', errors='ignore').rstrip('\x00')}


# =============================================================================
# REQUEST PACKET (Client -> Server, TCP)
# =============================================================================
def create_request_packet(num_rounds, team_name):
    """
    Encodes the initial client request after TCP connection.
    Format: Magic Cookie (4), Msg Type (1), Rounds (1), Team Name (32)
    """
    if not (0 <= num_rounds <= 255):
        raise ValueError("num_rounds must fit in 1 byte (0..255)")

    name_bytes = team_name.encode('utf-8')[:TEAM_NAME_SIZE].ljust(TEAM_NAME_SIZE, b'\x00')
    return struct.pack(REQUEST_FMT, MAGIC_COOKIE, MSG_TYPE_REQUEST, num_rounds, name_bytes)


def parse_request_packet(data):
    """
    Decodes an incoming TCP request packet.
    Returns a dict { "rounds": int, "team_name": str } or None if invalid.
    """
    if len(data) < REQUEST_SIZE:
        return None

    cookie, m_type, rounds, name = struct.unpack(REQUEST_FMT, data[:REQUEST_SIZE])

    if cookie != MAGIC_COOKIE or m_type != MSG_TYPE_REQUEST:
        return None

    team_name = name.decode('utf-8', errors='ignore').rstrip('\x00')
    return {"rounds": rounds, "team_name": team_name}


# =============================================================================
# PAYLOAD PACKETS (TCP Game communication)
# =============================================================================

def create_client_payload(decision):
    """
    Encodes the client's decision during their turn.
    Format: Magic Cookie (4), Msg Type (1), Decision (5)
    Decision must be: "Hittt" or "Stand"
    """
    if decision not in ("Hittt", "Stand"):
        raise ValueError("decision must be 'Hittt' or 'Stand'")

    decision_bytes = decision.encode('utf-8')[:PLAYER_DECISION_SIZE].ljust(PLAYER_DECISION_SIZE, b'\x00')
    return struct.pack(CLIENT_PAYLOAD_FMT, MAGIC_COOKIE, MSG_TYPE_PAYLOAD, decision_bytes)


def parse_client_payload(data):
    """
    Decodes an incoming client payload packet.
    Returns a dict { "decision": "Hittt"/"Stand" } or None if invalid.
    """
    if len(data) < CLIENT_PAYLOAD_SIZE:
        return None

    cookie, m_type, decision_bytes = struct.unpack(CLIENT_PAYLOAD_FMT, data[:CLIENT_PAYLOAD_SIZE])

    if cookie != MAGIC_COOKIE or m_type != MSG_TYPE_PAYLOAD:
        return None

    decision = decision_bytes.decode('utf-8', errors='ignore').rstrip('\x00')
    if decision not in ("Hittt", "Stand"):
        return None

    return {"decision": decision}


def create_server_payload(result, rank, suit):
    """
    Encodes the server's game update/result.
    Format: Magic Cookie (4), Msg Type (1), Result (1), Rank (2 bytes), Suit (1)

    - result: 0x0..0x3
    - rank: numeric value 1..13 encoded as unsigned short (2 bytes)
    - suit: numeric value 0..3 encoded as 1 byte
    """
    return struct.pack(SERVER_PAYLOAD_FMT, MAGIC_COOKIE, MSG_TYPE_PAYLOAD, result, rank, suit)


def parse_server_payload(data):
    """
    Decodes an incoming server payload packet.
    Returns a dict { "result": int, "rank": int, "suit": int } or None if invalid.
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
