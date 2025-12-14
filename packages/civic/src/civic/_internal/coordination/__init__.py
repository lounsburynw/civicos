"""
civic-coordination: LangGraph coordination workflows for civic campaigns

A standalone package for running multi-agent coordination workflows.
Part of the Civic Platform modular architecture.

Usage:
    from civic._internal.coordination import run_coordination, get_campaign_state

    # Start a coordination campaign
    result = run_coordination("city-san-rafael", "parking_policy")
    print(result['decision_score'])  # e.g., 140
    print(len(result['actors']['residents']))  # e.g., 42

    # Check campaign state later
    state = get_campaign_state("campaign-parking_policy-20241127")

    # Run suggestion workflow
    from civic._internal.coordination import run_suggestion_workflow

    suggestions = run_suggestion_workflow("san-rafael", user_id="user_123")
    print(suggestions['suggestions'])

    # Pattern learning workflow
    from civic._internal.coordination import PatternLearner, run_pattern_learning

    # Learn from an outcome
    learner = PatternLearner()
    pattern = learner.learn_from_outcome("out_12345678")

    # Get success patterns for a topic
    patterns = learner.get_success_patterns("housing")

    # Suggest strategy for an initiative
    strategy = learner.suggest_strategy("init_abc123")
    print(strategy['suggestion'])

    # Strategy suggestions workflow
    from civic._internal.coordination import run_strategy_suggestions

    result = run_strategy_suggestions("san-rafael", "housing")
    for s in result['suggestions']:
        print(f"[{s['type']}] {s['title']}")
"""

from civic._internal.coordination.state import CoordinationState, merge_actors
from civic._internal.coordination.nodes import (
    detect_decision,
    discover_residents,
    should_discover,
    DEFAULT_DB_PATH,
)
from civic._internal.coordination.graph import (
    CoordinationApp,
    create_coordination_workflow,
    run_coordination,
    get_campaign_state,
    get_default_app,
)
from civic._internal.coordination.suggestion_state import SuggestionState
from civic._internal.coordination.suggestion_nodes import (
    gather_context,
    generate_candidates,
    rank_suggestions,
    filter_suggestions,
    format_suggestions,
)
from civic._internal.coordination.suggestion_graph import (
    SuggestionApp,
    create_suggestion_workflow,
    run_suggestion_workflow,
    get_suggestion_state,
    get_default_suggestion_app,
)
from civic._internal.coordination.preparation_state import PreparationState
from civic._internal.coordination.preparation_nodes import (
    load_agenda_item,
    gather_regulatory_context,
    find_allies,
    generate_talking_points,
    compile_logistics,
    format_preparation,
)
from civic._internal.coordination.preparation_graph import (
    PreparationApp,
    create_preparation_workflow,
    run_preparation_workflow,
    get_preparation_state,
    get_default_preparation_app,
)
from civic._internal.coordination.pattern_state import PatternState, Pattern, Strategy
from civic._internal.coordination.pattern_nodes import (
    load_outcome,
    gather_preceding_actions,
    extract_context,
    create_pattern,
    store_pattern,
    load_initiative,
    query_patterns,
    analyze_patterns,
    generate_strategy,
)
from civic._internal.coordination.pattern_graph import (
    PatternLearner,
    create_learning_workflow,
    create_strategy_workflow,
    run_pattern_learning,
    get_success_patterns,
    suggest_strategy,
    get_pattern_state,
    get_default_learner,
)
from civic._internal.coordination.strategy_state import (
    StrategyState,
    StrategySuggestion,
    PatternAnalysis,
)
from civic._internal.coordination.strategy_nodes import (
    load_context as strategy_load_context,
    query_topic_patterns,
    analyze_success_factors,
    generate_strategy_suggestions,
    prioritize_suggestions,
    format_output as strategy_format_output,
)
from civic._internal.coordination.strategy_graph import (
    StrategySuggester,
    create_strategy_suggestions_workflow,
    run_strategy_suggestions,
    get_strategy_state,
    get_default_suggester,
)

__version__ = "0.1.0"
__all__ = [
    # Coordination State
    "CoordinationState",
    "merge_actors",
    # Coordination Nodes
    "detect_decision",
    "discover_residents",
    "should_discover",
    "DEFAULT_DB_PATH",
    # Coordination Graph
    "CoordinationApp",
    "create_coordination_workflow",
    "run_coordination",
    "get_campaign_state",
    "get_default_app",
    # Suggestion State
    "SuggestionState",
    # Suggestion Nodes
    "gather_context",
    "generate_candidates",
    "rank_suggestions",
    "filter_suggestions",
    "format_suggestions",
    # Suggestion Graph
    "SuggestionApp",
    "create_suggestion_workflow",
    "run_suggestion_workflow",
    "get_suggestion_state",
    "get_default_suggestion_app",
    # Preparation State
    "PreparationState",
    # Preparation Nodes
    "load_agenda_item",
    "gather_regulatory_context",
    "find_allies",
    "generate_talking_points",
    "compile_logistics",
    "format_preparation",
    # Preparation Graph
    "PreparationApp",
    "create_preparation_workflow",
    "run_preparation_workflow",
    "get_preparation_state",
    "get_default_preparation_app",
    # Pattern State
    "PatternState",
    "Pattern",
    "Strategy",
    # Pattern Nodes
    "load_outcome",
    "gather_preceding_actions",
    "extract_context",
    "create_pattern",
    "store_pattern",
    "load_initiative",
    "query_patterns",
    "analyze_patterns",
    "generate_strategy",
    # Pattern Graph
    "PatternLearner",
    "create_learning_workflow",
    "create_strategy_workflow",
    "run_pattern_learning",
    "get_success_patterns",
    "suggest_strategy",
    "get_pattern_state",
    "get_default_learner",
    # Strategy State
    "StrategyState",
    "StrategySuggestion",
    "PatternAnalysis",
    # Strategy Nodes
    "strategy_load_context",
    "query_topic_patterns",
    "analyze_success_factors",
    "generate_strategy_suggestions",
    "prioritize_suggestions",
    "strategy_format_output",
    # Strategy Graph
    "StrategySuggester",
    "create_strategy_suggestions_workflow",
    "run_strategy_suggestions",
    "get_strategy_state",
    "get_default_suggester",
]
