"""
Tools the model can call in agent mode, and a safe arithmetic evaluator.

Language models are unreliable at arithmetic: "what share of sales came from
Services" needs 109,158 / 416,161, and a model that guesses will sound just as
confident when it is wrong. `calculate` does the maths exactly. It parses the
expression into a syntax tree and evaluates only numbers and arithmetic, so it
cannot run code.
"""
import ast
import math
import operator
import re
from typing import Any, Dict, List

_BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {"round": round, "abs": abs, "min": min, "max": max, "sum": lambda *xs: sum(xs[0] if len(xs) == 1 and isinstance(xs[0], (list, tuple)) else xs)}
MAX_EXPRESSION = 300


class CalculationError(ValueError):
    pass


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise CalculationError("exponent too large")
        return _BINARY[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e) for e in node.elts]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords:
        return _FUNCTIONS[node.func.id](*[_eval(a) for a in node.args])
    raise CalculationError(f"unsupported syntax: {type(node).__name__}")


def calculate(expression: str) -> float:
    """Evaluate arithmetic like '(416161 - 391035) / 391035 * 100'. Thousands separators are accepted."""
    if len(expression) > MAX_EXPRESSION:
        raise CalculationError("expression too long")
    cleaned = re.sub(r"(?<=\d),(?=\d{3}\b)", "", expression).replace("$", "").replace("×", "*").replace("÷", "/")
    cleaned = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", cleaned)
    try:
        value = _eval(ast.parse(cleaned, mode="eval"))
    except (SyntaxError, ZeroDivisionError, TypeError, OverflowError) as e:
        raise CalculationError(str(e)) from e
    if isinstance(value, list) or not math.isfinite(value):
        raise CalculationError("result is not a single finite number")
    return value


def format_number(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate an arithmetic expression exactly. Use it for EVERY sum, difference, ratio, share or "
                "percentage change instead of doing arithmetic yourself. Example: (416161 - 391035) / 391035 * 100"
            ),
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Numbers, + - * / ** ( ), round(), abs(), min(), max(), sum()"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search the company documents again. Use it when the numbered context chunks do not contain "
                "something the question needs, with a focused query in the documents' own wording. "
                "New chunks come back numbered so you can cite them."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

AGENT_INSTRUCTIONS = (
    "You have tools. Call `calculate` for any arithmetic, including sums, differences, ratios, shares and percentage "
    "changes, and report the tool's result rather than your own estimate. Call `search_documents` only if the "
    "context chunks lack information the question needs. Stop calling tools once you can answer, and cite chunk "
    "numbers as usual; a calculated figure cites the chunks its inputs came from."
)
