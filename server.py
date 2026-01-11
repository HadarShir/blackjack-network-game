# server.py (Stage 4: hardened - timeouts, disconnect handling, cleaner logs + blackjack on initial)

import socket
import threading
import time

from constants import (
    UDP_PORT, OFFER_BROADCAST_INTERVAL, SERVER_NAME,
    RESULT_GAME_NOT_OVER
)
from packet_utils import (
    create_offer_packet,
    parse_request_packet,
    parse_client_payload,
    create_server_payload,
    REQUEST_SIZE,
    CLIENT_PAYLOAD_SIZE,
)
from game_logic import BlackjackGame


CLIENT_SOCKET_TIMEOUT_SEC = 60
ACCEPT_BACKLOG = 50


def get_preferred_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "0.0.0.0"
    finally:
        s.close()
    return ip


def recv_exact(sock: socket.socket, n: int):
    data = b""
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
        except socket.timeout:
            return None
        except OSError:
            return None

        if not chunk:
            return None
        data += chunk
    return data


def safe_sendall(sock: socket.socket, data: bytes) -> bool:
    try:
        sock.sendall(data)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def find_free_tcp_port(bind_ip: str) -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((bind_ip, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def udp_broadcast_offers(bind_ip: str, server_tcp_port: int, stop_event: threading.Event):
    offer = create_offer_packet(server_tcp_port, SERVER_NAME)

    udp_bcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_bcast.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_bcast.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_bcast.bind((bind_ip, UDP_PORT))

    udp_local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_local.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_local.bind(("127.0.0.1", 0))

    print(f"[UDP] Broadcasting offers on {bind_ip}:{UDP_PORT} (TCP port {server_tcp_port})")
    print(f"[UDP] Local test offers -> 127.0.0.1:{UDP_PORT}")

    while not stop_event.is_set():
        try:
            udp_bcast.sendto(offer, ("255.255.255.255", UDP_PORT))
            udp_local.sendto(offer, ("127.0.0.1", UDP_PORT))
        except Exception as e:
            print(f"[UDP] Error: {e}")

        time.sleep(OFFER_BROADCAST_INTERVAL)

    udp_bcast.close()
    udp_local.close()


def run_single_round(client_sock: socket.socket, game: BlackjackGame) -> bool:
    """
    Round protocol:
      - Send 2 player cards + 1 visible dealer card with RESULT_GAME_NOT_OVER
      - If player hits -> send new card with NOT_OVER (repeat)
      - On stand -> send hidden dealer card, then dealer draws cards, all NOT_OVER
      - End: send final payload with result code + a valid card (last sent)
    Also: if player has 21 immediately after initial 2 cards, finish round immediately (no client input).
    """
    player_hand, dealer_hand = game.deal_initial_hands()
    last_sent_card = None

    def send_card(result_code: int, card) -> bool:
        nonlocal last_sent_card
        rank, suit = card
        ok = safe_sendall(client_sock, create_server_payload(result_code, rank, suit))
        if ok:
            last_sent_card = card
        return ok

    # Initial: send 2 player cards
    if not send_card(RESULT_GAME_NOT_OVER, player_hand[0]): return False
    if not send_card(RESULT_GAME_NOT_OVER, player_hand[1]): return False

    # Send dealer visible card
    visible = game.get_visible_card(dealer_hand)
    if not send_card(RESULT_GAME_NOT_OVER, visible): return False

    # ✅ NEW: immediate blackjack check (Ace=11 always per your spec)
    # If player total == 21 right away, end round immediately without waiting for input.
    if game.calculate_hand_value(player_hand) == 21:
        result_code = game.determine_result(player_hand, dealer_hand)
        if last_sent_card is None:
            last_sent_card = (1, 0)
        return safe_sendall(
            client_sock,
            create_server_payload(result_code, last_sent_card[0], last_sent_card[1])
        )

    # ----- Player turn -----
    while True:
        if game.is_bust(player_hand):
            break

        data = recv_exact(client_sock, CLIENT_PAYLOAD_SIZE)
        if data is None:
            return False

        payload = parse_client_payload(data)
        if payload is None:
            # invalid payload => treat like Stand
            break

        decision = payload["decision"]
        if decision == "Stand":
            break

        # Hittt
        new_card = game.player_hit(player_hand)
        if not send_card(RESULT_GAME_NOT_OVER, new_card):
            return False

    # ----- Dealer turn (only if player not bust) -----
    if not game.is_bust(player_hand):
        hidden = game.get_hidden_card(dealer_hand)
        if not send_card(RESULT_GAME_NOT_OVER, hidden): return False

        for c in game.play_dealer_turn(dealer_hand):
            if not send_card(RESULT_GAME_NOT_OVER, c):
                return False

    # ----- Final result -----
    result_code = game.determine_result(player_hand, dealer_hand)

    if last_sent_card is None:
        last_sent_card = (1, 0)

    return safe_sendall(
        client_sock,
        create_server_payload(result_code, last_sent_card[0], last_sent_card[1])
    )


def handle_client(client_sock: socket.socket, client_addr):
    print(f"[TCP] Client connected from {client_addr}")
    client_sock.settimeout(CLIENT_SOCKET_TIMEOUT_SEC)

    try:
        req_bytes = recv_exact(client_sock, REQUEST_SIZE)
        if req_bytes is None:
            print("[TCP] Client disconnected/timeout before sending request.")
            return

        req = parse_request_packet(req_bytes)
        if req is None:
            print("[TCP] Invalid request packet. Closing.")
            return

        team = req["team_name"]
        rounds = req["rounds"]
        print(f"[TCP] Request: team='{team}', rounds={rounds}")

        game = BlackjackGame()

        for i in range(rounds):
            print(f"[TCP] Round {i+1}/{rounds} for team='{team}'")
            ok = run_single_round(client_sock, game)
            if not ok:
                print(f"[TCP] Client disconnected/timeout during round {i+1}.")
                return

        print(f"[TCP] Session finished for team='{team}'.")

    except Exception as e:
        print(f"[TCP] Error for {client_addr}: {e}")

    finally:
        try:
            client_sock.close()
        except Exception:
            pass


def run_tcp_server(server_tcp_port: int):
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    tcp_sock.bind(("0.0.0.0", server_tcp_port))
    tcp_sock.listen(ACCEPT_BACKLOG)

    print(f"[TCP] Listening on 0.0.0.0:{server_tcp_port} (all interfaces)")

    while True:
        client_sock, client_addr = tcp_sock.accept()
        t = threading.Thread(target=handle_client, args=(client_sock, client_addr), daemon=True)
        t.start()


if __name__ == "__main__":
    bind_ip = get_preferred_ip()
    tcp_port = find_free_tcp_port(bind_ip)

    print(f"--- {SERVER_NAME} Started ---")
    print(f"IP Address: {bind_ip}")
    print(f"TCP Port:   {tcp_port}")

    stop_event = threading.Event()

    t_udp = threading.Thread(target=udp_broadcast_offers, args=(bind_ip, tcp_port, stop_event), daemon=True)
    t_udp.start()

    try:
        run_tcp_server(tcp_port)
    except KeyboardInterrupt:
        print("\nServer shutting down...")
        stop_event.set()
