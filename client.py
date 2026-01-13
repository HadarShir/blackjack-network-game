# client.py (Final)
# Runs forever:
#   Welcome -> get name -> discover offers -> play session (3 rounds) -> ask play again
# If user says "n": go idle (no auto-connect) and wait for explicit "y" to search again.
# Supports clean exit via Ctrl+C OR typing 'q' in prompts.

import socket
from typing import List, Tuple, Optional

from constants import UDP_PORT
from packet_utils import (
    parse_offer_packet,
    create_request_packet,
    create_client_payload,
    parse_server_payload,
    SERVER_PAYLOAD_SIZE,
)

Card = Tuple[int, int]  # (rank, suit)

DEFAULT_NUM_ROUNDS = 3

#FILTER_SERVER_NAME = "BeautyBlendersServer"   # <- לשים את השם שלך
FILTER_SERVER_NAME = None                   # <- לכבות פילטר
# ==============================
# UDP Discovery
# ==============================

def find_server_offer(timeout_sec: int = 30) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Listen for offer packets on UDP_PORT and return (server_ip, tcp_port, server_name).
    Returns (None, None, None) on timeout.
    """
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_sock.bind(("0.0.0.0", UDP_PORT))
    udp_sock.settimeout(timeout_sec)

    active_filter = FILTER_SERVER_NAME if (FILTER_SERVER_NAME and FILTER_SERVER_NAME.strip()) else None
    if active_filter:
        print(f"Client listening for offers on UDP {UDP_PORT} (timeout {timeout_sec}s)... "
              f"[filter='{active_filter}']")
    else:
        print(f"Client listening for offers on UDP {UDP_PORT} (timeout {timeout_sec}s)...")

    try:
        while True:
            data, addr = udp_sock.recvfrom(2048)
            server_ip = addr[0]

            offer = parse_offer_packet(data)
            if offer is None:
                continue

            server_name = offer["server_name"]
            server_port = offer["port"]

            # ✅ Only accept matching server if filter is enabled
            if active_filter and server_name != active_filter:
                continue

            return server_ip, server_port, server_name

    except socket.timeout:
        return None, None, None
    finally:
        udp_sock.close()


# ==============================
# TCP Helpers
# ==============================

def recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    """
    Read exactly n bytes from TCP socket.
    Return None on disconnect/timeout/error.
    """
    data = b""
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
        except (socket.timeout, ConnectionAbortedError, ConnectionResetError, OSError):
            return None

        if not chunk:
            return None

        data += chunk

    return data


# ==============================
# ASCII Card Rendering
# ==============================

def rank_to_face(rank: int) -> str:
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(rank, str(rank))


def suit_to_symbol(suit: int) -> str:
    return {0: "♥", 1: "♦", 2: "♣", 3: "♠"}.get(suit, "?")


def card_to_ascii(rank: int, suit: int) -> List[str]:
    r = rank_to_face(rank)
    s = suit_to_symbol(suit)
    left = r.ljust(2)
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


def cards_to_ascii_row(cards: List[Card], show_hidden: bool = False) -> str:
    if not cards:
        return ""
    rendered = [card_to_ascii(r, s) for (r, s) in cards]
    if show_hidden:
        rendered.append(hidden_card_ascii())
    return "\n".join("  ".join(card[i] for card in rendered) for i in range(5))


# ==============================
# Totals
# ==============================

def card_value(rank: int) -> int:
    # Assignment simplification: Ace ALWAYS 11
    if rank == 1:
        return 11
    if rank >= 11:
        return 10
    return rank


def hand_total(cards: List[Card]) -> int:
    return sum(card_value(r) for (r, _) in cards)


def print_score(player: List[Card], dealer_visible: List[Card], reveal_dealer: bool):
    print(f"Your total: {hand_total(player)}")
    if reveal_dealer:
        print(f"Dealer total: {hand_total(dealer_visible)}")
    else:
        print(f"Dealer shown total: {hand_total(dealer_visible)}")


# ==============================
# User Prompts
# ==============================

def welcome_and_get_name() -> str:
    print("\n🂡 Welcome to Blackjacky 🂡")
    print(f"Each session is {DEFAULT_NUM_ROUNDS} rounds.")
    print("Play smart: you can walk away with everything… or with nothing 😈\n")

    while True:
        try:
            name = input("Enter your team/player name (or 'q' to quit): ").strip()
        except KeyboardInterrupt:
            raise

        if name.lower() in ("q", "quit", "exit"):
            raise KeyboardInterrupt

        if not name:
            print("Name can't be empty 🙂")
            continue

        # Keep it protocol-friendly (wire limit)
        return name[:32]


def ask_play_again() -> str:
    """
    Returns: "again" / "idle" / "quit"
    """
    while True:
        try:
            ans = input("\nPlay again? (y/n/q): ").strip().lower()
        except KeyboardInterrupt:
            return "quit"

        if ans in ("y", "yes"):
            return "again"
        if ans in ("n", "no"):
            return "idle"
        if ans in ("q", "quit", "exit"):
            return "quit"
        print("Please type y, n, or q.")


def ask_search_when_idle() -> str:
    """
    Returns: "search" / "idle" / "quit"
    """
    while True:
        try:
            ans = input("Search for a new table now? (y/n/q): ").strip().lower()
        except KeyboardInterrupt:
            return "quit"

        if ans in ("y", "yes"):
            return "search"
        if ans in ("n", "no"):
            return "idle"
        if ans in ("q", "quit", "exit"):
            return "quit"
        print("Please type y, n, or q.")


def print_stall_message():
    print("\n⏱️ Game Over!")
    print("You stall, you fall. Blackjack waits for no one 😉")
    print("The dealer closed the table.\n")


# ==============================
# One TCP Session (True = normal end, False = disconnect/timeout)
# ==============================

def play_session(server_ip: str, server_tcp_port: int, num_rounds: int, team_name: str) -> bool:
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.settimeout(70)  # slightly above server timeout

    try:
        tcp_sock.connect((server_ip, server_tcp_port))
    except Exception as e:
        print(f"Could not connect to server: {e}")
        return False

    try:
        tcp_sock.sendall(create_request_packet(num_rounds, team_name))
        print(f"\nConnected to {server_ip}:{server_tcp_port} | team='{team_name}' | rounds={num_rounds}")

        wins = losses = ties = 0

        for r in range(1, num_rounds + 1):
            print("\n" + "=" * 30)
            print(f"Round {r}")
            print("=" * 30)

            # Initial cards: 2 player + 1 dealer visible
            b1 = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            b2 = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            b3 = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            if b1 is None or b2 is None or b3 is None:
                print_stall_message()
                return False

            p1 = parse_server_payload(b1)
            p2 = parse_server_payload(b2)
            d1 = parse_server_payload(b3)
            if p1 is None or p2 is None or d1 is None:
                print("Invalid payload received. Ending session.")
                return False

            player_cards: List[Card] = [(p1["rank"], p1["suit"]), (p2["rank"], p2["suit"])]
            dealer_cards: List[Card] = [(d1["rank"], d1["suit"])]

            print("\nYour hand:")
            print(cards_to_ascii_row(player_cards))
            print("\nDealer shows (1 hidden):")
            print(cards_to_ascii_row(dealer_cards, show_hidden=True))
            print_score(player_cards, dealer_cards, reveal_dealer=False)

            # Client-side UX: if 21, don't ask for input, but MUST read server final payload
            if hand_total(player_cards) == 21:
                print("\n🎉 Blackjack! Waiting for server confirmation...")
                final_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                if final_bytes is None:
                    print_stall_message()
                    return False

                msg = parse_server_payload(final_bytes)
                if msg is None:
                    print("Invalid final payload.")
                    return False

                if msg["result"] == 3:
                    wins += 1
                    print("Result: WIN")
                elif msg["result"] == 2:
                    losses += 1
                    print("Result: LOSS")
                else:
                    ties += 1
                    print("Result: TIE")
                continue

            # ----- Player loop -----
            round_over = False
            while not round_over:
                try:
                    choice = input("\nType Hittt or Stand (or 'q' to quit): ").strip()
                except KeyboardInterrupt:
                    raise

                if choice.lower() in ("q", "quit", "exit"):
                    raise KeyboardInterrupt

                if choice not in ("Hittt", "Stand"):
                    print("Please type exactly: Hittt or Stand")
                    continue

                # Send decision (server may have closed due to timeout)
                try:
                    tcp_sock.sendall(create_client_payload(choice))
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                    print_stall_message()
                    return False

                resp_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                if resp_bytes is None:
                    print_stall_message()
                    return False

                resp = parse_server_payload(resp_bytes)
                if resp is None:
                    print("Invalid server payload. Ending session.")
                    return False

                # -----------------
                # HITTT
                # -----------------
                if choice == "Hittt":
                    if resp["result"] == 0:
                        # got a new player card
                        player_cards.append((resp["rank"], resp["suit"]))
                        print("\nYour hand:")
                        print(cards_to_ascii_row(player_cards))
                        print("\nDealer shows (1 hidden):")
                        print(cards_to_ascii_row(dealer_cards, show_hidden=True))
                        print_score(player_cards, dealer_cards, reveal_dealer=False)

                        # bust? then server sends one more final payload
                        if hand_total(player_cards) > 21:
                            print("You busted! Waiting for result...")
                            final_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                            if final_bytes is None:
                                print_stall_message()
                                return False

                            final_msg = parse_server_payload(final_bytes)
                            if final_msg is None:
                                print("Invalid final payload.")
                                return False

                            if final_msg["result"] == 3:
                                wins += 1
                                print("Result: WIN")
                            elif final_msg["result"] == 2:
                                losses += 1
                                print("Result: LOSS")
                            else:
                                ties += 1
                                print("Result: TIE")

                            round_over = True
                            continue

                    else:
                        # rare: server ended immediately
                        if resp["result"] == 3:
                            wins += 1
                            print("Result: WIN")
                        elif resp["result"] == 2:
                            losses += 1
                            print("Result: LOSS")
                        else:
                            ties += 1
                            print("Result: TIE")
                        round_over = True
                        continue

                # -----------------
                # STAND
                # -----------------
                if choice == "Stand":
                    print("\n--- Dealer turn ---")

                    # first NOT_OVER after Stand is hidden dealer card
                    if resp["result"] == 0:
                        dealer_cards.append((resp["rank"], resp["suit"]))
                        print(cards_to_ascii_row(dealer_cards))
                        print_score(player_cards, dealer_cards, reveal_dealer=True)
                    else:
                        # very rare immediate end
                        if resp["result"] == 3:
                            wins += 1
                            print("Result: WIN")
                        elif resp["result"] == 2:
                            losses += 1
                            print("Result: LOSS")
                        else:
                            ties += 1
                            print("Result: TIE")
                        round_over = True
                        continue

                    # dealer draws until final result
                    while True:
                        nxt_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                        if nxt_bytes is None:
                            print_stall_message()
                            return False

                        nxt = parse_server_payload(nxt_bytes)
                        if nxt is None:
                            print("Invalid dealer payload.")
                            return False

                        if nxt["result"] == 0:
                            dealer_cards.append((nxt["rank"], nxt["suit"]))
                            print(cards_to_ascii_row(dealer_cards))
                            print_score(player_cards, dealer_cards, reveal_dealer=True)
                            continue

                        # final result
                        if nxt["result"] == 3:
                            wins += 1
                            print("Result: WIN")
                        elif nxt["result"] == 2:
                            losses += 1
                            print("Result: LOSS")
                        else:
                            ties += 1
                            print("Result: TIE")

                        round_over = True
                        break

        # Session summary
        total = wins + losses + ties
        print("\n" + "=" * 30)
        print(f"Session finished. Rounds: {total} | Wins: {wins} | Losses: {losses} | Ties: {ties}")
        if total > 0:
            print(f"Win rate: {wins / total * 100:.1f}%")
        print("=" * 30)

        return True

    finally:
        try:
            tcp_sock.close()
        except Exception:
            pass


# ==============================
# Main: run forever
# ==============================

if __name__ == "__main__":
    print("=== Blackjack Client (runs forever) ===")
    print("Press Ctrl+C to quit.\n")

    # If False: keep team name across disconnects as well.
    # If True: ask for name again after disconnect/timeout.
    RESET_NAME_ON_DISCONNECT = False

    team_name: Optional[str] = None  # ask on first play; reused if user says "y"

    try:
        while True:
            # Ask name if needed (first time, or user went idle)
            if team_name is None:
                team_name = welcome_and_get_name()

            ip, port, server_name = find_server_offer(timeout_sec=30)

            if ip is None:
                print("No offers right now. Still listening...\n")
                continue

            print(f"\nFound server '{server_name}' at {ip}:{port}")
            ok = play_session(ip, port, DEFAULT_NUM_ROUNDS, team_name)

            # If disconnected/timeout: do NOT auto-loop into playing again without asking
            if not ok:
                print("\n⚠️ The table closed unexpectedly.")
                if RESET_NAME_ON_DISCONNECT:
                    team_name = None

                action = ask_search_when_idle()
                if action == "quit":
                    break
                if action == "search":
                    print("\nAlright — looking for a new table...\n")
                    continue

                # action == "idle"
                team_name = None
                print("\nClient is idle (not auto-connecting). (y=search, q=quit)\n")

                while True:
                    action2 = ask_search_when_idle()
                    if action2 == "quit":
                        raise KeyboardInterrupt
                    if action2 == "search":
                        print("\nBack to the tables...\n")
                        break
                    print("Staying idle. (y=search, q=quit)\n")

                continue

            # Normal session end -> ask play again
            action = ask_play_again()
            if action == "quit":
                break
            if action == "again":
                print("\nAlright — looking for a new table...\n")
                # keep same team_name
                continue

            # action == "idle"
            team_name = None
            print("\nClient is idle (not auto-connecting). (y=search, q=quit)\n")

            while True:
                action2 = ask_search_when_idle()
                if action2 == "quit":
                    raise KeyboardInterrupt
                if action2 == "search":
                    print("\nBack to the tables...\n")
                    break
                print("Staying idle. (y=search, q=quit)\n")

    except KeyboardInterrupt:
        print("\nClient terminated by user.")
