
# 🃏 Blackjacky – Client / Server Blackjack Game

**Blackjacky** is a network-based Blackjack game implemented as a **client–server application**.
The project demonstrates practical use of **UDP broadcasting** for server discovery and **TCP communication** for reliable game sessions, following the assignment protocol exactly.

The server acts as the **dealer**, while clients automatically discover available servers, connect, and play a fixed number of Blackjack rounds.

---

## 🚀 Features

* 🔊 **UDP Broadcast Offers** – servers advertise themselves once per second
* 🔗 **TCP Game Session** – reliable communication for the entire game
* 🃏 **Classic Blackjack Logic**
* 📊 **Client Statistics** – win count and win rate at the end
* 🧵 Designed for **multiple clients** (thread-based handling)

---

## 🧩 Project Structure

```
Blackjacky/
│
├── server.py        # Blackjack server (dealer logic, UDP offers, TCP handling)
├── client.py        # Blackjack client (listens for offers, plays the game)
├── protocol.py      # Protocol constants and packet structures
├── utils.py         # Helper functions (cards, printing, networking helpers)
└── README.md        # Project documentation
```

> File names may vary slightly depending on implementation, but the logic is split
> between **server**, **client**, and **protocol/utilities**.

---

## 📡 Network Protocol

### UDP – Server Offer

* Server broadcasts an **offer packet** once per second.
* The packet contains:

  * Magic cookie
  * Message type (Offer)
  * Server UDP port
  * Server TCP port

Clients listen for offers and connect to the **first server received**.

---

### TCP – Game Session

1. Client connects to the server’s TCP port
2. Client sends:

   ```
   <number_of_rounds>\n
   ```
3. Server starts the Blackjack game loop
4. All game interaction happens over the same TCP connection

---

## 🃏 Game Rules

* Standard **52-card deck**
* Card values:

  * 2–10 → numeric value
  * J, Q, K → 10
  * Ace → 11 (no soft Ace)
* No betting
* No splitting
* No Blackjack bonus

---

## 🔄 Game Flow

For each round:

1. Server deals:

   * 2 cards to the player (face up)
   * 2 cards to the dealer (1 hidden)
2. Player turn:

   * Chooses **Hit** or **Stand**
   * Bust if total > 21
3. Dealer turn:

   * Reveals hidden card
   * Hits until total ≥ 17
4. Winner is decided:

   * Player win
   * Dealer win
   * Tie
5. Result is sent to the client

After all rounds:

* Client prints final statistics:

  ```
  Finished playing X rounds, win rate: Y%
  ```

---

## ▶️ How to Run

### Start the Server

```bash
python server.py
```

### Start the Client

```bash
python client.py
```

The client will:

1. Listen for UDP offers
2. Connect to a server automatically
3. Ask for number of rounds
4. Play the game

---

## 🧪 Tested Scenarios

* Multiple consecutive game sessions
* Client reconnecting after game ends
* Stable communication over TCP
* Proper handling of player bust and dealer logic

---

## 📚 Educational Goals

This project was built to practice:

* UDP vs TCP communication
* Client–server architecture
* Custom application-level protocol
* Threaded server design
* Clean separation of game logic and networking logic

---

## 🏁 Summary

**Blackjacky** combines classic Blackjack rules with real networking concepts, providing a hands-on example of how discovery protocols and reliable connections work together in distributed systems.

♠️ Happy coding and good luck at the table! ♠️


