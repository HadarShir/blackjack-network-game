# constants.py

"""
Blackjack Hackathon - Shared constants.

This file contains:
1) Protocol constants (magic cookie, message types, fixed sizes) - per assignment spec.
2) Networking configuration (UDP listen port, offer interval).
3) Game constants (rank->value mapping for this simplified Blackjack).
"""

# Protocol Constants, if not -> message is rejected
MAGIC_COOKIE = 0xabcddcba

# Network Configuration
# # Server broadcasts offer once every second
OFFER_BROADCAST_INTERVAL = 1
# UDP_PORT is fixed by assignment (client must bind/listen on 13122)
UDP_PORT = 13122

# Message Types
# 0x2 = offer (server -> client, UDP)
# 0x3 = request (client -> server, TCP)
# 0x4 = payload (both directions, TCP)
MSG_TYPE_OFFER = 0x2  # server -> client
MSG_TYPE_REQUEST = 0x3
MSG_TYPE_PAYLOAD = 0x4


# Payload Result Codes (server -> client)
# 0x0 = round not over (game continues)
# 0x1 = tie
# 0x2 = loss (for the client)
# 0x3 = win (for the client)
RESULT_GAME_NOT_OVER = 0x00
RESULT_TIE = 0x01
RESULT_LOSS = 0x02
RESULT_WIN = 0x03

# Sizes & Padding
TEAM_NAME_SIZE = 32
SERVER_NAME_SIZE = 32
# Client sends ASCII text: b"Hittt" or b"Stand"
PLAYER_DECISION_SIZE = 5

# Team Settings
SERVER_NAME = "BeautyBlendersServer" # תבחרי שם יצירתי לתחרות!
TEAM_NAME = "BeautyBlenders"

# Connection Settings
# A generic receive buffer size. Note: TCP requires reading EXACT packet sizes,
# so do not rely on this to receive "one full message" in TCP.
BUFFER_SIZE = 1024

# ==============================
# Card Values for Game Logic
# ==============================

# Mapping from Rank (1-13) to Blackjack Value
# 2-10 => same number
# J/Q/K (11-13) => 10
# Ace => 11  in this assignment Ace is ALWAYS 11
CARD_VALUES = {
    1: 11,  # Ace (A)
    2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10,
    11: 10, # Jack (J)
    12: 10, # Queen (Q)
    13: 10  # King (K)
}

# Optional: helpful for debugging / printing
RANK_NAMES = {
    1: 'Ace', 11: 'Jack', 12: 'Queen', 13: 'King'
}