# client.py


import socket
import sys
from typing import List, Tuple, Optional

# Optional noise filter:
# If set to a specific server name, we accept offers only from that server.
# Useful on crowded testing networks with many teams broadcasting offers
FILTER_SERVER_NAME = "BeautyBlendersServer"   # <- enable filter (accept only this server_name)
#FILTER_SERVER_NAME = None  # <- disable filter (accept any server)

from constants import (
    UDP_PORT,
    TEAM_NAME,
    RESULT_WIN,
    RESULT_LOSS,
    RESULT_TIE,
    RESULT_GAME_NOT_OVER,
)
from packet_utils import (
    parse_offer_packet,
    create_request_packet,
    create_client_payload,
    parse_server_payload,
    SERVER_PAYLOAD_SIZE,
)

# ==============================
# UI toggles
# ==============================
SHOW_ASCII_CARDS = True   # set False if you want minimal output

# ==============================
# Timeouts
# ==============================
GAME_IDLE_TIMEOUT_SEC = 60    # if nothing happens on TCP socket for 60s -> stall message + quit session
TCP_CONNECT_TIMEOUT_SEC = 10  # how long to wait for TCP connect

# Card representation used locally for UI/statistics:
# (rank: 1..13, suit: 0..3)
Card = Tuple[int, int]  # (rank, suit)


# ==============================
# Fun messages
# ==============================
def print_welcome_banner() -> None:
    """
    Friendly welcome banner.
    Safe to print because the assignment only *requires* specific prints for offer listening and offer received.
    """
    print("\n🂡 Welcome to Blackjacky 🂡")
    print("Blackjack is fast: you can win everything… or lose everything 😈\n")


def print_stall_message() -> None:
    """
    Printed when the game stalls (TCP timeout / no response).
    """
    print("\n⏱️ Game Over!")
    print("You stall, you fall. Blackjack waits for no one 😉\n")

def print_slash_banner(text: str) -> None:
    """
    Slash-style big banner without external libs.
    Works for any text (simple but looks cool).
    """
    text = text.strip()
    line1 = " /" + "=" * (len(text) + 6) + "\\"
    line2 = f"|   {text}   |"
    line3 = " \\" + "=" * (len(text) + 6) + "/"

    print("\n" + line1)
    print(line2)
    print(line3 + "\n")

# ==============================
# Input: number of rounds
# ==============================
def get_num_rounds() -> int:
    """
    Ask the user how many rounds to play.
    Protocol uses 1 byte => valid range: 1..255.
    """
    while True:
        line = input("How many rounds would you like to play? (1-255, or 'q' to quit): ").strip()
        if line.lower() in ("q", "quit", "exit"):
            raise KeyboardInterrupt
        try:
            n = int(line)
            if 1 <= n <= 255:
                return n
        except ValueError:
            pass
        print("Invalid input. Please enter a number between 1 and 255.")


# ==============================
# TCP helper: recv exact bytes
# ==============================
def recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    """
    Read exactly n bytes from a TCP socket.

    Why needed?
    TCP is a byte-stream protocol (no message boundaries).
    Our protocol uses fixed-size binary messages (SERVER_PAYLOAD_SIZE),
    so we must loop until we receive exactly n bytes.

    Returns:
        bytes of length n on success, or None on timeout/disconnect/error.
    """
    data = b""
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
        except (socket.timeout, OSError):
            return None
        if not chunk:
            return None
        data += chunk
    return data


# ==============================
# Totals (Assignment values)
# ==============================
def card_value(rank: int) -> int:
    """
    Assignment rule:
    - Ace (A) = 11
    - J/Q/K = 10
    - 2..10 = numeric value
    """
    if rank == 1:
        return 11
    if rank >= 11:
        return 10
    return rank


def hand_total(cards: List[Card]) -> int:
    """Compute total points of a hand using assignment rules."""
    return sum(card_value(rank) for rank, _ in cards)


def print_totals(player_cards: List[Card], dealer_cards: List[Card], dealer_hidden: bool) -> None:
    """
    Print player's total and dealer's total.
    - dealer_hidden=True  => show only dealer's visible cards total ("Dealer shown total")
    - dealer_hidden=False => show full dealer total ("Dealer total")
    """
    print(f"Your total: {hand_total(player_cards)}")
    if dealer_hidden:
        print(f"Dealer shown total: {hand_total(dealer_cards)}")
    else:
        print(f"Dealer total: {hand_total(dealer_cards)}")


# ==============================
# ASCII Card Rendering
# ==============================
def rank_to_face(rank: int) -> str:
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(rank, str(rank))


def suit_to_symbol(suit: int) -> str:
    # Spec: Suit encoded 0-3 (H/D/C/S). We use:
    # 0=Hearts, 1=Diamonds, 2=Clubs, 3=Spades
    return {0: "♥", 1: "♦", 2: "♣", 3: "♠"}.get(suit, "?")


def card_to_ascii(rank: int, suit: int) -> List[str]:
    r = rank_to_face(rank)
    s = suit_to_symbol(suit)

    left = r.ljust(2)   # keep width stable for 10
    right = r.rjust(2)

    return [
        "┌───────┐",
        f"│ {left}    │",
        f"│   {s}   │",
        f"│    {right} │",
        "└───────┘",
    ]


def hidden_card_ascii() -> List[str]:
    return [
        "┌───────┐",
        "│░░░░░░░│",
        "│░░░░░░░│",
        "│░░░░░░░│",
        "└───────┘",
    ]


def cards_to_ascii_row(cards: List[Card], show_one_hidden: bool = False) -> str:
    """
    Render cards horizontally in ASCII.
    If show_one_hidden=True => adds ONE hidden (face-down) card at the end.
    """
    if not cards and not show_one_hidden:
        return ""

    rendered = [card_to_ascii(r, s) for (r, s) in cards]
    if show_one_hidden:
        rendered.append(hidden_card_ascii())

    # join line by line across all cards
    return "\n".join("  ".join(card[i] for card in rendered) for i in range(5))


def print_hands(player_cards: List[Card], dealer_visible_cards: List[Card], dealer_has_hidden: bool) -> None:
    """
    Prints player's hand and dealer's visible part.
    dealer_has_hidden=True draws an extra face-down card to indicate hidden card exists.
    """
    if not SHOW_ASCII_CARDS:
        return

    print("\nYour hand:")
    print(cards_to_ascii_row(player_cards))

    if dealer_has_hidden:
        print("\nDealer shows (1 hidden):")
        print(cards_to_ascii_row(dealer_visible_cards, show_one_hidden=True))
    else:
        print("\nDealer hand:")
        print(cards_to_ascii_row(dealer_visible_cards))


# ==============================
# Session: connect + play rounds
# ==============================
def play_session(server_ip: str, server_port: int, rounds: int) -> None:
    """
    Connect to the chosen server over TCP, send a REQUEST packet, then play 'rounds' rounds.

    Assignment flow:
    - Connect via TCP to the server IP + TCP port obtained from the UDP offer.
    - Immediately send REQUEST packet (binary struct; NO '\\n'):
        cookie(4) | type(1=0x3) | rounds(1) | client_team_name(32)
    - Play using PAYLOAD packets:
        client->server: cookie|type(0x4)|decision(5)
        server->client: cookie|type(0x4)|result(1)|rank(2)|suit(1)
    - When done, print:
        "Finished playing {x} rounds, win rate: {win_rate}"
    """
    wins = 0
    ties = 0
    losses = 0

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(GAME_IDLE_TIMEOUT_SEC)  # ✅ 60s stall detection during game (recv/send)

    try:
        # Connect timeout
        sock.settimeout(TCP_CONNECT_TIMEOUT_SEC)
        sock.connect((server_ip, server_port))

        # After connect, set game idle timeout again
        sock.settimeout(GAME_IDLE_TIMEOUT_SEC)

        # Request packet is fixed-size binary struct (NO '\n')
        sock.sendall(create_request_packet(rounds, TEAM_NAME))

        for r in range(1, rounds + 1):
            print(f"\n--- Round {r} ---")

            # Initial 3 payloads:
            # 2 player cards + 1 dealer visible card (dealer hidden card is not sent yet)
            p1b = recv_exact(sock, SERVER_PAYLOAD_SIZE)
            p2b = recv_exact(sock, SERVER_PAYLOAD_SIZE)
            d1b = recv_exact(sock, SERVER_PAYLOAD_SIZE)
            if not p1b or not p2b or not d1b:
                print_stall_message()
                return

            p1 = parse_server_payload(p1b)
            p2 = parse_server_payload(p2b)
            d1 = parse_server_payload(d1b)
            if not p1 or not p2 or not d1:
                print("Invalid payload received.")
                return

            player_cards: List[Card] = [(p1["rank"], p1["suit"]), (p2["rank"], p2["suit"])]
            dealer_cards: List[Card] = [(d1["rank"], d1["suit"])]

            # Display with one hidden dealer card (UI only)
            print_hands(player_cards, dealer_cards, dealer_has_hidden=True)
            print_totals(player_cards, dealer_cards, dealer_hidden=True)  # ✅ totals like before

            # Player turn loop: keep sending Hittt/Stand until server ends the round
            # Player turn
            while True:
                choice = input("Hittt or Stand? ").strip()
                if choice.lower() in ("q", "quit", "exit"):
                    raise KeyboardInterrupt
                if choice not in ("Hittt", "Stand"):
                    print("Please type exactly: Hittt or Stand")
                    continue

                try:
                    sock.sendall(create_client_payload(choice))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    print_stall_message()
                    return

                resp_b = recv_exact(sock, SERVER_PAYLOAD_SIZE)
                if not resp_b:
                    print_stall_message()
                    return

                resp = parse_server_payload(resp_b)
                if not resp:
                    print("Invalid server payload received.")
                    return

                # ✅ Option 2: If bust happened on server, server sends LOSS immediately here.
                if resp["result"] != RESULT_GAME_NOT_OVER:
                    if resp["result"] == RESULT_WIN:
                        wins += 1
                        print("Outcome: WIN")
                    elif resp["result"] == RESULT_LOSS:
                        losses += 1
                        print("Outcome: LOSS")
                    else:
                        ties += 1
                        print("Outcome: TIE")
                    break  # round over

                # resp result == NOT_OVER => it's a card update

                if choice == "Hittt":
                    player_cards.append((resp["rank"], resp["suit"]))
                    print_hands(player_cards, dealer_cards, dealer_has_hidden=True)
                    print_totals(player_cards, dealer_cards, dealer_hidden=True)
                    # ✅ IMPORTANT: No extra recv here in Option 2.
                    continue

                # choice == "Stand": first NOT_OVER payload after Stand is dealer hidden card reveal
                print("\n--- Dealer turn ---")
                dealer_cards.append((resp["rank"], resp["suit"]))
                print_hands(player_cards, dealer_cards, dealer_has_hidden=False)
                print_totals(player_cards, dealer_cards, dealer_hidden=False)

                while True:
                    nxt_b = recv_exact(sock, SERVER_PAYLOAD_SIZE)
                    if not nxt_b:
                        print_stall_message()
                        return

                    nxt = parse_server_payload(nxt_b)
                    if not nxt:
                        print("Invalid dealer payload received.")
                        return

                    if nxt["result"] == RESULT_GAME_NOT_OVER:
                        dealer_cards.append((nxt["rank"], nxt["suit"]))
                        print_hands(player_cards, dealer_cards, dealer_has_hidden=False)
                        print_totals(player_cards, dealer_cards, dealer_hidden=False)
                        continue

                    if nxt["result"] == RESULT_WIN:
                        wins += 1
                        print("Outcome: WIN")
                    elif nxt["result"] == RESULT_LOSS:
                        losses += 1
                        print("Outcome: LOSS")
                    else:
                        ties += 1
                        print("Outcome: TIE")
                    break

                break  # round over after dealer

        win_rate = (wins / rounds * 100.0) if rounds > 0 else 0.0

        # ✅ Required final line (exact required format)
        print(f"Finished playing {rounds} rounds, win rate: {win_rate:.1f}")

    finally:
        try:
            sock.close()
        except Exception:
            pass


# ==============================
# UDP listen for offers (blocking)
# ==============================
def listen_for_offer() -> tuple[str, int]:
    """
    Listen (blocking) for UDP OFFER packets on port 13122 (hardcoded by assignment).

    Required prints:
    - "Client started, listening for offer requests..."
    - "Received offer from <server_ip>"

    Implementation details:
    - bind("0.0.0.0", UDP_PORT) => listen on ALL local interfaces (WiFi/hotspot/etc.)
    - SO_REUSEPORT allows running multiple clients on the same machine (per assignment hint).
    """
    print("Client started, listening for offer requests...")

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    # 0.0.0.0 => receive offers on any local IP interface
    udp_sock.bind(("0.0.0.0", UDP_PORT))

    active_filter = (
        FILTER_SERVER_NAME.strip()
        if FILTER_SERVER_NAME and FILTER_SERVER_NAME.strip()
        else None
    )

    while True:
        # Buffer is bigger than the OFFER size (39 bytes), so we won't truncate the datagram.
        data, addr = udp_sock.recvfrom(2048)
        offer = parse_offer_packet(data)
        if not offer:
            continue

        server_ip = addr[0]
        server_port = offer["port"]
        server_name = offer["server_name"]

        # Noise filtering
        if active_filter and server_name != active_filter:
            continue

        print(f"Received offer from {server_ip}")
        if server_name == "BeautyBlendersServer" :
            print_slash_banner(server_name)
        else:
            print(f"Connected server name: {server_name}")
        udp_sock.close()
        return server_ip, server_port


# ==============================
# Main loop (runs forever)
# ==============================
if __name__ == "__main__":
    """
    Main loop runs forever until Ctrl+C (assignment requirement).
    Flow:
      1) Ask for rounds
      2) Listen for offer
      3) Connect via TCP, send request, play rounds
      4) Close TCP and return to listening again
    """
    try:
        while True:
            print_welcome_banner()         #  Welcome (safe addition)
            rounds = get_num_rounds()      # ask rounds
            ip, port = listen_for_offer()  # listen + select first matching offer
            play_session(ip, port, rounds) # play + close TCP
            # Immediately return to listening again (runs forever)
    except KeyboardInterrupt:
        print("\nClient terminated by user.")
        sys.exit(0)
