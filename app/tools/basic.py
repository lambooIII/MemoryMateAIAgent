import ast
import math
import operator
from datetime import datetime

from langchain_core.tools import tool


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {"sqrt": math.sqrt, "abs": abs, "round": round, "pow": pow}


def evaluate_expression(expression: str) -> int | float:
    if len(expression) > 200:
        raise ValueError("表达式过长")
    tree = ast.parse(expression, mode="eval")

    def evaluate(node: ast.AST) -> int | float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            return _BINARY_OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = _FUNCTIONS.get(node.func.id)
            if function is not None and not node.keywords:
                return function(*(evaluate(argument) for argument in node.args))
        raise ValueError("表达式包含不支持的语法")

    result = evaluate(tree)
    if not math.isfinite(float(result)):
        raise ValueError("计算结果不是有限数值")
    return result


@tool
def calculator(expression: str) -> str:
    """计算安全的数学表达式，支持四则运算、幂、余数、sqrt、abs、round 和 pow。"""
    try:
        return f"{expression} = {evaluate_expression(expression)}"
    except (SyntaxError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        return f"计算失败：{exc}"


@tool
def current_time() -> str:
    """获取服务器当前的日期、时间和星期。"""
    now = datetime.now().astimezone()
    return now.strftime("%Y-%m-%d %H:%M:%S %Z，星期%w")


def get_basic_tools() -> list:
    return [calculator, current_time]

