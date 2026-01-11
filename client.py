# client.py (Final Stage: ASCII cards, hidden dealer card, and stats)

import socket
from typing import List, Tuple

from constants import UDP_PORT, TEAM_NAME
from packet_utils import (
    parse_offer_packet,
    create_request_packet,
    create_client_payload,
    parse_server_payload,
    SERVER_PAYLOAD_SIZE,
)

Card = Tuple[int, int]  # (rank, suit)


# ==============================
# UDP Discovery
# ==============================

def find_server_offer(timeout_sec: int = 30):
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_sock.bind(("0.0.0.0", UDP_PORT))
    udp_sock.settimeout(timeout_sec)

    print(f"Client started, listening for offer requests on UDP port {UDP_PORT}...")

    while True:
        try:
            data, addr = udp_sock.recvfrom(2048)
            server_ip = addr[0]

            offer = parse_offer_packet(data)
            if offer is None:
                continue

            udp_sock.close()
            return server_ip, offer["port"], offer["server_name"]
        except socket.timeout:
            print("Discovery timed out. No server found.")
            return None, None, None


# ==============================
# TCP Helpers
# ==============================

def recv_exact(sock: socket.socket, n: int):
    data = b""
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
        except (ConnectionAbortedError, ConnectionResetError, OSError):
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
    if rank == 1: return 11
    if rank >= 11: return 10
    return rank


def hand_total(cards: List[Card]) -> int:
    return sum(card_value(r) for (r, _) in cards)


def print_score(player: List[Card], dealer: List[Card], reveal_dealer: bool):
    print(f"Your total: {hand_total(player)}")
    if reveal_dealer:
        print(f"Dealer total: {hand_total(dealer)}")
    else:
        print(f"Dealer shown total: {hand_total(dealer)}")


# ==============================
# Main Session
# ==============================

def play_session(server_ip: str, server_tcp_port: int, num_rounds: int):
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        tcp_sock.connect((server_ip, server_tcp_port))
    except Exception as e:
        print(f"Could not connect to server: {e}")
        return

    tcp_sock.sendall(create_request_packet(num_rounds, TEAM_NAME))
    print(f"Connected to {server_ip}:{server_tcp_port}\n")

    wins = losses = ties = 0

    for r in range(1, num_rounds + 1):
        print("\n" + "=" * 30)
        print(f"Round {r}")
        print("=" * 30)

        # Initial cards (3 payloads: 2 player, 1 dealer)
        initial_payloads = []
        for _ in range(3):
            b = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            if b is None: break
            initial_payloads.append(parse_server_payload(b))

        if len(initial_payloads) < 3 or any(p is None for p in initial_payloads):
            print("Disconnected while receiving initial cards.")
            break

        player_cards = [(initial_payloads[0]["rank"], initial_payloads[0]["suit"]),
                        (initial_payloads[1]["rank"], initial_payloads[1]["suit"])]
        dealer_cards = [(initial_payloads[2]["rank"], initial_payloads[2]["suit"])]

        print("\nYour hand:")
        print(cards_to_ascii_row(player_cards))
        print("\nDealer shows (1 hidden):")
        print(cards_to_ascii_row(dealer_cards, show_hidden=True))
        print_score(player_cards, dealer_cards, False)

        # Blackjack Check
        if hand_total(player_cards) == 21:
            print("\n🎉 Blackjack! Waiting for server confirmation...")
            final_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            if final_bytes:
                msg = parse_server_payload(final_bytes)
                if msg["result"] == 3:
                    wins += 1; print("Result: WIN")
                elif msg["result"] == 2:
                    losses += 1; print("Result: LOSS")
                else:
                    ties += 1; print("Result: TIE")
            continue

        round_over = False
        while not round_over:
            choice = input("\nType Hittt or Stand: ").strip()
            if choice not in ("Hittt", "Stand"): continue

            try:
                tcp_sock.sendall(create_client_payload(choice))
            except:
                print("\n⏱️ Connection lost - The dealer closed the table.")
                return

            resp_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            if resp_bytes is None:
                print("\n⏱️ Game Over! You stall, you fall 😉")
                return

            resp = parse_server_payload(resp_bytes)

            if choice == "Hittt":
                if resp["result"] == 0:
                    player_cards.append((resp["rank"], resp["suit"]))
                    print("\nYour hand:")
                    print(cards_to_ascii_row(player_cards))
                    print("\nDealer shows (1 hidden):")
                    print(cards_to_ascii_row(dealer_cards, show_hidden=True))
                    print_score(player_cards, dealer_cards, False)

                    if hand_total(player_cards) > 21:
                        print("You busted! Waiting for result...")
                        f_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                        if f_bytes: losses += 1; print("Result: LOSS")
                        round_over = True
                else:
                    if resp["result"] == 3:
                        wins += 1; print("Result: WIN")
                    elif resp["result"] == 2:
                        losses += 1; print("Result: LOSS")
                    else:
                        ties += 1; print("Result: TIE")
                    round_over = True

            elif choice == "Stand":
                print("\n--- Dealer turn ---")
                if resp["result"] == 0:
                    dealer_cards.append((resp["rank"], resp["suit"]))
                    print(cards_to_ascii_row(dealer_cards))
                    print_score(player_cards, dealer_cards, True)

                while True:
                    nxt_bytes = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                    if not nxt_bytes: break
                    nxt = parse_server_payload(nxt_bytes)
                    if nxt["result"] == 0:
                        dealer_cards.append((nxt["rank"], nxt["suit"]))
                        print(cards_to_ascii_row(dealer_cards))
                        print_score(player_cards, dealer_cards, True)
                    else:
                        if nxt["result"] == 3:
                            wins += 1; print("Result: WIN")
                        elif nxt["result"] == 2:
                            losses += 1; print("Result: LOSS")
                        else:
                            ties += 1; print("Result: TIE")
                        round_over = True
                        break

    print("\n" + "=" * 30)
    print(f"Session finished. Rounds: {wins + losses + ties} | Wins: {wins} | Losses: {losses} | Ties: {ties}")
    if (wins + losses + ties) > 0:
        print(f"Win rate: {wins / (wins + losses + ties) * 100:.1f}%")
    tcp_sock.close()


if __name__ == "__main__":
    ip, port, name = find_server_offer()
    if ip:
        print(f"Found server '{name}' at {ip}:{port}")
        play_session(ip, port, 3)