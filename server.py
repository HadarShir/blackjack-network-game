# server.py
import socket
import threading
import time

from constants import (
    UDP_PORT, OFFER_BROADCAST_INTERVAL, SERVER_NAME,
    RESULT_GAME_NOT_OVER, RESULT_WIN, RESULT_LOSS, RESULT_TIE
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

# How long we allow an idle TCP client before giving up (robustness requirement)
CLIENT_SOCKET_TIMEOUT_SEC = 60

# Max pending TCP connections in the accept queue
ACCEPT_BACKLOG = 50

# =========================
# Small print helpers
# =========================
def suit_to_char(suit: int) -> str:
    # Spec: suit encoded 0-3 (HDCS). We keep it consistent with your client.
    return {0: "♥", 1: "♦", 2: "♣", 3: "♠"}.get(suit, "?")


def rank_to_face(rank: int) -> str:
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(rank, str(rank))


def card_to_str(card) -> str:
    r, s = card
    return f"{rank_to_face(r)}{suit_to_char(s)}"


def result_to_text(code: int) -> str:
    if code == RESULT_WIN:
        return "WIN"
    if code == RESULT_LOSS:
        return "LOSS"
    if code == RESULT_TIE:
        return "TIE"
    return "NOT_OVER"


def get_preferred_ip() -> str:
    """
    Returns the IP address the OS would use to reach the internet.
    On university networks / hotspots, a machine may have multiple interfaces (WiFi, Ethernet, VPN).
    This trick asks the OS which local interface it would choose for an "internet route".
    We use it only for the required 'Server started...' print (informational)..
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP "connect" does not send packets; it just lets the OS pick a route/interface.
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        # Fallback: 0.0.0.0 means "unspecified / all interfaces"
        return "0.0.0.0"
    finally:
        s.close()


def find_free_tcp_port() -> int:
    """
    Bind to TCP port 0 => the OS chooses a free ephemeral port.
    The server does NOT need to listen on a specific fixed TCP port,
    because the chosen port is included in the UDP offer packet.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Bind to 0.0.0.0 => listen on ALL local interfaces (WiFi/hotspot/ethernet).
    # This reduces connectivity issues when the active interface changes.
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def recv_exact(sock: socket.socket, n: int):
    """
    Read exactly n bytes from a TCP socket.

    Why needed?
    TCP is a *byte stream* (no message boundaries). A single recv() may return
    fewer bytes than requested, even if the sender sent everything at once.
    Our protocol uses fixed-size binary messages (REQUEST_SIZE, PAYLOAD_SIZE),
    so we must keep reading until we collect exactly n bytes.

    Returns:
        bytes of length n on success, or None on timeout/disconnect/error.
    """
    data = b""
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
        except socket.timeout:
            return None, "timeout"
        except OSError:
            return None, "socket error"
        if not chunk:
            return None, "client closed connection"
        data += chunk
    return data, None


def safe_sendall(sock: socket.socket, data: bytes) -> bool:
    """
    Wrapper around sendall() that returns False if the send fails.
    Helps error clients may disconnect mid-game.
    We don't want the server to crash; we detect failures and stop the session gracefully.
    """
    try:
        sock.sendall(data)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def udp_broadcast_offers(server_tcp_port: int, stop_event: threading.Event):
    """
    Broadcast UDP 'offer' packets once every second.

    Assignment requirements:
    - Server sends offers via UDP broadcast once per second.
    - Offer packet format: cookie(4) + type(1=0x2) + tcp_port(2) + server_name(32)
    - Clients listen on UDP port 13122 (hardcoded).
        Notes:
    - This is NOT busy-waiting because we sleep (time.sleep) between broadcasts.
    """
    offer = create_offer_packet(server_tcp_port, SERVER_NAME)

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Bind to 0.0.0.0 => all interfaces (important in multi-interface environments).
    # Port must be UDP_PORT (13122) per assignment.
    udp_sock.bind(("0.0.0.0", UDP_PORT))

    while not stop_event.is_set():
        try:
            # Broadcast to all hosts on the LAN
            udp_sock.sendto(offer, ("255.255.255.255", UDP_PORT))
        except Exception:
            # We keep running even if one send fails (robustness requirement)
            pass
        time.sleep(OFFER_BROADCAST_INTERVAL)

    udp_sock.close()


def run_single_round(client_sock: socket.socket, game: BlackjackGame):
    """
    Runs one blackjack round for a single client connection.

    Round flow (assignment):
    1) Initial deal:
       - Send 2 player cards (face-up)
       - Send 1 dealer visible card (dealer's 2nd card stays hidden)
    2) Player turn:
       - Receive payload decisions: "Hittt" or "Stand"
       - On Hittt: send a new player card
       - If player busts (>21): round ends immediately
    3) Dealer turn (only if player did NOT bust):
       - Reveal hidden dealer card
       - Dealer hits until total >= 17, sending each new card
    4) Send final result: win/loss/tie (payload contains result + rank/suit fields)

    Returns:
        (ok: bool, reason: Optional[str])
        reason is only set when ok=False.
    """
    player_hand, dealer_hand = game.deal_initial_hands()
    last_card = player_hand[0]  # fallback values for final payload's rank/suit fields

    def send_card(result_code: int, card):
        nonlocal last_card
        last_card = card
        rank, suit = card
        if not safe_sendall(client_sock, create_server_payload(result_code, rank, suit)):
            return False, "send failed"
        return True, None

    if VERBOSE:
        p_total = game.calculate_hand_value(player_hand)
        d_visible = dealer_hand[0]
        print(f"  [Deal] Player: {card_to_str(player_hand[0])}, {card_to_str(player_hand[1])}  (total={p_total})")
        print(f"  [Deal] Dealer shows: {card_to_str(d_visible)}  (1 hidden)")

    # Initial deal: 2 player + 1 dealer visible
    ok, reason = send_card(RESULT_GAME_NOT_OVER, player_hand[0])
    if not ok:
        return False, reason

    ok, reason = send_card(RESULT_GAME_NOT_OVER, player_hand[1])
    if not ok:
        return False, reason

    visible = game.get_visible_card(dealer_hand)
    ok, reason = send_card(RESULT_GAME_NOT_OVER, visible)
    if not ok:
        return False, reason

    # Player turn
    # client -> server decisions until Stand OR server ends round on Bust

    if VERBOSE:
        print("  [Player Turn] Waiting for client decisions...")
    while True:
        data, r = recv_exact(client_sock, CLIENT_PAYLOAD_SIZE)
        if data is None:
            return False, r

        payload = parse_client_payload(data)
        if payload is None:
            # invalid => treat as Stand (robust fallback)
            if VERBOSE:
                print("    Invalid decision payload -> treating as Stand")
            decision = "Stand"
        else:
            decision = payload["decision"]

        if decision == "Stand":
            if VERBOSE:
                print(f"    Player stands (total={game.calculate_hand_value(player_hand)})")
            break

        # decision == "Hittt"
        new_card = game.player_hit(player_hand)
        new_total = game.calculate_hand_value(player_hand)

        if VERBOSE:
            print(f"    Player hits -> drew {card_to_str(new_card)}  (total={new_total})")

        # ✅ Option 2: If bust, end round immediately in THIS payload:
        if new_total > 21:
            ok, reason = send_card(RESULT_LOSS, new_card)  # immediate final result
            if not ok:
                return False, reason

            if VERBOSE:
                print("  [Stage] Result")
                print(f"    Outcome: LOSS (player bust)  (Player={new_total})")

            return True, None  # round ended; DO NOT send extra final payload later

        # otherwise keep going, send the card as NOT_OVER
        ok, reason = send_card(RESULT_GAME_NOT_OVER, new_card)
        if not ok:
            return False, reason


    # -------------------------
    # Stage: Dealer turn (only if player did not bust)
    # server reveals hidden, hits until >=17
    # -------------------------
    if VERBOSE:
        print("  [Dealer Turn] Reveal hidden + hits until >= 17")

    hidden = dealer_hand[1]
    ok, reason = send_card(RESULT_GAME_NOT_OVER, hidden)
    if not ok:
        return False, reason

    if VERBOSE:
        print(f"    Reveal hidden card: {card_to_str(hidden)}  (dealer_total={game.calculate_hand_value(dealer_hand)})")

    for c in game.play_dealer_turn(dealer_hand):
        ok, reason = send_card(RESULT_GAME_NOT_OVER, c)
        if not ok:
            return False, reason
        if VERBOSE:
            print(f"    Dealer hits -> drew {card_to_str(c)}  (dealer_total={game.calculate_hand_value(dealer_hand)})")

    if VERBOSE:
        print(f"    Dealer stands (final dealer_total={game.calculate_hand_value(dealer_hand)})")

    # Final result (must send a full payload including rank/suit fields)
    result_code = game.determine_result(player_hand, dealer_hand)
    if VERBOSE:
        print("  [Stage] Result")
        print(f"    Outcome: {result_to_text(result_code)}  (Player={game.calculate_hand_value(player_hand)} vs Dealer={game.calculate_hand_value(dealer_hand)})")

    if not safe_sendall(client_sock, create_server_payload(result_code, last_card[0], last_card[1])):
        return False, "send failed "

    return True, None


def handle_client(client_sock: socket.socket, client_addr):
    """
    Handle a single TCP client connection (one client session).

    Flow:
    1) Read REQUEST packet (fixed size) to get rounds + client team name.
    2) Run that many rounds using the blackjack game logic.
    """

    client_sock.settimeout(CLIENT_SOCKET_TIMEOUT_SEC)

    try:
        req_bytes, r = recv_exact(client_sock, REQUEST_SIZE)
        if req_bytes is None:
            if VERBOSE:
                print(f"Client disconnected before request (reason: {r})")
            return

        req = parse_request_packet(req_bytes)
        if req is None:
            if VERBOSE:
                print("Invalid request packet. Closing connection.")
            return

        team = req["team_name"]      # ✅ correct key
        rounds = req["rounds"]

        if VERBOSE:
            print(f"Received request from team '{team}'. Starting {rounds} rounds of Blackjack.")

        game = BlackjackGame()

        for i in range(1, rounds + 1):
            if VERBOSE:
                print(f"Start round {i}/{rounds} for team {team}")

            ok, reason = run_single_round(client_sock, game)
            if not ok:
                if VERBOSE:
                    print(f"Client {team} disconnected (reason: {reason})")
                return

        if VERBOSE:
            print(f"Team {team} finished all rounds.")

    finally:
        try:
            client_sock.close()
        except Exception:
            pass


def run_tcp_server(server_tcp_port: int):
    """
    TCP accept loop: runs forever and spawns a dedicated thread per client.

    This design allows multiple clients to play concurrently.
    accept() is blocking => no busy-wait.
    """
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Bind to 0.0.0.0 => listen on all local interfaces (important in multi-interface networks).
    tcp_sock.bind(("0.0.0.0", server_tcp_port))
    tcp_sock.listen(ACCEPT_BACKLOG)

    while True:
        client_sock, client_addr = tcp_sock.accept()  # blocking (no busy-wait)
        t = threading.Thread(target=handle_client, args=(client_sock, client_addr), daemon=True)
        t.start()


if __name__ == "__main__":
    ip = get_preferred_ip()
    tcp_port = find_free_tcp_port()
    # Required print
    print(f"Server started, listening on IP address {ip}")

    stop_event = threading.Event()
    t_udp = threading.Thread(target=udp_broadcast_offers, args=(tcp_port, stop_event), daemon=True)
    t_udp.start()

    try:
        run_tcp_server(tcp_port)
    except KeyboardInterrupt:
        stop_event.set()
        print("\nServer terminated by user.")
