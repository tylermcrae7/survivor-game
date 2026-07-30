"""
Survivor Game Rules Engine

This module centralizes all game rule logic, card management, and validation
for the Survivor app, providing a clean separation of concerns between
game mechanics and server infrastructure.
"""

import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# Tribal Phase State Machine
class TribalPhase(Enum):
	"""Enum for tribal council phases with strict ordering and transitions."""
	ANNOUNCEMENT = "announcement"
	ADVANTAGE_PLAY = "advantage_play"
	DISCUSSION = "discussion"
	VOTING = "voting"
	IMMUNITY = "immunity"
	REVEAL = "reveal"
	
# Valid transitions for tribal phases
TRIBAL_PHASE_TRANSITIONS = {
    TribalPhase.ANNOUNCEMENT: [TribalPhase.ADVANTAGE_PLAY, TribalPhase.DISCUSSION],
    TribalPhase.ADVANTAGE_PLAY: [TribalPhase.DISCUSSION],
    TribalPhase.DISCUSSION: [TribalPhase.IMMUNITY, TribalPhase.VOTING],
    TribalPhase.IMMUNITY: [TribalPhase.VOTING, TribalPhase.REVEAL],  # Allow going to reveal from immunity
    TribalPhase.VOTING: [TribalPhase.IMMUNITY, TribalPhase.REVEAL],  # Allow going back to immunity
    TribalPhase.REVEAL: []  # Final phase
}

# Game Constants
VALID_PHASES = [
    "lobby", "playing", "tribal_council", "final", "finished"
]

VALID_TURN_PHASES = [
    "turn_steal", "turn_play", "turn_draw", "waiting",
    "tribal_discussion", "tribal_advantage_play", "tribal_voting",
    "tribal_immunity", "tribal_reveal", "reactive_theft"
]

VALID_CATEGORIES = [
    "vote", "tribal_advantage", "action", "tribal_council", "challenge"
]

# ───────────────────────── Deck composition (F7) ─────────────────────────
# The official box contains 67 Action Cards. These 7 are house/homebrew extras
# that ship in survivor_cards.json but are NOT in the official Survival Guide.
# They are included only in "extended" deck mode.
NON_OFFICIAL_CARD_TYPES = {
    "idol_nullifier",   # x2
    "steal_vote",       # x2
    "block_vote",       # x2
    "grant_immunity",   # x1
}

# Card types that count as a vote when placed in the Voting Box (F2).
# Per the Survival Guide: Vote Cards MUST be used at the tribal where you hold
# them; Goodwill Gamble counts as 1 vote and MUST be used at the tribal where it
# was played; Extra Vote MAY be used (or saved for later).
MANDATORY_VOTE_CARD_TYPES = ("vote", "goodwill_gamble")
OPTIONAL_VOTE_CARD_TYPES = ("extra_vote",)
VOTE_CARD_TYPES = MANDATORY_VOTE_CARD_TYPES + OPTIONAL_VOTE_CARD_TYPES

# Let's Go To Rocks expansion — the 5 Orange Challenge Cards (Phase 4).
CHALLENGE_CARD_TYPES = (
    "challenge_lowest_score_loses",
    "challenge_1_now_or_2_later",
    "challenge_highest_bidder",
    "challenge_pull_or_steal",
    "challenge_hide_n_seek",
)

# Card validation constants
REQUIRED_CARD_FIELDS = [
    "type", "category", "name", "description", "playable_phases",
    "requires_target", "requires_multiple_targets", "requires_confirmation",
    "reactive_only", "count"
]


class SurvivorRulesEngine:
	"""
	Consolidated rules engine for Survivor game mechanics.
	
	Responsibilities:
	- Load and validate card registry
	- Dispatch card effects
	- Construct game decks
	- Validate game phases and card playability
	- Enforce all game rules
	"""
	
	def __init__(self, cards_file: str = "survivor_cards.json"):
		"""Initialize the rules engine with card definitions."""
		self.card_definitions = None
		self.card_effects_registry = {}
		self._load_card_definitions(cards_file)
		self._setup_effect_registry()
		
	def _load_card_definitions(self, cards_file: str) -> None:
		"""Load and validate card definitions from JSON file."""
		try:
			cards_path = Path(__file__).parent / cards_file
			with open(cards_path, 'r') as f:
				self.card_definitions = json.load(f)
				
			self._validate_card_definitions()
			logger.info(f"Loaded {len(self.card_definitions['cards'])} card types from {cards_file}")
			
		except FileNotFoundError:
			logger.error(f"{cards_file} not found - using fallback card definitions")
			self.card_definitions = self._get_fallback_cards()
		except json.JSONDecodeError as e:
			logger.error(f"Invalid JSON in {cards_file}: {e} - using fallback")
			self.card_definitions = self._get_fallback_cards()
		except ValueError as e:
			logger.error(f"Card validation failed: {e} - using fallback")
			self.card_definitions = self._get_fallback_cards()
		except Exception as e:
			logger.error(f"Error loading card definitions: {e} - using fallback")
			self.card_definitions = self._get_fallback_cards()
			
	def _validate_card_definitions(self) -> None:
		"""Validate that card definitions have required structure and content."""
		if 'cards' not in self.card_definitions:
			raise ValueError("Missing 'cards' section in card definitions")
			
		if 'validation' not in self.card_definitions:
			raise ValueError("Missing 'validation' section in card definitions")
			
		expected_total = self.card_definitions['validation']['total_expected_cards']
		required_fields = self.card_definitions['validation']['required_fields']
		
		# Count total cards and validate structure
		actual_total = 0
		for card_type, card_data in self.card_definitions['cards'].items():
			# Validate required fields exist
			for field in required_fields:
				if field not in card_data:
					raise ValueError(f"Card '{card_type}' missing required field '{field}'")
					
			# Validate field types and values
			if not isinstance(card_data.get('playable_phases'), list):
				raise ValueError(f"Card '{card_type}' playable_phases must be a list")
				
			if card_data.get('category') not in VALID_CATEGORIES:
				raise ValueError(f"Card '{card_type}' has invalid category: {card_data.get('category')}")
				
			actual_total += card_data.get('count', 0)
			
		if actual_total != expected_total:
			raise ValueError(f"Total cards mismatch: expected {expected_total}, got {actual_total}")
			
	def _get_fallback_cards(self) -> Dict[str, Any]:
		"""Return minimal fallback card definitions if JSON loading fails."""
		return {
		"metadata": {"version": "1.0", "total_cards": 0},
		"cards": {},
		"categories": {},
		"validation": {"total_expected_cards": 0, "required_fields": REQUIRED_CARD_FIELDS}
		}
		
	def get_card_definition(self, card_type: str) -> Optional[Dict[str, Any]]:
		"""Get the definition for a specific card type."""
		return self.card_definitions.get('cards', {}).get(card_type)
		
	def get_all_card_definitions(self) -> Dict[str, Any]:
		"""Get all card definitions."""
		return self.card_definitions.get('cards', {})
		
	def resolve_card(self, compact_card: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Resolve a compact card representation into a full card with metadata.
		
		Args:
		compact_card: Dict with at least 'type' field, may contain dynamic params
		
		Returns:
		Full card dictionary with metadata from survivor_cards.json
		"""
		card_type = compact_card.get('type')
		if not card_type:
			return compact_card  # Return as-is if no type
			
		card_definition = self.get_card_definition(card_type)
		if not card_definition:
			logger.warning(f"Unknown card type: {card_type}")
			return compact_card  # Return as-is if unknown type
			
		# Create full card by merging definition with any dynamic params
		resolved_card = {
		"type": card_definition["type"],
		"category": card_definition["category"],
		"name": card_definition["name"],
		"description": card_definition["description"],
		"playable_phases": card_definition["playable_phases"],
		"requires_target": card_definition["requires_target"],
		"requires_multiple_targets": card_definition["requires_multiple_targets"],
		"requires_confirmation": card_definition["requires_confirmation"],
		"reactive_only": card_definition["reactive_only"]
		}
		
		# Merge in any dynamic parameters from the compact card
		for key, value in compact_card.items():
			if key != 'type':  # Don't overwrite the type from definition
				resolved_card[key] = value
				
		return resolved_card
		
	def resolve_cards(self, compact_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
		"""Resolve a list of compact cards into full cards with metadata."""
		return [self.resolve_card(card) for card in compact_cards]
		
	def create_deck(self, player_count: int = 4, deck_mode: str = "official",
	                expansion: bool = False) -> List[Dict[str, Any]]:
		"""
		Create a complete game deck with action cards and tribal council cards.

		Official Setup (rules step 2): gather all 67 Action Cards and remove the
		9 Tribal Council and 6 Vote Cards. Each player is given 1 Vote Card and
		the extras are put away — so **no Vote Cards remain in the Draw Pile**.
		Tribal Council Cards are shuffled back in at step 5.

		Args:
		player_count: Number of players in the game
		deck_mode: "official" (67-card box) or "extended" (adds the 7 house cards)
		expansion: True to add the 5 Orange Challenge Cards from
		           Survivor: Let's Go To Rocks (combined mode)

		Returns:
		List of card dictionaries representing the shuffled deck
		"""
		deck = []
		total_action_cards = 0
		official_only = (deck_mode or "official") != "extended"

		# Add action cards from definitions (excluding tribal_council + vote cards)
		for card_type, card_data in self.card_definitions.get('cards', {}).items():
			category = card_data.get('category')
			if category == 'tribal_council':
				continue  # Skip tribal council cards - added separately
			if category == 'vote' and card_type == 'vote':
				continue  # Vote Cards are dealt at setup, never left in the deck
			if official_only and card_type in NON_OFFICIAL_CARD_TYPES:
				continue  # House cards only appear in "extended" mode
			if category == 'challenge' and not expansion:
				continue  # Orange Challenge Cards only in combined expansion mode

			# Add the specified count of each card type (compact format)
			for _ in range(card_data.get('count', 0)):
				card = {"type": card_data["type"]}
				deck.append(card)
				total_action_cards += 1

		# Shuffle action cards
		random.shuffle(deck)
		
		# Create and insert tribal council cards
		tribal_cards = self._create_tribal_council_cards(player_count)
		if tribal_cards:
			deck = self._insert_tribal_cards(deck, tribal_cards)
			
		logger.info(
			f"Created {deck_mode} deck ({'with' if expansion else 'no'} expansion) with "
			f"{len(deck)} total cards ({total_action_cards} action + {len(tribal_cards)} tribal)"
		)
		return deck

	# ═══════════════════════════════════════════════════════════════════════════════════
	# VOTE CARD ECONOMY (F2)
	# ═══════════════════════════════════════════════════════════════════════════════════

	@staticmethod
	def count_cards_of_type(player: Dict[str, Any], card_types) -> int:
		"""Count how many cards of the given type(s) are in a player's hand."""
		if isinstance(card_types, str):
			card_types = (card_types,)
		return sum(1 for c in player.get("hand", []) or [] if c.get("type") in card_types)

	def get_vote_capacity(self, player: Dict[str, Any]) -> Tuple[int, int]:
		"""
		Return (mandatory, optional) vote counts a player can cast from their hand.

		mandatory — Vote Cards and Goodwill Gamble cards, which MUST be placed in
		            the Voting Box at this Tribal Council.
		optional  — Extra Vote cards, which MAY be used now or saved for later.
		"""
		mandatory = self.count_cards_of_type(player, MANDATORY_VOTE_CARD_TYPES)
		optional = self.count_cards_of_type(player, OPTIONAL_VOTE_CARD_TYPES)
		return mandatory, optional

	def sync_vote_counters(self, game: Dict[str, Any]) -> None:
		"""
		Recompute every player's vote-card counters from their actual hand.

		Keeps the legacy ``extraVotes`` counter and the derived helper fields in
		lockstep with the physical cards so the client and engine never disagree.
		"""
		for player in game.get("players", {}).values():
			mandatory, optional = self.get_vote_capacity(player)
			player["voteCards"] = self.count_cards_of_type(player, "vote")
			player["goodwillVotes"] = self.count_cards_of_type(player, "goodwill_gamble")
			player["extraVotes"] = optional
			player["mandatoryVotes"] = mandatory
			player["maxVotes"] = mandatory + optional

	def spend_vote_cards(self, player: Dict[str, Any], total_votes: int) -> List[Dict[str, Any]]:
		"""
		Remove the cards used to cast ``total_votes`` votes from a player's hand.

		Mandatory cards (Vote / Goodwill Gamble) are spent first, then Extra Votes.
		Returns the list of spent cards (for the discard pile).
		"""
		spent = []
		hand = player.setdefault("hand", [])

		def _take(types, limit):
			taken = 0
			i = 0
			while i < len(hand) and taken < limit:
				if hand[i].get("type") in types:
					spent.append(hand.pop(i))
					taken += 1
				else:
					i += 1
			return taken

		used = _take(MANDATORY_VOTE_CARD_TYPES, total_votes)
		if used < total_votes:
			_take(OPTIONAL_VOTE_CARD_TYPES, total_votes - used)
		return spent
		
	def _create_tribal_council_cards(self, player_count: int) -> List[Dict[str, Any]]:
		"""Create tribal council cards based on player count mapping."""
		tribal_cards = []
		
		# Official rules table - per-player tribal council card counts
		tribal_config = {
		3: {"single": 4, "double": 0},
		4: {"single": 2, "double": 2},
		5: {"single": 2, "double": 3},
		6: {"single": 0, "double": 5}
		}
		
		config = tribal_config.get(player_count, {"single": 2, "double": 2})
		
		# Get tribal council card definitions
		single_def = self.get_card_definition('tribal_council_single')
		double_def = self.get_card_definition('tribal_council_double')
		
		if not single_def or not double_def:
			logger.warning("Missing tribal council card definitions")
			return []
			
		# Add single elimination cards
		for _ in range(config["single"]):
			tribal_cards.append({
			"type": "tribal_council_single",
			"category": "tribal_council",
			"name": single_def["name"],
			"description": single_def["description"],
			"elimination_type": "single"
			})
			
		# Add double elimination cards
		for _ in range(config["double"]):
			tribal_cards.append({
			"type": "tribal_council_double",
			"category": "tribal_council",
			"name": double_def["name"],
			"description": double_def["description"],
			"elimination_type": "double"
			})
			
		return tribal_cards
		
	def _insert_tribal_cards(self, deck: List[Dict], tribal_cards: List[Dict]) -> List[Dict]:
		"""Insert tribal council cards at proper intervals throughout the deck."""
		if not tribal_cards:
			return deck
			
		final_deck = deck.copy()
		
		# Place 1 tribal card at bottom as per rules
		if tribal_cards:
			final_deck.append(tribal_cards.pop())
			
		# Insert remaining tribal cards evenly throughout the deck
		if tribal_cards:
			deck_size = len(final_deck)
			interval = deck_size // (len(tribal_cards) + 1)
			
			for i, tribal_card in enumerate(tribal_cards):
				insert_pos = (i + 1) * interval
				if insert_pos >= len(final_deck):
					insert_pos = len(final_deck) - 1
				final_deck.insert(insert_pos, tribal_card)
				
		return final_deck
		
	def get_current_turn_phase(self, game: Dict[str, Any], player_id: str) -> str:
		"""
		Determine the current turn phase for card validation.
		
		Explicit phase mapping ensures consistent card playability across the system.
		"""
		if game.get("phase") == "playing":
			# Check if it's this player's turn
			turn_order = game.get("turnOrder", [])
			if not turn_order:
				return "waiting"
				
			current_player = turn_order[game.get("currentTurnIndex", 0)]
			if current_player == player_id:
				player = game["players"][player_id]
				if not player.get("hasStolen"):
					return "turn_steal"
				else:
					return "turn_play"
			else:
				return "waiting"
				
		elif game.get("phase") == "tribal_council":
			vote_phase = game.get("currentVote", {}).get("phase", "announcement")
			
			# Explicit phase mapping for tribal council phases
			# Maps tribal sub-phases to standard turn phases for card playability
			phase_mapping = {
			"announcement": "tribal_discussion",      # Phase 1: Allow tribal advantage cards
			"advantage_play": "tribal_discussion",   # Phase 2: Allow tribal advantage cards
			"discussion": "tribal_discussion",       # Phase 3: Allow tribal advantage cards
			"voting": "tribal_voting",               # Phase 4: Allow vote cards only
			"immunity": "tribal_immunity",           # Phase 5: Allow immunity cards only
			"reveal": "waiting"                      # Phase 6: Lock all card plays during reveal
			}
			
			return phase_mapping.get(vote_phase, "tribal_discussion")  # Default fallback
			
		return "waiting"
		
	def is_card_playable(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any]) -> Tuple[bool, str]:
		"""
		Check if a card can be played by a player in the current game state.
		
		Returns:
		Tuple of (is_playable: bool, reason: str)
		"""
		player = game["players"].get(player_id)
		if not player:
			return False, "Player not found"
			
		if player.get("isEliminated", False):
			return False, "Eliminated players cannot play cards"
			
		# Get current turn phase
		current_phase = self.get_current_turn_phase(game, player_id)
		
		# Check if card is playable in current phase
		playable_phases = card.get("playable_phases", [])
		if current_phase not in playable_phases:
			return False, f"Card not playable during {current_phase} phase"
			
		# Check reactive-only cards
		if card.get("reactive_only", False) and current_phase != "reactive_theft":
			return False, "This is a reactive card and can only be played in response to theft"
			
		# Additional validation based on card requirements
		if card.get("requires_target") and current_phase != "reactive_theft":
			# We can't fully validate target here without knowing the intended target
			# This will be validated when the card is actually played
			pass
			
		return True, "Card is playable"
		
	# ═══════════════════════════════════════════════════════════════════════════════════
	# CLEAN RULES ENGINE API - Centralized interface for all game rule operations
	# ═══════════════════════════════════════════════════════════════════════════════════
	
	def validate_play(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], phase: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
		"""
		Validate if a card can be played by a player in the current game state and phase.
		
		This is the primary validation entry point for all card plays.
		
		Args:
		game: Current game state
		player_id: ID of player attempting to play the card
		card: Card being validated for play
		phase: Current turn/game phase
		params: Additional parameters for the card play
		
		Returns:
		Tuple of (is_valid: bool, message: str)
		"""
		if params is None:
			params = {}
			
		# Basic player validation
		player = game["players"].get(player_id)
		if not player:
			return False, "Player not found"
			
		if player.get("isEliminated", False):
			return False, "Eliminated players cannot play cards"
			
		# Use existing card playability logic
		playable, reason = self.is_card_playable(game, player_id, card)
		if not playable:
			return False, reason
			
		# Category-specific validation
		category = card.get("category")
		if category == "tribal_advantage":
			return self._validate_tribal_advantage_play(game, player_id, card, phase, params)
		elif category == "action":
			return self._validate_action_card_play(game, player_id, card, phase, params)
		elif category == "vote":
			return self._validate_vote_card_play(game, player_id, card, phase, params)
		elif category == "challenge":
			return self._validate_challenge_card_play(game, player_id, card, phase, params)
		elif category == "tribal_council":
			return self._validate_tribal_council_card_play(game, player_id, card, phase, params)
			
		return True, "Card play is valid"
		
	def execute_effect(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], params: Dict[str, Any] = None) -> Dict[str, Any]:
		"""
		Execute the effect of a played card.
		
		This is the primary effect execution entry point for all card plays.
		
		Args:
		game: Current game state (will be modified)
		player_id: ID of player playing the card
		card: Card whose effect is being executed
		params: Additional parameters for the card effect
		
		Returns:
		Dictionary with effect results and messages
		"""
		return self.execute_card_effect(game, player_id, card, params)
		
	def can_play_card(self, game: Dict[str, Any], player_id: str, card_type: str, phase: str) -> bool:
		"""
		Check if a specific card type can be played by a player in the current phase.
		
		Args:
		game: Current game state
		player_id: ID of player
		card_type: Type of card to check
		phase: Current game/turn phase
		
		Returns:
		True if the card type can be played, False otherwise
		"""
		card_def = self.get_card_definition(card_type)
		if not card_def:
			return False
			
		# Create a minimal card object for validation
		card = {
		"type": card_type,
		"category": card_def["category"],
		"playable_phases": card_def["playable_phases"],
		"requires_target": card_def["requires_target"],
		"requires_multiple_targets": card_def["requires_multiple_targets"],
		"reactive_only": card_def["reactive_only"]
		}
		
		playable, _ = self.is_card_playable(game, player_id, card)
		return playable

	def can_play_card_in_phase(self, card: Dict[str, Any], phase: str) -> bool:
		"""
		Pure phase check: is this card playable during ``phase``?

		Unlike ``can_play_card`` this needs no game state — it answers purely from
		the card's declared ``playable_phases`` (falling back to the registry when
		the caller passes a bare ``{"type": ...}``).
		"""
		playable_phases = card.get("playable_phases")
		if playable_phases is None:
			definition = self.get_card_definition(card.get("type")) or {}
			playable_phases = definition.get("playable_phases", [])

		if phase not in playable_phases:
			return False

		reactive_only = card.get("reactive_only")
		if reactive_only is None:
			definition = self.get_card_definition(card.get("type")) or {}
			reactive_only = definition.get("reactive_only", False)

		if reactive_only and phase != "reactive_theft":
			return False

		return True

	def get_complete_card(self, card_type: str) -> Optional[Dict[str, Any]]:
		"""
		Build a fully-resolved card dict from a card type name.

		Returns None for unknown card types.
		"""
		if not self.get_card_definition(card_type):
			return None
		return self.resolve_card({"type": card_type})


	def advance_tribal_phase(self, game: Dict[str, Any], target_phase: str) -> Tuple[bool, str]:
		"""
		Advance tribal council to a specific phase with validation.
		
		Args:
		game: Current game state
		target_phase: Phase to advance to
		
		Returns:
		Tuple of (success: bool, message: str)
		"""
		if game.get("phase") != "tribal_council":
			return False, f"Cannot advance tribal phase - game is in '{game.get('phase')}' phase, not tribal council"
			
		current_vote = game.get("currentVote")
		if not current_vote:
			return False, "No active tribal council found"
			
		current_phase_str = current_vote.get("phase", "announcement")
		
		# Convert string phases to enum values for validation
		try:
			current_phase = TribalPhase(current_phase_str)
			target_phase_enum = TribalPhase(target_phase)
		except ValueError:
			return False, f"Invalid tribal phase: {target_phase}"
			
		# Check if transition is valid
		valid_transitions = TRIBAL_PHASE_TRANSITIONS.get(current_phase, [])
		if target_phase_enum not in valid_transitions and current_phase != target_phase_enum:
			valid_next = [p.value for p in valid_transitions]
			return False, f"Cannot advance from {current_phase_str} to {target_phase}. Valid next phases: {valid_next}"
			
		# Execute the phase transition
		current_vote["phase"] = target_phase
		
		# Phase-specific initialization
		if target_phase == "advantage_play":
			current_vote["advantageCardsPlayed"] = []
		elif target_phase == "discussion":
			current_vote["discussionStarted"] = True
		elif target_phase == "voting":
			current_vote["votingStarted"] = True
			# Reset voting states
			for p in game["players"].values():
				p["hasVoted"] = False
		elif target_phase == "immunity":
			current_vote["immunityPlayed"] = []
			for p in game["players"].values():
				p["immunityPlayed"] = False
				
		logger.info(f"Advanced tribal phase from {current_phase_str} to {target_phase}")
		return True, f"Advanced to {target_phase} phase"
		
	def play_tribal_advantage(self, game: Dict[str, Any], player_id: str, advantage_type: str, target_id: str = None) -> Dict[str, Any]:
		"""
		Play a tribal advantage card during appropriate tribal phases.
		
		Args:
		game: Current game state
		player_id: Player playing the advantage
		advantage_type: Type of tribal advantage
		target_id: Optional target player ID
		
		Returns:
		Dictionary with play results
		"""
		current_vote = game.get("currentVote")
		if not current_vote or current_vote.get("phase") not in ["advantage_play", "discussion"]:
			return {"success": False, "message": "Tribal advantages can only be played during advantage play or discussion phases"}
			
		player = game["players"].get(player_id)
		if not player or player.get("isEliminated", False):
			return {"success": False, "message": "Invalid or eliminated player cannot play advantages"}
			
		# Look for the advantage in player's hand
		tribal_card_idx = None
		hand = player.get("hand", [])
		for i, card in enumerate(hand):
			if card.get("type") == advantage_type or card.get("type") == "tribal_advantage":
				tribal_card_idx = i
				break
				
		if tribal_card_idx is None:
			return {"success": False, "message": f"Player does not have a {advantage_type} advantage card"}
			
		# Remove the card from hand
		advantage_card = hand.pop(tribal_card_idx)
		
		# Execute advantage effect
		advantage_effects = {
		"control_the_vote": lambda: self._effect_control_the_vote(game, player_id, advantage_card, {"targetId": target_id}),
		"goodwill_gamble": lambda: self._effect_goodwill_gamble(game, player_id, advantage_card, {"targetId": target_id}),
		"im_the_leader_now": lambda: self._effect_im_the_leader_now(game, player_id, advantage_card, {}),
		"steal_vote": lambda: self._effect_steal_vote(game, player_id, advantage_card, {"targetId": target_id}),
		"block_vote": lambda: self._effect_block_vote(game, player_id, advantage_card, {"targetId": target_id}),
		"grant_immunity": lambda: self._effect_grant_immunity(game, player_id, advantage_card, {"targetId": target_id})
		}
		
		effect_func = advantage_effects.get(advantage_type)
		if not effect_func:
			return {"success": False, "message": f"Unknown tribal advantage type: {advantage_type}"}
			
		# Execute the effect
		effect_result = effect_func()
		
		# Record the played advantage
		current_vote.setdefault("advantageCardsPlayed", []).append({
		"player": player_id,
		"type": advantage_type,
		"target": target_id
		})
		
		logger.info(f"Player {player_id} played tribal advantage {advantage_type}")
		return {"success": True, "message": effect_result.get("message", f"Played {advantage_type} advantage")}
		
	# ═══════════════════════════════════════════════════════════════════════════════════
	# CATEGORY-SPECIFIC VALIDATION METHODS
	# ═══════════════════════════════════════════════════════════════════════════════════
	
	def _validate_tribal_advantage_play(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], phase: str, params: Dict[str, Any]) -> Tuple[bool, str]:
		"""Validate tribal advantage card play."""
		if phase not in ["tribal_discussion", "tribal_advantage_play"]:
			return False, "Tribal advantage cards can only be played during tribal council discussion or advantage phase"
			
		# Card-specific validations
		card_type = card.get("type")
		if card_type in ["control_the_vote", "goodwill_gamble", "idol_nullifier"]:
			target_id = params.get("targetId")
			if not target_id or target_id not in game["players"]:
				return False, f"{card.get('name', card_type)} requires a valid target player"
				
			target = game["players"][target_id]
			if target.get("isEliminated", False):
				return False, "Cannot target eliminated players"
				
		return True, "Tribal advantage card play is valid"
		
	def _validate_action_card_play(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], phase: str, params: Dict[str, Any]) -> Tuple[bool, str]:
		"""Validate action card play."""
		card_type = card.get("type")
		
		# Reactive cards have special validation
		if card.get("reactive_only", False):
			if phase != "reactive_theft":
				return False, "This is a reactive card and can only be played in response to theft"
				
			if card_type == "sorry_for_you":
				thief_id = params.get("thiefId")
				if not thief_id or thief_id not in game["players"]:
					return False, "Sorry For You requires the thief's player ID"
					
		# Multi-target cards
		if card.get("requires_multiple_targets", False):
			if card_type == "lets_form_an_alliance":
				ally_id = params.get("allyId")
				victim_id = params.get("victimId")
				if not ally_id or not victim_id:
					return False, "Alliance requires both ally and victim player IDs"
				if ally_id not in game["players"] or victim_id not in game["players"]:
					return False, "Alliance requires valid ally and victim players"
					
		return True, "Action card play is valid"
		
	def _validate_vote_card_play(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], phase: str, params: Dict[str, Any]) -> Tuple[bool, str]:
		"""
		Validate vote card play.

		Vote Cards and Extra Vote Cards are never "played" onto the discard pile —
		they are placed in the Voting Box when you vote, which the engine models as
		spending them through ``cast_vote``. Reject direct plays with a clear reason.
		"""
		return False, "Vote cards are spent when you vote at Tribal Council, not played from your hand"

	def _validate_challenge_card_play(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], phase: str, params: Dict[str, Any]) -> Tuple[bool, str]:
		"""Validate a Let's Go To Rocks Challenge Card play (combined mode)."""
		if not game.get("expansion"):
			return False, "Challenge Cards require a game created with the Let's Go To Rocks expansion enabled"

		if game.get("challenge") and game["challenge"].get("phase") != "complete":
			return False, "A Challenge is already in progress"

		# Combined-mode rule: "If both of your Survivor Character Cards have been
		# voted out you can't take part in Challenges."
		participants = [
			pid for pid, p in game.get("players", {}).items()
			if not p.get("isEliminated", False)
		]
		if len(participants) < 2:
			return False, "A Challenge needs at least 2 players still in the game"

		return True, "Challenge card play is valid"
		
	def _validate_tribal_council_card_play(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], phase: str, params: Dict[str, Any]) -> Tuple[bool, str]:
		"""Validate tribal council card play."""
		# Tribal council cards trigger automatically when drawn
		return True, "Tribal council card play is valid"
		
	def _setup_effect_registry(self) -> None:
		"""Set up the card effect dispatch registry."""
		self.card_effects_registry = {
		# Tribal Advantage Cards
		"control_the_vote": self._effect_control_the_vote,
		"goodwill_gamble": self._effect_goodwill_gamble,
		"im_the_leader_now": self._effect_im_the_leader_now,
		"immunity_idol": self._effect_immunity_idol,
		"idol_nullifier": self._effect_idol_nullifier,
		
		# Action Cards
		"sorry_for_you": self._effect_sorry_for_you,
		"the_spy_shack": self._effect_the_spy_shack,
		"knowledge_is_power": self._effect_knowledge_is_power,
		"camp_raid": self._effect_camp_raid,
		"inheritance": self._effect_inheritance,
		"lets_form_an_alliance": self._effect_lets_form_an_alliance,
		"reward_challenge_do_or_die": self._effect_reward_challenge_do_or_die,
		"reward_challenge_power_pair": self._effect_reward_challenge_power_pair,
		"reward_challenge_its_a_numbers_game": self._effect_reward_challenge_its_a_numbers_game,

		# Generic tribal advantage effects (for backward compatibility)
		"steal_vote": self._effect_steal_vote,
		"block_vote": self._effect_block_vote,
		"grant_immunity": self._effect_grant_immunity,
		}

		# Let's Go To Rocks Challenge Cards (combined mode) all start a Challenge;
		# the server owns the challenge state machine.
		for challenge_type in CHALLENGE_CARD_TYPES:
			self.card_effects_registry[challenge_type] = self._effect_start_challenge
		
	def execute_card_effect(self, game: Dict[str, Any], player_id: str, card: Dict[str, Any], params: Dict[str, Any] = None) -> Dict[str, Any]:
		"""
		Execute the effect of a played card.
		
		Args:
		game: Current game state
		player_id: ID of player playing the card
		card: Card being played
		params: Additional parameters for card effect
		
		Returns:
		Dictionary with effect results and messages
		"""
		if params is None:
			params = {}
			
		card_type = card.get("type")
		if card_type not in self.card_effects_registry:
			return {"success": False, "message": f"Unknown card type: {card_type}"}
			
		try:
			result = self.card_effects_registry[card_type](game, player_id, card, params)
			return {"success": True, **result}
		except Exception as e:
			logger.error(f"Error executing card effect for {card_type}: {e}")
			return {"success": False, "message": f"Card effect failed: {str(e)}"}
			
	# ═══════════════════════════════════════════════════════════════════════════════════
	# TRIBAL ELIMINATION RESOLUTION (F9) — official tie & double-elimination cascade
	# ═══════════════════════════════════════════════════════════════════════════════════

	def resolve_tribal_eliminations(
		self,
		game: Dict[str, Any],
		vote_counts: Dict[str, int],
		protected_players=None,
		idol_players=None,
		elimination_type: str = "single",
	) -> Dict[str, Any]:
		"""
		Decide who is voted out from a tallied set of votes, per the official rules.

		Single Elimination
		  Most votes goes out. On a tie, the Tribal Council Leader decides.

		Double Elimination
		  · 3+ players tied for most votes → Leader decides which 2 of them go out.
		  · exactly 2 tied for most votes  → both go out (no choice).
		  · 1 clear most + 2 or more tied for second → the most-votes player goes out
		    first, then the Leader decides which of the second-place tied players
		    is also voted out.
		  · If eliminating 2 could leave fewer than 2 players in the game, only 1 is
		    voted out and the Final Tribal Council begins immediately.

		Unclear who is voted out?
		  The Leader must choose using this priority ladder:
		    1. non-immune players who got votes
		    2. non-immune players who got no votes
		    3. players who played Immunity Idols (or wear the Necklace)

		Returns a dict describing the outcome:
		  eliminated            — players voted out with no Leader input required
		  tieBreakNeeded        — True if the Leader must choose
		  tiedPlayers           — candidates the Leader chooses from (priority order)
		  eliminationsNeeded    — total vote-outs this Tribal Council
		  finalTribalAfter      — True if the double-elim was reduced to protect the
		                          "never leave 1 player" rule
		  reason                — human-readable explanation
		"""
		protected_players = set(protected_players or ())
		idol_players = set(idol_players or ())
		players = game.get("players", {})
		counts = {pid: n for pid, n in (vote_counts or {}).items() if n > 0}

		alive = [pid for pid, p in players.items() if not p.get("isEliminated", False)]
		needed = 2 if elimination_type == "double" else 1
		if len(alive) <= 2:
			needed = min(needed, max(0, len(alive) - 1))

		def players_left_after(chosen) -> int:
			left = 0
			for pid in alive:
				cards = players[pid].get("characterCards", 1)
				if pid in chosen:
					cards -= 1
				if cards >= 1:
					left += 1
			return left

		# Candidate tiers for the "unclear who is voted out" ladder. Immunity Idol
		# players and the Necklace wearer are only chosen as a last resort.
		safe = protected_players | idol_players
		non_immune = [pid for pid in alive if pid not in safe]
		with_votes = sorted(
			[pid for pid in non_immune if counts.get(pid, 0) > 0],
			key=lambda pid: -counts[pid],
		)
		without_votes = [pid for pid in non_immune if counts.get(pid, 0) == 0]
		last_resort = [pid for pid in alive if pid in safe]

		def ladder(picks_needed: int, exclude=()) -> List[str]:
			out: List[str] = []
			for tier in (with_votes, without_votes, last_resort):
				for pid in tier:
					if pid not in out and pid not in exclude:
						out.append(pid)
				if len(out) >= picks_needed:
					break
			return out

		# ── "Never leave only 1 player" guard (official 3-players-left rule) ──
		final_tribal_after = False
		if needed == 2:
			# Worst case: the two chosen players are the ones closest to elimination.
			pool = with_votes or ladder(2)
			worst = sorted(pool, key=lambda pid: players[pid].get("characterCards", 1))[:2]
			if len(worst) >= 2 and players_left_after(worst) < 2:
				needed = 1
				final_tribal_after = True

		result = {
			"eliminated": [],
			"tieBreakNeeded": False,
			"tiedPlayers": [],
			"eliminationsNeeded": needed,
			"finalTribalAfter": final_tribal_after,
			"reason": "",
		}

		if needed <= 0:
			result["reason"] = "Not enough players remain to vote anyone out"
			return result

		def unclear(picks_needed: int, already: List[str]) -> None:
			"""Fill the result using the unclear-who-is-voted-out priority ladder."""
			candidates = ladder(picks_needed, exclude=tuple(already))
			result["eliminated"] = list(already)
			if len(candidates) <= picks_needed:
				result["eliminated"].extend(candidates)
				result["reason"] = "Unclear who is voted out — only enough candidates for a forced outcome"
			else:
				result["tieBreakNeeded"] = True
				result["tiedPlayers"] = candidates
				result["reason"] = "Unclear who is voted out — Council Leader must choose"

		if not with_votes:
			unclear(needed, [])
			return result

		top_votes = counts[with_votes[0]]
		tied_first = [pid for pid in with_votes if counts[pid] == top_votes]

		if needed == 1:
			if len(tied_first) == 1:
				result["eliminated"] = list(tied_first)
				result["reason"] = f"{players[tied_first[0]].get('name', tied_first[0])} received the most votes"
			else:
				result["tieBreakNeeded"] = True
				result["tiedPlayers"] = tied_first
				result["reason"] = f"{len(tied_first)} players tied with {top_votes} votes — Council Leader breaks the tie"
			return result

		# ── Double elimination ──
		if len(tied_first) >= 3:
			result["tieBreakNeeded"] = True
			result["tiedPlayers"] = tied_first
			result["reason"] = (
				f"{len(tied_first)} players tied with {top_votes} votes — "
				"Council Leader decides which 2 are voted out"
			)
			return result

		if len(tied_first) == 2:
			result["eliminated"] = list(tied_first)
			result["reason"] = f"2 players tied with {top_votes} votes — both are voted out"
			return result

		# Exactly one player has the most votes; resolve second place.
		first = tied_first[0]
		rest = [pid for pid in with_votes if pid != first]
		if not rest:
			unclear(1, [first])
			return result

		second_votes = counts[rest[0]]
		tied_second = [pid for pid in rest if counts[pid] == second_votes]
		if len(tied_second) == 1:
			result["eliminated"] = [first, tied_second[0]]
			result["reason"] = "Most votes and second-most votes are both voted out"
		else:
			result["eliminated"] = [first]
			result["tieBreakNeeded"] = True
			result["tiedPlayers"] = tied_second
			result["reason"] = (
				f"{players[first].get('name', first)} is voted out first; "
				f"{len(tied_second)} players tied for second with {second_votes} votes — "
				"Council Leader decides who else goes"
			)
		return result

	def _reset_post_tribal_flags(self, game: Dict[str, Any]) -> None:
		"""
		Reset all transient per-round flags after tribal council completion.
		
		This centralizes the cleanup of flags that should be reset after each tribal council
		to prevent bugs from inconsistent flag management across the codebase.
		"""
		for player in game.get("players", {}).values():
			# Reset immunity and nullification flags
			player.pop("immunityIdolProtection", None)
			player.pop("idolNullified", None)
			player.pop("immunityNullified", None)
			
			# Reset vote manipulation flags
			player.pop("voteStolen", None)
			player.pop("voteBanned", None)
			player.pop("temporaryImmunity", None)

			# Extra votes are now derived from the actual Extra Vote cards in hand
			# (see sync_vote_counters), so there is no counter to zero out here.
			player.pop("mustUseExtraVotes", None)

			# Reset camp raid markers
			player.pop("campRaidedBy", None)
			
			# Reset inheritance markers that may have been processed
			player.pop("inheritanceProcessed", None)
			
		# Reset any global tribal flags
		game.pop("tribalInterrupted", None)
		game.pop("pendingTheft", None)
		
		logger.info("Post-tribal flags reset completed")
		
	# Card Effect Implementations
	
	def _effect_control_the_vote(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""
		Execute Control The Vote card effect.

		Survival Guide: "Play this card during a Tribal Council before voting begins
		to take any player's Vote Card. You MUST use that Vote Card in addition to
		your Vote Card during the Tribal Council at which this card is played. If the
		player you pick has more than 1 Vote Card, you only take 1."
		"""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "Control The Vote requires a valid target player"}

		player = game["players"][player_id]
		target = game["players"][target_id]

		# Take exactly one physical Vote Card out of the target's hand
		stolen = None
		for i, hand_card in enumerate(target.get("hand", []) or []):
			if hand_card.get("type") == "vote":
				stolen = target["hand"].pop(i)
				break

		if stolen is None:
			self.sync_vote_counters(game)
			return {"message": f"{player['name']} played Control The Vote, but {target['name']} had no Vote Card to take"}

		player.setdefault("hand", []).append(stolen)
		self.sync_vote_counters(game)

		return {"message": f"{player['name']} took {target['name']}'s Vote Card — they must use it at this Tribal Council"}

	def _effect_goodwill_gamble(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""
		Execute Goodwill Gamble card effect.

		Survival Guide: "Give this card to another player during a Tribal Council
		before voting begins. This card counts as 1 vote, and MUST be used during the
		Tribal Council at which it is played (just like a Vote Card). They can use it
		to vote for any player they want."
		"""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "Goodwill Gamble requires a valid target player"}

		player = game["players"][player_id]
		target = game["players"][target_id]

		# The physical card moves into the recipient's hand and counts as 1 vote
		target.setdefault("hand", []).append({"type": "goodwill_gamble"})
		self.sync_vote_counters(game)

		return {"message": f"{player['name']} gave a Goodwill Gamble to {target['name']} — it counts as 1 vote and must be used at this Tribal Council"}

	def _effect_im_the_leader_now(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""
		Execute I'm The Leader Now card effect.

		Survival Guide: "Play this card during a Tribal Council before voting begins
		to become the Tribal Council Leader. It's your turn when the Tribal Council
		ends (or the player after you if you are eliminated)."
		"""
		player = game["players"][player_id]

		# Update the council leader ID (isCouncilLeader will be derived from this)
		if "currentVote" in game:
			game["currentVote"]["councilLeaderId"] = player_id

		# The new leader takes the next turn once tribal council ends
		turn_order = game.get("turnOrder", [])
		if player_id in turn_order:
			game["pendingTurnPlayerId"] = player_id

		return {"message": f"{player['name']} is now the Tribal Council Leader!"}
		
	def _effect_immunity_idol(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Hidden Immunity Idol card effect."""
		target_id = params.get("targetId", player_id)  # Can protect self or others
		if target_id not in game["players"]:
			target_id = player_id  # Default to self if invalid target
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		target["immunityIdolProtection"] = True
		
		if target_id == player_id:
			return {"message": f"{player['name']} played an immunity idol for protection!"}
		else:
			return {"message": f"{player['name']} played an immunity idol to protect {target['name']}!"}
			
	def _effect_idol_nullifier(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Idol Nullifier card effect."""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "Idol Nullifier requires a valid target player"}
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		# Nullify target's immunity idol protection
		target["immunityIdolProtection"] = False
		target["idolNullified"] = True
		
		return {"message": f"{player['name']} nullified {target['name']}'s immunity idol!"}
		
	def _effect_sorry_for_you(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Sorry For You reactive card effect."""
		thief_id = params.get("thiefId")
		if not thief_id or thief_id not in game["players"]:
			return {"message": "Sorry For You requires the thief's player ID"}
			
		player = game["players"][player_id]
		thief = game["players"][thief_id]
		
		# Thief gets nothing and must discard a card
		if thief.get("hand"):
			discarded = thief["hand"].pop()
			return {"message": f"Sorry for you, {thief['name']}! Your theft failed and you discarded {discarded.get('name', 'a card')}"}
		else:
			return {"message": f"Sorry for you, {thief['name']}! Your theft failed but you have no cards to discard"}
			
	def _effect_the_spy_shack(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute The Spy Shack card effect."""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "The Spy Shack requires a valid target player"}
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		if not target.get("hand"):
			return {"message": f"{target['name']} has no cards to spy on"}
			
		# In a real implementation, this would show the hand to the player
		# For now, we'll just indicate successful spying
		return {"message": f"{player['name']} looked at {target['name']}'s hand", "spied_hand": target["hand"]}
		
	def _effect_knowledge_is_power(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Knowledge Is Power card effect."""
		target_id = params.get("targetId")
		requested_card_type = params.get("cardType")
		
		if not target_id or target_id not in game["players"]:
			return {"message": "Knowledge Is Power requires a valid target player"}
		if not requested_card_type:
			return {"message": "Knowledge Is Power requires specifying a card type"}
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		# Look for the requested card type in target's hand
		for i, hand_card in enumerate(target.get("hand", [])):
			if hand_card.get("type") == requested_card_type:
				# Take the card
				taken_card = target["hand"].pop(i)
				player["hand"].append(taken_card)
				return {"message": f"{player['name']} demanded and received {taken_card.get('name', requested_card_type)} from {target['name']}"}
				
		return {"message": f"{target['name']} does not have a {requested_card_type} card"}
		
	def _effect_camp_raid(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Camp Raid card effect."""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "Camp Raid requires a valid target player"}
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		stolen_cards = []
		for _ in range(min(2, len(target.get("hand", [])))):
			if target["hand"]:
				stolen_card = target["hand"].pop(random.randint(0, len(target["hand"]) - 1))
				player["hand"].append(stolen_card)
				stolen_cards.append(stolen_card.get("name", "a card"))
				
		if stolen_cards:
			return {"message": f"{player['name']} raided {target['name']}'s camp and stole {', '.join(stolen_cards)}"}
		else:
			return {"message": f"{target['name']} had no cards to steal"}
			
	def _effect_inheritance(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Inheritance card effect."""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "Inheritance requires a valid target player"}
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		# Mark inheritance relationship
		player["inheritanceTarget"] = target_id
		
		return {"message": f"{player['name']} will inherit {target['name']}'s cards when they are eliminated"}
		
	def _effect_lets_form_an_alliance(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Let's Form An Alliance card effect."""
		ally_id = params.get("allyId")
		victim_id = params.get("victimId")
		
		if not ally_id or ally_id not in game["players"]:
			return {"message": "Alliance requires a valid ally player"}
		if not victim_id or victim_id not in game["players"]:
			return {"message": "Alliance requires a valid victim player"}
			
		player = game["players"][player_id]
		ally = game["players"][ally_id]
		victim = game["players"][victim_id]
		
		stolen_cards = []
		
		# Each ally steals one card from victim
		if victim.get("hand"):
			# Player steals first
			stolen_card = victim["hand"].pop(random.randint(0, len(victim["hand"]) - 1))
			player["hand"].append(stolen_card)
			stolen_cards.append(f"{player['name']} stole {stolen_card.get('name', 'a card')}")
			
		if victim.get("hand"):
			# Ally steals second
			stolen_card = victim["hand"].pop(random.randint(0, len(victim["hand"]) - 1))
			ally["hand"].append(stolen_card)
			stolen_cards.append(f"{ally['name']} stole {stolen_card.get('name', 'a card')}")
			
		if stolen_cards:
			return {"message": f"Alliance formed! {' and '.join(stolen_cards)} from {victim['name']}"}
		else:
			return {"message": f"{victim['name']} had no cards for the alliance to steal"}
			
	def _effect_reward_challenge_do_or_die(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Reward Challenge: Do Or Die card effect."""
		target_id = params.get("targetId")
		player_choice = params.get("choice")  # rock, paper, scissors
		
		if not target_id or target_id not in game["players"]:
			return {"message": "Do Or Die challenge requires a valid opponent"}
		if not player_choice or player_choice not in ["rock", "paper", "scissors"]:
			return {"message": "Do Or Die challenge requires a valid choice (rock, paper, scissors)"}
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		# Simulate opponent's choice
		opponent_choice = random.choice(["rock", "paper", "scissors"])
		
		# Determine winner
		if player_choice == opponent_choice:
			return {"message": f"Rock Paper Scissors tie! {player['name']} chose {player_choice}, {target['name']} chose {opponent_choice}. No cards stolen."}
			
		win_conditions = {
		"rock": "scissors",
		"paper": "rock",
		"scissors": "paper"
		}
		
		if win_conditions[player_choice] == opponent_choice:
			# Player wins - steal 2 cards
			stolen_cards = []
			for _ in range(min(2, len(target.get("hand", [])))):
				if target["hand"]:
					stolen_card = target["hand"].pop(random.randint(0, len(target["hand"]) - 1))
					player["hand"].append(stolen_card)
					stolen_cards.append(stolen_card.get("name", "a card"))
					
			if stolen_cards:
				return {"message": f"{player['name']} won Rock Paper Scissors and stole {', '.join(stolen_cards)} from {target['name']}!"}
			else:
				return {"message": f"{player['name']} won but {target['name']} had no cards to steal"}
		else:
			# Player loses - opponent steals 2 cards
			stolen_cards = []
			for _ in range(min(2, len(player.get("hand", [])))):
				if player["hand"]:
					stolen_card = player["hand"].pop(random.randint(0, len(player["hand"]) - 1))
					target["hand"].append(stolen_card)
					stolen_cards.append(stolen_card.get("name", "a card"))
					
			if stolen_cards:
				return {"message": f"{target['name']} won Rock Paper Scissors and stole {', '.join(stolen_cards)} from {player['name']}!"}
			else:
				return {"message": f"{target['name']} won but {player['name']} had no cards to steal"}
				
	def _effect_reward_challenge_power_pair(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Reward Challenge: Power Pair card effect."""
		# This requires 3 players total including the player
		active_players = [pid for pid, p in game["players"].items() if not p.get("isEliminated")]
		if len(active_players) < 3:
			return {"message": "Power Pair requires at least 3 active players"}
			
		player = game["players"][player_id]
		
		# Simulate finger choices for all players
		choices = {}
		for pid in active_players[:3]:  # Take first 3 players
			choices[pid] = random.randint(1, 5)
			
		player_choice = choices[player_id]
		
		# Find pairs
		choice_counts = {}
		for pid, choice in choices.items():
			choice_counts[choice] = choice_counts.get(choice, []) + [pid]
			
		# Players with pairs give cards to the challenge player
		cards_received = []
		for choice, players_with_choice in choice_counts.items():
			if len(players_with_choice) == 2 and player_id not in players_with_choice:
				# Other players have a pair - they give cards
				for pair_player_id in players_with_choice:
					pair_player = game["players"][pair_player_id]
					if pair_player.get("hand"):
						stolen_card = pair_player["hand"].pop(random.randint(0, len(pair_player["hand"]) - 1))
						player["hand"].append(stolen_card)
						cards_received.append(f"{stolen_card.get('name', 'a card')} from {pair_player['name']}")
						
		if cards_received:
			return {"message": f"Power Pair success! {player['name']} received {', '.join(cards_received)}"}
		else:
			return {"message": f"Power Pair failed - no pairs formed or no cards to take"}
			
	def _effect_reward_challenge_its_a_numbers_game(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute Reward Challenge: It's A Numbers Game card effect."""
		active_players = [pid for pid, p in game["players"].items() if not p.get("isEliminated")]
		if len(active_players) < 2:
			return {"message": "Numbers Game requires at least 2 active players"}
			
		player = game["players"][player_id]
		player_number = random.randint(1, 3)
		
		# Simulate numbers for other players
		other_numbers = {}
		for pid in active_players:
			if pid != player_id:
				other_numbers[pid] = random.randint(1, 3)
				
		# Find closest number to player's number
		closest_players = []
		min_distance = float('inf')
		
		for pid, number in other_numbers.items():
			distance = abs(player_number - number)
			if distance < min_distance:
				min_distance = distance
				closest_players = [pid]
			elif distance == min_distance:
				closest_players.append(pid)
				
		# Steal cards from closest players
		cards_stolen = []
		for closest_id in closest_players:
			closest_player = game["players"][closest_id]
			if closest_player.get("hand"):
				stolen_card = closest_player["hand"].pop(random.randint(0, len(closest_player["hand"]) - 1))
				player["hand"].append(stolen_card)
				cards_stolen.append(f"{stolen_card.get('name', 'a card')} from {closest_player['name']}")
				
		if cards_stolen:
			return {"message": f"Numbers Game success! {player['name']} chose {player_number} and stole {', '.join(cards_stolen)}"}
		else:
			return {"message": f"Numbers Game failed - closest players had no cards to steal"}
			
	def _effect_start_challenge(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""
		Marker effect for Let's Go To Rocks Challenge Cards.

		The actual challenge state machine lives on the server (it needs to drive
		multi-player turn-taking); this effect just signals which challenge to start.
		"""
		player = game["players"][player_id]
		challenge_type = card.get("type")
		return {
			"message": f"{player.get('name', player_id)} played {card.get('name', challenge_type)}",
			"start_challenge": challenge_type,
		}

	def _effect_steal_vote(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute steal vote tribal advantage effect."""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "Steal vote requires a valid target player"}
			
		stealer = game["players"][player_id]
		target = game["players"][target_id]
		
		# Remove one vote from target (they can't vote)
		target["voteBanned"] = True
		# Give extra vote to stealer
		stealer["extraVotes"] = stealer.get("extraVotes", 0) + 1
		
		return {"message": f"{stealer['name']} stole a vote from {target['name']}"}
		
	def _effect_block_vote(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute block vote tribal advantage effect."""
		target_id = params.get("targetId")
		if not target_id or target_id not in game["players"]:
			return {"message": "Block vote requires a valid target player"}
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		# Block target from voting this tribal council
		target["voteBanned"] = True
		
		return {"message": f"{player['name']} blocked {target['name']} from voting"}
		
	def _effect_grant_immunity(self, game: Dict, player_id: str, card: Dict, params: Dict) -> Dict:
		"""Execute grant immunity tribal advantage effect."""
		target_id = params.get("targetId", player_id)  # Can target self if no target specified
		if target_id not in game["players"]:
			target_id = player_id
			
		player = game["players"][player_id]
		target = game["players"][target_id]
		
		# Grant temporary immunity
		target["temporaryImmunity"] = True
		
		if target_id == player_id:
			return {"message": f"{player['name']} granted themselves immunity"}
		else:
			return {"message": f"{player['name']} granted immunity to {target['name']}"}
			
	# ═══════════════════════════════════════════════════════════════════════════════════
	# GAME MECHANICS - Centralized theft, combat, and effect systems
	# ═══════════════════════════════════════════════════════════════════════════════════
	
	def execute_theft(self, game: Dict[str, Any], thief_id: str, target_id: str) -> Dict[str, Any]:
		"""
		Execute card theft between players with all card effect bonuses.
		
		Args:
		game: Current game state
		thief_id: Player performing the theft
		target_id: Player being stolen from
		
		Returns:
		Dictionary with theft results
		"""
		if thief_id not in game["players"] or target_id not in game["players"]:
			return {"success": False, "message": "Invalid player IDs for theft"}
			
		thief = game["players"][thief_id]
		target = game["players"][target_id]
		
		# Clear any pending theft state
		if "pending_theft" in game:
			del game["pending_theft"]
			
		# Determine how many cards to steal (including Steal Two card effect)
		steal_count = 1 + thief.get("stealBonus", 0)
		thief["stealBonus"] = 0  # Reset bonus after use
		
		# Steal random cards
		stolen_cards = []
		for _ in range(min(steal_count, len(target.get("hand", [])))):
			if target.get("hand"):
				stolen_card_idx = random.randint(0, len(target["hand"]) - 1)
				stolen_card = target["hand"].pop(stolen_card_idx)
				thief["hand"].append(stolen_card)
				stolen_cards.append(stolen_card.get("type", "unknown"))
				
		thief["hasStolen"] = True
		
		# Check for Camp Raid effect - steal extra card at end of turn
		if target.get("campRaidedBy") == thief_id:
			target["campRaidedBy"] = None  # Use up the camp raid
			if target.get("hand"):
				extra_stolen_idx = random.randint(0, len(target["hand"]) - 1)
				extra_stolen = target["hand"].pop(extra_stolen_idx)
				thief["hand"].append(extra_stolen)
				stolen_cards.append(f"(+{extra_stolen.get('type', 'unknown')} from Camp Raid)")
				
		logger.info(f"Player {thief_id} stole {len(stolen_cards)} cards from {target_id}")
		return {"success": True, "stolen_cards": stolen_cards}
		
	def execute_reactive_interrupt(self, game: Dict[str, Any], defender_id: str, thief_id: str, reactive_card: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Execute reactive card interrupt (like Sorry For You) during theft.
		
		Args:
		game: Current game state
		defender_id: Player playing the reactive card
		thief_id: Player attempting theft
		reactive_card: The reactive card being played
		
		Returns:
		Dictionary with interrupt results
		"""
		if defender_id not in game["players"] or thief_id not in game["players"]:
			return {"success": False, "message": "Invalid player IDs for reactive interrupt"}
			
		# Execute the card effect for reactive interrupt
		effect_result = self.execute_card_effect(game, defender_id, reactive_card, {"thiefId": thief_id})
		
		if not effect_result.get("success", False):
			return effect_result
			
		# Mark the thief's steal as completed (they don't get to try again)
		thief = game["players"][thief_id]
		thief["hasStolen"] = True
		
		# Clear any pending theft state
		if "pending_theft" in game:
			del game["pending_theft"]
			
		logger.info(f"Reactive interrupt: {defender_id} blocked theft from {thief_id}")
		return {
		"success": True,
		"reactive_interrupt": True,
		"message": effect_result.get("message", "Theft blocked by reactive card")
		}
		
	def process_card_draw_effects(self, game: Dict[str, Any], player_id: str, drawn_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
		"""
		Process any card draw effects like Camp Raid stealing drawn cards.
		
		Args:
		game: Current game state
		player_id: Player drawing cards
		drawn_cards: Cards that were drawn
		
		Returns:
		Modified drawn cards list (may have some cards stolen)
		"""
		if not drawn_cards:
			return drawn_cards
			
		player = game["players"].get(player_id)
		if not player:
			return drawn_cards
			
		# Handle Camp Raid effects - check if someone has Camp Raid placed on this player
		camp_raider_id = player.get("campRaidedBy")
		if camp_raider_id and camp_raider_id in game["players"]:
			# Last drawn card goes to the camp raider instead
			raider = game["players"][camp_raider_id]
			stolen_card = drawn_cards[-1]  # Take the last card drawn
			
			# Remove from player's hand and give to raider
			if stolen_card in player.get("hand", []):
				player["hand"].remove(stolen_card)
				raider["hand"].append(stolen_card)
				player["campRaidedBy"] = None  # Use up the camp raid
				drawn_cards[-1] = {"type": "stolen_by_camp_raid", "original": stolen_card}
				logger.info(f"Camp Raid: {camp_raider_id} stole {stolen_card.get('type')} from {player_id}")
				
		return drawn_cards
		
	def get_card_draw_count(self, player: Dict[str, Any]) -> int:
		"""
		Get the number of cards a player should draw (including Double Draw effects).
		
		Args:
		player: Player object
		
		Returns:
		Number of cards to draw
		"""
		draw_count = 1 + player.get("drawBonus", 0)
		player["drawBonus"] = 0  # Reset bonus after calculating
		return draw_count
		
	def process_elimination_inheritance(self, game: Dict[str, Any], eliminated_player_id: str) -> List[str]:
		"""
		Process inheritance effects when a player is eliminated.
		
		Args:
		game: Current game state
		eliminated_player_id: Player being eliminated
		
		Returns:
		List of messages about inheritance transfers
		"""
		inheritance_messages = []
		eliminated_player = game["players"].get(eliminated_player_id)
		if not eliminated_player:
			return inheritance_messages
			
		eliminated_hand = eliminated_player.get("hand", [])
		if not eliminated_hand:
			return inheritance_messages
			
		# Find players who have inheritance on this eliminated player
		for player_id, player in game["players"].items():
			if player.get("inheritanceTarget") == eliminated_player_id and not player.get("isEliminated"):
				# Transfer all cards from eliminated player to inheritor
				inheritor_cards = eliminated_hand.copy()
				player["hand"].extend(inheritor_cards)
				eliminated_player["hand"] = []
				player["inheritanceTarget"] = None  # Use up the inheritance
				
				card_names = [card.get("name", card.get("type", "unknown")) for card in inheritor_cards]
				message = f"{player.get('name', player_id)} inherited {len(inheritor_cards)} cards from {eliminated_player.get('name', eliminated_player_id)}: {', '.join(card_names)}"
				inheritance_messages.append(message)
				logger.info(f"Inheritance: {player_id} inherited {len(inheritor_cards)} cards from {eliminated_player_id}")
				break  # Only one inheritance per eliminated player
				
		return inheritance_messages

