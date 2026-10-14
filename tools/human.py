"""
Human-in-the-loop tool.
Used when the agent detects ambiguity, encounters approval-required thresholds,
or exhausts automated retries.
Supports interactive terminal prompts or mock pre-set responses for automated evals.
"""

from typing import Optional, Callable

# Global hook for injecting responses during automated evals
_HUMAN_MOCK_CALLBACK: Optional[Callable[[str], str]] = None

def set_mock_human_response(callback: Optional[Callable[[str], str]]):
    """Allows eval scripts to simulate human input automatically."""
    global _HUMAN_MOCK_CALLBACK
    _HUMAN_MOCK_CALLBACK = callback


def ask_human(question: str) -> str:
    """
    Asks the human operator for clarification, approval, or instructions.
    
    Args:
        question: The question or approval request to present to the user.
        
    Returns:
        The human's answer or decision.
    """
    global _HUMAN_MOCK_CALLBACK
    if _HUMAN_MOCK_CALLBACK is not None:
        answer = _HUMAN_MOCK_CALLBACK(question)
        print(f"\n[HUMAN-IN-THE-LOOP - EVAL MOCK]\nAgent asks: {question}\nHuman response: {answer}\n")
        return f"Human answered: {answer}"

    print(f"\n" + "=" * 60)
    print("HUMAN INTERVENTION REQUIRED")
    print("=" * 60)
    print(f"Agent asks: {question}")
    try:
        user_input = input("Your answer (or 'approve'/'reject'): ").strip()
        if not user_input:
            user_input = "No input provided by user."
        return f"Human answered: {user_input}"
    except (EOFError, KeyboardInterrupt):
        return "Human was unavailable to respond."
