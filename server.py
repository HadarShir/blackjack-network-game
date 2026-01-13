# server.py
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

# Toggle extra prints for your own debugging
VERBOSE = True

CLIENT_SOCKET_TIMEOUT_SEC = 60
ACCEPT_BACKLOG = 50


def get_preferred_ip() -> str:
    """
    Returns the IP address the OS would use to reach the internet.
    This helps in university networks where multiple interfaces exist.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"
    finally:
        s.close()


def find_free_tcp_port() -> int:
    """
    Bind to port 0 => OS chooses a free ephemeral port.
    Then we advertise that port in the UDP offers.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def recv_exact(sock: socket.socket, n: int):
    """
    Read exactly n bytes from TCP socket.
    Returns None on timeout or disconnect.
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


def safe_sendall(sock: socket.socket, data: bytes) -> bool:
    """
    sendall wrapper that returns False if send fails.
    Helps error handling when clients disconnect mid-game.
    """
    try:
        sock.sendall(data)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def udp_broadcast_offers(server_tcp_port: int, stop_event: threading.Event):
    """
    Broadcast UDP offers once per second.
    This is NOT busy-waiting because we sleep between sends.
    """
    offer = create_offer_packet(server_tcp_port, SERVER_NAME)

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.bind(("0.0.0.0", UDP_PORT))

    while not stop_event.is_set():
        try:
            udp_sock.sendto(offer, ("255.255.255.255", UDP_PORT))
        except Exception:
            # We keep running even if one send fails (robustness requirement)
            pass
        time.sleep(OFFER_BROADCAST_INTERVAL)

    udp_sock.close()


def run_single_round(client_sock: socket.socket, game: BlackjackGame) -> bool:
    """
    Runs one blackjack round for a single client connection.
    Sends:
      - 2 player cards (NOT_OVER)
      - 1 dealer visible card (NOT_OVER)
      - then receives client decisions, sends cards/results
    Returns False on disconnect or send failure.
    """
    player_hand, dealer_hand = game.deal_initial_hands()
    last_card = player_hand[0]  # fallback card for final message fields

    def send_card(result_code: int, card) -> bool:
        nonlocal last_card
        last_card = card
        rank, suit = card
        return safe_sendall(client_sock, create_server_payload(result_code, rank, suit))

    # Initial dealing: 2 to player, 1 visible dealer
    if not send_card(RESULT_GAME_NOT_OVER, player_hand[0]): return False
    if not send_card(RESULT_GAME_NOT_OVER, player_hand[1]): return False

    visible = game.get_visible_card(dealer_hand)
    if not send_card(RESULT_GAME_NOT_OVER, visible): return False

    # Player turn
    while True:
        if game.is_bust(player_hand):
            break

        data = recv_exact(client_sock, CLIENT_PAYLOAD_SIZE)
        if data is None:
            return False

        payload = parse_client_payload(data)
        if payload is None:
            # Invalid payload => treat as Stand (simple robust behavior)
            break

        if payload["decision"] == "Stand":
            break

        # Hittt
        new_card = game.player_hit(player_hand)
        if not send_card(RESULT_GAME_NOT_OVER, new_card):
            return False

    # Dealer turn (only if player not bust)
    if not game.is_bust(player_hand):
        hidden = game.get_hidden_card(dealer_hand)
        if not send_card(RESULT_GAME_NOT_OVER, hidden): return False

        for c in game.play_dealer_turn(dealer_hand):
            if not send_card(RESULT_GAME_NOT_OVER, c): return False

    # Final result
    result_code = game.determine_result(player_hand, dealer_hand)
    # Must send a full payload including rank/suit fields (any valid values).
    return safe_sendall(client_sock, create_server_payload(result_code, last_card[0], last_card[1]))


def handle_client(client_sock: socket.socket, client_addr):
    """
    Handles a single TCP client connection.
    """
    client_sock.settimeout(CLIENT_SOCKET_TIMEOUT_SEC)

    try:
        req_bytes = recv_exact(client_sock, REQUEST_SIZE)
        if req_bytes is None:
            return

        req = parse_request_packet(req_bytes)
        if req is None:
            return

        team = req["team_name"]      # ✅ correct key
        rounds = req["rounds"]

        if VERBOSE:
            print(f"Received request from team '{team}'. Starting {rounds} rounds of Blackjack.")

        game = BlackjackGame()
        for _ in range(rounds):
            ok = run_single_round(client_sock, game)
            if not ok:
                return

    finally:
        try:
            client_sock.close()
        except Exception:
            pass


def run_tcp_server(server_tcp_port: int):
    """
    TCP server loop: accept clients forever, spawn a thread for each.
    """
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_sock.bind(("0.0.0.0", server_tcp_port))
    tcp_sock.listen(ACCEPT_BACKLOG)

    while True:
        client_sock, client_addr = tcp_sock.accept()  # blocking (no busy-wait)
        t = threading.Thread(target=handle_client, args=(client_sock, client_addr), daemon=True)
        t.start()


if __name__ == "__main__":
    ip = get_preferred_ip()
    tcp_port = find_free_tcp_port()

    print(f"Server started, listening on IP address {ip}")

    stop_event = threading.Event()
    t_udp = threading.Thread(target=udp_broadcast_offers, args=(tcp_port, stop_event), daemon=True)
    t_udp.start()

    try:
        run_tcp_server(tcp_port)
    except KeyboardInterrupt:
        stop_event.set()
        print("\nServer terminated by user.")
