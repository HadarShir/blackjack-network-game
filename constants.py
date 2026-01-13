# constants.py

# Protocol Constants
MAGIC_COOKIE = 0xabcddcba

# Network Configuration
OFFER_BROADCAST_INTERVAL = 1 # Send offer every 1 second
UDP_PORT = 13122

# Message Types
MSG_TYPE_OFFER = 0x2
MSG_TYPE_REQUEST = 0x3
MSG_TYPE_PAYLOAD = 0x4

# הגדרה של ניצחון הפסד וכדומה
# Payload Result Codes (server -> client)
RESULT_GAME_NOT_OVER = 0x00
RESULT_TIE = 0x01
RESULT_LOSS = 0x02
RESULT_WIN = 0x03

# Sizes & Padding
TEAM_NAME_SIZE = 32
SERVER_NAME_SIZE = 32
PLAYER_DECISION_SIZE = 5  # Both "Hittt" and "Stand" are 5 bytes

# Team Settings
SERVER_NAME = "BeautyBlendersServer" # תבחרי שם יצירתי לתחרות!
TEAM_NAME = "BeautyBlenders"

# Connection Settings
BUFFER_SIZE = 1024

# ==============================
# Card Values for Game Logic
# ==============================

# Mapping from Rank (1-13) to Blackjack Value
CARD_VALUES = {
    1: 11,  # Ace (A)
    2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10,
    11: 10, # Jack (J)
    12: 10, # Queen (Q)
    13: 10  # King (K)
}

# For pretty printing (Optional)
RANK_NAMES = {
    1: 'Ace', 11: 'Jack', 12: 'Queen', 13: 'King'
}