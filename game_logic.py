# game_logic.py
import random
from typing import List, Tuple, Optional

from constants import CARD_VALUES, RESULT_WIN, RESULT_LOSS, RESULT_TIE

# Type aliases for better readability
Card = Tuple[int, int]          # (rank: 1..13, suit: 0..3)
Hand = List[Card]


class BlackjackGame:
    """
    Pure game logic for a single Blackjack round.
    This class handles deck management, hand evaluation, and dealer rules.
    It remains independent of networking code for easier testing.
    """

    def __init__(self):
        self.deck: List[Card] = []
        self.reset_deck()

    # ==============================
    # Deck Management
    # ==============================

    def reset_deck(self) -> None:
        """
        Creates a fresh 52-card deck and shuffles it.
        Ranks: 1 (Ace) to 13 (King).
        Suits: 0 (Heart), 1 (Diamond), 2 (Club), 3 (Spade).
        """
        self.deck = [(rank, suit) for rank in range(1, 14) for suit in range(4)]
        random.shuffle(self.deck)

    def draw_card(self) -> Card:
        """
        Draws the top card from the deck.
        If the deck is empty, automatically replenishes and shuffles it.
        """
        if not self.deck:
            self.reset_deck()
        return self.deck.pop()

    # ==============================
    # Hand Evaluation Logic
    # ==============================

    @staticmethod
    def calculate_hand_value(hand: Hand) -> int:
        """
        Calculates the total value of a blackjack hand.
        Uses CARD_VALUES for standard ranks.
        Handles Aces dynamically: Starts as 11, but converts to 1 if the total exceeds 21.
        """
        total = 0
        for rank, _ in hand:
            total += CARD_VALUES.get(rank, 0)

        return total

    @classmethod
    def is_bust(cls, hand: Hand) -> bool:
        """Checks if the provided hand is over 21."""
        return cls.calculate_hand_value(hand) > 21

    @classmethod
    def dealer_should_hit(cls, dealer_hand: Hand) -> bool:
        """
        Standard Blackjack dealer rule:
        Hit on any total less than 17, Stand on 17 or more.
        """
        return cls.calculate_hand_value(dealer_hand) < 17

    # ==============================
    # Game Flow Helpers
    # ==============================

    def deal_initial_hands(self) -> Tuple[Hand, Hand]:
        """
        Deals 2 cards each to the player and the dealer.
        Returns: (player_hand, dealer_hand)
        """
        player_hand = [self.draw_card(), self.draw_card()]
        dealer_hand = [self.draw_card(), self.draw_card()]
        return player_hand, dealer_hand

    def player_hit(self, player_hand: Hand) -> Card:
        """
        Give one card to the player (Hit).
        Returns the new card that was drawn.
        """
        card = self.draw_card()
        player_hand.append(card)
        return card

    def play_dealer_turn(self, dealer_hand: Hand) -> List[Card]:
        """
        Executes the dealer's logic until they stand or bust.
        Returns: A list of ONLY the new cards drawn during this turn (in order).
        """
        new_cards: List[Card] = []
        while self.dealer_should_hit(dealer_hand):
            card = self.draw_card()
            dealer_hand.append(card)
            new_cards.append(card)
        return new_cards

    @classmethod
    def determine_result(cls, player_hand: Hand, dealer_hand: Hand) -> int:
        """
        Compares the final hands and returns the result code from constants.
        Returns: RESULT_WIN (0x3), RESULT_LOSS (0x2), or RESULT_TIE (0x1).
        """
        player_score = cls.calculate_hand_value(player_hand)
        dealer_score = cls.calculate_hand_value(dealer_hand)

        # Player bust
        if player_score > 21:
            return RESULT_LOSS

        # Dealer bust
        if dealer_score > 21:
            return RESULT_WIN

        # Compare scores
        if player_score > dealer_score:
            return RESULT_WIN
        if dealer_score > player_score:
            return RESULT_LOSS
        return RESULT_TIE

    # ==============================
    # Protocol Visibility Helpers
    # ==============================

    @staticmethod
    def get_visible_card(dealer_hand: Hand) -> Optional[Card]:
        """Returns the first dealer card (visible to client during player's turn)."""
        return dealer_hand[0] if dealer_hand else None

    @staticmethod
    def get_hidden_card(dealer_hand: Hand) -> Optional[Card]:
        """Returns the second dealer card (hidden until dealer's turn)."""
        return dealer_hand[1] if len(dealer_hand) >= 2 else None
